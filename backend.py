import subprocess
import re
import time
from collections import deque
import statistics
import pandas as pd
import math
from flask import Flask, jsonify




QUEUE_MAX_SIZE = 7 #meters
CLIENT_RSSI_BUFFER_SIZE = 10 #rssi samples
SERVICE_DIST = 1 #distance at which the person is being served at the balcony, in meters
LEAVING_DIST = 2 #distance at whereafter the person is probably leaving, in meters
DIST_TO_PEOPLE_RATIO = 0.6 #average distance between two people in the queue, in meters
AVG_NUMBER = 3 #number of past clients to take into acount when calculating average times
RSSI_TO_DIST_DATABASE = 'Fila_Medições.xlsx' #excel sheet with RSSI to distance relation
DIST_COLUMN_NAME = 'Distancia' #name of the column with distance values
RSSI_COLUMN_NAME = 'RSSI' #name of the column with the RSSI values

Service_Flag = False #flag that marks if there's a client being serviced 


def get_time():
    """
    Get's the current time as an int
    :params: nothing
    :returns: current time (int)
    """
    return float(time.time())



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
    
    try:
        # Run the command and capture the output
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

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
    
    except subprocess.CalledProcessError as e:
        err_msg = "Machine probably doesn't have access to the AP."
        args = e.args
        if not args:
            arg0 = err_msg
        else:
            arg0 = f"{args[0]}\n{err_msg}"
        e.args = (arg0,) + args[1:]
        raise



def rssi_to_dist(signal):
    """
    Gives the average the distance for the given RSSI value.
    :param data: signal strength (RSSI)
    :return: The average of the distances for the given value of RSSI
    """
    data = pd.read_excel(RSSI_TO_DIST_DATABASE)
    dfSelected = data[[DIST_COLUMN_NAME, RSSI_COLUMN_NAME]]
    rssiDist = {}
    key = signal
    print("key: ", key)
    print("signal: ", signal)
    rssiDist.setdefault(key, [])
    
    # Group the data by RSSI and calculate the median distance for each RSSI
    rssiDist = dfSelected.groupby(RSSI_COLUMN_NAME)[DIST_COLUMN_NAME].apply(list).to_dict()
    print("rssiDist: ", rssiDist)
    # Sort the RSSI keys to find the closest lower value if the exact signal is not present
    sorted_rssi = sorted(rssiDist.keys(), reverse=True)
    # Look for exact RSSI or closest lower value
    for rssi in sorted_rssi:
        print("rssi: ", rssi)
        if signal >= rssi:
            print("rssi no if: ", rssi)
            return statistics.median(rssiDist[rssi])
        if signal not in sorted_rssi:
            fake_signal = min(sorted_rssi)
            print("fake signal: ", fake_signal)
            return statistics.median(rssiDist[fake_signal])
    
    
    return None



class RSSIBuffer:
    """
    A queue with defined max size, and a method for getting it's median
    """
    def __init__(self, max_len):
        self.__buffer = deque(maxlen=max_len)
        self.__size = max_len


    def add_rssi(self, rssi):
        """
        Adds a new RSSI value to the buffer.
        If the buffer is empty, fills it with the initial RSSI value to prevent early median from being 0.
        :param data: RSSI
        :return: nothing
        """
        if len(self.__buffer) == 0:
            for _ in range(self.__size):
                self.__buffer = [rssi] * self.__size
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
            return math.floor(statistics.median(self.__buffer))
        else:
            raise ValueError("Tried to read from an empty buffer")



class Client:
    """
    Processes all information relative a generic client
    """
    def __init__(self, MAC):
        self.__MAC = MAC
        self.__distance = 0
        self.__RSSI_buffer = RSSIBuffer(CLIENT_RSSI_BUFFER_SIZE)
        self.__waiting_time = 0 #time the client has spent in the queue
        self.__service_time = 0 #time the client has spent being serviced
        self.__leaving_time = 0 #time the client has spent leaving
        self.__expected_wait_time = 0 #time the client can expect to wait in line
        self.__state = 'waiting'  # States: 'waiting', 'service', 'leaving'


    def __update_rssi(self, rssi):
        """
        Updates the client's rssi and distance
        :param data: self and the current rssi
        :return: nothing
        """
        self.__RSSI_buffer.add_rssi(rssi)
        self.__distance = rssi_to_dist(self.__RSSI_buffer.calculate_median())


    def __update_state(self, time_passed):
        """
        Updates the client's state and times
        :param data: self and the current time
        :return: nothing
        :raises: ValueError if the client has an invalid state
        """
        print("state: ", self.__state)
        print("time: ", time_passed)
        global Service_Flag
        
        match self.__state:
            case 'waiting':
                if self.__distance < SERVICE_DIST and  not Service_Flag:
                    self.__state = 'service'
                    Service_Flag = True
                else:
                    self.__waiting_time += time_passed #client has been waiting for the last "timePassed" seconds
            case 'service':
                if self.__distance > LEAVING_DIST: #fazemos distancia? nao tempo + rssi ? -> por tempo não sabemos se houve algum problema, ou zigzageamento, por RSSI é igual a por distância
                    self.__state = 'leaving'
                    Service_Flag = False
                else:
                    self.__service_time += time_passed #client has been being serviced for the last "timePassed" seconds

            case 'leaving':
                self.__leaving_time += time_passed #client has been leaving for the last "timePassed" seconds
                #se estamos sempre a dar update e o cliente quando sai nao muda o state, isto nao vai so continuar a acresentar
                # tempo para sempre?

            case _:
                raise ValueError("Client: ", self.__MAC, " has an impossible state")


    def update_client(self, rssi, time_passed):
        """
        Updates the client's rssi, distance, state and times
        :param data: self, client's rssi and the current time
        :return: nothing
        """
        self.__update_rssi(rssi)
        self.__update_state(time_passed)


    def set_expected_time(self, expected_time): #isto nao devia ser usado no update_state() ?
        """
        Set's the client's expected waiting time
        :param data: self
        :return: nothing
        """
        self.__expected_wait_time = expected_time


    def get_client_service_time(self):
        """
        Gets the client's service time
        :param data: self
        :return: client's service time
        """
        return self.__service_time


    def get_client_waiting_time(self):
        """
        Gets the client's waiting time
        :param data: self
        :return: client's waiting time
        """
        return self.__waiting_time
    
    def get_client_state(self):
        """
        Gets the client's state
        :param data: self
        :return: client's state
        """
        return self.__state


    def get_expected_waiting_time(self): #site needs this
        """
        Gets the client's expected waiting time
        :param data: self
        :return: client's expected waiting time
        """
        return self.__expected_wait_time


    def get_expected_leaving_time(self):
        """
        Gets the client's expected leaving time
        :param data: self
        :return: client's expected leaving time
        """
        return self.__leaving_time


    def get_mac(self):
        """
        Gets the client's MAC address
        :param data: self
        :return: client's MAC address
        """
        return self.__MAC


    def get_distance(self):
        """
        Gets the client's distance to the AP
        :param data: self
        :return: client's distance to the AP
        """
        return self.__distance


#classe AP tem:
# 2 listas de clientes - atual e pessoas que ja foram atendidas
# inteiro para o tempo medio de espera
# inteiro para o tempo medio de serviço
# inteiro para o tempo atual (tudo de tempo em segundos)

# X funçao que atualiza a lista de clientes - chama o get_station_info_direct() e compara as chaves com os MACs da sua propria lista
# se houver clientes novos adiciona e se houver clientes que ja nao existe na tabela e apaga esses os clientes da lista
# X outra funçao para atualizar todos os clientes que estao na lista - chama update()
# X outra funcao que atualiza os tempos medios (clientes tem uma funçao que da os seus tempos)
# X outra funcao que atualiza os tempos de espera esperados dos clientes, multiplicando o tempo de serviço médio pelo numero de pessoas que estão à sua frente
# X outra funcao que se atualiza a si propria: corre as ultimas funcoes
# X outra funcao que devolve tempos medios esperados
# X outra funcao que devolve todos os tempos do cliente com o mac especifico



class AccessPoint:
    """
    Processes all information that's accessible to the access point
    """
    def __init__(self):
        self.__clients_list = [] # Current clients
        self.__past_clients_list = [] # Past clients
        self.__avg_waiting_time = 0 # Average waiting time (global)
        self.__avg_service_time = 0 # Average service time (global)
        self.__stations = {} # Dictionary with the measured MAC and corresponding RSSIs of each connected client
        self.__times = deque(maxlen=2) # Queue with the times of the past and current measurements (to measure time passed between measurements)
        self.__times.append(0) # Initializing it at 0 (the first time it runs, zero will be the past measurement)


    def measure_queue(self):
        """
        Measures how many clients are in the queue, calculates their RSSIs, and updates the queue times
        :param data: self
        :return: nothing
        """
        self.__stations = get_station_info_direct()
        self.__times.append(get_time())


    def update_client_list(self):
        """
        Measures how many clients are in the queue, adds new ones, removes old ones, and updates them all
        :param data: self
        :return: nothing
        """
        new_clients = [] #list of the MACs of the new clients
        regulars = [] #list of clients that aren't new nor old

        self.measure_queue() #fazemos isto primeiro para ter a certeza que nao se chamou o update antes do measure e nao temos a stations
        # e o times vazio

        time_passed = self.__times[1] - self.__times[0] # time passed between measurements
        print("time 1: ", self.__times[1])
        print("time 0: ", self.__times[0])

        for client in self.__clients_list: #check for old clients (clients that have already left the queue completely) and remove them
            state = client.get_client_state()
            print(state)
            if client.get_mac() not in self.__stations or state == 'leaving':
                self.__past_clients_list.append(client)
                self.__clients_list.remove(client)
            else:
                regulars.append(client.get_mac()) #list of existing mac addresses

        for mac, rssi in self.__stations.items(): #checks for new clients, then adds and updates them, while updating the rest of the clients

            if mac not in regulars:
                client = Client(mac)
                client.update_client(rssi, 0) #new clients start with time set to 0 (because they're new)
                self.__clients_list.append(client)
                new_clients.append(mac)
        
        for client in self.__clients_list: #updates all other clients
            mac = client.get_mac()
            rssi = self.__stations[mac]
            if mac in self.__stations and mac not in new_clients:
                client.update_client(rssi, time_passed) #other clients get their time updated


    def update_service_time(self):
        """
        This function updates the AP's service time based on the mean of the last AVG_NUMBER available clients that left
        :params: self
        :returns: nothing
        """
        avg_service = []
        if len(self.__past_clients_list) > 0:
            for old_client in self.__past_clients_list[-1:-AVG_NUMBER -1:-1]: # [-1, -2, -3] -> last three elements of a list, for example
                avg_service.append(old_client.get_client_service_time())
        else:
            for cur_client in self.__clients_list[-1:-AVG_NUMBER -1:-1]: # [-1, -2, -3] -> last three elements of a list, for example
                avg_service.append(cur_client.get_client_service_time())
        self.__avg_service_time = statistics.mean(avg_service)


    def update_waiting_time(self):
        """
        This function updates the AP's average waiting time based on the mean of the last AVG_NUMBER available clients that left
        :params: self
        :returns: nothing
        """
        avg_waiting = []
        if len(self.__past_clients_list) > 0:
            avg_waiting = []
            for old_client in self.__past_clients_list[-1:-AVG_NUMBER -1:-1]: # [-1, -2, -3] -> last three elements of a list, for example
                avg_waiting.append(old_client.get_client_waiting_time())
            self.__avg_waiting_time = statistics.mean(avg_waiting)
        else:
            for cur_client in self.__clients_list[-1:-AVG_NUMBER -1:-1]: # [-1, -2, -3] -> last three elements of a list, for example
                avg_waiting.append(cur_client.get_client_waiting_time())
        self.__avg_waiting_time = statistics.mean(avg_waiting)


    def update_clients_expected_time(self):
        """
        Updates all clients' expected waiting times
        :param data: self
        :return: nothing
        """
        for client in self.__clients_list:
            dist = client.get_distance()
            expected_time = round(dist / DIST_TO_PEOPLE_RATIO) * self.__avg_service_time
            client.set_expected_time(expected_time)


    def update_ap(self):
        """
        Updates the client list, and every client
        :param data: self
        :return: nothing
        """
        self.update_client_list() # see what clients are present and update their position and times
        self.update_service_time() # update average service time
        self.update_waiting_time() # update average waiting time
        self.update_clients_expected_time() # update clients' expected wait time


    def find_client(self, mac_address): #site needs this
        """
        Finds the client in the list of clients that has a given MAC address
        :param data: self
        :return: the client, or nothing if the client doesn't exist
        """
        for client in self.__clients_list:
            if client.get_mac() == mac_address:
                return client
        return None


    def get_ap_times(self): #site needs this
        """
        Returns the average waiting and service times, in that order
        :param data: self
        :return: average waiting and service times, in that order
        """
        return (self.__avg_waiting_time, self.__avg_service_time)
    
    
    def get_stations(self):
        """
        Returns the dictionary with all of the clients' MACs and RSSIs
        :param data: self
        :return: dictionary with all of the clients' MACs and RSSIs
        """
        return self.__stations




app = Flask(__name__)

# initialize AP
access_point = AccessPoint()

@app.route('/get-station-info', methods=['GET'])
def get_station_info():
    station_info = access_point.get_stations()
    return jsonify(station_info)  # Returns the dictionary as a JSON response


@app.route('/get-waiting-info', methods=['GET'])
def get_waiting_info():
    access_point.update_ap()  # update the AP
    #distance = client_station.get_distance()  
    #own_wait_time = client_station.get_expected_waiting_time()  
    avg_waiting_time, avg_service_time  = access_point.get_ap_times() 
    
    return jsonify({
        #'distance': distance,
        #'own_wait_time': own_wait_time,
        'avg-wait-time': avg_waiting_time,
        'avg-serv-time': avg_service_time
    })


if __name__ == '__main__':
    app.run(debug=True)
