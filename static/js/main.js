const socket = io();

// DOM Elements
const connDot = document.getElementById('connection-dot');
const connStatus = document.getElementById('connection-status');

const valTemp = document.getElementById('val-temp');
const valHum = document.getElementById('val-hum');
const valPres = document.getElementById('val-pres');

const cardTemp = document.getElementById('card-temp');
const cardHum = document.getElementById('card-hum');
const cardPres = document.getElementById('card-pres');

const alertsList = document.getElementById('alerts-list');
const alarmHistoryList = document.getElementById('alarm-history-list');
const valZscore = document.getElementById('val-zscore');
const valTrend = document.getElementById('val-trend');

// Chart Setup
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', sans-serif";

function createChart(ctxId, label, color, bg, min, max) {
    const ctx = document.getElementById(ctxId).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [], 
            datasets: [{
                label: label,
                data: [],
                borderColor: color,
                backgroundColor: bg,
                borderWidth: 2,
                pointBackgroundColor: color,
                pointRadius: 2,
                pointHoverRadius: 4,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            scales: {
                x: { grid: { color: 'rgba(0, 0, 0, 0.05)' } },
                y: { 
                    grid: { color: 'rgba(0, 0, 0, 0.05)' },
                    suggestedMin: min,
                    suggestedMax: max
                }
            },
            plugins: { legend: { display: false } }
        }
    });
}

const tempChart = createChart('tempChart', 'Temperature (°C)', '#0056b3', 'rgba(0, 86, 179, 0.1)', 10, 40);
const humChart  = createChart('humChart', 'Humidity (%)', '#0284c7', 'rgba(2, 132, 199, 0.1)', 20, 80);
const presChart = createChart('presChart', 'Pressure (hPa)', '#7c3aed', 'rgba(124, 58, 237, 0.1)', 980, 1020);

// Socket.IO Events
socket.on('connect', () => {
    connDot.classList.add('connected');
    connStatus.textContent = 'Data Link Active';
    connStatus.style.color = 'var(--safe)';
});

socket.on('disconnect', () => {
    connDot.classList.remove('connected');
    connStatus.textContent = 'Connection Lost';
    connStatus.style.color = 'var(--danger)';
});

// Helper to render persistent logs
function appendLog(log) {
    const li = document.createElement('li');
    li.innerHTML = `<span class="log-time">${log.timestamp}</span><span class="accent-text" style="color:var(--${log.severity})">${log.message}</span>`;
    alarmHistoryList.prepend(li); // newest on top
}

socket.on('sync_state', (state) => {
    // 1. Sync threshold inputs with backend state
    document.getElementById('temp_min').value = state.thresholds.temp_min;
    document.getElementById('temp_max').value = state.thresholds.temp_max;
    document.getElementById('hum_min').value = state.thresholds.hum_min;
    document.getElementById('hum_max').value = state.thresholds.hum_max;
    document.getElementById('pres_min').value = state.thresholds.pres_min;
    document.getElementById('pres_max').value = state.thresholds.pres_max;

    // 2. Fast-forward Chart data
    const labels = state.history.timestamps.map(ts => new Date(ts).toLocaleTimeString());
    
    tempChart.data.labels = [...labels];
    tempChart.data.datasets[0].data = state.history.temperatures;
    tempChart.update();
    
    humChart.data.labels = [...labels];
    humChart.data.datasets[0].data = state.history.humidities;
    humChart.update();
    
    presChart.data.labels = [...labels];
    presChart.data.datasets[0].data = state.history.pressures;
    presChart.update();
    
    // 3. Populate Historical Logs
    alarmHistoryList.innerHTML = '';
    
    // Safely iterate even if backend hasn't initialized historical_alarms yet
    (state.historical_alarms || []).reverse().forEach(log => {
        appendLog(log);
    });
});

socket.on('sensor_update', (payload) => {
    const data = payload.data;
    const timeLabel = new Date(payload.timestamp).toLocaleTimeString();

    // 1. Update Numeric Values gracefully checking for nulls from backend
    valTemp.textContent = data.temperature !== null ? data.temperature.toFixed(1) : '--';
    valHum.textContent = data.humidity !== null ? data.humidity.toFixed(1) : '--';
    valPres.textContent = data.pressure !== null ? data.pressure.toFixed(1) : '--';

    // 2. Update Graph (Sliding Window of 60)
    if (tempChart.data.labels.length > 60) {
        tempChart.data.labels.shift(); tempChart.data.datasets[0].data.shift();
        humChart.data.labels.shift(); humChart.data.datasets[0].data.shift();
        presChart.data.labels.shift(); presChart.data.datasets[0].data.shift();
    }
    tempChart.data.labels.push(timeLabel); tempChart.data.datasets[0].data.push(data.temperature);
    humChart.data.labels.push(timeLabel); humChart.data.datasets[0].data.push(data.humidity);
    presChart.data.labels.push(timeLabel); presChart.data.datasets[0].data.push(data.pressure);
    
    tempChart.update();
    humChart.update();
    presChart.update();

    // 3. Process Alarms & Formatting
    let alarmHTML = '';

    // Reset card borders
    cardTemp.classList.remove('card-alert');
    cardHum.classList.remove('card-alert');
    cardPres.classList.remove('card-alert');

    if (payload.alarms.length > 0) {
        payload.alarms.forEach(msg => {
            alarmHTML += `<div class="alert-item danger">⚠️ ${msg}</div>`;
            // Highlight specific cards based on message content
            if(msg.includes('Temperature') || msg.includes('temperature')) cardTemp.classList.add('card-alert');
            if(msg.includes('Humidity') || msg.includes('humidity')) cardHum.classList.add('card-alert');
            if(msg.includes('Pressure') || msg.includes('pressure')) cardPres.classList.add('card-alert');
        });
    } else {
        alarmHTML = `<div class="alert-item safe">✅ System Nominal</div>`;
    }

    alertsList.innerHTML = alarmHTML;
    
    // 4. Update Persistent Logs (Edge-triggered)
    if (payload.new_log_alarms && payload.new_log_alarms.length > 0) {
        payload.new_log_alarms.forEach(log => {
            appendLog(log);
        });
    }

    // 5. Update Analysis panel
    valZscore.textContent = payload.analysis.z_score;
    // Highlight Z-score if > 3
    valZscore.style.color = payload.analysis.z_score > 3.0 ? 'var(--danger)' : 'var(--text-main)';
    
    valTrend.textContent = payload.analysis.trend.toUpperCase();
    if(payload.analysis.trend === 'upward') valTrend.style.color = 'var(--danger)';
    else if(payload.analysis.trend === 'downward') valTrend.style.color = '#3b82f6';
    else valTrend.style.color = 'var(--text-main)';


});

// Form Submission for Thresholds
document.getElementById('thresholds-form').addEventListener('submit', (e) => {
    e.preventDefault();
    
    const newThresholds = {
        temp_min: parseFloat(document.getElementById('temp_min').value),
        temp_max: parseFloat(document.getElementById('temp_max').value),
        hum_min: parseFloat(document.getElementById('hum_min').value),
        hum_max: parseFloat(document.getElementById('hum_max').value),
        pres_min: parseFloat(document.getElementById('pres_min').value),
        pres_max: parseFloat(document.getElementById('pres_max').value)
    };

    // Send via socket
    socket.emit('update_thresholds', newThresholds);
    
    // Provide user feedback
    const btn = e.target.querySelector('button');
    const originalText = btn.textContent;
    btn.textContent = 'Protocols Updated!';
    btn.style.background = 'var(--safe)';
    
    setTimeout(() => {
        btn.textContent = originalText;
        btn.style.background = '';
    }, 2000);
});
