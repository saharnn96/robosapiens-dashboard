import dash
from dash import dcc, html, Input, Output, State, ctx
import plotly.graph_objs as go
import redis
import json
import time
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("dashboard")

r = redis.Redis(host='localhost', port=6379, decode_responses=True, db=6)

app = dash.Dash(__name__)
app.title = "RoboSAPIENS Adaptive Platform Dashboard"

app.layout = html.Div([
    # Header Section
    html.Div([
        html.H1("RoboSAPIENS Adaptive Platform Dashboard", 
                style={
                    'textAlign': 'center', 
                    'color': '#2c3e50',
                    'marginBottom': '10px',
                    'fontWeight': '300',
                    'fontSize': '2.5rem'
                }),
        html.P("Real-time monitoring and control of distributed components", 
               style={
                   'textAlign': 'center', 
                   'color': '#7f8c8d',
                   'marginBottom': '30px',
                   'fontSize': '1.1rem'
               })
    ], style={
        'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'padding': '40px 20px',
        'marginBottom': '30px',
        'borderRadius': '0 0 15px 15px',
        'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)'
    }),

    # Gantt Chart Section
    html.Div([
        html.H3("Components Activation Timeline", 
                style={
                    'color': '#2c3e50',
                    'marginBottom': '20px',
                    'fontWeight': '400'
                }),
        dcc.Graph(id="gantt-chart", style={'height': '400px'})
    ], style={
        'backgroundColor': '#ffffff',
        'padding': '25px',
        'marginBottom': '30px',
        'borderRadius': '10px',
        'boxShadow': '0 2px 10px rgba(0, 0, 0, 0.08)',
        'border': '1px solid #e9ecef'
    }),

    # Device Cards Section
    html.Div([
        html.Div([
            html.H3("Device Status", 
                    style={
                        'color': '#2c3e50',
                        'marginBottom': '20px',
                        'fontWeight': '400',
                        'display': 'inline-block'
                    }),
            html.Button('+ Add Device', 
                       id='add-processor-btn', 
                       style={
                           'backgroundColor': '#3498db',
                           'color': 'white',
                           'border': 'none',
                           'padding': '8px 16px',
                           'borderRadius': '5px',
                           'cursor': 'pointer',
                           'fontSize': '14px',
                           'float': 'right',
                           'transition': 'all 0.3s ease'
                       })
        ], style={'marginBottom': '20px'}),
        html.Div(id='processor-cards', 
                style={
                    'display': 'grid', 
                    'gridTemplateColumns': 'repeat(auto-fill, minmax(280px, 1fr))', 
                    'gap': '20px'
                })
    ], style={
        'backgroundColor': '#ffffff',
        'padding': '25px',
        'marginBottom': '30px',
        'borderRadius': '10px',
        'boxShadow': '0 2px 10px rgba(0, 0, 0, 0.08)',
        'border': '1px solid #e9ecef'
    }),

    # Logs Section
    html.Div([
        html.H3("System Logs", 
                style={
                    'color': '#2c3e50',
                    'marginBottom': '20px',
                    'fontWeight': '400'
                }),
        html.Pre(id='live-log', 
                style={
                    'height': '250px', 
                    'overflowY': 'auto', 
                    'backgroundColor': '#f8f9fa',
                    'border': '1px solid #dee2e6',
                    'borderRadius': '5px',
                    'padding': '15px',
                    'fontFamily': 'Monaco, Consolas, "Courier New", monospace',
                    'fontSize': '12px',
                    'lineHeight': '1.4'
                })
    ], style={
        'backgroundColor': '#ffffff',
        'padding': '25px',
        'borderRadius': '10px',
        'boxShadow': '0 2px 10px rgba(0, 0, 0, 0.08)',
        'border': '1px solid #e9ecef'
    }),

    # Intervals
    dcc.Interval(id='interval-gantt', interval=1000, n_intervals=0),
    dcc.Interval(id='interval-redis', interval=2000, n_intervals=0),
    dcc.Interval(id='interval-log', interval=1000, n_intervals=0)
], style={
    'backgroundColor': '#f5f6fa',
    'minHeight': '100vh',
    'padding': '0',
    'margin': '0',
    'fontFamily': '"Segoe UI", Tahoma, Geneva, Verdana, sans-serif'
})

@app.callback(
    Output("gantt-chart", "figure"),
    Input("interval-gantt", "n_intervals")
)
def update_gantt(_):
    fig = go.Figure()
    phase_colors = {
        "Monitor": "#1f77b4",
        "Analysis": "#2ca02c",
        "Plan": "#ff7f0e",
        "Execute": "#d62728",
        "Legitimate": "#9467bd",
        "Trustworthiness": "#8c564b"
    }
    device_names = r.lrange('devices', 0, -1)
    now = time.time()
    for device in device_names:
        components = r.lrange(f"{device}:components", 0, -1)
        for comp in components:
            status = r.get(f"{device}:{comp}:status")
            execution_time = r.get(f"{device}:{comp}:execution_time")
            start_execution = r.get(f"{device}:{comp}:start_execution")
            try:
                if status and execution_time and start_execution:
                    start_exec = float(start_execution)
                    if now - start_exec <= 10:
                        exec_time = float(execution_time)
                        fig.add_trace(go.Bar(
                            name=f"{comp}",
                            x=[exec_time],
                            y=[f"{comp}"],
                            base=start_execution,
                            orientation="h",
                            marker=dict(color=phase_colors.get(comp, "#7f7f7f"))
                        ))
            except ValueError:
                continue

    fig.update_layout(
        title={
            'text': "MAPE-K Phases Timeline (Last 10 Seconds)",
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 16, 'color': '#2c3e50'}
        },
        xaxis_title="Time (seconds)",
        yaxis_title="Components",
        barmode="overlay",
        template="plotly_white",
        showlegend=False,
        plot_bgcolor="rgba(248, 249, 250, 1)",
        paper_bgcolor="rgba(255, 255, 255, 1)",
        font={'family': '"Segoe UI", Tahoma, Geneva, Verdana, sans-serif'},
        margin={'l': 80, 'r': 20, 't': 60, 'b': 60}
    )
    return fig

@app.callback(
    Output("processor-cards", "children"),
    Input("interval-redis", "n_intervals")
)
def update_processors(_):
    import time
    device_names = r.lrange('devices', 0, -1)  # List of device names
    logger.debug(f"Devices in Redis: {device_names}")
    cards = []
    for device in device_names:
        heartbeat = r.get(f"{device}:heartbeat")
        logger.debug(f"{device} heartbeat: {heartbeat}")
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
            else:
                online_status = "🔴 Offline (no heartbeat)"
                online_color = "red"
        except Exception as e:
            logger.warning(f"Exception for {device} heartbeat: {e}")
            online_status = "Unknown"
            online_color = "gray"

        # Get components for this device
        components = r.lrange(f"{device}:components", 0, -1)
        logger.debug(f"{device} components: {components}")
        running_count = 0
        comp_list = []
        for comp in components:
            status_key = f"{device}:{comp}:status"
            status = r.get(status_key)
            logger.debug(f"{device} component {comp} status: {status}")
            if status == "running":
                status_text = "🟢 Running"
                status_color = "green"
                running_count += 1
            elif status == "paused":
                status_text = "⏸️ Paused"
                status_color = "orange"
            else:
                status_text = "⚪ Stopped"
                status_color = "gray"
            comp_list.append(html.Div([
                html.Div([
                    html.Span(comp, style={
                        'fontWeight': '600', 
                        'color': '#2c3e50',
                        'fontSize': '14px'
                    }),
                    html.Span(status_text, style={
                        'color': status_color, 
                        'fontWeight': '500',
                        'fontSize': '12px',
                        'marginLeft': '8px'
                    })
                ], style={'marginBottom': '8px'}),
                html.Div([
                    html.Button('▶️', 
                               id={'type': 'run-comp-btn', 'proc': device, 'comp': comp},
                               style={
                                   'backgroundColor': '#27ae60',
                                   'color': 'white',
                                   'border': 'none',
                                   'borderRadius': '4px',
                                   'padding': '4px 8px',
                                   'marginRight': '4px',
                                   'cursor': 'pointer',
                                   'fontSize': '12px'
                               }),
                    html.Button('⏸️', 
                               id={'type': 'pause-comp-btn', 'proc': device, 'comp': comp},
                               style={
                                   'backgroundColor': '#f39c12',
                                   'color': 'white',
                                   'border': 'none',
                                   'borderRadius': '4px',
                                   'padding': '4px 8px',
                                   'marginRight': '4px',
                                   'cursor': 'pointer',
                                   'fontSize': '12px'
                               }),
                    html.Button('❌', 
                               id={'type': 'del-comp-btn', 'proc': device, 'comp': comp}, 
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
                ])
            ], style={
                'backgroundColor': '#f8f9fa',
                'border': '1px solid #e9ecef',
                'borderRadius': '8px',
                'padding': '12px',
                'marginBottom': '8px',
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
                'marginBottom': '15px',
                'paddingBottom': '10px',
                'borderBottom': '2px solid #ecf0f1'
            }),
            
            # Device Status
            html.Div([
                html.Div([
                    html.Span("Status: ", style={'color': '#7f8c8d', 'fontSize': '14px'}),
                    html.Span(online_status, style={
                        'color': online_color, 
                        'fontWeight': '600',
                        'fontSize': '14px'
                    })
                ], style={'marginBottom': '8px'}),
                html.Div([
                    html.Span("Active: ", style={'color': '#7f8c8d', 'fontSize': '14px'}),
                    html.Span(f"{running_count}/{len(components)}", style={
                        'fontWeight': '600',
                        'color': '#2c3e50',
                        'fontSize': '14px'
                    })
                ])
            ], style={'marginBottom': '20px'}),
            
            # Components List
            html.Div([
                html.H5("Components", style={
                    'margin': '0 0 10px 0',
                    'color': '#34495e',
                    'fontSize': '14px',
                    'fontWeight': '600'
                }),
                html.Div(comp_list)
            ]),
            
            # Add Component Button
            html.Button('+ Add Component', 
                       id={'type': 'add-comp-btn', 'proc': device},
                       style={
                           'width': '100%',
                           'backgroundColor': '#3498db',
                           'color': 'white',
                           'border': 'none',
                           'borderRadius': '6px',
                           'padding': '10px',
                           'marginTop': '15px',
                           'cursor': 'pointer',
                           'fontSize': '14px',
                           'fontWeight': '500',
                           'transition': 'all 0.3s ease'
                       })
        ], style={
            'backgroundColor': '#ffffff',
            'border': '1px solid #e9ecef',
            'borderRadius': '12px',
            'padding': '20px',
            'boxShadow': '0 2px 8px rgba(0, 0, 0, 0.1)',
            'transition': 'transform 0.2s ease, box-shadow 0.2s ease',
            'minHeight': '300px'
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
        # r.rpush('devices', new_device)
        logger.debug(f"Added device: {new_device}")
        # import time
        # r.set(f'{new_device}:heartbeat', time.time())
        # r.delete(f'{new_device}:components')
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
            logger.debug(f"Setting {device}:{comp} to running")
            # r.set(f'{device}:status:{comp}', 'running')
        elif tid['type'] == 'pause-comp-btn':
            device, comp = tid['proc'], tid['comp']
            logger.debug(f"Setting {device}:{comp} to paused")
            # r.set(f'{device}:status:{comp}', 'paused')
    return dash.no_update

@app.callback(
    Output('live-log', 'children'),
    Input('interval-log', 'n_intervals')
)
def update_log(_):
    logs = r.lrange('log', -5, -1)
    if logs:
        return '\n'.join(logs)
    else:
        return "No logs found in Redis."

if __name__ == '__main__':
    app.run_server(debug=True)
