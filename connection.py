from flask_cors import CORS
from flask import Flask, make_response
import time
import statistics
from ClientApp import access_point, main
from ClientApp import Client

app = Flask(__name__)
CORS(app)
# route to get MAC and RSSI information
@app.route("/get-station-info", methods=["GET"])
def get_station_info():
    return access_point.get_clients_stuffs(), 200  # returns the dictionary as a JSON response


@app.route("/get-waiting-info", methods=["GET"])
def get_waiting_info():
    access_point.update_ap()  # update the AP
    # distance = client_station.get_distance()
    # own_wait_time = client_station.get_expected_waiting_time()
    avg_waiting_time, avg_service_time = access_point.get_ap_times()

    return {
        #    'distance': distance,
        #    'own_wait_time': own_wait_time,
        "avg-wait-time": round(avg_waiting_time/60,2),
        "avg-serv-time": avg_service_time,
    }


if __name__ == "__main__":
    # by putting host on 0.0.0.0, flask will listen for connections on all network
    # interfaces of the machine, that includes devices in the same network of it
    app.run(debug=True, host="0.0.0.0")
