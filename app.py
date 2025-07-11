import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objs as go
from datetime import datetime
import pandas as pd
import redis
import json

LOG_FILE = 'MAPE_test.log'

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

app = dash.Dash(__name__)
app.title = "Enhanced MAPE-K Dashboard"

phases = []

app.layout = html.Div([
    html.H1("MAPE-K Dashboard"),
    dcc.Graph(id="gantt-chart"),
    dcc.Interval(id='interval-gantt', interval=1000, n_intervals=0),
    html.H2("Processor/Component Status"),
    html.Div(id='processor-cards'),
    dcc.Interval(id='interval-redis', interval=2000, n_intervals=0),
    html.H2("Live Logs"),
    html.Pre(id='live-log', style={'height': '200px', 'overflowY': 'scroll', 'border': '1px solid #ccc'}),
    dcc.Interval(id='interval-log', interval=1000, n_intervals=0)
])

@app.callback(
    Output("gantt-chart", "figure"),
    Input("interval-gantt", "n_intervals")
)
def update_gantt(n):
    df = pd.DataFrame({
        "Task": ["Monitor", "Plan", "Execute"],
        "Start": [0, 2, 4],
        "Finish": [2, 4, 6]
    })
    fig = go.Figure()
    for _, row in df.iterrows():
        fig.add_trace(go.Bar(
            x=[row["Finish"] - row["Start"]],
            y=[row["Task"]],
            base=row["Start"],
            orientation="h"
        ))
    return fig

@app.callback(
    Output("processor-cards", "children"),
    Input("interval-redis", "n_intervals")
)
def update_cards(_):
    processor_keys = r.keys("processor:*")
    cards = []
    for key in processor_keys:
        processor = key.split(":")[1]
        components = r.lrange(key, 0, -1)
        component_items = []
        for comp in components:
            component_items.append(
                html.Div([
                    html.Span(comp, style={'marginRight': '10px'}),
                    html.Button("Run", id={'type': 'run-btn', 'proc': processor, 'comp': comp}),
                    html.Button("Stop", id={'type': 'stop-btn', 'proc': processor, 'comp': comp}),
                    html.Button("Delete", id={'type': 'del-btn', 'proc': processor, 'comp': comp})
                ], style={'display': 'flex', 'gap': '5px', 'alignItems': 'center'})
            )
        cards.append(
            html.Div([
                html.H4(f"Processor: {processor}"),
                html.Div(component_items)
            ], style={'border': '1px solid #ccc', 'padding': '10px', 'margin': '10px'})
        )
    return cards

@app.callback(
    Output('interval-redis', 'n_intervals'),
    Input({'type': 'run-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'n_clicks'),
    Input({'type': 'stop-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'n_clicks'),
    Input({'type': 'del-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'n_clicks'),
    State({'type': 'run-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'id'),
    State({'type': 'stop-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'id'),
    State({'type': 'del-btn', 'proc': dash.ALL, 'comp': dash.ALL}, 'id'),
    prevent_initial_call=True
)
def handle_actions(run_clicks, stop_clicks, del_clicks, run_ids, stop_ids, del_ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    btn_id = ctx.triggered[0]['prop_id'].split('.')[0]
    btn_id_dict = json.loads(btn_id)
    action = btn_id_dict['type'].split('-')[0]
    proc = btn_id_dict['proc']
    comp = btn_id_dict['comp']
    if action == "run":
        print(f"Run requested for {comp} on {proc}")
    elif action == "stop":
        print(f"Stop requested for {comp} on {proc}")
    elif action == "del":
        r.lrem(f"processor:{proc}", 0, comp)
    return dash.no_update

@app.callback(
    Output('live-log', 'children'),
    Input('interval-log', 'n_intervals')
)
def update_log(_):
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            last_lines = lines[-20:]  # show last 20 lines
            return ''.join(last_lines)
    except FileNotFoundError:
        return "Log file not found."

if __name__ == '__main__':
    app.run_server(debug=True)
