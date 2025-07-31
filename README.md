# RoboSAPIENS Adaptive Platform Dashboard

A real-time monitoring and control dashboard for the RoboSAPIENS adaptive platform, built with Dash and Redis. This dashboard provides real-time visualization of distributed component status, timeline tracking, and centralized logging.

## Features

- **Real-time Device Monitoring**: Track status of distributed devices and their components
- **Interactive Timeline**: Visualize component activation states with MAPE-K phase colors
- **Component Control**: Run, pause, build, and delete operations for individual components
- **Centralized Logging**: View aggregated logs from multiple sources with filtering
- **Responsive UI**: Compact single-screen layout optimized for monitoring dashboards

## Prerequisites

- Python 3.8+
- Redis server running on your system

## Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd robosapiens-dashboard
   ```

2. Install required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Start your Redis server (default: localhost:6379, database 6)

## Configuration

The application can be configured using environment variables:

- `REDIS_HOST`: Redis server hostname (default: localhost)
- `REDIS_PORT`: Redis server port (default: 6379)
- `REDIS_DB`: Redis database number (default: 6)
- `DEBUG`: Enable debug mode (default: False)
- `PORT`: Dashboard port (default: 8050)

## Usage

1. Start the dashboard:

   ```bash
   python app.py
   ```

2. Open your browser and navigate to `http://localhost:8050`

3. The dashboard will automatically detect devices and components stored in Redis

## Redis Data Structure

The dashboard expects the following Redis data structure:

### Device Management

```
devices:list                        # List of all device names
```

### Device Information

```
devices:{device}:heartbeat          # Timestamp of last device heartbeat
devices:{device}:nodes              # List of components/nodes for this device
```

### Component Status

```
devices:{device}:{component}:status # Current status of component (active/inactive/building/error)
```

### Logging

```
*:logs                             # Any Redis key ending with ':logs' containing log entries
dashboard:logs                     # Application logs from the dashboard itself
```

### Example Data Structure

```
devices:list = ["robot1", "robot2", "workstation1"]
devices:robot1:nodes = ["sensor", "actuator", "controller"]
devices:robot1:sensor:status = "active"
devices:robot1:actuator:status = "inactive"
devices:robot1:controller:status = "building"
devices:robot1:heartbeat = "1703123456.789"
robot1:logs = ["[2023-12-20 15:30:45] Sensor initialized", "[2023-12-20 15:30:46] Reading data..."]
workstation1:logs = ["[2023-12-20 15:30:50] Processing started"]
dashboard:logs = ["[2023-12-20 15:30:55] Dashboard started successfully"]
```

### Component States

- **active**: Component is running normally (green)
- **inactive**: Component is stopped (red)
- **building**: Component is being built/compiled (yellow)
- **error**: Component encountered an error (orange)

### MAPE-K Phase Colors

The Gantt chart uses MAPE-K (Monitor, Analyze, Plan, Execute, Knowledge) phase colors:

- Monitor: Blue (#3498db)
- Analyze: Green (#2ecc71)
- Plan: Orange (#f39c12)
- Execute: Red (#e74c3c)
- Knowledge: Purple (#9b59b6)

## Component Control

The dashboard provides control buttons for each component:

- **▶️ Run**: Start/activate the component
- **⏸️ Pause**: Stop/deactivate the component
- **🔨 Build**: Trigger build process for the component
- **🗑️ Delete**: Remove the component

These actions publish messages to Redis pub/sub channels for orchestrator consumption.

## Log Filtering

The dashboard automatically detects Redis keys matching the pattern `*:logs` and provides checkboxes to filter log sources. Logs are displayed in real-time with timestamps and source identification.

## File Structure

```
robosapiens-dashboard/
├── app.py                 # Main dashboard application
├── redis_filler.py        # Utility script to populate Redis with sample data
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── Dash_design_01.jpg    # Dashboard design mockup
```

## Development

To populate Redis with sample data for testing:

```bash
python redis_filler.py
```

This will create sample devices, components, and log entries for development and testing purposes.

## Troubleshooting

1. **Connection Issues**: Ensure Redis server is running and accessible
2. **No Data Displayed**: Check if devices are registered in `devices:list` Redis key
3. **Logs Not Showing**: Verify log sources exist with keys ending in `:logs`
4. **Component Actions Not Working**: Check Redis pub/sub channels for orchestrator connectivity

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is part of the RoboSAPIENS adaptive platform research project.
robosapiens-dashboard

````

## Local Development

1. **Install dependencies**:

```bash
pip install -r requirements.txt
````

2. **Start Redis**:

   ```bash
   redis-server
   ```

3. **Run the application**:
   ```bash
   python app.py
   ```

## Environment Variables

| Variable     | Default     | Description           |
| ------------ | ----------- | --------------------- |
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379`      | Redis server port     |
| `REDIS_DB`   | `6`         | Redis database number |
| `DEBUG`      | `false`     | Enable debug mode     |
| `PORT`       | `8050`      | Dashboard port        |

## Data Structure

The dashboard expects Redis data in the following format:

- `devices:list` - List of device names
- `devices:{device}:heartbeat` - Device heartbeat timestamp
- `devices:{device}:nodes` - List of components for a device
- `devices:{device}:{node}:status` - Component status (running/exited/removed)
- `*:logs` - Log sources (automatically discovered)

## Architecture

- **Frontend**: Dash (Plotly) with real-time callbacks
- **Backend**: Redis for data storage and pub/sub messaging
- **Logging**: Custom Redis log handler for centralized logging
- **Deployment**: Docker with health checks and restart policies

## Screenshots

The dashboard features a compact, single-screen layout with:

- Header with app title and description
- Left panel: MAPE-K timeline chart
- Right panel: Device status cards with components
- Bottom panel: Multi-source log viewer with filtering

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with Docker Compose
5. Submit a pull request

## License

[Your license here]
