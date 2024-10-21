from flask import Flask, jsonify
import time
import statistics
from backend import AccessPoint 

app = Flask(__name__)

# initialize AP
access_point = AccessPoint()

# route to get AP times (general waiting time and service time)
@app.route('/get-ap-times', methods=['GET'])
def get_ap_times():
    access_point.update_ap()  # update the AP
    avg_waiting_time, avg_service_time = access_point.get_ap_times()
    return jsonify({
        'avg_waiting_time': avg_waiting_time,
        'avg_service_time': avg_service_time
    })

# route to get client's estimated wait time by MAC address
@app.route('/get-client-wait-time/<mac_address>', methods=['GET'])
def get_client_wait_time(mac_address):
    client = access_point.find_client(mac_address)
    if client:
        return jsonify({
            'estimated_wait_time': client.get_expected_waiting_time()
        })
    else:
        return jsonify({
            'error': 'Client not found'
        }), 404


if __name__ == '__main__':
    # by putting host on 0.0.0.0, flask will listen for connections on all network
    # interfaces of the machine, that includes devices in the same network of it
    app.run(debug=True, host='0.0.0.0') 
