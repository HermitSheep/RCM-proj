import subprocess
import re
import time
from collections import deque
import statistics
import pandas as pd

QUEUE_MAX_SIZE = 7 #meters
RSSI_MAX_SIZE = 10 #rssi samples
SERVICE_DIST = 1 #distance at which the person is being served at the balcony
LEAVING_DIST = 3 #distance at whereafter the person is probably leaving

def get_time():
    return int(time.time())

def get_station_info_direct():
    """
    Runs the iw command and stores the output. It retrieves the client's information (MAC address, RSSI and distance).
    :params: nothing
    :returns: nothing
    """
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
        signalStrength = int(match[1])
        stations[mac_address] = signalStrength

    return stations

def rssi_to_dist(signal):
#    """
#    Gives the median of the distances for the given RSSI value.
#    :param data: signal strength (RSSI)
#    :return: The median of the distances for the given value of RSSI
#    """
#    data = pd.read_excel('wifi_data.csv', index_col=0)
#
#    df_selected = data[['Distancia', 'RSSI']]
#    rssi_dist = {}
#    key = signal
#    rssi_dist.setdefault(key, [])
#    for _, row in df_selected.iterrows():
#        rssi = row['RSSI']
#        distance = row['Distancia']
#        if (rssi == signal):
#            rssi_dist[key].append(distance)
#    
#    median_dist = statistics.mean(rssi_dist[key])
#    
#    return median_dist
    return 6

class RSSIBuffer:
    def __init__(self):
        self.buffer = deque(maxlen=RSSI_MAX_SIZE)
        self.size = RSSI_MAX_SIZE
        
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
    
    def get_true_rssi(self):
        """
        Calculates the median of the RSSI values in the buffer.
        :param data: self
        :return: The median of the buffer (median of the RSSI) or None if the buffer is empty
        """
        if len(self.buffer) > 0:
            return statistics.median(self.buffer)
        else:
            raise ValueError("Tried to read from an empty buffer")
        
# Define the Client class
class Client:
    def __init__(self, macAddress):
        self.__mac_address = macAddress
        self.__distance = 0
        self.__rssi_buffer = RSSIBuffer()
        self.__waiting_time = 0
        self.__service_time = 0
        self.__leaving_time = 0 #Measuring the leave time so we can better detect when someone is leaving
        self.__expected_wait_time = 0
        self.__state = 'waiting'  # States: 'waiting', 'service', 'leaving', 'left'
        self.__past_time = get_time()
        
    def __update_rssi(self, rssi):
        """
        Updates the client's rssi and distance
        :param data: self and the client's current rssi
        :return: nothing
        """
        self.__rssi_buffer.add_rssi(rssi)
        self.__distance = rssi_to_dist(self.__rssi_buffer.get_true_rssi())
        
    def __update_state(self, time_passed):
        """
        Updates the client's state and times
        :param data: self and the current time
        :return: nothing
        :raises: ValueError if the client has an invalid state
        """
        match self.__state:
            case 'waiting':
                if self.__distance < SERVICE_DIST:
                    self.__state = 'service'
                else:
                    self.__waiting_time += time_passed
            case 'service':
                if self.__distance > LEAVING_DIST:
                    self.__state = 'leaving'
                else:
                    self.__service_time += time_passed
            case 'leaving':
                self.__leaving_time += time_passed
            case _:
                raise ValueError("Client: ", self.__mac_address, " has an impossible state")
    
    def update(self, rssi, current_time):
        """
        Updates the client's rssi, distance, state and times
        :param data: self, and the client's current rssi and time
        :return: nothing
        """
        time_passed = current_time - self.__past_time
        self.__update_rssi(rssi)
        self.__update_state(time_passed)
        
    def get_times(self):
        """
        Gets the client's times
        :param data: self
        :return: the time the client has spent
        """
        match self.__state:
            case 'waiting':
                return (self.__state, self.__waiting_time)
            case 'service':
                return (self.__state, self.__service_time)
            case 'leaving':
                return (self.__state, self.__leaving_time)
            case _:
                raise ValueError("Client: ", self.__mac_address, " has an impossible state")
            
    def get_mac(self):
        return self.__mac_address
    
    def get_distance(self):
        return self.__distance
    
    def set_expected_time(self, time):
        self.__expected_wait_time = time


# Define the TrackClients class
#class AccessPoint:
#    def __init__(self):
#        self.clients = []
#        self.wait_times = []
#        self.service_times = []
#        self.start_time = time.time()
#
#    def track_clients(self, mac_address):
#        """
#        Find an existing client or create a new one if not found.
#        :param data: self and MAC address of the client
#        :return: If the MAC address exits, returns the corresponding client. Otherwise, returns a new client
#        """
#        for client in self.clients:
#            if client.get_mac() == mac_address:
#                return client
#            
#        new_client = Client(mac_address)
#        self.clients.append(new_client)
#        return new_client
#
#    def start(self):
#        """
#        Start tracking clients' MAC addresses and RSSI using iw every second.
#        :param data: self
#        :return: nothing
#        """
#        while True:
#            client_data = self.get_client_info() #array of clients
#            current_time = time.time()
#
#            for mac_address, rssi, distance in client_data:
#                client = self.track_clients(mac_address)
#
#                # Update RSSI buffer and distances
#                client.__rssi_buffer.add_rssi(rssi)
#                client.update_distance(distance)
#
#                # Check client state and update wait times
#                client.check_state()
#
#                if client.__state == 'waiting':
#                    client.update_waited_time(current_time - self.start_time)
#
#            time.sleep(1)
#
#    def get_client_info(self):
#        """
#        After retrieving all the clients, it organizes each client into an array.
#        :param data: self
#        :return: the client's information
#        """
#        #result = subprocess.run(['iw', 'dev', 'wlan0', 'station', 'dump'], stdout=subprocess.PIPE)
#        #wlan0 AP's interface
#        #output = result.stdout.decode('utf-8')
#        result = get_station_info_direct()
#
#        client_info = []
#        current_mac = None
#        current_stignal = None
#        current_distance = None
#
#        for line in output.split('\n'):
#
#            if 'Station' in line:
#                current_mac = line.split()[1]
#
#            elif 'signal' in line:
#                current_signal = int(line.split()[1])  # signal strength (RSSI)
#
#            elif 'distance' in line:  # This assumes there's a way to get the distance, which might be computed differently
#                current_distance = float(line.split()[1])  # Replace this with how you get distance
#                
#            if current_mac and current_signal is not None:
#                client_info.append((current_mac, current_signal, current_distance))
#                current_mac, current_signal, current_distance = None, None, None
#
#        return client_info
#
#    def average_time(self):
#        """Calculate average wait and service times for all clients."""
#        waiting_times = [client.waited_time for client in self.clients if client.state == 'waiting']
#        service_times = [client.waited_time for client in self.clients if client.state == 'service']
#        
#        avg_wait_time = sum(waiting_times) / len(waiting_times) if waiting_times else 0
#        avg_service_time = sum(service_times) / len(service_times) if service_times else 0
#
#        return avg_wait_time, avg_service_time
#        
#classe AP tem:
# 2 listas de clientes - atual e pessoas que ja foram atendidas
# inteiro para o tempo medio de espera
# inteiro para o tempo medio de serviço
# inteiro para o tempo atual (tudo de tempo em segundos)
# funçao que atualiza a lista de clientes - chama o get_station_info_direct() e compara as chaves com os MACs da sua propria lista
# se houver clientes novos adiciona e se houver clientes que ja nao existe na tabela e apaga esses os clientes da lista
# outra funçao para atualizar todos os clientes que estao na lista - chama update()
# outra funcao que o atualiza a si propria e volta a calcular os tempos
# ultima funcao que devolve esses tempos
# clientes tem uma funçao que da os seus tempos

def main():
    mac = 'c6:f3:7f:ec:15:2b'
    client = Client(mac)
    time.sleep(3)
    cur_time = get_time()
    rssi = -40
    client.update(rssi, cur_time)
    time.sleep(3)
    cur_time = get_time()
    rssi = -30
    client.update(rssi, cur_time)
    client.update(rssi, cur_time)
    client.update(rssi, cur_time)
    client.update(rssi, cur_time)
    client.update(rssi, cur_time)
    client.update(rssi, cur_time)
    client.update(rssi, cur_time)
    client.update(rssi, cur_time)
    state, waiting = client.get_times()
    print("state: ", state, ": ", waiting)
    print("distance: ", client.get_distance())
    
if __name__ == '__main__':
    main()
