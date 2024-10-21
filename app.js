document.addEventListener('DOMContentLoaded', function() {
    // light and dark mode themes, first select elements and then change when people click it
    const modeToggle = document.getElementById('mode-toggle');
    const body = document.body;

    modeToggle.addEventListener('click', function() {
        if (body.classList.contains('light-mode')) {
            body.classList.remove('light-mode');
            body.classList.add('dark-mode');
            modeToggle.textContent = '🌙';
        } else {
            body.classList.remove('dark-mode');
            body.classList.add('light-mode');
            modeToggle.textContent = '🌞';
        }
    });

    // update the "current time" every second
    function updateClock() {
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        document.getElementById('current-time').textContent = `Current time: ${timeString}`;
    }

    setInterval(updateClock, 1000);
    updateClock();

    // update the table with MAC addresses and RSSI values
    function updateInfo() {
        // get the data from the flask
        fetch('http://localhost:5000/get-ap-times')
            .then(response => response.json())
            .then(data => {
                // get the dictionary of MACs and RSSIs
                const stations = data;
    
                // get the table where we will add the rows (in home.html) and clear previous entries
                const tableBody = document.getElementById('stations-table-body');
                tableBody.innerHTML = ''; 
    
                // add each station (MAC address and RSSI) to the table
                for (const [mac, rssi] of Object.entries(stations)) {
                    const row = document.createElement('tr');
    
                    // add MAC address
                    const macCell = document.createElement('td');
                    macCell.textContent = mac;
    
                    // add RSSI value
                    const rssiCell = document.createElement('td');
                    rssiCell.textContent = rssi;
    
                    // append the last two to the row
                    row.appendChild(macCell);
                    row.appendChild(rssiCell);
    
                    // append the row to the table
                    tableBody.appendChild(row);
                }
            })
            .catch(error => console.error('Error fetching MAC addresses:', error));
    }

    // update the table every 3 seconds
    setInterval(updateInfo, 3000);
});
