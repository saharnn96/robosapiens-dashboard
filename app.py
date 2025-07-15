import dash
from dash import dcc, html, Input, Output, State, ctx
import plotly.graph_objs as go
import redis
import json
import time

r = redis.Redis(host='localhost', port=6379, decode_responses=True, db=6)

app = dash.Dash(__name__)
app.title = "RoboSAPIENS Adaptive Platform Dashboard"

app.layout = html.Div([
    html.H1("RoboSAPIENS Adaptive Platform Dashboard", style={'textAlign': 'center'}),
    html.H3("Components Activation Gantt Chart", style={'textAlign': 'center'}),
    dcc.Graph(id="gantt-chart"),
    dcc.Interval(id='interval-gantt', interval=1000, n_intervals=0),

    html.Div([
        html.Div(id='processor-cards', style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px'}),
        html.Div([
            html.Button('+', id='add-processor-btn', title='Add Processor', style={'fontSize': '24px', 'width': '50px', 'height': '50px'}),
            html.Div("Add Processor", style={'textAlign': 'center'})
        ], style={'margin': '10px', 'textAlign': 'center'})
    ], style={'display': 'flex', 'flexDirection': 'row', 'alignItems': 'flex-start'}),

    html.H3("Logs"),
    html.Pre(id='live-log', style={'height': '200px', 'overflowY': 'scroll', 'border': '1px solid #ccc'}),

    dcc.Interval(id='interval-redis', interval=2000, n_intervals=0),
    dcc.Interval(id='interval-log', interval=1000, n_intervals=0)
])

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
                            x=[exec_time],
                            y=[f"{comp}"],
                            base=start_execution,
                            orientation="h",
                            marker=dict(color=phase_colors.get(status, "#7f7f7f"))
                        ))
            except ValueError:
                continue
    # for _, row in df.iterrows():
    #     fig.add_trace(go.Bar(
    #         x=[row["Duration"]],
    #         y=[row["Phase"]],
    #         base=row["Start"] - row["Duration"],
    #         orientation="h",
    #         # marker=dict(
    #         #     color=phase_colors.get(row["Phase"], "#7f7f7f"),  # Default gray fallback
    #         # )
    #     ))

    fig.update_layout(
        title="MAPE-K Phases Timeline (Last 10 Seconds)",
        xaxis_title="Time (seconds)",
        yaxis_title="Phases",
        barmode="overlay",
        template="plotly",
        showlegend=False,
        plot_bgcolor="rgba(240, 240, 240, 1)"  # Light gray background
    )
    return fig

@app.callback(
    Output("processor-cards", "children"),
    Input("interval-redis", "n_intervals")
)
def update_processors(_):
    import time
    device_names = r.lrange('devices', 0, -1)  # List of device names
    print(f"[DEBUG] Devices in Redis: {device_names}")
    cards = []
    for device in device_names:
        heartbeat = r.get(f"{device}:heartbeat")
        print(f"[DEBUG] {device} heartbeat: {heartbeat}")
        try:
            if heartbeat:
                now = time.time()
                heartbeat_val = float(heartbeat)
                print(f"[DEBUG] {device} now: {now}, heartbeat_val: {heartbeat_val}, diff: {now - heartbeat_val}")
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
            print(f"[DEBUG] Exception for {device} heartbeat: {e}")
            online_status = "Unknown"
            online_color = "gray"

        # Get components for this device
        components = r.lrange(f"{device}:components", 0, -1)
        print(f"[DEBUG] {device} components: {components}")
        running_count = 0
        comp_list = []
        for comp in components:
            status_key = f"{device}:status:{comp}"
            status = r.get(status_key)
            print(f"[DEBUG] {device} component {comp} status: {status}")
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
                html.Span(comp, style={'marginRight': '10px', 'fontWeight': 'bold'}),
                html.Span(status_text, style={'color': status_color, 'marginRight': '10px'}),
                html.Button('▶️', id={'type': 'run-comp-btn', 'proc': device, 'comp': comp}),
                html.Button('⏸️', id={'type': 'pause-comp-btn', 'proc': device, 'comp': comp}),
                html.Button('❌', id={'type': 'del-comp-btn', 'proc': device, 'comp': comp}, disabled=True, title='Delete disabled')
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '5px', 'border': '1px solid #bbb', 'borderRadius': '5px', 'padding': '4px', 'marginBottom': '6px', 'background': '#fafafa'}))

        cards.append(html.Div([
            html.Div([
                html.H4(device, style={'marginBottom': 0}),
                html.Button('❌', id={'type': 'del-proc-btn', 'proc': device}, style={'float': 'right', 'marginLeft': 'auto'}, disabled=True, title='Delete disabled'),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}),
            html.Div([
                html.Span(f"Heartbeat: {heartbeat if heartbeat else 'N/A'}", style={'marginRight': '15px'}),
                html.Span(online_status, style={'color': online_color, 'fontWeight': 'bold', 'marginRight': '15px'}),
                html.Span(f"Running components: {running_count}/{len(components)}", style={'fontWeight': 'bold'})
            ], style={'marginBottom': '10px', 'marginTop': '5px'}),
            html.Div(comp_list),
            html.Button('+', id={'type': 'add-comp-btn', 'proc': device}, title='Add Component', style={'marginTop': '10px'}),
            html.Div("add component", style={'textAlign': 'center', 'color': '#888', 'fontSize': '13px', 'marginTop': '2px'})
        ], style={'border': '1px solid #ccc', 'padding': '14px', 'borderRadius': '14px', 'minWidth': '220px', 'marginRight': '18px', 'marginBottom': '18px', 'background': '#fff', 'boxShadow': '0 2px 8px #eee'}))
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
    print(f"[DEBUG] handle_actions triggered_id: {ctx.triggered_id}")
    if ctx.triggered_id == 'add-processor-btn':
        # Add a new device
        device_names = r.lrange('devices', 0, -1)
        print(f"[DEBUG] Devices before add: {device_names}")
        new_device = f"Device{len(device_names) + 1}"
        # r.rpush('devices', new_device)
        # print(f"[DEBUG] Added device: {new_device}")
        # # Initialize heartbeat and components for new device
        # import time
        # r.set(f'{new_device}:heartbeat', time.time())
        # r.delete(f'{new_device}:components')
    elif isinstance(ctx.triggered_id, dict):
        tid = ctx.triggered_id
        print(f"[DEBUG] handle_actions tid: {tid}")
        # Deactivate all delete actions
        if tid['type'] == 'del-proc-btn':
            print(f"[DEBUG] Delete device action is deactivated.")
            pass
        elif tid['type'] == 'add-comp-btn':
            device = tid['proc']
            comps = r.lrange(f'{device}:components', 0, -1)
            print(f"[DEBUG] Adding component to {device}, current comps: {comps}")
            comp_name = f"Component{len(comps) + 1}"
            # r.rpush(f'{device}:components', comp_name)
            print(f"[DEBUG] Added component: {comp_name}")
        elif tid['type'] == 'del-comp-btn':
            print(f"[DEBUG] Delete component action is deactivated.")
            pass
        elif tid['type'] == 'run-comp-btn':
            device, comp = tid['proc'], tid['comp']
            print(f"[DEBUG] Setting {device}:{comp} to running")
            # r.set(f'{device}:status:{comp}', 'running')
        elif tid['type'] == 'pause-comp-btn':
            device, comp = tid['proc'], tid['comp']
            # print(f"[DEBUG] Setting {device}:{comp} to paused")
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
