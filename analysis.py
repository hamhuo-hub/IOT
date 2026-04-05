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
    
    return z_score > threshold_z, z_score


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


def predict_threshold_breach(time_queue, data_queue, threshold_value, trend):
    """
    Predicts when the threshold will be breached using OLS linear regression.
    time_queue: list of timestamps (relative or absolute)
    data_queue: list of values
    Returns: remaining_time_seconds as float, or None if no breach predicted.
    """
    if len(time_queue) < 10 or len(data_queue) < 10:
        return None
        
    # Perform OLS linear regression
    slope, intercept, r_value, p_value, std_err = stats.linregress(time_queue, data_queue)
    
    if slope == 0:
        return None
        
    # Predict time when y = threshold_value -> x = (y - intercept) / slope
    predicted_time = (threshold_value - intercept) / slope
    
    current_time = time_queue[-1]
    remaining_time = predicted_time - current_time
    
    # Only return valid future predictions depending on the trend
    if trend == 'upward' and slope > 0 and remaining_time > 0:
        return remaining_time
    elif trend == 'downward' and slope < 0 and remaining_time > 0:
        return remaining_time
        
    return None
