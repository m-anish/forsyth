"""uplink.py — WiFi + MQTT with an offline spool.

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

import network
import ntptime
from umqtt.simple import MQTTClient

import config


def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan
    print("wifi: connecting to %s" % config.WIFI_SSID)
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    for _ in range(60):
        if wlan.isconnected():
            print("wifi: %s" % wlan.ifconfig()[0])
            return wlan
        time.sleep(1)
    print("wifi: timed out; will retry from the main loop")
    return wlan


def ntp_sync():
    ntptime.host = config.NTP_HOST
    for _ in range(3):
        try:
            ntptime.settime()
            return True
        except OSError:
            time.sleep(2)
    print("ntp: sync failed — timestamps fall back to server receive time")
    return False


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
        except OSError as e:
            print("mqtt: connect failed (%s)" % e)
            self._client = None
            return False

    def check_msg(self):
        if self._client:
            try:
                self._client.check_msg()
            except OSError:
                self._client = None

    def ping(self):
        if self._client:
            try:
                self._client.ping()
            except OSError:
                self._client = None

    @property
    def connected(self):
        return self._client is not None

    def publish(self, topic, obj):
        payload = json.dumps(obj)
        if self._client:
            try:
                self._client.publish(topic.encode(), payload.encode())
                return True
            except OSError:
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
            except OSError:
                # keep the unsent tail
                with open(config.SPOOL_FILE, "w") as f:
                    for t, p in entries[sent:]:
                        f.write(json.dumps([t, p]) + "\n")
                self._client = None
                return
        os.remove(config.SPOOL_FILE)
        if sent:
            print("spool: drained %d buffered messages" % sent)
