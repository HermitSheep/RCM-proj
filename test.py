from collections import deque
import statistics
import math

CLIENT_RSSI_BUFFER_SIZE = 3  # rssi samples

class RSSIBuffer:
    """
    A queue with defined max size, and a method for getting its median
    """

    def __init__(self, max_len):
        self.__buffer = deque(maxlen=max_len)  # Use deque with a fixed size
        self.__size = max_len

    def add_rssi(self, rssi):
        """
        Adds a new RSSI value to the buffer.
        If the buffer is empty, fills it with the initial RSSI value to prevent early median from being 0.
        :param rssi: RSSI value to add
        :return: nothing
        """
        if len(self.__buffer) == 0:
            # Append the initial RSSI value to fill the deque
            self.__buffer.extend([rssi] * self.__size)
        else:
            self.__buffer.append(rssi)

    def calculate_median(self):
        """
        Calculates the median of the RSSI values in the buffer.
        :return: The median of the RSSI values in the buffer
        :raises: ValueError if the buffer is empty
        """
        if len(self.__buffer) > 0:
            return math.floor(statistics.median(self.__buffer))
        else:
            raise ValueError("Tried to read from an empty buffer")


# Example usage
buffer = RSSIBuffer(CLIENT_RSSI_BUFFER_SIZE)
buffer.add_rssi(-48)  # Buffer -> [-48, -48, -48]
buffer.add_rssi(-48)  # Buffer -> [-48, -48, -48] (still max length 3)
buffer.add_rssi(-6)   # Buffer -> [-48, -48, -6]
buffer.add_rssi(-6)   # Buffer -> [-48, -6, -6]

buffer.add_rssi(-6)
buffer.add_rssi(-6)
buffer.add_rssi(-6)
buffer.add_rssi(-6)

