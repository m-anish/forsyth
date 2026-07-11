"""MQTT → DB bridge, plus Home Assistant discovery.

Topic shape follows jigawatt's convention:
    forsyth/<slug>/reading       JSON reading (same fields as HTTP ingest)
    forsyth/<slug>/lightning     JSON {ts?, distance_km, energy, count?}
    forsyth/<slug>/availability  online/offline (device LWT; passed through to HA)

Authentication model: the broker itself is authenticated (per-device passwords in
mosquitto), so a publish on forsyth/<slug>/# is trusted if <slug> exists. Station
API keys are an HTTP concern.

Runs as a daemon thread inside the API process; if MQTT_HOST is unset or the
broker is down it retries quietly and the HTTP side is unaffected.
"""
import json
import logging
import threading
import time

from sqlalchemy import text

from .config import settings
from .db import engine
from .ingest import Reading, store_readings

log = logging.getLogger("forsyth.mqtt")

HA_SENSORS = {
    # field: (HA name suffix, unit, device_class)
    "temp_c": ("Temperature", "°C", "temperature"),
    "rh": ("Humidity", "%", "humidity"),
    "pressure_pa": ("Pressure", "Pa", "atmospheric_pressure"),
    "wind_avg_ms": ("Wind speed", "m/s", "wind_speed"),
    "wind_gust_ms": ("Wind gust", "m/s", "wind_speed"),
    "wind_dir_deg": ("Wind direction", "°", None),
    "rain_mm": ("Rain", "mm", "precipitation"),
    "pm25": ("PM2.5", "µg/m³", "pm25"),
    "pm10": ("PM10", "µg/m³", "pm10"),
    "batt_v": ("Battery", "V", "voltage"),
}


def _slug_ids() -> dict[str, int]:
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT slug, id FROM stations")).all())


def _publish_discovery(client, slug: str) -> None:
    """Retained HA discovery configs; state read via template from the reading topic."""
    dev = {
        "identifiers": [f"forsyth_{slug}"],
        "name": f"Forsyth {slug}",
        "manufacturer": "starstucklab",
        "model": "forsyth leaf",
    }
    for field, (name, unit, dclass) in HA_SENSORS.items():
        cfg = {
            "name": name,
            "unique_id": f"forsyth_{slug}_{field}",
            "state_topic": f"forsyth/{slug}/reading",
            "value_template": "{{ value_json.%s }}" % field,
            "unit_of_measurement": unit,
            "availability_topic": f"forsyth/{slug}/availability",
            "device": dev,
        }
        if dclass:
            cfg["device_class"] = dclass
        client.publish(
            f"homeassistant/sensor/forsyth_{slug}/{field}/config",
            json.dumps(cfg), qos=1, retain=True,
        )
    log.info("published HA discovery for %s", slug)


def _handle(client, slug: str, kind: str, payload: bytes, ids: dict[str, int]) -> None:
    sid = ids.get(slug)
    if sid is None:
        ids.update(_slug_ids())          # station may have been created since
        sid = ids.get(slug)
        if sid is None:
            log.warning("MQTT for unknown station %r ignored", slug)
            return
        _publish_discovery(client, slug)
    if kind == "reading":
        store_readings(sid, [Reading.model_validate(json.loads(payload))])
    elif kind == "lightning":
        ev = json.loads(payload)
        store_readings(sid, [Reading.model_validate({"lightning": [ev]})])
    # availability is HA's business; nothing to store


def start_bridge():
    """Returns a stop() callable. No-op if MQTT_HOST is unset."""
    if not settings.mqtt_host:
        log.info("MQTT bridge disabled (no MQTT_HOST)")
        return lambda: None

    import paho.mqtt.client as mqtt

    stop = threading.Event()

    def run():
        ids: dict[str, int] = {}
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="forsyth-api")
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

        def on_connect(c, _u, _f, rc, _p=None):
            if rc == 0:
                c.subscribe("forsyth/+/reading")
                c.subscribe("forsyth/+/lightning")
                ids.update(_slug_ids())
                for slug in ids:
                    _publish_discovery(c, slug)
                log.info("MQTT bridge connected")
            else:
                log.warning("MQTT connect failed rc=%s", rc)

        def on_message(c, _u, msg):
            try:
                _, slug, kind = msg.topic.split("/", 2)
                _handle(c, slug, kind, msg.payload, ids)
            except Exception:
                log.exception("bad MQTT message on %s", msg.topic)

        client.on_connect = on_connect
        client.on_message = on_message

        while not stop.is_set():
            try:
                client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
                client.loop_start()
                stop.wait()
                client.loop_stop()
                client.disconnect()
                return
            except Exception as e:
                log.warning("MQTT unavailable (%s); retrying in 30 s", e)
                stop.wait(30)

    t = threading.Thread(target=run, name="mqtt-bridge", daemon=True)
    t.start()
    return stop.set
