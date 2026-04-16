from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
PORT = 1883
NUM_DEVICES = 5
PUBLISH_INTERVAL = 3.0
ANOMALY_AFTER_SECONDS = 20

class DeviceSimulator(threading.Thread):
    def __init__(self, device_id: str, simulate_attack: bool = False) -> None:
        super().__init__(daemon=True)
        self.device_id = device_id
        self.simulate_attack = simulate_attack
        self.isolated = False
        self.stop_event = threading.Event()
        self.client = mqtt.Client(client_id=f"device-{device_id}")
        self.client.on_message = self.on_message
        self.client.connect(BROKER, PORT, 60)
        self.client.loop_start()
        self.client.subscribe(f"devices/{device_id}/control", qos=1)
        self.start_time = datetime.utcnow()

    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            return

        command = payload.get("command")
        if command == "isolate":
            self.isolated = True
            self.publish_status("isolated")
            print(f"[{self.device_id}] Received isolate command, entering isolation mode.")

    def publish_status(self, state: str) -> None:
        topic = f"devices/{self.device_id}/status"
        payload = {
            "device_id": self.device_id,
            "state": state,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        self.client.publish(topic, json.dumps(payload), qos=1)

    def build_telemetry(self) -> dict[str, Any]:
        uptime_seconds = (datetime.utcnow() - self.start_time).total_seconds()
        temperature = random.uniform(16, 32)
        humidity = random.uniform(25, 65)
        battery = max(5, 100 - uptime_seconds * 0.1)
        packet_rate = random.randint(10, 45)
        ports_scanned = random.randint(0, 3)
        network_rtt = random.randint(20, 85)

        if self.simulate_attack and uptime_seconds > ANOMALY_AFTER_SECONDS:
            temperature = random.uniform(20, 38)
            packet_rate = random.randint(130, 220)
            ports_scanned = random.randint(40, 90)
            network_rtt = random.randint(180, 320)

        return {
            "device_id": self.device_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "temperature": round(temperature, 1),
            "humidity": round(humidity, 1),
            "battery": round(battery, 1),
            "packet_rate": packet_rate,
            "ports_scanned": ports_scanned,
            "network_rtt": network_rtt,
            "location": "gateway-zone-1",
        }

    def run(self) -> None:
        self.publish_status("online")
        while not self.stop_event.is_set() and not self.isolated:
            payload = self.build_telemetry()
            topic = f"devices/{self.device_id}/telemetry"
            self.client.publish(topic, json.dumps(payload), qos=1)
            print(f"[{self.device_id}] Sent telemetry: {payload}")
            time.sleep(PUBLISH_INTERVAL)

        if self.isolated:
            print(f"[{self.device_id}] Stopped telemetry after isolation.")
            self.client.loop_stop()
            self.client.disconnect()

    def stop(self) -> None:
        self.stop_event.set()


if __name__ == "__main__":
    simulators: list[DeviceSimulator] = []

    for idx in range(1, NUM_DEVICES + 1):
        device_id = f"device-{idx}"
        simulate_attack = idx == 2
        sim = DeviceSimulator(device_id, simulate_attack=simulate_attack)
        simulators.append(sim)
        sim.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping simulator...")
        for sim in simulators:
            sim.stop()
        time.sleep(1)
