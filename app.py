from flask import Flask, render_template
from flask_socketio import SocketIO
from sensor import background_sensor_loop, update_thresholds_internal, get_current_state
import db

app = Flask(__name__)
# Explicitly force Threading mode to bypass auto-discovery of left-over eventlet packages
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# Initialize SQLite Alarm Database
db.init_db()

# Start background loop immediately upon server startup
thread = socketio.start_background_task(background_sensor_loop, socketio)
@app.route('/')
def index():
    """
    Serve the main Web Interface SPA.
    """
    return render_template('index.html')

@socketio.on('connect')
def connect():
    """
    Handle client WebSocket connection.
    """
    print("Client connected via SocketIO.")
    socketio.emit('sync_state', get_current_state())

@socketio.on('update_thresholds')
def handle_threshold_updates(data):
    """
    RPC from the frontend to dynamically update warning thresholds
    without restarting the server.
    """
    print(f"Received new thresholds: {data}")
    # Update global thresholds in sensor module
    update_thresholds_internal(data)

if __name__ == '__main__':
    print("Starting Smart Environment Monitoring System...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
