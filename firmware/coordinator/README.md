# Forsyth coordinator firmware — ESP32-S3 (Waveshare mini), MicroPython

The always-on translator: E220 LoRa frames in, MQTT JSON out, ACKs (with
piggybacked config) back down. MicroPython on purpose — it's the lokki
lineage, the E220 discipline ports directly, and a future maintainer can edit
any behavior with `mpremote` and a text editor, no toolchain.

## Install

```bash
# 1. Flash MicroPython (once): https://micropython.org/download/ESP32_GENERIC_S3/
#    esptool.py --chip esp32s3 write_flash 0 ESP32_GENERIC_S3-*.bin
# 2. Dependencies + code:
mpremote mip install umqtt.simple
mpremote cp src/config.py src/protocol.py src/e220.py src/uplink.py \
            src/main.py src/boot.py :
# 3. Edit the on-device config (WiFi, MQTT password, station map, LoRa pins):
mpremote edit config.py
mpremote reset
# 4. Watch it work:
mpremote repl
```

The repo copy of `config.py` holds placeholders; real credentials live only on
the device. The MQTT credential is the `coordinator-01` mosquitto user created
during droplet deployment (cloud/docs/deploy.md).

## Wiring (config.py `LORA_PINS`, adjust to taste)

| E220 pin | ESP32-S3 GPIO | note |
|---|---|---|
| RXD | 11 (TX) | |
| TXD | 12 (RX) | |
| M0 | 13 | driven, never floated |
| M1 | 14 | driven, never floated |
| AUX | 15 | input |
| VCC | 5 V | **with 100–220 µF bulk + 100 nF at the module** — the lokki rule applies to the coordinator too |
| GND | GND | |

Defaults avoid the S3's strapping pins (0/3/45/46) and USB pins (19/20).

## Data flow

```
leaf ──LoRa──► E220 ──► protocol.parse ──► dedupe(seq) ──► JSON ──► MQTT broker
                 │                                            │        (droplet)
                 ◄── ACK + pending TLVs (≤1 per uplink) ◄─────┘
                                                    forsyth/<slug>/cmd
```

- **ACK before anything else**: the leaf holds its radio on for ~1.5 s after
  TX and then cuts power. Network work happens after the ACK is out.
- **Timestamps**: coordinator stamps `ts` at receipt (NTP). Lightning frames
  carry `age_s`, so a strike queued on the leaf still gets a truthful time.
- **Rain**: leaves send cumulative tip counts; this side diffs them
  (wrap-aware, reboot-tolerant) and applies `rain_mm_per_tip` from
  `config.STATIONS`. Fixing a bucket calibration = edit config, no mast trip.
- **Offline spool**: broker unreachable → readings buffer to flash JSONL and
  drain on reconnect. WiFi wobble costs latency, not data.
- **Remote leaf config**: publish JSON to `forsyth/<slug>/cmd` — key map in
  `protocol.tlvs_from_cmd()` docstring, wire semantics in
  [`../PROTOCOL.md`](../PROTOCOL.md). Example, from anywhere with mosquitto
  credentials:

  ```bash
  mosquitto_pub -h live.forsyth.starstucklab.com -u forsyth-api -P '…' \
    -t forsyth/leaf-01/cmd \
    -m '{"report_interval_s": 600, "as3935": {"noise_floor": 3}}'
  ```

  The TLVs ride the next ACK to that leaf — so they take effect within one
  report interval, not instantly.

## Adding a leaf

1. Flash the leaf with a fresh `STATION_ID` (leaf Makefile).
2. Create the station in the cloud admin console → note its slug.
3. Add `unit_id: {"slug": …, "rain_mm_per_tip": …}` to `config.STATIONS`,
   `mpremote cp` + reset.
4. The leaf's boot STATUS should appear in the coordinator log within one
   power cycle; the dashboard's health widget shows it once readings flow.

## Failure behavior (designed, not accidental)

| Failure | Behavior |
|---|---|
| WiFi down | frames still ACKed; readings spool to flash |
| Broker down | same — spool drains on reconnect |
| Unknown unit_id | logged loudly, dropped (add it to STATIONS) |
| Duplicate frame (leaf retry) | ACKed again, published once |
| Coordinator reboot | LWT flips availability to `offline` until reconnect; rain baselines persist in `state.json` |
| Bad/corrupt frame | logged with length + RSSI, dropped — CRC decides, not optimism |
