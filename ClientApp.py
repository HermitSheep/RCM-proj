import subprocess
import re
import time
from collections import deque
import statistics
import pandas as pd

QUEUE_MAX_SIZE = 7 #meters
RSSI_BUF_MAX_SIZE = 10 #rssi samples
SERVICE_DIST = 1 #distance at which the person is being served at the balcony, in meters
LEAVING_DIST = 3 #distance at whereafter the person is probably leaving, in meters
DIST_TO_PEOPLE_RATIO = 0.6 #average distance between two people in the queue, in meters

def get_time():
    """
    Get's the current time as an int
    :params: nothing
    :returns: current time (int)
    """
    return int(time.time())

def get_station_info_direct():
    """
    Runs the iw command to retrieve the clients' MAC address and RSSI, and stores them in a dictionary.
    :params: nothing
    :returns: dictionary with the MAC address as key and the corresponding RSSI as the value
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
    """
    Gives the average the distance for the given RSSI value.
    :param data: signal strength (RSSI)
    :return: The average of the distances for the given value of RSSI
    """
    data = pd.read_excel('Fila_Medições.xlsx', index_col=0)

    dfSelected = data[['Distancia', 'RSSI']]
    rssiDist = {}
    key = signal
    rssiDist.setdefault(key, [])
    for _, row in dfSelected.iterrows():
        rssi = row['RSSI']
        distance = row['Distancia']
        if (rssi == signal):
            rssiDist[key].append(distance)
    
    medianDist = statistics.mean(rssiDist[key])
    
    return medianDist

class RSSIBuffer:
    def __init__(self):
        self.__buffer = deque(maxlen=RSSI_BUF_MAX_SIZE)
        self.__size = RSSI_BUF_MAX_SIZE
        
    def add_rssi(self, rssi):
        """
        Adds a new RSSI value to the buffer.
        If the buffer is empty, fills it with the initial RSSI value to prevent early median from being 0.
        :param data: RSSI
        :return: nothing
        """
        if len(self.__buffer) == 0:
            for _ in range(self.__size):
                self.add_rssi(rssi)
        else:
            self.__buffer.append(rssi)
    
    def calculate_median(self):
        """
        Calculates the median of the RSSI values in the buffer.
        :param data: self
        :return: The median of the RSSI values in the buffer
        :raises: ValueError if the buffer is empty
        """
        if len(self.__buffer) > 0:
            return statistics.median(self.__buffer)
        else:
            raise ValueError("Tried to read from an empty buffer")
        
# Define the Client class
class Client:
    def __init__(self, macAddress):
        self.__macAddress = macAddress
        self.__distance = 0
        self.__rssiBuffer = RSSIBuffer()
        self.__waitingTime = 0
        self.__serviceTime = 0
        self.__leavingTime = 0 #Measuring the leave time so we can better detect when someone is leaving
        self.__expectedWaitTime = 0
        self.__state = 'waiting'  # States: 'waiting', 'service', 'leaving'
        self.__pastTime = get_time()
        
    def __update_rssi(self, rssi):
        """
        Updates the client's rssi and distance
        :param data: self and the current rssi
        :return: nothing
        """
        self.__rssiBuffer.add_rssi(rssi)
        self.__distance = rssi_to_dist(self.__rssiBuffer.calculate_median())
        
    def __update_state(self, timePassed):
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
                    self.__waitingTime += timePassed
            case 'service':
                if self.__distance > LEAVING_DIST:
                    self.__state = 'leaving'
                else:
                    self.__serviceTime += timePassed
            case 'leaving':
                self.__leavingTime += timePassed
            case _:
                raise ValueError("Client: ", self.__macAddress, " has an impossible state")
    
    def update(self, rssi, currentTime):
        """
        Updates the client's rssi, distance, state and times
        :param data: self, client's rssi and the current time
        :return: nothing
        """
        timePassed = currentTime - self.__pastTime
        self.__update_rssi(rssi)
        self.__update_state(timePassed)
        
    def get_time(self):
        """
        Gets the client's state and corresponding time
        :param data: self
        :return: the current state and the corresponding time
        :raises: ValueError if the client has an invalid state
        """
        match self.__state:
            case 'waiting':
                return (self.__state, self.__waitingTime)
            case 'service':
                return (self.__state, self.__serviceTime)
            case 'leaving':
                return (self.__state, self.__leavingTime)
            case _:
                raise ValueError("Client: ", self.__macAddress, " has an impossible state")
        
    def get_times(self):
        """
        Gets the client's waiting, service, leaving and expected wait time, in that order
        :param data: self
        :return: client's waiting, service, leaving and expected wait time, in that order
        """
        return (self.__waitingTime, self.__serviceTime, self.__leavingTime, self.__expectedWaitTime)
            
    def get_mac(self):
        """
        Gets the client's MAC address
        :param data: self
        :return: client's MAC address
        """
        return self.__macAddress
    
    def get_distance(self):
        """
        Gets the client's distance to the AP
        :param data: self
        :return: client's distance to the AP
        """
        return self.__distance
    
    def set_expected_time(self, expected_time):
        """
        Set's the client's expected waiting time
        :param data: self
        :return: nothing
        """
        self.__expectedWaitTime = expected_time


# Define the TrackClients class
class APoint:
    def __init__(self):
        self.__clients = []
        self.__old_clients = []
        self.__avg_wait_time = 0
        self.__avg_service_time = 0
        self.__current_time = time.time()

    def track_clients(self, mac_address):
        """
        Find an existing client or create a new one if not found.
        :param data: self and MAC address of the client
        :return: If the MAC address exits, returns the corresponding client. Otherwise, returns a new client
        """
        for client in self.__clients:
            if client.mac_address == mac_address:
                return client
            
        new_client = Client(mac_address)
        self.__clients.append(new_client)
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
                client.__rssiBuffer.add_rssi(rssi)
                client.update_distance(distance)

                # Check client state and update wait times
                client.check_state()

                if client.__state == 'waiting':
                    client.update_waited_time(current_time - self.__current_time)

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

        clientInfo = []
        currentMac = None
        currentSignal = None
        current_distance = None

        for line in output.split('\n'):

            if 'Station' in line:
                currentMac = line.split()[1]

            elif 'signal' in line:
                current_signal = int(line.split()[1])  # signal strength (RSSI)

            elif 'distance' in line:  # This assumes there's a way to get the distance, which might be computed differently
                current_distance = float(line.split()[1])  # Replace this with how you get distance
                
            if currentMac and current_signal is not None:
                clientInfo.append((currentMac, current_signal, current_distance))
                currentMac, current_signal, current_distance = None, None, None

        return clientInfo

    def average_time(self):
        """Calculate average wait and service times for all clients."""
        waiting_times = [client.waited_time for client in self.__clients if client.state == 'waiting']
        service_times = [client.waited_time for client in self.__clients if client.state == 'service']
        
        avg_wait_time = sum(waiting_times) / len(waiting_times) if waiting_times else 0
        avg_service_time = sum(service_times) / len(service_times) if service_times else 0

        return avg_wait_time, avg_service_time
    
    
    def update_clients_expected_time(self):
        """
        Updates all clients' expected waiting times
        :param data: self
        :return: nothing
        """
        for client in self.__clients:
            dist = client.get_distance()
            expected_time = round(dist / DIST_TO_PEOPLE_RATIO) * self.__avg_service_time
            client.set_expected_time(expected_time)
        
    def find_client_by_mac(self, mac_address):
        """
        Finds the client in the list of clients that has a given MAC address
        :param data: self
        :return: the client, or nothing if the client doesn't exist
        """
        for client in self.__clients:
            if client.get_mac() == mac_address:
                return client
        return None
    
    def get_times(self):
        """
        Returns the average waiting and service times, in that order
        :param data: self
        :return: average waiting and service times, in that order
        """
        return (self.__avg_wait_time, self.__avg_service_time)
    
    def get_client_times(self, mac):
        """
        Returns the waiting, service, leaving and expected waiting times of the client that has a given MAC address
        :param data: self, mac address
        :return: the client's waiting, service, leaving and expected waiting times, in that order
        """
        client = self.find_client_by_mac(mac)
        if client == None:
            return None
        else:
            return client.get_times()
        
#classe AP tem:
# 2 listas de clientes - atual e pessoas que ja foram atendidas
# inteiro para o tempo medio de espera
# inteiro para o tempo medio de serviço
# inteiro para o tempo atual (tudo de tempo em segundos)

# - funçao que atualiza a lista de clientes - chama o get_station_info_direct() e compara as chaves com os MACs da sua propria lista
# se houver clientes novos adiciona e se houver clientes que ja nao existe na tabela e apaga esses os clientes da lista
# - outra funçao para atualizar todos os clientes que estao na lista - chama update()
# - outra funcao que atualiza os tempos medios (clientes tem uma funçao que da os seus tempos)
# X outra funcao que atualiza os tempos de espera esperados dos clientes, multiplicando o tempo de serviço médio pelo numero de pessoas que estão à sua frente
# - outra funcao que se atualiza a si propria: corre as ultimas funcoes
# X outra funcao que devolve tempos medios esperados
# X outra funcao que devolve todos os tempos do cliente com o mac especifico



class AccessPoint:
    def __init__(self, client):
        self.client_list = Client()
        self.client_left = Client()
        self.waitingTime = 0
        self.serviceTime = 0
        self.currentTime = 0 #this is the time that it takes for the last person to be served

    def update_client_list(self): #funçao que atualiza a lista de clientes

        stations = get_station_info_direct() #dictionary
        tmp = Client()

        for client in self.client_list: #se houver clientes que ja nao existe na tabela e apaga esses os clientes da lista
            if client.macAddress not in stations:
                self.client_left.append(client)
                self.client_list.remove(client)
            tmp.append(client.macAddress)

        
        for key in stations.keys(): #se houver clientes novos adiciona
            if key not in tmp:
                client = Client(key)
                client.update_rssi(stations[key])
                self.client_list.append(client)


    def update_client(self): #funçao para atualizar todos os clientes que estao na lista 
        
        stations = get_station_info_direct() #dictionary
        avg_time = 0

        for client in self.client_list:
            if client.macAddress in stations:
                rssi = stations[client.macAddres]
                self.serviceTime = client.service_time
                self.currentTime = len(self.client_list) * self.serviceTime
                client.update(rssi, self.currentTime)
                avg_time += client.waitingTime
        
        self.waitingTime = avg_time + self.serviceTime
                

    def update(self): #funcao que o atualiza a si propria e volta a calcular os tempos
        self.update_client()
        self.update_client_list()
            

    def get_times(self):
        return self.waitingTime, self.serviceTime, self.currentTime



def main():
    i = 1
    return i    

if __name__ == '__main__':
    while (True):
        main()