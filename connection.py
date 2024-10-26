from flask_cors import CORS
from flask import Flask, make_response, render_template
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
    avg_waiting_time, avg_service_time = access_point.get_ap_times()
    num_people = access_point.get_num_people()
    print(round(avg_waiting_time/60,2))
    print(avg_waiting_time)
    #create a response object
    return {
        "avg-wait-time": round(avg_waiting_time/60,2),
        "avg-serv-time": round(avg_service_time/60,2),
        "num-people": num_people,
    }
    


@app.route('/')
def home():
    return render_template('home.html')

if __name__ == "__main__":
    # by putting host on 0.0.0.0, flask will listen for connections on all network
    # interfaces of the machine, that includes devices in the same network of it
    app.run(debug=True, host="0.0.0.0", port=5000)
