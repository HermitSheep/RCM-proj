import subprocess
import re
import time
from collections import deque
import statistics
import pandas as pd

queue_max_size = 7 #meters
rssi_max_size = 10 #rssi samples


def get_station_info_direct():
    '''
    Runs the iw command and stores the output. It retrieves the client's information (MAC address, RSSI and distance).
    :params: nothing
    :returns: nothing
    '''
    # Command to run via SSH and capture the output directly
    command = (
        "ssh -i /home/mateus/.ssh/mikrotik_rsa "
        "-o HostKeyAlgorithms=+ssh-rsa "
        "root@192.168.1.1 'iw dev wlan0 station dump'"
    )
    
    # Run the command and capture the output
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Check for errors
    if result.returncode != 0:
        print(f"Error: {result.stderr.decode('utf-8')}")
        return None
    
    # Get the output as text
    output = result.stdout.decode('utf-8')
    
    # Dictionary to hold MAC address and signal strength
    stations = {}

    # Use regular expressions to extract MAC addresses and signal strength
    matches = re.findall(r"Station ([0-9a-f:]+).*?signal:\s+(-?\d+)", output, re.DOTALL)
    
    for match in matches:
        mac_address = match[0]
        signal_strength = int(match[1])
        stations[mac_address] = signal_strength

    return stations

def rssi_dist(signal):
    """
    Gives the median of the distances for the given RSSI value.
    :param data: signal strength (RSSI)
    :return: The median of the distances for the given value of RSSI
    """
    data = pd.read_excel('Fila_Medições.xlsx', index_col=0)

    df_selected = data[['Distancia', 'RSSI']]
    rssi_dist = {}
    key = signal
    rssi_dist.setdefault(key, [])
    for _, row in df_selected.iterrows():
        rssi = row['RSSI']
        distance = row['Distancia']
        if (rssi == signal):
            rssi_dist[key].append(distance)
    
    median_dist = statistics.mean(rssi_dist[key])
    
    return median_dist

class RSSIBuffer:
    def __init__(self):
        self.buffer = deque(maxlen=rssi_max_size)
        self.size = rssi_max_size
        
    def add_rssi(self, rssi_value):
        """
        Adds a new RSSI value to the buffer.
        Fills the buffer with the initial RSSI value to prevent early median from being 0.
        :param data: Self and the RSSI
        :return: nothing
        """
        if len(self.buffer) == 0:
            for _ in range(len(self.buffer)):
                self.add_rssi(rssi_value)
        self.buffer.append(rssi_value)
    
    def calculate_median(self):
        """
        Calculates the median of the RSSI values in the buffer.
        :param data: self
        :return: The median of the buffer (median of the RSSI) or None if the buffer is empty
        """
        if len(self.buffer) > 0:
            return statistics.median(self.buffer)
        else:
            print('Tried to calculate median of empty buffer')
            return None
        
# Define the Client class
class Client:
    def __init__(self, mac_address):
        self.mac_address = mac_address
        self.distance = 0
        self.past_distance = 0
        self.rssi_buffer = RSSIBuffer()
        self.waiting_time = 0
        self.service_time = 0
        self.leaving_time = 0 #Measuring the leave time so we can better detect when someone is leaving
        self.expected_wait_time = 0
        self.state = 'waiting'  # States: 'waiting', 'service', 'leaving', 'left'
        
    def update_client(self, rssi, time):
        """Update the client's values."""
        #update distance and past distance
        self.rssi_buffer.add_rssi(rssi)
        self.distance = rssi_dist(self.rssi_buffer.calculate_median())
        #TODO I'm not sure this even works...
        if self.waiting_time%5 == 4 and self.distance > queue_max_size:
            self.past_distance = self.distance
        #update the state or times
        match self.state:
            case 'waiting':
                if self.distance < 1:
                    self.state = 'service'
                else:
                    self.waiting_time += time
            case 'service':
                if self.distance < 1:
                    self.state = 'leaving'
                else:
                    self.service_time += time
            case 'leaving':
                if rssi == -100:
                    self.state = 'left'
                else:
                    self.leaving_time += time

    def update_expected_wait_time(self, expected_time):
        self.expected_wait_time = expected_time

    def get_waiting_time(self):
        return self.waiting_time

    def get_service_time(self):
        return self.service_time

    def get_leaving_time(self):
        return self.leaving_time

    def get_distance(self):
        return self.distance


# Define the TrackClients class
class TrackClients:
    def __init__(self):
        self.clients = []
        self.wait_times = []
        self.service_times = []
        self.start_time = time.time()

    def track_clients(self, mac_address):
        """
        Find an existing client or create a new one if not found.
        :param data: self and MAC address of the client
        :return: If the MAC address exits, returns the corresponding client. Otherwise, returns a new client
        """
        for client in self.clients:
            if client.mac_address == mac_address:
                return client
            
        new_client = Client(mac_address)
        self.clients.append(new_client)
        return new_client

    def start(self):
        """
        Start tracking clients' MAC addresses and RSSI using iw every second.
        :param data: self
        :return: nothing
        """
        while True:
            client_data = self.get_client_info() #array of clients
            current_time = time.time()

            for mac_address, rssi, distance in client_data:
                client = self.track_clients(mac_address)

                # Update RSSI buffer and distances
                client.rssi_buffer.add_rssi(rssi)
                client.update_distance(distance)

                # Check client state and update wait times
                client.check_state()

                if client.state == 'waiting':
                    client.update_waited_time(current_time - self.start_time)

            time.sleep(1)

    def get_client_info(self):
        """
        After retrieving all the clients, it organizes each client into an array.
        :param data: self
        :return: the client's information
        """
        #result = subprocess.run(['iw', 'dev', 'wlan0', 'station', 'dump'], stdout=subprocess.PIPE)
        #wlan0 AP's interface
        #output = result.stdout.decode('utf-8')
        result = get_station_info_direct()

        client_info = []
        current_mac = None
        current_signal = None
        current_distance = None

        for line in output.split('\n'):

            if 'Station' in line:
                current_mac = line.split()[1]

            elif 'signal' in line:
                current_signal = int(line.split()[1])  # signal strength (RSSI)

            elif 'distance' in line:  # This assumes there's a way to get the distance, which might be computed differently
                current_distance = float(line.split()[1])  # Replace this with how you get distance
                
            if current_mac and current_signal is not None:
                client_info.append((current_mac, current_signal, current_distance))
                current_mac, current_signal, current_distance = None, None, None

        return client_info

    def average_time(self):
        """Calculate average wait and service times for all clients."""
        waiting_times = [client.waited_time for client in self.clients if client.state == 'waiting']
        service_times = [client.waited_time for client in self.clients if client.state == 'service']
        
        avg_wait_time = sum(waiting_times) / len(waiting_times) if waiting_times else 0
        avg_service_time = sum(service_times) / len(service_times) if service_times else 0

        return avg_wait_time, avg_service_time
        

