import time
import requests
import json
import sys
from collections import deque
from analysis import detect_spike, detect_trend
import db

import os
import subprocess


try:
    from sense_emu import SenseHat
    import sense_emu.RTIMU
    import struct
    
    # -------------------------------------------------------------------------
    # HOTFIX: 64-bit Architecture ABI Struct Alignment Bug in sense-emu
    # The C-compiled GUI uses packed structs, but Python's sense_emu package 
    # uses Native '@' format which introduces padding bytes on 64-bit systems 
    # (like Raspberry Pi OS Bookworm AArch64), shifting all data reads by 1+ bytes
    # and mixing Temperature sliders into Humidity data.
    # We dynamically intercept and force Standard '=' (no padding) in memory.
    # -------------------------------------------------------------------------
    sense_emu.RTIMU.HUMIDITY_DATA = struct.Struct(sense_emu.RTIMU.HUMIDITY_DATA.format.replace('@', '='))
    sense_emu.RTIMU.PRESSURE_DATA = struct.Struct(sense_emu.RTIMU.PRESSURE_DATA.format.replace('@', '='))
    sense_emu.RTIMU.IMU_DATA = struct.Struct(sense_emu.RTIMU.IMU_DATA.format.replace('@', '='))
    
except ImportError:
    print("FATAL: sense_emu package is not installed.")
    sys.exit(1)

def is_gui_running():
    """Manually checks if the GUI process is alive to prevent silent auto-spawns."""
    try:
        # Check if sense_emu_gui process is running
        output = subprocess.check_output(["pgrep", "-f", "sense_emu_gui"])
        return len(output.strip()) > 0
    except subprocess.CalledProcessError:
        return False
    except Exception:
        return True # Fallback if pgrep fails for some reason

sense = None

# Global data queues for analysis
MAX_QUEUE_LEN = 60
temp_queue = deque(maxlen=MAX_QUEUE_LEN)
hum_queue = deque(maxlen=MAX_QUEUE_LEN)
pres_queue = deque(maxlen=MAX_QUEUE_LEN)
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

# State tracker for alarms deduplication
active_alarms = set()


def get_sensor_data():
    """
    Attempts to read sensory data.
    Will reload the SenseHat instance if memory mapping is corrupted.
    """
    global sense
    
    if not is_gui_running():
        sense = None
        raise ValueError("Sense HAT Emulator GUI process is not running. Please launch 'sense_emu_gui'.")
        
    if sense is None:
        sense = SenseHat()
        
    temp = sense.get_temperature()
    hum = sense.get_humidity()
    pres = sense.get_pressure()

    # Sense HAT Emulator returns exact zeros or crazy garbage values (like 16000 humidity)
    # when the memory map structure is corrupted or misaligned (e.g. 32-bit vs 64-bit OS).
    if hum < 0 or hum > 150 or pres < 0 or pres > 2000 or (temp == 0.0 and pres == 0.0):
        sense = None
        raise ValueError(
            f"Sense HAT Memory Map is corrupted or architecture-mismatched. "
            f"(Values read - Temp: {temp}, Hum: {hum}, Pres: {pres}). "
            "Please clear the emulator cache or reinstall system packages."
        )

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
            'humidities': list(hum_queue),
            'pressures': list(pres_queue),
            'timestamps': [int(t * 1000) for t in time_queue]
        },
        'historical_alarms': db.get_recent_alarms(50)
    }

def background_sensor_loop(socketio):
    """
    The main background task running via eventlet.
    Takes socketio instance to broadcast data.
    """
    global active_alarms
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
                'new_log_alarms': [],
                'analysis': {
                    'trend': 'offline',
                    'spike_detected': False,
                    'z_score': 0.0
                }
            }
            socketio.emit('sensor_update', payload)
            socketio.sleep(2.0)
            continue
            
        current_time_ms = int(time.time() * 1000)
        current_time_sec = time.time()
        
        # Add to queues for analysis
        temp_queue.append(data['temperature'])
        hum_queue.append(data['humidity'])
        pres_queue.append(data['pressure'])
        time_queue.append(current_time_sec)
        
        # --- Perform Data Analysis (Requirement 5) ---
        t_spike, t_z = detect_spike(list(temp_queue))
        h_spike, h_z = detect_spike(list(hum_queue))
        p_spike, p_z = detect_spike(list(pres_queue))
        
        trend = detect_trend(list(temp_queue)) # Macro trend defaults to temp
        
        is_spike = t_spike or h_spike or p_spike
        z_val = max(t_z, h_z, p_z)
        # ---------------------------------------------
        
        # Check standard threshold warnings
        current_alarms = set()
        if data['temperature'] < thresholds['temp_min']: current_alarms.add("Temperature too low!")
        if data['temperature'] > thresholds['temp_max']: current_alarms.add("Temperature too high!")
        if data['humidity'] < thresholds['hum_min']: current_alarms.add("Humidity too low!")
        if data['humidity'] > thresholds['hum_max']: current_alarms.add("Humidity too high!")
        if data['pressure'] < thresholds['pres_min']: current_alarms.add("Pressure too low!")
        if data['pressure'] > thresholds['pres_max']: current_alarms.add("Pressure too high!")
        
        if t_spike: current_alarms.add("Sudden temperature spike/drop detected!")
        if h_spike: current_alarms.add("Sudden humidity spike/drop detected!")
        if p_spike: current_alarms.add("Sudden pressure spike/drop detected!")
        
        # Determine NEW edge-triggered alarms for SQLite Persistence
        new_alarms = current_alarms - active_alarms
        new_db_logs = []
        for msg in new_alarms:
            db.log_alarm(msg, "danger")
            # Create object to send to frontend immediately for append
            new_db_logs.append({'message': msg, 'severity': 'danger', 'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")})
            print(f"\n[DB ALARM LOGGED] - {msg}")
            
        active_alarms = current_alarms
        alarms_list = list(current_alarms)
            
        # Trigger hardware feedback & Console log
        if len(alarms_list) > 0:
            trigger_physical_alarm()
        else:
            clear_physical_alarm()
            
        # Send to VictoriaMetrics via Database Layer
        db.push_to_tsdb(data)
        
        # Construct payload for web interface
        payload = {
            'timestamp': current_time_ms,
            'data': data,
            'alarms': alarms_list,
            'new_log_alarms': new_db_logs,
            'analysis': {
                'trend': trend,
                'spike_detected': is_spike,
                'z_score': round(z_val, 2)
            }
        }
        
        socketio.emit('sensor_update', payload)
        
        socketio.sleep(1) # Eventlet cooperative yield and sleep
