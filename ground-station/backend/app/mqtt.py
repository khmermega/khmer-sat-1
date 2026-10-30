"""Optional MQTT bridge: republishes decoded telemetry/events to an authenticated broker."""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("ground.mqtt")


class MqttBridge:
    def __init__(self, host: str, port: int, username: str, password: str, prefix: str) -> None:
        import paho.mqtt.client as mqtt

        if not username or not password:
            raise ValueError("MQTT_USERNAME and MQTT_PASSWORD are required (broker allows no anonymous access)")
        self.prefix = prefix
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="khmersat-ground")
        self._client.username_pw_set(username, password)
        self._client.reconnect_delay_set(1, 30)
        self._client.connect_async(host, port, keepalive=30)
        self._client.loop_start()
        log.info("MQTT bridge connecting to %s:%s", host, port)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._client.publish(f"{self.prefix}/{topic}", json.dumps(payload, default=str), qos=0)

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
