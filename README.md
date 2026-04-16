# IoT Smart-Gateway with MQTT

This project implements a simulated IoT smart gateway with MQTT device telemetry ingestion, real-time dashboard reporting, and automated device isolation.

## What it includes

- `gateway.py`: MQTT gateway that subscribes to IoT device telemetry and status topics.
- `device_simulator.py`: Simulates multiple IoT devices publishing telemetry and responding to isolation commands.
- `docker-compose.yml`: Optional local Mosquitto MQTT broker for quick setup.
- `requirements.txt`: Python dependencies.

## Features

- Real-time device health tracking.
- Automated anomaly detection based on packet rate, battery, temperature, and RTT.
- Automatic isolation of suspicious or degraded devices.
- Simulated device behavior with anomaly injection.

## Requirements

- Python 3.9+
- `pip install -r requirements.txt`
- Local MQTT broker on `localhost:1883` (Mosquitto recommended).

## Setup

### Option 1: Run a local Mosquitto broker with Docker

```powershell
cd C:\Users\USER\IoT_SmartGateway
docker compose up -d
```

### Option 2: Install Mosquitto directly

Install the Eclipse Mosquitto broker for Windows and start it with the default config.

## Run the project

1. Start the gateway:

```powershell
python gateway.py
```

2. In another terminal, start the simulated devices:

```powershell
python device_simulator.py
```

3. Watch the dashboard update and observe automatic isolation when a simulated device becomes suspicious.

## Notes

- The smart gateway uses MQTT topics under `devices/{device_id}/telemetry` and `devices/{device_id}/control`.
- The simulator publishes telemetry every few seconds and can trigger an anomaly after startup.
- The gateway will broadcast isolation commands to suspicious devices automatically.
