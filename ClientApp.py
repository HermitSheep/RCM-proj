import subprocess
import re
import time
from collections import deque
import statistics
import pandas as pd
import math


QUEUE_MAX_SIZE = 2  # meters
CLIENT_RSSI_BUFFER_SIZE = 3  # rssi samples
SERVICE_DIST = (
    1  # distance at which the person is being served at the balcony, in meters
)
LEAVING_DIST = 2  # distance at whereafter the person is probably leaving, in meters
LEAVING_RSSI = -55  # distance at whereafter the person is probably leaving, in meters
DIST_TO_PEOPLE_RATIO = (
    0.6  # average distance between two people in the queue, in meters
)
AVG_NUMBER = (
    3  # number of past clients to take into acount when calculating average times
)
RSSI_TO_DIST_DATABASE = (
    "Fila_Medições.xlsx"  # excel sheet with RSSI to distance relation
)
DIST_COLUMN_NAME = "Distancia"  # name of the column with distance values
RSSI_COLUMN_NAME = "RSSI"  # name of the column with the RSSI values

Service_Flag = False  # flag that marks if there's a client being serviced


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
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Get the output as text
        output = result.stdout.decode("utf-8")

        # Dictionary to hold MAC address and signal strength
        stations = {}

        # Use regular expressions to extract MAC addresses and signal strength
        matches = re.findall(
            r"Station ([0-9a-f:]+).*?signal:\s+(-?\d+)", output, re.DOTALL
        )

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
    rssiDist.setdefault(key, [])
    print("signal: ", signal)
    # Group the data by RSSI and calculate the median distance for each RSSI
    rssiDist = (
        dfSelected.groupby(RSSI_COLUMN_NAME)[DIST_COLUMN_NAME].apply(list).to_dict()
    )
    # Sort the RSSI keys to find the closest lower value if the exact signal is not present
    sorted_rssi = sorted(rssiDist.keys(), reverse=True)
    # Look for exact RSSI or closest lower value
    for rssi in sorted_rssi:
        if signal >= rssi:
            print("real dist: ", statistics.median(rssiDist[rssi]))
            return statistics.median(rssiDist[rssi])
        if signal not in sorted_rssi:
            fake_signal = min(sorted_rssi)
            print("fake dist: ", statistics.median(rssiDist[fake_signal]))
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
            self.__buffer.extend([rssi] * self.__size)
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
        self.__waiting_time = 0  # time the client has spent in the queue
        self.__service_time = 0  # time the client has spent being serviced
        self.__leaving_time = 0  # time the client has spent leaving
        self.__expected_wait_time = 0  # time the client can expect to wait in line
        self.__state = "waiting"  # States: 'waiting', 'service', 'leaving'

    def __update_rssi(self, rssi):
        """
        Updates the client's rssi and distance
        :param data: self and the current rssi
        :return: nothing
        """
        self.__RSSI_buffer.add_rssi(rssi)
        print("buffer: ", self.__RSSI_buffer.calculate_median())
        self.__distance = rssi_to_dist(self.__RSSI_buffer.calculate_median())

    def __update_state(self, time_passed):
        """
        Updates the client's state and times
        :param data: self and the current time
        :return: nothing
        :raises: ValueError if the client has an invalid state
        """
        print("state: ", self.__state)
        print("MAC: ", self.__MAC)
        print("time: ", time_passed)
        print("distance: ", self.__distance)
        global Service_Flag
        print("after global: ", Service_Flag)

        match self.__state:
            case "waiting":
                print("wait: ", Service_Flag)
                if self.__distance < SERVICE_DIST and not Service_Flag:
                    self.__state = "service"
                    Service_Flag = True
                    print("service: ", Service_Flag)
                    print("wait service", self.__state)
                    print("mac serv: ", self.__MAC)
                else:
                    self.__waiting_time += time_passed  # client has been waiting for the last "timePassed" seconds
            case "service":
                if self.__distance > LEAVING_DIST:
                    self.__state = "leaving"
                    Service_Flag = False
                    print("leave: ", Service_Flag)
                    print("service leave", self.__state)
                    print("mac leave: ", self.__MAC)
                else:
                    self.__service_time += time_passed  # client has been being serviced for the last "timePassed" seconds

            case "leaving":
                self.__leaving_time += time_passed  # client has been leaving for the last "timePassed" seconds

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

    def set_expected_time(
        self, expected_time
    ):  # isto nao devia ser usado no update_state() ?
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

    def get_expected_waiting_time(self):  # site needs this
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


class AccessPoint:
    """
    Processes all information that's accessible to the access point
    """

    def __init__(self):
        self.__clients_list = []  # Current clients
        self.__past_clients_list = []  # Past clients
        self.__avg_waiting_time = 0  # Average waiting time (global)
        self.__avg_service_time = 0  # Average service time (global)
        self.__stations = (
            {}
        )  # Dictionary with the measured MAC and corresponding RSSIs of each connected client
        self.__times = deque(
            maxlen=2
        )  # Queue with the times of the past and current measurements (to measure time passed between measurements)
        self.__times.append(
            0
        )  # Initializing it at 0 (the first time it runs, zero will be the past measurement)

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
        new_clients = []  # list of the MACs of the new clients
        regulars = []  # list of clients that aren't new nor old

        self.measure_queue()

        time_passed = self.__times[1] - self.__times[0] # time passed between measurements
        #print("time 1: ", self.__times[1])
        #print("time 0: ", self.__times[0])

        for (
            client
        ) in (
            self.__clients_list
        ):  # check for old clients (clients that have already left the queue completely) and remove them
            state = client.get_client_state()
            #print(state)
            if client.get_mac() not in self.__stations or state == "leaving":
                self.__past_clients_list.append(client)
                self.__clients_list.remove(client)
            else:
                regulars.append(client.get_mac())  # list of existing mac addresses
        #print("should enter now")
        for mac,rssi in self.__stations.items():  # checks for new clients, then adds and updates them, while updating the rest of the clients
         #   print("indeed i did")
          #  print("mac and rssi: ", mac, rssi)
            
            if mac not in regulars and rssi > LEAVING_RSSI:
           #     print("not not")
                client = Client(mac)
                client.update_client(
                    rssi, 0
                )  # new clients start with time set to 0 (because they're new)
                self.__clients_list.append(client)
            #    print("list: ", self.__clients_list)
                new_clients.append(mac)

        for client in self.__clients_list:  # updates all other clients
            mac = client.get_mac()
            rssi = self.__stations[mac]
            if mac in self.__stations and mac not in new_clients:
                client.update_client(
                    rssi, time_passed
                )  # other clients get their time updated

    def update_service_time(self):
        """
        This function updates the AP's service time based on the mean of the last AVG_NUMBER available clients that left
        :params: self
        :returns: nothing
        """
        avg_service = []
        size_past_clients = len(self.__past_clients_list)
        if size_past_clients > 0:
            for old_client in self.__past_clients_list[
                -1 : -AVG_NUMBER - 1 : -1
            ]:  # [-1, -2, -3] -> last three elements of a list, for example
                avg_service.append(old_client.get_client_service_time())
            self.__avg_service_time = statistics.mean(avg_service)
        else:
            for cur_client in self.__clients_list[
                -1 : -AVG_NUMBER - 1 : -1
            ]:  # [-1, -2, -3] -> last three elements of a list, for example
                avg_service.append(cur_client.get_client_service_time())

    def update_waiting_time(self):
        """
        This function updates the AP's average waiting time based on the mean of the last AVG_NUMBER available clients that left
        :params: self
        :returns: nothing
        """
        avg_waiting = []
        size_past_clients = len(self.__past_clients_list)
      #  print("size of list: ", size_past_clients)
        size_cur_clients = len(self.__clients_list)
       # print("size cur clients: ", size_cur_clients)
        if size_past_clients > 0:
            if size_past_clients >= AVG_NUMBER:
        #        print("whyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy")
                for old_client in self.__past_clients_list[
                    -1 : -AVG_NUMBER - 1 : -1
                ]:  # [-1, -2, -3] -> last three elements of a list, for example
                    avg_waiting.append(old_client.get_client_waiting_time())
                self.__avg_waiting_time = statistics.mean(avg_waiting)
            elif size_past_clients == 2:
                for old_client in self.__past_clients_list[-1:-(size_past_clients):-1]:
         #           print(
           #             "old_client.get_client_waiting_time() 2  ",
          #              old_client.get_client_waiting_time(),
            #        )
                    avg_waiting.append(old_client.get_client_waiting_time())
             #       print("avg_wait 2 : ", old_client.get_client_waiting_time())
                self.__avg_waiting_time = statistics.mean(avg_waiting)
            else:
              #  print("wtffffffffffffffffffffffffffffffffffffffffff")
               # print(self.__past_clients_list)
                old_client = self.__past_clients_list[0]
                avg_waiting.append(old_client.get_client_waiting_time())
                #print("avg_wait: ", old_client.get_client_waiting_time())
                self.__avg_waiting_time = statistics.mean(avg_waiting)
        else:
            if size_cur_clients >= AVG_NUMBER:
                for cur_client in self.__clients_list[
                -1 : -AVG_NUMBER - 1 : -1
            ]:  # [-1, -2, -3] -> last three elements of a list, for example
                    avg_waiting.append(cur_client.get_client_waiting_time())
                self.__avg_waiting_time = statistics.mean(avg_waiting)
                
            elif size_past_clients == 2:
                for cur_client in self.__clients_list[-1:-(size_cur_clients):-1]:
                    avg_waiting.append(cur_client.get_client_waiting_time())
                self.__avg_waiting_time = statistics.mean(avg_waiting)
            else:
                cur_client = self.__clients_list[0]
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
        self.update_client_list()  # see what clients are present and update their position and times
        self.update_service_time()  # update average service time
        self.update_waiting_time()  # update average waiting time
        self.update_clients_expected_time()  # update clients' expected wait time

    def find_client(self, mac_address):  # site needs this
        """
        Finds the client in the list of clients that has a given MAC address
        :param data: self
        :return: the client, or nothing if the client doesn't exist
        """
        for client in self.__clients_list:
            if client.get_mac() == mac_address:
                return client
        return None

    def get_ap_times(self):  # site needs this
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
    
    def get_place_dist(self):
        station_client = {}
        clients = self.__stations
        i = 1
        for key in clients:
            station_client[i] = rssi_to_dist(clients[key])
            i += 1
            
        return  station_client



#    def get_clients_stuffs(self):
#        """
#        Returns the dictionary with all of the clients' MACs and people distances
#        :param data: self
#        :return: dictionary with all of the clients' MACs and people distances
#        """
#        clients = {}
#        for client in self.__clients_list:
#            clients[client.get_mac()] = client.get_distance()


def main(AP):
    AP.update_ap()
    print(AP.get_ap_times())
    print(AP.get_stations())
    time.sleep(2)


access_point = AccessPoint()
if __name__ == "__main__":
    while True:
        main(access_point)
