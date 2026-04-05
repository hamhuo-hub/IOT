import numpy as np
from scipy import stats

def detect_spike(data_queue, threshold_z=3.0):
    """
    Detects sudden spikes or drops using the Z-Score method.
    data_queue: list of floats (e.g., recent 30 temperature readings)
    Returns True if the latest reading is an anomaly, False otherwise.
    """
    if len(data_queue) < 10:
        return False, 0.0 # Not enough data
    
    # Calculate Z-score of the latest data point based on the history
    history = np.array(data_queue[:-1])
    current_value = data_queue[-1]
    
    mean = np.mean(history)
    std = np.std(history)
    
    if std == 0:
        return False, 0.0
        
    z_score = abs((current_value - mean) / std)
    
    return bool(z_score > threshold_z), float(z_score)


def detect_trend(data_queue, window_size=5):
    """
    Detects consistent upward or downward trends using Simple Moving Average.
    Returns 'upward', 'downward', or 'stable'
    """
    if len(data_queue) < window_size * 3:
        return 'stable'
        
    # Calculate SMAs
    smas = []
    for i in range(len(data_queue) - window_size + 1):
        window = data_queue[i : i + window_size]
        smas.append(np.mean(window))
        
    # Check if the last M SMAs are strictly increasing or decreasing
    M = 3
    recent_smas = smas[-M:]
    
    is_increasing = all(recent_smas[i] < recent_smas[i+1] for i in range(len(recent_smas)-1))
    is_decreasing = all(recent_smas[i] > recent_smas[i+1] for i in range(len(recent_smas)-1))
    
    if is_increasing:
        return 'upward'
    if is_decreasing:
        return 'downward'
    return 'stable'



