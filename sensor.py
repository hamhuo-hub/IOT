import time
import requests
import json
import sys
from collections import deque
from analysis import detect_spike, detect_trend, predict_threshold_breach

try:
    from sense_emu import SenseHat
except ImportError:
    print("FATAL: sense_emu package is not installed.")
    sys.exit(1)

sense = None

# Global data queues for analysis
MAX_QUEUE_LEN = 60
temp_queue = deque(maxlen=MAX_QUEUE_LEN)
time_queue = deque(maxlen=MAX_QUEUE_LEN)

# Global Thresholds (Mutable)
thresholds = {
    'temp_min': 0,
    'temp_max': 40,
    'hum_min': 10,
    'hum_max': 90,
    'pres_min': 970,
    'pres_max': 1030
}

# VictoriaMetrics config
VM_WRITE_URL = "http://localhost:8428/write"

def get_sensor_data():
    """
    Attempts to read sensory data.
    Will reload the SenseHat instance if memory mapping is corrupted.
    """
    global sense
    if sense is None:
        sense = SenseHat()
        
    temp = sense.get_temperature()
    hum = sense.get_humidity()
    pres = sense.get_pressure()

    # Sense HAT Emulator is known to return crazy garbage values (like 16000% humidity or exact flat 0)
    # if the Python object was initialized BEFORE the GUI was opened (Memory Map corruption).
    # If we detect wild non-physical values, we destroy the corrupted instance and raise error to reset.
    if hum < 0 or hum > 150 or pres < 0 or pres > 2000 or (temp == 0.0 and pres == 0.0):
        sense = None
        raise ValueError("Sense HAT shared memory corrupted (GUI restarted). Forcing remap...")

    return {
        'temperature': round(temp, 2),
        'humidity': round(hum, 2),
        'pressure': round(pres, 2)
    }

def trigger_physical_alarm():
    global sense
    if sense:
        try:
            sense.clear(255, 0, 0) # Red
        except Exception:
            pass

def clear_physical_alarm():
    global sense
    if sense:
        try:
            sense.clear()
        except Exception:
            pass

def push_to_victoriametrics(data):
    """
    Push data to VictoriaMetrics using InfluxDB line protocol.
    measurement,tag_key=tag_val field_key=field_val timestamp
    """
    line = f"environment,device=raspberrypi temperature={data['temperature']},humidity={data['humidity']},pressure={data['pressure']}"
    try:
        requests.post(VM_WRITE_URL, data=line, timeout=0.5)
    except requests.exceptions.RequestException:
        pass

def update_thresholds_internal(new_thresholds):
    global thresholds
    thresholds.update(new_thresholds)

def get_current_state():
    """
    Returns the current active thresholds and historical data
    so a cleanly restarted browser can catch up instantly.
    """
    return {
        'thresholds': thresholds,
        'history': {
            'temperatures': list(temp_queue),
            'timestamps': [int(t * 1000) for t in time_queue]
        }
    }

def background_sensor_loop(socketio):
    """
    The main background task running via eventlet.
    Takes socketio instance to broadcast data.
    """
    print("\nSystem started. Initiating background sensor loop...")
    gui_warning_printed = False
    
    while True:
        try:
            # 尝试拉取真实数据（若 GUI 未开启，这里将抛出异常）
            data = get_sensor_data()
            
            # 若之前打印过警告，说明这会儿刚才连上了
            if gui_warning_printed:
                print("\n[+] Successfully connected to sense-emu-gui instance! Resuming data capture...")
                gui_warning_printed = False
                
        except Exception as e:
            # GUI 不存在，捕获异常，并且作为一个普通的广播事件通知给前端，但不破坏分析队列
            if not gui_warning_printed:
                print(f"\n[!] WARNING: Sense HAT Emulator GUI is not running or accessible. (Error: {e})")
                print("    -> System is in standby mode. Waiting for the GUI instance to appear...")
                gui_warning_printed = True
            
            payload = {
                'timestamp': int(time.time() * 1000),
                'data': {'temperature': None, 'humidity': None, 'pressure': None},
                'alarms': ["CRITICAL: Sense HAT Hardware Offline. Please start 'sense-emu-gui'"],
                'analysis': {
                    'trend': 'offline',
                    'spike_detected': False,
                    'z_score': 0.0,
                    'predicted_breach_sec': None
                }
            }
            socketio.emit('sensor_update', payload)
            socketio.sleep(2.0)
            continue
            
        current_time_ms = int(time.time() * 1000)
        current_time_sec = time.time()
        
        # Add to queues for analysis
        temp_queue.append(data['temperature'])
        time_queue.append(current_time_sec)
        
        # --- Perform Data Analysis (Requirement 5) ---
        is_spike, z_val = detect_spike(list(temp_queue))
        trend = detect_trend(list(temp_queue))
        predicted_breach_time = predict_threshold_breach(
            list(time_queue), list(temp_queue), thresholds['temp_max'], trend
        )
        # ---------------------------------------------
        
        # Check standard threshold warnings
        alarms = []
        if data['temperature'] < thresholds['temp_min']: alarms.append("Temperature too low!")
        if data['temperature'] > thresholds['temp_max']: alarms.append("Temperature too high!")
        if data['humidity'] < thresholds['hum_min']: alarms.append("Humidity too low!")
        if data['humidity'] > thresholds['hum_max']: alarms.append("Humidity too high!")
        if data['pressure'] < thresholds['pres_min']: alarms.append("Pressure too low!")
        if data['pressure'] > thresholds['pres_max']: alarms.append("Pressure too high!")
        
        if is_spike:
            alarms.append("Sudden temperature spike/drop detected!")
            
        # Trigger hardware feedback
        if len(alarms) > 0:
            trigger_physical_alarm()
        else:
            clear_physical_alarm()
            
        # Send to VictoriaMetrics
        push_to_victoriametrics(data)
        
        # Construct payload for web interface
        payload = {
            'timestamp': current_time_ms,
            'data': data,
            'alarms': alarms,
            'analysis': {
                'trend': trend,
                'spike_detected': is_spike,
                'z_score': round(z_val, 2),
                'predicted_breach_sec': round(predicted_breach_time, 1) if predicted_breach_time else None
            }
        }
        
        socketio.emit('sensor_update', payload)
        
        socketio.sleep(1) # Eventlet cooperative yield and sleep
