"""main.py — Forsyth coordinator: LoRa in, MQTT out, ACKs + config back down.

Loop shape: poll the E220 for a frame → validate/dedupe → ACK immediately
(the leaf's RX window is short and its radio is about to be unpowered — the
ACK cannot wait for the network) → translate to JSON → publish (or spool).

Pending config for a leaf (from forsyth/<slug>/cmd) rides on the next ACK to
that leaf; there is no other downlink opportunity by design.
"""
import json
import time

import config
import protocol
import uplink as uplink_mod
from e220 import E220
from net import Net

# unit_id -> pending TLV bytes, delivered on next uplink from that leaf
_pending_tlvs = {}
# unit_id -> last seq seen (dedupe of TX retries)
_last_seq = {}
# persisted state: rain baselines per unit_id
_state = {}
_slug_to_unit = {st["slug"]: uid for uid, st in config.STATIONS.items()}


def _load_state():
    global _state
    try:
        with open(config.STATE_FILE) as f:
            _state = json.load(f)
    except (OSError, ValueError):
        _state = {}


def _save_state():
    try:
        with open(config.STATE_FILE, "w") as f:
            json.dump(_state, f)
    except OSError as e:
        print("state: save failed (%s)" % e)


def _rain_mm(unit_id, tips, mm_per_tip):
    """Wrap-aware cumulative-tip delta → mm. First sighting (or a leaf
    reboot, detected by the counter shrinking a lot) only re-baselines —
    never invent rain from a counter reset."""
    key = str(unit_id)
    prev = _state.get(key)
    _state[key] = tips
    _save_state()
    if prev is None:
        return None
    delta = (tips - prev) & 0xFFFF
    if delta > 1000:            # >1000 tips between reports isn't weather
        return None             # it's a reboot/rollback — re-baseline
    return round(delta * mm_per_tip, 3)


def _on_cmd(slug, cmd):
    unit = _slug_to_unit.get(slug)
    if unit is None:
        print("cmd: unknown slug %r" % slug)
        return
    tlvs = protocol.tlvs_from_cmd(cmd)
    if tlvs:
        _pending_tlvs[unit] = _pending_tlvs.get(unit, b"") + tlvs
        print("cmd: queued %d TLV bytes for %s (unit %d)"
              % (len(tlvs), slug, unit))


def _handle_frame(radio, up, payload, rssi):
    msg = protocol.parse(payload)
    if msg is None:
        print("rx: undecodable frame (%d B, rssi %s)" % (len(payload), rssi))
        return
    unit = msg["station_id"]
    st = config.STATIONS.get(unit)
    if st is None:
        print("rx: frame from unregistered unit %d — add it to config.STATIONS"
              % unit)
        return
    slug = st["slug"]

    # ACK first — the leaf is holding its radio on for us right now.
    tlvs = _pending_tlvs.pop(unit, b"")[:64]
    radio.send_to(unit, protocol.build_ack(unit, msg["seq"], tlvs))
    if tlvs:
        print("ack: delivered %d TLV bytes to unit %d" % (len(tlvs), unit))

    # Dedupe TX retries (same seq = same frame, already handled).
    if _last_seq.get(unit) == msg["seq"]:
        return
    _last_seq[unit] = msg["seq"]

    flags = msg["flags"]
    if msg["type"] == protocol.T_READING:
        r = {"ts": uplink_mod.iso_now(), "rssi_dbm": rssi}
        for k in ("temp_c", "rh", "pressure_pa", "wind_avg_ms",
                  "wind_gust_ms", "wind_dir_deg", "pm1", "pm25", "pm10",
                  "batt_v"):
            if k in msg:
                r[k] = msg[k]
        if "rain_tips" in msg:
            mm = _rain_mm(unit, msg["rain_tips"], st["rain_mm_per_tip"])
            if mm is not None:
                r["rain_mm"] = mm
        r["solar_state"] = ("inhibited" if flags & protocol.F_CHG_INHIBIT
                            else "charging-allowed")
        up.publish("forsyth/%s/reading" % slug, r)
        if config.STATUS_LOG:
            print("rx %-10s seq=%3d rssi=%4d flags=%02x %s"
                  % (slug, msg["seq"], rssi, flags,
                     {k: v for k, v in r.items() if k != "ts"}))
        if "vane_adc" in msg:
            print("   diag: vane_adc=%d mcu_temp=%s"
                  % (msg["vane_adc"], msg.get("mcu_temp_c")))
    elif msg["type"] == protocol.T_LIGHTNING:
        ev = {"ts": uplink_mod.iso_ago(msg["age_s"]),
              "energy": msg["energy"], "count": msg["count"]}
        if msg["distance"] is not None:
            ev["distance_km"] = msg["distance"]
        up.publish("forsyth/%s/lightning" % slug, ev)
        print("rx %-10s LIGHTNING dist=%skm energy=%d age=%ds"
              % (slug, msg["distance"], msg["energy"], msg["age_s"]))
    elif msg["type"] == protocol.T_STATUS:
        print("rx %-10s STATUS fw=%04x reset=%02x boots=%d nvram_ok=%d "
              "batt=%.2fV cfg_crc=%04x"
              % (slug, msg["fw_version"], msg["reset_cause"],
                 msg["boot_count"], msg["radio_nvram_ok"],
                 msg["batt_v"], msg["cfg_crc"]))
        # STATUS also lands as a minimal reading so battery + boot events
        # are visible on the dashboard's health widget.
        up.publish("forsyth/%s/reading" % slug,
                   {"ts": uplink_mod.iso_now(), "batt_v": msg["batt_v"],
                    "rssi_dbm": rssi})


def run():
    print("forsyth coordinator — %s" % config.COORDINATOR_ID)
    _load_state()
    net = Net()
    if net.ensure(block_s=90):        # boot: give the link a real chance
        uplink_mod.ntp_sync()

    radio = E220()
    radio.configure()

    up = uplink_mod.Uplink(_on_cmd)
    up.connect()

    last_ping = last_retry = time.time()
    ntp_ok = net.isconnected
    while True:
        payload, rssi = radio.recv()
        if payload:
            try:
                _handle_frame(radio, up, payload, rssi)
            except Exception as e:
                # one bad frame must not take the fleet's ears down
                print("handle_frame: %r" % e)

        up.check_msg()
        net.ensure()                  # one repair-ladder rung when needed
        now = time.time()
        if now - last_ping > 30:
            up.ping()
            last_ping = now
        if net.isconnected and not up.connected and now - last_retry > 60:
            if not ntp_ok:            # first successful link since boot
                ntp_ok = uplink_mod.ntp_sync()
            up.connect()
            last_retry = now
        time.sleep_ms(20)


run()
