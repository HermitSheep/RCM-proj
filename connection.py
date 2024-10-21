from flask import Flask, jsonify
import time
import statistics
from ClientApp import AccessPoint 
from ClientApp import Client

app = Flask(__name__)

# initialize AP
access_point = AccessPoint()
client_station = Client()

# route to get MAC and RSSI information
@app.route('/get-station-info', methods=['GET'])
def get_station_info():
    station_info = access_point.get_stations()
    return jsonify(station_info)  # returns the dictionary as a JSON response


@app.route('/get-waiting-info', methods=['GET'])
def get_waiting_info():
    access_point.update_ap()  # update the AP
    distance = client_station.get_distance()  
    own_wait_time = client_station.get_expected_waiting_time()  
    avg_waiting_time, avg_service_time  = access_point.get_ap_times() 
    
    return jsonify({
        'distance': distance,
        'own_wait_time': own_wait_time,
        'avg_wait_time': avg_waiting_time,
        'avg-serv-time': avg_service_time
    })


if __name__ == '__main__':
    # by putting host on 0.0.0.0, flask will listen for connections on all network
    # interfaces of the machine, that includes devices in the same network of it
    app.run(debug=True, host='0.0.0.0') 
