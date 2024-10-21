document.addEventListener("DOMContentLoaded", function () {
  // light and dark mode themes, first select elements and then change when people click it
  const modeToggle = document.getElementById("mode-toggle");
  const body = document.body;

  modeToggle.addEventListener("click", function () {
    if (body.classList.contains("light-mode")) {
      body.classList.remove("light-mode");
      body.classList.add("dark-mode");
      modeToggle.textContent = "🌙";
    } else {
      body.classList.remove("dark-mode");
      body.classList.add("light-mode");
      modeToggle.textContent = "🌞";
    }
  });

  // update the "current time" every second
  function updateClock() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    document.getElementById(
      "current-time"
    ).textContent = `Current time: ${timeString}`;
  }

  setInterval(updateClock, 1000);
  updateClock();

    // update the table with MAC addresses and RSSI values
    function getStationInfo() {
        fetch('http://localhost:5000/get-station-info')
            .then(response => response.json())
            .then(data => {
                const tableBody = document.getElementById('stations-table-body');
                tableBody.innerHTML = '';  // Clear the table before adding new data
    
                // Loop through each MAC-RSSI pair and create a row in the table
                Object.entries(data).forEach(([mac, rssi]) => {
                    const row = document.createElement('tr');
                    
                    // Create and append MAC address cell
                    const macCell = document.createElement('td');
                    macCell.innerText = mac;
                    row.appendChild(macCell);
                    
                    // Create and append RSSI value cell
                    const rssiCell = document.createElement('td');
                    rssiCell.innerText = rssi;
                    row.appendChild(rssiCell);
    
                    // Append the row to the table body
                    tableBody.appendChild(row);
                });
            })
            .catch(error => {
                console.error('Error fetching station info:', error);
            });
    }

    // Function to fetch and display average waiting time and service time
    function getWaitingInfo() {
        fetch('http://localhost:5000/get-waiting-info')
            .then(response => response.json())
            .then(data => {
                const avgWaitTime = data['avg-wait-time'];
                const avgServTime = data['avg-serv-time'];

                // Update the text content of the respective elements
                document.getElementById('avg-wait-time').innerText = `Average Waiting Time: ${avgWaitTime} mins`;
                document.getElementById('avg-serv-time').innerText = `Average Service Time: ${avgServTime} mins`;
            })
            .catch(error => {
                console.error('Error fetching waiting info:', error);
            });
    }

    function updateInfo() {
        getStationInfo();
        getWaitingInfo();
    }

    // update the table every 3 seconds
    setInterval(updateInfo, 3000);

    // Initial call to populate the data when the page loads
    updateInfo()
});
