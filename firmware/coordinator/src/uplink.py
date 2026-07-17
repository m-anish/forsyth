"""uplink.py — MQTT with an offline spool (link management lives in net.py).

Publishes to the topics cloud/api/app/mqtt_bridge.py subscribes to:
  forsyth/<slug>/reading    forsyth/<slug>/lightning
and maintains forsyth/<slug>/availability (retained, LWT = offline) so Home
Assistant and the dashboard's health widget see leaves come and go.

When the broker is unreachable, publishes append to a flash spool
(config.SPOOL_FILE, JSONL of [topic, payload]) and drain on reconnect —
a WiFi wobble costs latency, not data. Requires umqtt.simple:
  mpremote mip install umqtt.simple
"""
import json
import os
import time

from umqtt.simple import MQTTClient, MQTTException

import config

# NTP/RTC discipline lives in clock.py — one implementation, one source of time.


def iso_now():
    t = time.gmtime()
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % t[:6]


def iso_ago(seconds):
    t = time.gmtime(time.time() - seconds)
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % t[:6]


class Uplink:
    def __init__(self, on_cmd):
        """on_cmd(slug, dict) is called for forsyth/<slug>/cmd messages."""
        self._on_cmd = on_cmd
        self._client = None

    def _mk_client(self):
        c = MQTTClient(config.COORDINATOR_ID, config.MQTT_HOST,
                       port=config.MQTT_PORT, user=config.MQTT_USER,
                       password=config.MQTT_PASSWORD,
                       keepalive=config.MQTT_KEEPALIVE)
        # LWT: if we drop dead, every station shows offline (honest > stale)
        for st in config.STATIONS.values():
            c.set_last_will(b"forsyth/%s/availability" % st["slug"],
                            b"offline", retain=True)
            break   # umqtt supports one LWT; coordinator death ≈ fleet offline
        c.set_callback(self._dispatch)
        return c

    def _dispatch(self, topic, payload):
        try:
            parts = topic.decode().split("/")
            if len(parts) == 3 and parts[2] == "cmd":
                self._on_cmd(parts[1], json.loads(payload))
        except Exception as e:
            print("cmd: bad message on %s: %s" % (topic, e))

    def connect(self):
        try:
            self._client = self._mk_client()
            self._client.connect()
            for st in config.STATIONS.values():
                self._client.publish(
                    b"forsyth/%s/availability" % st["slug"],
                    b"online", retain=True)
                self._client.subscribe(b"forsyth/%s/cmd" % st["slug"])
            print("mqtt: connected to %s" % config.MQTT_HOST)
            self._drain_spool()
            return True
        except (OSError, MQTTException) as e:
            # MQTTException("5") = broker said "not authorised" — a wrong or
            # unprovisioned password. Never fatal: we spool and keep serving.
            print("mqtt: connect failed (%r)%s" % (
                e, " — check the device's MQTT credential"
                if isinstance(e, MQTTException) else ""))
            self._client = None
            return False

    def check_msg(self):
        if self._client:
            try:
                self._client.check_msg()
            except (OSError, MQTTException):
                self._client = None

    def ping(self):
        if self._client:
            try:
                self._client.ping()
            except (OSError, MQTTException):
                self._client = None

    @property
    def spooled(self):
        """How many messages are waiting out an outage (for the web status)."""
        try:
            with open(config.SPOOL_FILE) as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0

    @property
    def connected(self):
        return self._client is not None

    def publish(self, topic, obj):
        payload = json.dumps(obj)
        if self._client:
            try:
                self._client.publish(topic.encode(), payload.encode())
                return True
            except (OSError, MQTTException):
                self._client = None
        self._spool(topic, payload)
        return False

    # ---- offline spool ----
    def _spool(self, topic, payload):
        try:
            try:
                lines = sum(1 for _ in open(config.SPOOL_FILE))
            except OSError:
                lines = 0
            if lines >= config.SPOOL_MAX_LINES:
                print("spool: full, dropping oldest-policy skipped (drop new)")
                return
            with open(config.SPOOL_FILE, "a") as f:
                f.write(json.dumps([topic, payload]) + "\n")
        except OSError as e:
            print("spool: write failed (%s)" % e)

    def _drain_spool(self):
        try:
            with open(config.SPOOL_FILE) as f:
                entries = [json.loads(l) for l in f if l.strip()]
        except (OSError, ValueError):
            return
        sent = 0
        for topic, payload in entries:
            try:
                self._client.publish(topic.encode(), payload.encode())
                sent += 1
            except (OSError, MQTTException):
                # keep the unsent tail
                with open(config.SPOOL_FILE, "w") as f:
                    for t, p in entries[sent:]:
                        f.write(json.dumps([t, p]) + "\n")
                self._client = None
                return
        os.remove(config.SPOOL_FILE)
        if sent:
            print("spool: drained %d buffered messages" % sent)
