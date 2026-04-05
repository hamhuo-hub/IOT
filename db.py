import sqlite3
import os
import requests
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'alarms.db')
VM_WRITE_URL = "http://localhost:8428/write"

def push_to_tsdb(data):
    """
    Push data to VictoriaMetrics using InfluxDB line protocol.
    measurement,tag_key=tag_val field_key=field_val timestamp
    """
    line = f"environment,device=raspberrypi temperature={data['temperature']},humidity={data['humidity']},pressure={data['pressure']}"
    try:
        requests.post(VM_WRITE_URL, data=line, timeout=0.5)
    except requests.exceptions.RequestException:
        pass

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            message TEXT NOT NULL,
            severity TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def log_alarm(message, severity="danger"):
    """
    Log an alarm dynamically.
    Severity can be 'danger', 'warning', etc.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO alarms (message, severity, timestamp) 
        VALUES (?, ?, datetime('now', 'localtime'))
    ''', (message, severity))
    conn.commit()
    conn.close()

def get_recent_alarms(limit=50):
    """
    Fetch the most recent persisted alarms.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, message, severity FROM alarms 
        ORDER BY id DESC LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    
    alarms = []
    for row in rows:
        alarms.append({
            'timestamp': row[0],
            'message': row[1],
            'severity': row[2]
        })
    return alarms
