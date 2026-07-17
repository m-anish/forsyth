"""main.py — Forsyth coordinator: LoRa in, MQTT out, ACKs + config back down.

Loop shape: poll the E220 for a frame → validate/dedupe → ACK immediately
(the leaf's RX window is short and its radio is about to be unpowered — the
ACK cannot wait for the network) → translate to JSON → publish (or spool).

Pending config for a leaf (from forsyth/<slug>/cmd) rides on the next ACK to
that leaf; there is no other downlink opportunity by design.

Everything else in the loop is subordinate to that timing: the web server
accepts at most one connection per pass, the network ladder does at most one
rung per check_s, and NTP only re-syncs on a slow cadence. Nothing here may
block, or a leaf somewhere misses its ACK and burns a retry.

With no peripherals attached the box runs in BENCH mode (bench.py): it invents
a station and publishes it down the real path, so the network/uplink half can
be proven long before the radio hardware exists.
"""
import json
import time

import bench as bench_mod
import clock as clock_mod
import config
import display
import led as led_mod
import protocol
import uplink as uplink_mod
from e220 import E220
from net import Net
from webserver import Web

# the one status LED, created early so a crash anywhere still gets a red light
_led = led_mod.Status()

# unit_id -> pending TLV bytes, delivered on next uplink from that leaf
_pending_tlvs = {}
# unit_id -> last seq seen (dedupe of TX retries)
_last_seq = {}
# optional OLED/LED panel + per-slug frame counter for its display
_panel = None
_frames = {}
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

    _frames[slug] = _frames.get(slug, 0) + 1
    _led.blip((0, 120, 255))          # blue blip: a leaf was heard
    if _panel:
        _panel.blink()
        _panel.show(["forsyth coord",
                     "%s #%d" % (slug, _frames[slug]),
                     "rssi %d dBm" % rssi,
                     "batt %.2fV" % msg.get("batt_v", 0),
                     "net %s" % ("up" if up.connected else "SPOOL")])

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
    global _panel
    boot_t = time.time()
    print("forsyth coordinator — %s" % config.COORDINATOR_ID)
    _led.set(led_mod.BOOT)
    _led.boot_glow()                  # calm fade-up, held white through boot
    _load_state()
    _panel = display.Panel()
    _panel.show(["forsyth coord", config.COORDINATOR_ID, "starting..."])

    # Clock before network: with a DS3231 fitted we get sane timestamps even if
    # the LAN never shows up. NTP overrides it the moment we're online.
    clock = clock_mod.Clock()
    clock.seed_from_rtc()

    # What's actually attached? Probe before the radio is used in anger.
    peripherals = {"lora": bench_mod.probe_lora(), "eth": bench_mod.probe_eth()}
    bench_on = bench_mod.decide(peripherals)
    print("boot: peripherals lora=%s eth=%s → %s mode"
          % (peripherals["lora"], peripherals["eth"],
             "BENCH" if bench_on else "normal"))

    net = Net()
    net.ensure(block_s=90)            # boot: give the link a real chance
    clock.maybe_resync(net.isconnected)

    radio = None
    if peripherals["lora"]:
        radio = E220()
        radio.configure()
    elif not bench_on:
        print("boot: no radio and bench mode off — idling (web UI still up)")

    bench = bench_mod.Bench(clock, net) if bench_on else None
    up = uplink_mod.Uplink(_on_cmd)
    up.connect()

    def _status():
        return {
            "id": config.COORDINATOR_ID,
            "mode": "bench" if bench_on else "normal",
            "uptime_s": int(time.time() - boot_t),
            "net": net.status(),
            "clock": clock.status(),
            "uplink": {"connected": up.connected, "spooled": up.spooled,
                       "host": config.MQTT_HOST},
            "peripherals": peripherals,
            "mcu_temp": (bench or bench_mod.Bench(clock, net)).mcu_temp(),
            "frames": _frames,
        }

    def _on_wifi(ssid, password):
        from net import save_wifi_creds
        save_wifi_creds(ssid, password)
        print("web: new credentials for %r saved — rebooting into them" % ssid)
        import machine
        time.sleep(1)
        machine.reset()

    # slugs this coordinator can locate: its mapped leaves + the bench station
    _slugs = [s["slug"] for s in config.STATIONS.values()]
    if bench is not None and bench.slug not in _slugs:
        _slugs.append(bench.slug)
    from location import LocationManager
    loc = LocationManager(up, _slugs)

    web = Web(_status, _on_wifi, loc)

    _led.from_status(_status())       # settle straight from 'booting' to the
    _led.tick()                       # real state — no lingering white
    last_ping = last_retry = last_led = last_locsync = time.time()
    while True:
        if radio is not None:
            payload, rssi = radio.recv()
            if payload:
                try:
                    _handle_frame(radio, up, payload, rssi)
                except Exception as e:
                    # one bad frame must not take the fleet's ears down
                    print("handle_frame: %r" % e)

        if bench is not None and bench.due():
            r = bench.reading()
            ok = up.publish("forsyth/%s/reading" % bench.slug, r)
            _led.blip((0, 255, 60) if ok else (255, 140, 0))  # green sent / amber spooled
            print("bench: %s %s → %s" % (bench.slug,
                                         "published" if ok else "spooled",
                                         {k: r[k] for k in ("temp_c", "rh",
                                                            "wind_avg_ms")}))
            if _panel:
                _panel.blink()
                _panel.show(["forsyth bench", bench.slug,
                             "%.1f C" % r["temp_c"],
                             "net %s" % ("up" if up.connected else "SPOOL")])

        web.poll()                    # at most one request; never blocks
        up.check_msg()
        net.ensure()                  # one repair-ladder rung when needed
        clock.maybe_resync(net.isconnected)
        _led.tick()                   # render this instant's colour every pass
        now = time.time()
        if now - last_led >= 1:       # re-derive the base state once a second —
            _led.from_status(_status())  # cheaper than rebuilding status at 50 Hz
            last_led = now
        if now - last_ping > 30:
            up.ping()
            last_ping = now
        if net.isconnected and not up.connected and now - last_retry > 60:
            up.connect()
            last_retry = now
        if now - last_locsync > 15:   # push any site-captured coords once online
            loc.sync_pending()
            last_locsync = now
        time.sleep_ms(20)


run()
