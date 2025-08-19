import dash
from dash import dcc, html, Input, Output, State, ctx
import plotly.graph_objs as go
import redis
import json
import time
import logging
import os
import threading

# Setup logging
logger = logging.getLogger("dashboard")

# Custom Redis Log Handler
class RedisLogHandler(logging.Handler):
    def __init__(self, redis_client, key_name="dashboard:logs", max_logs=100):
        super().__init__()
        self.redis_client = redis_client
        self.key_name = key_name
        self.max_logs = max_logs
    
    def emit(self, record):
        try:
            # Format the log record
            log_message = self.format(record)
            # Add timestamp
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.created))
            formatted_message = f"[{timestamp}] {log_message}"
            
            # Push to Redis list
            self.redis_client.lpush(self.key_name, formatted_message)
            # Trim list to keep only the latest logs
            self.redis_client.ltrim(self.key_name, 0, self.max_logs - 1)
        except Exception:
            # Don't let logging errors crash the app
            pass

r = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0)),
    decode_responses=True
)

# Add Redis handler to logger
redis_handler = RedisLogHandler(r, "dashboard:logs")
redis_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')
redis_handler.setFormatter(formatter)
logger.addHandler(redis_handler)

# --- Trustworthiness pub/sub listener state ---
_trust_state = {
    'value': None,          # True/False
    'timestamp': 0.0        # last message time.time()
}
_trust_history = []  # List of (timestamp, value) tuples for recent events
_trust_lock = threading.Lock()
_TRUST_TOPIC = 'maple'
_TRUST_DISPLAY_SECONDS = float(os.getenv('TRUST_DISPLAY_SECONDS', '5'))  # show for 3–5s
_TRUST_HISTORY_WINDOW = 60  # Keep trust events for 60 seconds

# --- Loading state management for buttons ---
_loading_states = {}  # Format: {f"{device}:{node}:{action}": timestamp}
_loading_lock = threading.Lock()
_LOADING_TIMEOUT = 30  # Maximum time to show loading state (30 seconds)


def _parse_trust_payload(data):
    """Accepts JSON or plain strings; returns True/False/None."""
    try:
        if isinstance(data, (bytes, bytearray)):
            data = data.decode('utf-8', errors='ignore')
    except Exception:
        pass

    try:
        obj = json.loads(data) if isinstance(data, str) else data
    except Exception:
        obj = data

    # Handle dict payloads like {"Str": true}
    if isinstance(obj, dict):
        # common keys variants
        for key in ("Str", "str", "trust", "Trust", "value", "ok","Bool"):
            if key in obj:
                val = obj[key]
                if isinstance(val, bool):
                    return val
                if isinstance(val, str):
                    v = val.strip().lower()
                    if v in ("true", "1", "yes", "ok"):
                        return True
                    if v in ("false", "0", "no"):
                        return False
                if isinstance(val, (int, float)):
                    return bool(val)
    # Handle simple strings 'true'/'false'
    if isinstance(obj, str):
        v = obj.strip().lower()
        if v in ("true", "1", "yes", "ok"):
            return True
        if v in ("false", "0", "no"):
            return False
    # Unsupported
    return None


def _set_loading_state(device, node, action):
    """Set a loading state for a specific device:node:action combination."""
    key = f"{device}:{node}:{action}"
    with _loading_lock:
        _loading_states[key] = time.time()
    logger.debug(f"Set loading state for {key}")


def _clear_loading_state(device, node, action):
    """Clear a loading state for a specific device:node:action combination."""
    key = f"{device}:{node}:{action}"
    with _loading_lock:
        _loading_states.pop(key, None)
    logger.debug(f"Cleared loading state for {key}")


def _is_loading(device, node, action):
    """Check if a specific device:node:action is in loading state."""
    key = f"{device}:{node}:{action}"
    with _loading_lock:
        if key not in _loading_states:
            return False
        # Check if loading state has timed out
        elapsed = time.time() - _loading_states[key]
        if elapsed > _LOADING_TIMEOUT:
            _loading_states.pop(key, None)
            logger.debug(f"Loading state timed out for {key}")
            return False
        return True


def _cleanup_loading_states():
    """Clean up expired loading states."""
    current_time = time.time()
    with _loading_lock:
        expired_keys = [
            key for key, timestamp in _loading_states.items()
            if current_time - timestamp > _LOADING_TIMEOUT
        ]
        for key in expired_keys:
            _loading_states.pop(key, None)
        if expired_keys:
            logger.debug(f"Cleaned up expired loading states: {expired_keys}")


def _trust_listener():
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    try:
        pubsub.subscribe(_TRUST_TOPIC)
        logger.info(f"Subscribed to trust topic '{_TRUST_TOPIC}'")
        for msg in pubsub.listen():
            try:
                data = msg.get('data')
                val = _parse_trust_payload(data)
                if val is not None:
                    current_time = time.time()
                    with _trust_lock:
                        _trust_state['value'] = bool(val)
                        _trust_state['timestamp'] = current_time
                        # Add to history
                        _trust_history.append((current_time, bool(val)))
                        # Clean old history entries
                        cutoff_time = current_time - _TRUST_HISTORY_WINDOW
                        _trust_history[:] = [(ts, v) for ts, v in _trust_history if ts > cutoff_time]
                    logger.debug(f"Trust update: {val} at {current_time}")
                else:
                    logger.debug(f"Ignored trust payload: {data}")
            except Exception as e:
                logger.warning(f"Error processing trust message: {e}")
    except Exception as e:
        logger.error(f"Trust listener error: {e}")
    finally:
        try:
            pubsub.close()
        except Exception:
            pass


def _start_trust_thread_once():
    # Prevent multiple listener threads in debug reloader
    if getattr(_start_trust_thread_once, '_started', False):
        return
    t = threading.Thread(target=_trust_listener, name='TrustListener', daemon=True)
    t.start()
    _start_trust_thread_once._started = True
    logger.info("Trust listener thread started")

app = dash.Dash(__name__)
app.title = "RoboSAPIENS Adaptive Platform Dashboard"

# Log application startup
logger.info("Dashboard application starting up")
logger.info("Redis log handler configured for dashboard:logs")

app.layout = html.Div([
    # Header Section
    html.Div([
        html.H1("RoboSAPIENS Adaptive Platform Dashboard", 
                style={
                    'textAlign': 'center', 
                    'color': '#2c3e50',
                    'marginBottom': '5px',
                    'fontWeight': '300',
                    'fontSize': '1.8rem'
                }),
        html.P("Real-time monitoring and control of distributed components", 
               style={
                   'textAlign': 'center', 
                   'color': '#7f8c8d',
                   'marginBottom': '10px',
                   'fontSize': '0.9rem'
               })
    ], style={
        'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'padding': '20px 20px',
        'marginBottom': '15px',
        'borderRadius': '0 0 10px 10px',
        'boxShadow': '0 2px 4px rgba(0, 0, 0, 0.1)'
    }),

    # Components Timeline Section (Full Width)
    html.Div([
        html.Div([
            html.H3("Components Timeline", 
                    style={
                        'color': '#2c3e50',
                        'marginBottom': '10px',
                        'fontWeight': '400',
                        'fontSize': '1.1rem'
                    }),
            # Trust popup (toast-like) anchored to this card
            html.Div(
                id='trust-popup',
                style={
                    'display': 'none',
                    'position': 'absolute',
                    'top': '8px',
                    'right': '8px',
                    'zIndex': 5,
                    'padding': '10px 14px',
                    'borderRadius': '8px',
                    'boxShadow': '0 4px 10px rgba(0,0,0,0.15)',
                    'color': 'white',
                    'fontWeight': '600',
                    'fontSize': '13px'
                }
            ),
            dcc.Graph(id="gantt-chart", style={'height': '370px'})
        ], style={
            'backgroundColor': '#ffffff',
            'padding': '15px',
            'borderRadius': '8px',
            'boxShadow': '0 2px 8px rgba(0, 0, 0, 0.08)',
            'border': '1px solid #e9ecef',
            'height': '420px',
            'position': 'relative'  # anchor for absolute popup
        })
    ], style={'marginBottom': '15px'}),

    # Device Status Section (Full Width)
    html.Div([
        html.Div([
            html.Div([
                html.H3("Device Status", 
                        style={
                            'color': '#2c3e50',
                            'marginBottom': '10px',
                            'fontWeight': '400',
                            'display': 'inline-block',
                            'fontSize': '1.1rem'
                        }),
                html.Button('+ Add Device', 
                           id='add-processor-btn', 
                           style={
                               'backgroundColor': '#3498db',
                               'color': 'white',
                               'border': 'none',
                               'padding': '6px 12px',
                               'borderRadius': '4px',
                               'cursor': 'pointer',
                               'fontSize': '12px',
                               'float': 'right',
                               'transition': 'all 0.3s ease'
                           })
            ], style={'marginBottom': '10px'}),
            html.Div(id='processor-cards', 
                    style={
                        'display': 'flex', 
                        'flexDirection': 'row',
                        'gap': '8px',
                        'maxHeight': '280px',
                        'overflowX': 'auto',
                        'overflowY': 'hidden',
                        'paddingBottom': '5px'
                    })
        ], style={
            'backgroundColor': '#ffffff',
            'padding': '15px',
            'borderRadius': '8px',
            'boxShadow': '0 2px 8px rgba(0, 0, 0, 0.08)',
            'border': '1px solid #e9ecef',
            'height': '330px'
        })
    ], style={'marginBottom': '15px'}),

    # Logs Section
    html.Div([
        html.Div([
            html.H3("System Logs", 
                    style={
                        'color': '#2c3e50',
                        'marginBottom': '10px',
                        'fontWeight': '400',
                        'display': 'inline-block',
                        'fontSize': '1.1rem'
                    }),
            html.Button('🔄 Refresh Log Sources', 
                       id='refresh-log-sources-btn',
                       style={
                           'backgroundColor': '#17a2b8',
                           'color': 'white',
                           'border': 'none',
                           'padding': '6px 12px',
                           'borderRadius': '4px',
                           'cursor': 'pointer',
                           'fontSize': '12px',
                           'float': 'right',
                           'transition': 'all 0.3s ease'
                       })
        ], style={'marginBottom': '8px'}),
        
        html.Div([
            html.Label("Select Log Sources:", style={
                'fontWeight': '600',
                'color': '#2c3e50',
                'marginBottom': '5px',
                'display': 'block',
                'fontSize': '12px'
            }),
            dcc.Checklist(
                id='log-sources-checklist',
                options=[],
                value=[],
                style={
                    'marginBottom': '8px'
                },
                inputStyle={
                    'marginRight': '6px'
                },
                labelStyle={
                    'display': 'inline-block',
                    'marginRight': '12px',
                    'marginBottom': '3px',
                    'color': '#34495e',
                    'fontSize': '12px'
                }
            )
        ], style={
            'backgroundColor': '#f8f9fa',
            'padding': '8px',
            'borderRadius': '4px',
            'border': '1px solid #dee2e6',
            'marginBottom': '8px'
        }),
        
        html.Pre(id='live-log', 
                style={
                    'height': '150px', 
                    'overflowY': 'auto', 
                    'backgroundColor': '#f8f9fa',
                    'border': '1px solid #dee2e6',
                    'borderRadius': '4px',
                    'padding': '8px',
                    'fontFamily': 'Monaco, Consolas, "Courier New", monospace',
                    'fontSize': '11px',
                    'lineHeight': '1.3',
                    'margin': '0'
                })
    ], style={
        'backgroundColor': '#ffffff',
        'padding': '15px',
        'borderRadius': '8px',
        'boxShadow': '0 2px 8px rgba(0, 0, 0, 0.08)',
        'border': '1px solid #e9ecef',
        'height': '300px'
    }),

    # Intervals
    dcc.Interval(id='interval-gantt', interval=1000, n_intervals=0),
    dcc.Interval(id='interval-redis', interval=2000, n_intervals=0),
    dcc.Interval(id='interval-log', interval=1000, n_intervals=0),
    dcc.Interval(id='interval-log-sources', interval=5000, n_intervals=0),  # Check for new sources every 5 seconds
    dcc.Interval(id='interval-trust', interval=1000, n_intervals=0)  # drive trust popup
], style={
    'backgroundColor': '#f5f6fa',
    'minHeight': '100vh',
    'maxHeight': '100vh',
    'padding': '10px',
    'margin': '0',
    'fontFamily': '"Segoe UI", Tahoma, Geneva, Verdana, sans-serif',
    'overflow': 'hidden'
})

@app.callback(
    Output("gantt-chart", "figure"),
    Input("interval-gantt", "n_intervals")
)
def update_gantt(_):
    fig = go.Figure()
    phase_colors = {
        "Monitor": "#3498db",      # Blue
        "Analysis": "#f39c12",     # Orange  
        "Plan": "#9b59b6",         # Purple
        "Legitimate": "#e67e22",   # Dark Orange
        "Execute": "#34495e",      # Dark Gray
        "Knowledge": "#95a5a6",    # Light Gray
        "Trustworthiness": "#16a085"  # Teal (keeping green/red for trust states)
    }
    
    device_names = r.lrange('devices:list', 0, -1)
    now = time.time()
    time_window = 15  # Show last 60 seconds to keep history

    # Track y labels so we can force Trustworthiness at the top
    y_labels = set()
    
    # Add trustworthiness spikes/steps for each event in history
    with _trust_lock:
        trust_history = _trust_history.copy()  # Safe copy
    
    trust_label = "🛡️ Trustworthiness"
    if trust_history:
        y_labels.add(trust_label)
        
        for event_time, trust_val in trust_history:
            elapsed = now - event_time
            if 0 <= elapsed <= time_window:
                # Create a spike/step for each event
                spike_start = -elapsed
                spike_width = 0.5  # Short spike duration for visibility
                
                # Adjust if spike extends beyond current time
                if spike_start + spike_width > 0:
                    spike_width = -spike_start
                
                if spike_width > 0:
                    trust_color = '#2ecc71' if trust_val else '#e74c3c'
                    
                    fig.add_trace(go.Bar(
                        name=trust_label,
                        x=[spike_width],
                        y=[trust_label],
                        base=spike_start,
                        orientation="h",
                        marker=dict(
                            color=trust_color,
                            opacity=0.9,
                            line=dict(color='rgba(0,0,0,0.5)', width=2)
                        ),
                        hovertemplate=(
                            f"<b>Trustworthiness Event</b><br>"
                            f"Status: {'✅ TRUSTED' if trust_val else '❌ NOT TRUSTED'}<br>"
                            f"Time: {elapsed:.1f}s ago<br>"
                            f"Event at: {time.strftime('%H:%M:%S', time.localtime(event_time))}<br>"
                            "<extra></extra>"
                        ),
                        showlegend=False
                    ))
    
    for device in device_names:
        nodes = r.lrange(f"devices:{device}:nodes", 0, -1)
        for node in nodes:
            # Get execution history for this component
            history_key = f"devices:{device}:{node}:execution_history"
            execution_history = r.lrange(history_key, 0, -1)  # Get all history entries
            
            # Also check for current execution data (single execution)
            execution_time_key = f"{node}:execution_time"
            start_execution_key = f"{node}:start_execution"
            device_execution_time_key = f"devices:{device}:{node}:execution_time"
            device_start_execution_key = f"devices:{device}:{node}:start_execution"
            
            execution_time = r.get(execution_time_key) or r.get(device_execution_time_key)
            start_execution = r.get(start_execution_key) or r.get(device_start_execution_key)
            
            # Process execution history if available
            if execution_history:
                for history_entry in execution_history:
                    try:
                        # Parse history entry (format: "start_time,duration,status")
                        parts = history_entry.split(',')
                        if len(parts) >= 2:
                            start_exec = float(parts[0])
                            exec_time = float(parts[1])
                            status = parts[2] if len(parts) > 2 else "completed"
                            
                            # Only show executions with "running" status
                            if status != "running":
                                continue
                            
                            # Calculate relative time positions
                            start_relative = now - start_exec
                            
                            # Show all executions within time window
                            if start_relative <= time_window and start_relative >= 0:
                                bar_start = -start_relative
                                bar_width = exec_time
                                
                                # Adjust bar width if it extends beyond current time
                                if bar_start + bar_width > 0:
                                    bar_width = -bar_start
                                
                                if bar_width > 0:
                                    # Color based on node type and status
                                    node_color = phase_colors.get(node, "#27ae60")  # Green for running status
                                    
                                    y_label = f"{device}:{node}"
                                    y_labels.add(y_label)
                                    fig.add_trace(go.Bar(
                                        name=y_label,
                                        x=[bar_width],
                                        y=[y_label],
                                        base=bar_start,
                                        orientation="h",
                                        marker=dict(
                                            color=node_color,
                                            line=dict(color='rgba(0,0,0,0.3)', width=1)
                                        ),
                                        hovertemplate=(
                                            f"<b>{device}:{node}</b><br>"
                                            f"Started: {start_relative:.1f}s ago<br>"
                                            f"Duration: {exec_time:.1f}s<br>"
                                            f"Status: {status}<br>"
                                            "<extra></extra>"
                                        ),
                                        showlegend=False
                                    ))
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Error parsing history entry {history_entry}: {e}")
                        continue
            
            # ALWAYS check for current/new execution data (even if history exists)
            if execution_time and start_execution:
                try:
                    start_exec = float(start_execution)
                    exec_time = float(execution_time)
                    
                    # Check if this execution is already in history to avoid duplicates
                    is_duplicate = False
                    if execution_history:
                        for history_entry in execution_history:
                            try:
                                parts = history_entry.split(',')
                                if len(parts) >= 2:
                                    hist_start = float(parts[0])
                                    hist_duration = float(parts[1])
                                    # Consider it duplicate if start time and duration match closely
                                    if abs(hist_start - start_exec) < 0.1 and abs(hist_duration - exec_time) < 0.1:
                                        is_duplicate = True
                                        break
                            except (ValueError, IndexError):
                                continue
                    
                    # Only process if not a duplicate
                    if not is_duplicate:
                        # Get component status for color coding - only show if running
                        status = r.get(f"devices:{device}:{node}:status")
                        
                        # Only show executions with "running" status
                        if status != "running":
                            continue
                        
                        # Calculate relative time positions
                        start_relative = now - start_exec
                        
                        # Show if within time window
                        if start_relative <= time_window and start_relative >= 0:
                            bar_start = -start_relative
                            bar_width = exec_time
                            
                            # Adjust bar width if it extends beyond current time
                            if bar_start + bar_width > 0:
                                bar_width = -bar_start
                            
                            if bar_width > 0:
                                # Use green color for running nodes
                                node_color = phase_colors.get(node, "#27ae60")
                                
                                y_label = f"{device}:{node}"
                                y_labels.add(y_label)
                                fig.add_trace(go.Bar(
                                    name=y_label,
                                    x=[bar_width],
                                    y=[y_label],
                                    base=bar_start,
                                    orientation="h",
                                    marker=dict(
                                        color=node_color,
                                        line=dict(color='rgba(0,0,0,0.3)', width=1)
                                    ),
                                    hovertemplate=(
                                        f"<b>{device}:{node}</b><br>"
                                        f"Started: {start_relative:.1f}s ago<br>"
                                        f"Duration: {exec_time:.1f}s<br>"
                                        f"Status: {status or 'current'}<br>"
                                        "<extra></extra>"
                                    ),
                                    showlegend=False
                                ))
                                
                                logger.debug(f"Added NEW bar for {device}:{node} - start: {bar_start:.2f}, width: {bar_width:.2f}")
                            
                            # Store this NEW execution in history for future reference
                            history_entry = f"{start_exec},{exec_time},{status or 'running'}"
                            r.lpush(f"devices:{device}:{node}:execution_history", history_entry)
                            # Keep only last 50 history entries per component
                            r.ltrim(f"devices:{device}:{node}:execution_history", 0, 49)
                            logger.debug(f"Stored new execution in history: {history_entry}")
                                
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error processing {device}:{node} execution data: {e}")
                    continue

    # Add invisible traces for legend (color guide)
    legend_items = [
        ("Monitor", "#3498db"),
        ("Analysis", "#f39c12"),
        ("Plan", "#9b59b6"),
        ("Legitimate", "#e67e22"),
        ("Execute", "#34495e"),
        ("Knowledge", "#95a5a6"),
        ("Trustworthiness", "#16a085"),
        ("Trust OK", "#2ecc71"),
        ("Trust Alert", "#e74c3c")
    ]
    
    for name, color in legend_items:
        fig.add_trace(go.Scatter(
            x=[None],
            y=[None],
            mode='markers',
            marker=dict(
                size=10,
                color=color,
                symbol='square'
            ),
            name=name,
            showlegend=True,
            hoverinfo='skip'
        ))

    # Sort y-axis labels to put trustworthiness at the top
    sorted_labels = sorted(y_labels)
    trust_label = "🛡️ Trustworthiness"
    if trust_label in sorted_labels:
        # Remove from sorted list and put at beginning
        sorted_labels.remove(trust_label)
        sorted_labels.insert(0, trust_label)

    # Update layout with proper time axis (restore category ordering without trust bar)
    fig.update_layout(
        title={
            'text': f"Component Execution History (Last {time_window} Seconds)",
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 14, 'color': '#2c3e50'}
        },
        xaxis={
            'title': "Time (seconds ago ← | → now)",
            'range': [-time_window, 0],
            'tickmode': 'linear',
            'dtick': 10,
            'showgrid': True,
            'gridcolor': 'rgba(0,0,0,0.1)',
            'zeroline': True,
            'zerolinecolor': 'rgba(231, 76, 60, 0.8)',
            'zerolinewidth': 2
        },
        yaxis={
            'title': "Components",
            'showgrid': True,
            'gridcolor': 'rgba(0,0,0,0.1)',
            'categoryorder': 'array',
            'categoryarray': sorted_labels
        },
        barmode="overlay",
        template="plotly_white",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255, 255, 255, 0.8)",
            bordercolor="rgba(0, 0, 0, 0.2)",
            borderwidth=1,
            font=dict(size=10)
        ),
        plot_bgcolor="rgba(248, 249, 250, 1)",
        paper_bgcolor="rgba(255, 255, 255, 1)",
        font={'family': '"Segoe UI", Tahoma, Geneva, Verdana, sans-serif'},
        margin={'l': 120, 'r': 20, 't': 100, 'b': 60},
        height=350
    )
    
    fig.add_vline(
        x=0,
        line_dash="dash",
        line_color="rgba(231, 76, 60, 0.8)",
        annotation_text="Now",
        annotation_position="top"
    )
    return fig

@app.callback(
    Output("processor-cards", "children"),
    Input("interval-redis", "n_intervals")
)
def update_processors(_):
    import time
    # Clean up expired loading states
    _cleanup_loading_states()
    
    device_names = r.lrange('devices:list', 0, -1)  # List of device names
    logger.debug(f"Devices in Redis: {device_names}")
    cards = []
    for device in device_names:
        heartbeat = r.get(f"devices:{device}:heartbeat")
        logger.debug(f"{device} heartbeat: {heartbeat}")
        device_is_offline = False
        try:
            if heartbeat:
                now = time.time()
                heartbeat_val = float(heartbeat)
                logger.debug(f"{device} now: {now}, heartbeat_val: {heartbeat_val}, diff: {now - heartbeat_val}")
                if now - heartbeat_val < 10:
                    online_status = "🟢 Online"
                    online_color = "green"
                else:
                    online_status = "🔴 Offline"
                    online_color = "red"
                    device_is_offline = True
            else:
                online_status = "🔴 Offline (no heartbeat)"
                online_color = "red"
                device_is_offline = True
        except Exception as e:
            logger.warning(f"Exception for {device} heartbeat: {e}")
            online_status = "Unknown"
            online_color = "gray"
            device_is_offline = True

        # Get components for this device
        nodes = r.lrange(f"devices:{device}:nodes", 0, -1)
        logger.debug(f"{device} nodes: {nodes}")
        
        # If device is offline, set all its nodes to stopped
        if device_is_offline and nodes:
            logger.info(f"Device {device} is offline, setting all nodes to stopped")
            for node in nodes:
                r.set(f"devices:{device}:{node}:status", "stopped")
                logger.debug(f"Set {device}:{node} status to stopped due to device offline")
        
        running_count = 0
        comp_list = []
        for node in nodes:
            status_key = f"devices:{device}:{node}:status"
            status = r.get(status_key)
            logger.debug(f"{device} component {node} status: {status}")
            
            # Check loading states
            is_pausing = _is_loading(device, node, 'pause')
            is_running_action = _is_loading(device, node, 'run')
            
            # Clear loading state if node has reached expected state
            if is_pausing and status in ["stopped", "exited", "paused"]:
                _clear_loading_state(device, node, 'pause')
                is_pausing = False
            if is_running_action and status == "running":
                _clear_loading_state(device, node, 'run')
                is_running_action = False
            
            if status == "running":
                status_text = "🟢 Running"
                status_color = "green"
                running_count += 1
            elif status == "exited":
                status_text = "⏸️ Stopped"
                status_color = "orange"
            elif status == "paused":
                status_text = "⏸️ Paused"
                status_color = "orange"
            elif status == "stopped":
                status_text = "⏸️ Stopped"
                status_color = "orange"
            else:
                status_text = "⚪ Removed"
                status_color = "gray"
                
            # Prepare button styles based on loading states
            run_button_style = {
                'backgroundColor': '#95a5a6' if is_running_action else '#27ae60',
                'color': 'white',
                'border': 'none',
                'borderRadius': '4px',
                'padding': '4px 8px',
                'marginRight': '4px',
                'cursor': 'wait' if is_running_action else 'pointer',
                'fontSize': '12px',
                'opacity': '0.7' if is_running_action else '1'
            }
            
            pause_button_style = {
                'backgroundColor': '#95a5a6' if is_pausing else '#f39c12',
                'color': 'white',
                'border': 'none',
                'borderRadius': '4px',
                'padding': '4px 8px',
                'marginRight': '4px',
                'cursor': 'wait' if is_pausing else 'pointer',
                'fontSize': '12px',
                'opacity': '0.7' if is_pausing else '1'
            }
            
            # Button content changes based on loading state
            run_button_content = '⏳' if is_running_action else '▶️'
            pause_button_content = '⏳' if is_pausing else '⏸️'
            
            comp_list.append(html.Div([
                html.Div([
                    # Left side: Node name and status
                    html.Div([
                        html.Span(node, style={
                            'fontWeight': '600', 
                            'color': '#2c3e50',
                            'fontSize': '14px',
                            'display': 'block',
                            'wordBreak': 'break-word',
                            'lineHeight': '1.2',
                            'marginBottom': '2px'
                        }),
                        html.Span(status_text, style={
                            'color': status_color, 
                            'fontWeight': '500',
                            'fontSize': '12px',
                            'display': 'block'
                        })
                    ], style={
                        'flex': '1',
                        'minWidth': '0',  # Allow shrinking
                        'paddingRight': '8px'
                    }),
                    
                    # Right side: Action buttons
                    html.Div([
                        html.Button(run_button_content, 
                                   id={'type': 'run-comp-btn', 'proc': device, 'comp': node},
                                   disabled=is_running_action,
                                   style=run_button_style),
                        html.Button(pause_button_content, 
                                   id={'type': 'pause-comp-btn', 'proc': device, 'comp': node},
                                   disabled=is_pausing,
                                   style=pause_button_style),
                        html.Button('❌', 
                                   id={'type': 'del-comp-btn', 'proc': device, 'comp': node}, 
                                   disabled=True,
                                   style={
                                       'backgroundColor': '#bdc3c7',
                                       'color': 'white',
                                       'border': 'none',
                                       'borderRadius': '4px',
                                       'padding': '4px 8px',
                                       'cursor': 'not-allowed',
                                       'fontSize': '12px'
                                   })
                    ], style={
                        'display': 'flex',
                        'alignItems': 'center',
                        'flexShrink': '0'  # Don't shrink buttons
                    })
                ], style={
                    'display': 'flex', 
                    'alignItems': 'center', 
                    'justifyContent': 'space-between',
                    'width': '100%',
                    'marginBottom': '8px'
                }),
            ], style={
                'backgroundColor': '#f8f9fa',
                'border': '1px solid #e9ecef',
                'borderRadius': '6px',
                'padding': '8px',
                'marginBottom': '6px',
                'transition': 'all 0.2s ease'
            }))

        cards.append(html.Div([
            # Device Header
            html.Div([
                html.H4(device, style={
                    'margin': '0',
                    'color': '#2c3e50',
                    'fontSize': '18px',
                    'fontWeight': '600'
                }),
                html.Button('❌', 
                           id={'type': 'del-proc-btn', 'proc': device}, 
                           disabled=True,
                           style={
                               'backgroundColor': '#bdc3c7',
                               'color': 'white',
                               'border': 'none',
                               'borderRadius': '4px',
                               'padding': '4px 8px',
                               'cursor': 'not-allowed',
                               'fontSize': '12px'
                           })
            ], style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'alignItems': 'center',
                'marginBottom': '10px',
                'paddingBottom': '8px',
                'borderBottom': '2px solid #ecf0f1'
            }),
            
            # Device Status
            html.Div([
                html.Div([
                    # Left side: Device status
                    html.Div([
                        html.Span("Status: ", style={'color': '#7f8c8d', 'fontSize': '14px'}),
                        html.Span(online_status, style={
                            'color': online_color, 
                            'fontWeight': '600',
                            'fontSize': '14px'
                        })
                    ], style={'display': 'flex', 'alignItems': 'center'}),
                    
                    # Right side: Active count
                    html.Div([
                        html.Span("Active: ", style={'color': '#7f8c8d', 'fontSize': '14px', 'marginRight': '4px'}),
                        html.Span(f"{running_count}/{len(nodes)}", style={
                            'fontWeight': '600',
                            'color': '#2c3e50',
                            'fontSize': '14px'
                        })
                    ], style={'display': 'flex', 'alignItems': 'center'})
                ], style={
                    'display': 'flex', 
                    'justifyContent': 'space-between', 
                    'alignItems': 'center',
                    'marginBottom': '6px'
                }),
            ], style={'marginBottom': '12px'}),
            
            # Components List
            html.Div([
                html.H5("Components", style={
                    'margin': '0 0 10px 0',
                    'color': '#34495e',
                    'fontSize': '14px',
                    'fontWeight': '600'
                }),
                html.Div(comp_list, style={
                    'maxHeight': '220px',       # Increased height to show more nodes
                    'overflowY': 'auto',
                    'paddingRight': '5px'
                })
            ]),
            
            # # Add Component Button
            # html.Button('+ Add Component', 
            #            id={'type': 'add-comp-btn', 'proc': device},
            #            style={
            #                'width': '100%',
            #                'backgroundColor': '#3498db',
            #                'color': 'white',
            #                'border': 'none',
            #                'borderRadius': '6px',
            #                'padding': '10px',
            #                'marginTop': '15px',
            #                'cursor': 'pointer',
            #                'fontSize': '14px',
            #                'fontWeight': '500',
            #                'transition': 'all 0.3s ease'
            #            })
        ], style={
            'backgroundColor': '#ffffff',
            'border': '1px solid #e9ecef',
            'borderRadius': '12px',
            'padding': '15px',
            'boxShadow': '0 2px 8px rgba(0, 0, 0, 0.1)',
            'transition': 'transform 0.2s ease, box-shadow 0.2s ease',
            'minHeight': '320px',       # Changed to minHeight to allow expansion
            'minWidth': '320px',        # Increased minimum width for longer names
            'maxWidth': '420px',        # Increased max width to accommodate longer names
            'flex': '0 0 auto',
            'display': 'flex',
            'flexDirection': 'column'
        }))
    return cards

@app.callback(
    Output('interval-redis', 'n_intervals'),
    Input('add-processor-btn', 'n_clicks'),
    Input({'type': 'del-proc-btn', 'proc': dash.ALL}, 'n_clicks'),
    Input({'type': 'add-comp-btn', 'proc': dash.ALL}, 'n_clicks'),
    Input({'type': 'del-comp-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'n_clicks'),
    Input({'type': 'run-comp-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'n_clicks'),
    Input({'type': 'pause-comp-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'n_clicks'),
    State({'type': 'del-proc-btn', 'proc': dash.ALL}, 'id'),
    State({'type': 'add-comp-btn', 'proc': dash.ALL}, 'id'),
    State({'type': 'del-comp-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'id'),
    State({'type': 'run-comp-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'id'),
    State({'type': 'pause-comp-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'id'),
    prevent_initial_call=True
)
def handle_actions(add_proc_clicks, del_proc_clicks, add_comp_clicks, del_comp_clicks, run_clicks, pause_clicks,
                   del_proc_ids, add_comp_ids, del_comp_ids, run_ids, pause_ids):
    logger.debug(f"handle_actions triggered_id: {ctx.triggered_id}")
    # All actions are deactivated for now
    if ctx.triggered_id == 'add-processor-btn':
        device_names = r.lrange('devices', 0, -1)
        logger.debug(f"Devices before add: {device_names}")
        new_device = f"Device{len(device_names) + 1}"
        logger.debug(f"Added device: {new_device}")
    elif isinstance(ctx.triggered_id, dict):
        tid = ctx.triggered_id
        logger.debug(f"handle_actions tid: {tid}")
        if tid['type'] == 'del-proc-btn':
            logger.debug(f"Delete device action is deactivated.")
            pass
        elif tid['type'] == 'add-comp-btn':
            device = tid['proc']
            comps = r.lrange(f'{device}:components', 0, -1)
            logger.debug(f"Adding component to {device}, current comps: {comps}")
            comp_name = f"Component{len(comps) + 1}"
            # r.rpush(f'{device}:components', comp_name)
            logger.debug(f"Added component: {comp_name}")
        elif tid['type'] == 'del-comp-btn':
            logger.debug(f"Delete component action is deactivated.")
            pass
        elif tid['type'] == 'run-comp-btn':
            device, comp = tid['proc'], tid['comp']
            # Set loading state for run action
            _set_loading_state(device, comp, 'run')
            msg = {"command": "up", "app": comp}
            r.publish(f"{device}-orchestrator", json.dumps(msg))
            logger.debug(f"Setting {device}:{comp} to running")

        elif tid['type'] == 'pause-comp-btn':
            device, comp = tid['proc'], tid['comp']
            # Set loading state for pause action
            _set_loading_state(device, comp, 'pause')
            msg = {"command": "down", "app": comp}
            r.publish(f"{device}-orchestrator", json.dumps(msg))
            logger.debug(f"Setting {device}:{comp} to paused")

        elif tid['type'] == 'del-proc-btn':
            device, comp = tid['proc'], tid['comp']
            msg = {"command": "remove", "app": comp}
            r.set(f'devices:{device}:{comp}:status', 'removed')
            r.publish(f"{device}-orchestrator", json.dumps(msg))
            logger.debug(f"Deleted device: {device}")

            # elif tid['type'] == 'del-comp-btn':
            #     device, comp = tid['proc'], tid['comp']
            #     # Remove component from device's nodes list
            #     r.lrem(f"devices:{device}:nodes", 0, comp)
            #     # Clean up component status
            #     r.delete(f"devices:{device}:{comp}:status")
            #     logger.debug(f"Deleted component {comp} from device {device}")

    return dash.no_update

@app.callback(
    Output('log-sources-checklist', 'options'),
    Output('log-sources-checklist', 'value'),
    [Input('refresh-log-sources-btn', 'n_clicks')],
    [State('log-sources-checklist', 'value')],
    prevent_initial_call=False
)
def update_log_sources(refresh_clicks, current_values):
    """Update the available log sources by scanning Redis for *:logs keys"""
    try:
        # Get all keys matching the pattern *:logs
        all_keys = r.keys('*')
        log_keys = []
        
        for key in all_keys:
            if key.endswith(':logs'):
                log_keys.append(key)
        
        # Also include the general 'log' key if it exists
        if r.exists('log'):
            log_keys.append('log')
        
        # Sort the keys for consistent ordering
        log_keys = sorted(set(log_keys))
            
        # Create options for checklist
        options = [{'label': key, 'value': key} for key in log_keys]
        
        # Preserve current user selections, or select all if first load
        if current_values is None:
            # First load - select all available sources
            values = log_keys if log_keys else []
        else:
            # Keep only the currently selected sources that still exist
            values = [source for source in current_values if source in log_keys]
            # If no valid selections remain and we have sources, don't auto-select
            if not values and log_keys:
                values = []
        
        logger.info(f"Found log sources: {log_keys}, Selected: {values}")
        return options, values
        
    except Exception as e:
        logger.error(f"Error updating log sources: {e}")
        # Return some default options for testing
        default_options = [{'label': 'log', 'value': 'log'}]
        return default_options, current_values if current_values else []

@app.callback(
    Output('log-sources-checklist', 'options', allow_duplicate=True),
    [Input('interval-log-sources', 'n_intervals')],
    [State('log-sources-checklist', 'options'),
     State('log-sources-checklist', 'value')],
    prevent_initial_call=True
)
def auto_refresh_log_sources(_, current_options, current_values):
    """Automatically refresh log sources options without changing user selections"""
    try:
        # Get all keys matching the pattern *:logs
        all_keys = r.keys('*')
        log_keys = []
        
        for key in all_keys:
            if key.endswith(':logs'):
                log_keys.append(key)
        
        # Also include the general 'log' key if it exists
        if r.exists('log'):
            log_keys.append('log')
        
        # Sort the keys for consistent ordering
        log_keys = sorted(set(log_keys))
        
        # Get current options values
        current_option_values = [opt['value'] for opt in current_options] if current_options else []
        
        # Only update if there are new sources
        if set(log_keys) != set(current_option_values):
            options = [{'label': key, 'value': key} for key in log_keys]
            logger.info(f"Auto-refreshed log sources: {log_keys}")
            return options
        else:
            # No change needed
            return dash.no_update
            
    except Exception as e:
        logger.error(f"Error auto-refreshing log sources: {e}")
        return dash.no_update

@app.callback(
    Output('live-log', 'children'),
    [Input('interval-log', 'n_intervals'),
     Input('log-sources-checklist', 'value')],
    prevent_initial_call=False
)
def update_log(_, selected_sources):
    """Update log display based on selected sources"""
    try:
        # If no sources selected or None, try to show default log
        if not selected_sources:
            if r.exists('log'):
                logs = r.lrange('log', -10, -1)
                if logs:
                    return '\n'.join(logs)
            return "No log sources selected. Please select log sources from the checklist above."
        
        all_logs = []
        
        for source in selected_sources:
            try:
                # Get logs from each source (latest 10 entries per source)
                logs = r.lrange(source, -10, -1)
                if logs:
                    # Add source prefix to each log entry
                    source_name = source.replace(':logs', '') if source.endswith(':logs') else source
                    for log_entry in logs:
                        formatted_log = f"[{source_name}] {log_entry}"
                        all_logs.append(formatted_log)
                        
            except Exception as e:
                logger.warning(f"Error reading logs from {source}: {e}")
                all_logs.append(f"[ERROR] Could not read from {source}: {str(e)}")
                continue
        
        if all_logs:
            # Get the latest 10 entries from all combined logs
            latest_logs = all_logs[-10:] if len(all_logs) > 10 else all_logs
            return '\n'.join(latest_logs)
        else:
            return "No logs found in selected sources."
            
    except Exception as e:
        logger.error(f"Error updating logs: {e}")
        return f"Error loading logs: {str(e)}"

# New: Trust popup updater
@app.callback(
    Output('trust-popup', 'style'),
    Output('trust-popup', 'children'),
    Input('interval-trust', 'n_intervals'),
    prevent_initial_call=False
)
def update_trust_popup(_):
    base_style = {
        'position': 'absolute',
        'top': '8px',
        'right': '8px',
        'zIndex': 5,
        'padding': '10px 14px',
        'borderRadius': '8px',
        'boxShadow': '0 4px 10px rgba(0,0,0,0.15)',
        'color': 'white',
        'fontWeight': '600',
        'fontSize': '13px'
    }
    now = time.time()
    with _trust_lock:
        trust_val = _trust_state.get('value')
        trust_ts = _trust_state.get('timestamp', 0.0)
    if trust_ts:
        elapsed = now - trust_ts
        if 0 <= elapsed <= _TRUST_DISPLAY_SECONDS:
            color = '#2ecc71' if trust_val else '#e74c3c'
            style = dict(base_style, **{'display': 'block', 'backgroundColor': color})
            status_txt = '✅ Trust OK' if trust_val else '❌ Trust ALERT'
            return style, f"{status_txt} • updated {elapsed:.1f}s ago"
    # Hidden when stale/no data
    return {'display': 'none'}, ""

if __name__ == '__main__':
    # Start trust listener only in the actual reloader process (avoids double threads)
    if os.getenv('WERKZEUG_RUN_MAIN') == 'true' or not bool(os.getenv('FLASK_DEBUG')):
        _start_trust_thread_once()
    # Get configuration from environment variables
    dash_host = os.getenv('DASH_HOST', '0.0.0.0')
    dash_port = int(os.getenv('DASH_PORT', '8050'))
    logger.info("Starting Dash server in debug mode")
    app.run(host=dash_host, port=dash_port, debug=True)

