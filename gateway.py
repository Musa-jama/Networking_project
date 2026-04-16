from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import paho.mqtt.client as mqtt
from rich.console import Console
from rich.live import Live
from rich.table import Table

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
KEEPALIVE = 60
OFFLINE_TIMEOUT = 12
ISOLATION_FEEDBACK_WINDOW = 20

console = Console()

# device state stored by gateway
state: dict[str, dict[str, Any]] = defaultdict(lambda: {
    "last_seen": None,
    "status": "unknown",
    "telemetry": {},
    "alerts": [],
    "isolated": False,
    "last_isolation": None,
})

lock = threading.Lock()

THRESHOLDS = {
    "packet_rate": 100,
    "temperature": {"min": -5, "max": 55},
    "battery": 20,
    "network_rtt": 250,
    "ports_scanned": 35,
}


def pretty_duration(seconds: float) -> str:
    if seconds < 0:
        return "0s"
    return f"{int(seconds)}s"


def build_table() -> Table:
    table = Table(title="IoT Smart Gateway Dashboard")
    table.add_column("Device", style="bold cyan")
    table.add_column("Status")
    table.add_column("Last Seen")
    table.add_column("Temp (°C)")
    table.add_column("Humidity (%)")
    table.add_column("Battery (%)")
    table.add_column("Packets/s")
    table.add_column("RTT (ms)")
    table.add_column("Ports Scanned")
    table.add_column("Alerts", overflow="fold")

    now = datetime.now(timezone.utc)

    with lock:
        for device_id, info in sorted(state.items()):
            last_seen = info["last_seen"]
            last_seen_str = "never"
            if last_seen:
                last_seen_str = pretty_duration((now - last_seen).total_seconds())

            telemetry = info["telemetry"]
            alerts = info["alerts"]
            status = info["status"]
            if info["isolated"]:
                status = "isolated"

            table.add_row(
                device_id,
                status,
                last_seen_str,
                str(telemetry.get("temperature", "-")),
                str(telemetry.get("humidity", "-")),
                str(telemetry.get("battery", "-")),
                str(telemetry.get("packet_rate", "-")),
                str(telemetry.get("network_rtt", "-")),
                str(telemetry.get("ports_scanned", "-")),
                ", ".join(alerts[-3:]) if alerts else "none",
            )
    return table


def evaluate_anomaly(device_id: str, telemetry: dict[str, Any]) -> list[str]:
    alerts: list[str] = []

    if telemetry.get("packet_rate", 0) > THRESHOLDS["packet_rate"]:
        alerts.append("High packet rate (possible DDoS)")
    if telemetry.get("temperature") is not None:
        temp = telemetry["temperature"]
        if temp < THRESHOLDS["temperature"]["min"] or temp > THRESHOLDS["temperature"]["max"]:
            alerts.append("Temperature out of safe range")
    if telemetry.get("battery", 100) < THRESHOLDS["battery"]:
        alerts.append("Low battery")
    if telemetry.get("network_rtt", 0) > THRESHOLDS["network_rtt"]:
        alerts.append("High network latency")
    if telemetry.get("ports_scanned", 0) > THRESHOLDS["ports_scanned"]:
        alerts.append("Port scanning behavior detected")

    if telemetry.get("packet_rate", 0) > THRESHOLDS["packet_rate"] and telemetry.get("ports_scanned", 0) > THRESHOLDS["ports_scanned"]:
        alerts.append("Composite anomaly: traffic storm + scan")

    return alerts


def update_device(device_id: str, payload: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    with lock:
        info = state[device_id]
        info["last_seen"] = now
        info["status"] = "online"
        info["telemetry"] = payload
        info["alerts"] = evaluate_anomaly(device_id, payload)

        if info["alerts"] and not info["isolated"]:
            if info["last_isolation"] is None or (now - info["last_isolation"]).total_seconds() > ISOLATION_FEEDBACK_WINDOW:
                isolate_device(device_id)


def isolate_device(device_id: str) -> None:
    topic = f"devices/{device_id}/control"
    command = {"command": "isolate"}
    payload = json.dumps(command)
    client.publish(topic, payload, qos=1)

    with lock:
        info = state[device_id]
        info["isolated"] = True
        info["status"] = "isolated"
        info["last_isolation"] = datetime.now(timezone.utc)
        info["alerts"].append("Isolation command sent")

    console.log(f"[red]Isolation command sent[/red] to {device_id}")


def mark_offline_devices() -> None:
    now = datetime.now(timezone.utc)
    with lock:
        for device_id, info in state.items():
            if info["last_seen"] is None:
                continue
            elapsed = (now - info["last_seen"]).total_seconds()
            if elapsed > OFFLINE_TIMEOUT and info["status"] != "offline":
                info["status"] = "offline"
                info["alerts"].append("Offline or missing from network")
                console.log(f"[yellow]Device offline detected:[/yellow] {device_id}")


def on_connect(client: mqtt.Client, userdata: Any, flags: dict[str, Any], rc: int) -> None:
    if rc == 0:
        console.log("Connected to MQTT broker")
        client.subscribe("devices/+/telemetry", qos=1)
        client.subscribe("devices/+/status", qos=1)
    else:
        console.log(f"Failed to connect to broker: {rc}")


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    topic_parts = msg.topic.split("/")
    if len(topic_parts) < 3:
        return

    device_id = topic_parts[1]
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        return

    if topic_parts[2] == "telemetry":
        update_device(device_id, payload)
    elif topic_parts[2] == "status":
        with lock:
            info = state[device_id]
            info["status"] = payload.get("state", "online")
            info["last_seen"] = datetime.now(timezone.utc)
            info["telemetry"].update(payload)


def monitor_loop() -> None:
    with Live(build_table(), refresh_per_second=1, transient=False) as live:
        while True:
            mark_offline_devices()
            live.update(build_table())
            time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = mqtt.Client(client_id="iot-smart-gateway")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, KEEPALIVE)
    client.loop_start()

    try:
        monitor_loop()
    except KeyboardInterrupt:
        console.print("\nShutting down gateway...")
    finally:
        client.loop_stop()
        client.disconnect()
