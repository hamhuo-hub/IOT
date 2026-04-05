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
const valZscore = document.getElementById('val-zscore');
const valTrend = document.getElementById('val-trend');
const valCountdown = document.getElementById('val-countdown');

// Chart Setup
const ctx = document.getElementById('tempChart').getContext('2d');
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', sans-serif";

const tempChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [], // Timestamps
        datasets: [{
            label: 'Temperature (°C)',
            data: [],
            borderColor: '#0056b3',
            backgroundColor: 'rgba(0, 86, 179, 0.1)',
            borderWidth: 2,
            pointBackgroundColor: '#0056b3',
            pointRadius: 2,
            pointHoverRadius: 4,
            fill: true,
            tension: 0.4 // Smooth curves
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
            duration: 0 // Disable animation for real-time performance
        },
        scales: {
            x: {
                grid: { color: 'rgba(0, 0, 0, 0.05)' }
            },
            y: {
                grid: { color: 'rgba(0, 0, 0, 0.05)' },
                suggestedMin: 10,
                suggestedMax: 40
            }
        },
        plugins: {
            legend: { display: false }
        }
    }
});

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

socket.on('sync_state', (state) => {
    // 1. Sync threshold inputs with backend state
    document.getElementById('temp_min').value = state.thresholds.temp_min;
    document.getElementById('temp_max').value = state.thresholds.temp_max;
    document.getElementById('hum_min').value = state.thresholds.hum_min;
    document.getElementById('hum_max').value = state.thresholds.hum_max;
    document.getElementById('pres_min').value = state.thresholds.pres_min;
    document.getElementById('pres_max').value = state.thresholds.pres_max;

    // 2. Fast-forward Chart data
    tempChart.data.labels = state.history.timestamps.map(ts => new Date(ts).toLocaleTimeString());
    tempChart.data.datasets[0].data = state.history.temperatures;
    tempChart.update();
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
        tempChart.data.labels.shift();
        tempChart.data.datasets[0].data.shift();
    }
    tempChart.data.labels.push(timeLabel);
    tempChart.data.datasets[0].data.push(data.temperature);
    tempChart.update();

    // 3. Process Alarms & Formatting
    let hasCriticalAlarm = false;
    let alarmHTML = '';

    // Reset card borders
    cardTemp.classList.remove('card-alert');
    cardHum.classList.remove('card-alert');
    cardPres.classList.remove('card-alert');

    if (payload.alarms.length > 0) {
        hasCriticalAlarm = true;
        payload.alarms.forEach(msg => {
            alarmHTML += `<div class="alert-item danger">⚠️ ${msg}</div>`;
            // Highlight specific cards based on message content
            if(msg.includes('Temperature') || msg.includes('spike')) cardTemp.classList.add('card-alert');
            if(msg.includes('Humidity')) cardHum.classList.add('card-alert');
            if(msg.includes('Pressure')) cardPres.classList.add('card-alert');
        });
    } else {
        alarmHTML = `<div class="alert-item safe">✅ System Nominal</div>`;
    }

    alertsList.innerHTML = alarmHTML;

    // 4. Update Analysis panel
    valZscore.textContent = payload.analysis.z_score;
    // Highlight Z-score if > 3
    valZscore.style.color = payload.analysis.z_score > 3.0 ? 'var(--danger)' : 'var(--text-main)';
    
    valTrend.textContent = payload.analysis.trend.toUpperCase();
    if(payload.analysis.trend === 'upward') valTrend.style.color = 'var(--danger)';
    else if(payload.analysis.trend === 'downward') valTrend.style.color = '#3b82f6';
    else valTrend.style.color = 'var(--text-main)';

    if (payload.analysis.predicted_breach_sec !== null) {
        const secs = payload.analysis.predicted_breach_sec;
        if (secs < 60) {
            valCountdown.textContent = `< ${Math.ceil(secs)} sec!`;
            valCountdown.style.color = 'var(--danger)';
        } else {
            valCountdown.textContent = `${(secs / 60).toFixed(1)} min`;
            valCountdown.style.color = 'var(--accent)';
        }
    } else {
        valCountdown.textContent = '--';
        valCountdown.style.color = 'var(--text-muted)';
    }
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
