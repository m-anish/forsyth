# Forsyth coordinator firmware — ESP32-S3, MicroPython

The always-on translator: E220 LoRa frames in, MQTT JSON out, ACKs (with
piggybacked config) back down. MicroPython on purpose — it's the lokki
lineage, the E220 discipline ports directly, and a future maintainer can edit
any behavior with `mpremote` and a text editor, no toolchain.

It also knows what to do with *nothing* attached: see [bench mode](#bench-mode).

## Install

```bash
pip install esptool mpremote

# 1. Flash MicroPython (once) — v1.28.0 verified on the N8R2 board 2026-07-17.
#    Use the STANDARD ESP32_GENERIC_S3 build: it auto-detects the 2 MB quad
#    PSRAM. (SPIRAM_OCT is only for octal-PSRAM R8 boards.)
curl -O https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin
esptool.py --chip esp32s3 --port /dev/cu.usbmodem* erase_flash
esptool.py --chip esp32s3 --port /dev/cu.usbmodem* write_flash -z 0 \
    ESP32_GENERIC_S3-20260406-v1.28.0.bin      # S3 images flash at offset 0x0
#    The native USB-Serial/JTAG port enumerates as /dev/cu.usbmodem* and
#    esptool resets into the bootloader on its own — no BOOT/RESET dance needed.
#    Confirm it took: free heap should be ~1.9 MB (that's the PSRAM).

# 2. Secrets, once per board (rotates the broker credential, registers the
#    bench station, writes config.py — nothing is printed):
./provision.sh --port /dev/cu.usbmodemXXX --ssid "Anish’s iPhone" --pass '…'

# 3. Code + deps (idempotent; never touches the device's config.py):
./install.sh --port /dev/cu.usbmodemXXX

# 4. Watch it work:
mpremote repl            # or just open http://forsyth.local/
```

## Bench mode

A coordinator with no radio has nothing to coordinate — so with **no E220 and
no W5500 detected** it invents a plausible station and publishes it down the
*real* path: same MQTT topic, broker, bridge, and database a leaf's data uses.
Everything except the radio gets exercised, months before the radio exists.

- The numbers are invented, and say so: the `bench` slug is registered
  `is_simulated=True`, so the dashboard badges it *rehearsal data*. The RSSI it
  reports is real (its own uplink), as is the chip temperature on the web page.
- Detection is positive-evidence-only — a peripheral counts as present when it
  *answers*, never because a pin floated the right way. Plug a radio in and the
  board demotes itself to normal mode on the next boot.
- Switch: `config.BENCH["mode"]` = `auto` (default) · `on` · `off`.

## Status LED (WS2812 on GPIO48)

The DevKitC-1 has one addressable RGB LED, and it's the box's only face once
it's off the bench. The scheme rests on two ideas: **colour = what, pattern =
how urgent**, and the LED shows the *single most urgent unresolved* condition.
Full logic + priority order live in [`led.py`](src/led.py).

| state | colour | pattern | meaning |
|---|---|---|---|
| boot | white | solid | powering up, probing peripherals |
| error | red | fast blink | the loop died — read the REPL |
| **setup AP** | **magenta** | slow blink | **needs you**: join `forsyth-setup`, set wifi |
| no network | red | slow blink | no LAN; the repair ladder is climbing |
| spooling | amber | slow blink | LAN ok, broker unreachable — buffering, not losing |
| bench | cyan | breathe | healthy, but the data is invented |
| ok | green | breathe | healthy; listening for leaves |
| activity | blue/green/amber | brief blip | frame heard / reading sent / reading spooled |

The priority order is the point: a box with no LAN *and* no broker shows
"no network", because that's the deeper failure and where you'd start. Fix a
rung and the next one surfaces on its own — **walking the LED red → amber →
green is a debug procedure you can run without a laptop.** Breathing = content;
blinking = attention; fast = broken; *dark = the firmware isn't running at all*,
which is itself the loudest signal.

**Boot behaviour** is deliberately calm: a single gentle fade-up to dim white
that's *held* through the whole boot, then one clean transition to the live
colour — you see exactly two states, "booting" → "running". (An earlier version
flashed all six colours on every reset and then went dark before the loop took
over; that read as noise-then-nothing, so it's gone. The palette-walk still
exists as `led.selftest()` for when you actually want the demo — call it from
the REPL.) It renders from the same status dict the web page serves — one
source of truth, shown two ways — re-derived once a second while the animation
ticks every loop pass (rendering never blocks; a leaf's ACK window doesn't get
a vote). Brightness defaults low (`config.RGB_LED`); a WS2812 at full output is
a room-filling glare and this box lives on a shelf.

## The box's own web page

`http://forsyth.local/` (mDNS is free on this port — MicroPython's ESP32 build
starts a responder as soon as `network.hostname()` is set). A single
self-contained page (inline CSS/JS, no external loads — the box may have no
internet) with two parts:

- **status tiles** — network, uplink + spool depth, clock, peripherals, chip
  temp, uptime; a header dot in the *same colour as the physical LED* so the
  two always agree.
- **live system log** — the firmware narrates itself with `print()`, and
  `logbuf.py` tees `builtins.print` at boot into a 150-line ring buffer (every
  existing log line captured, nothing retrofitted). The console polls
  `/api/logs?after=<id>` for just what's new, colours warnings/errors, and
  gives you **follow** (autoscroll — turn it off to read/select without the
  view jumping), **wrap**, **pause** (freeze polling while you work), **copy**
  (clipboard), and native text selection for grabbing individual lines.

**It is not a second weather dashboard; the cloud owns the weather.** Endpoints:
`/api/status` and `/api/logs` (both JSON). The server is non-blocking and
accepts at most one connection per main-loop pass — a browser must never delay
a leaf's ACK.

## No network? The setup portal

With no LAN for `NETWORK["ap_after_s"]` (default 120 s), the board raises an AP
(`forsyth-setup`) running the same web server, whose `/wifi` form takes real
credentials, saves them to `wifi.json`, and reboots into them. Saved credentials
beat the compiled ones; delete the file to fall back. While the portal is up the
watchdog reboot is suspended — rebooting out from under someone mid-typing would
lose the credentials.

## Timekeeping

The coordinator stamps every reading it forwards, so a wrong clock quietly
poisons the archive. `clock.py`: NTP whenever there's connectivity (at boot,
then every `NTP_EVERY_S`), mirrored into a **DS3231 if one is fitted**; with no
network at boot, the internal RTC is seeded *from* the DS3231 instead. None is
fitted today — it probes, says so, and carries on.

## Field notes (learned on real hardware, 2026-07-17)

- **iOS hotspot SSIDs contain a typographic apostrophe** (U+2019 `’`), not
  ASCII `'`. `Anish's iPhone` will never associate with `Anish’s iPhone`. Copy
  the SSID out of a scan; don't retype it.
- **iPhone hotspots reject the first association** while waking, and the ESP32
  reports it as `STAT_WRONG_PASSWORD (202)` — a lie. The retry succeeds. Never
  treat 202 as fatal; this is precisely what the repair ladder is for.
- **The radio needs ~2 s after `active(True)`** before it can see anything: an
  immediate `scan()` returns zero networks on a board that's fine.

`install.sh` re-uploads code but **never overwrites the on-device
`config.py`** (that's where the real WiFi/MQTT credentials live) unless you
pass `--force-config`. Updating deployed code is just `git pull && ./install.sh`.

The repo copy of `config.py` holds placeholders; real credentials live only on
the device. The MQTT credential is the `coordinator-01` mosquitto user created
during droplet deployment (cloud/docs/deploy.md).

## Carrier board

**Decided 2026-07-13: ESP32-S3-DevKitC-1 clone on a hand-soldered perfboard**
carrying the W5500 module and the E220. **Ordered: N8R2 variant, dual USB-C**
(quad PSRAM — GPIO 33–37 fully usable; one port is native USB, the other the
CH343 UART bridge — flash/REPL on either). Scope rationale: the
coordinator exists to push frames to the internet (and someday to config
leaves locally) — pins + USB + 3.3 V is the whole requirement; battery backup
and integrated anything were gold-plating. Socket the DevKit on female
headers; give the W5500 its own 100 nF + 10 µF at 3V3, the E220 its
100–220 µF + 100 nF at 5 V (lokki rule), antenna end away from the RJ45
magnetics.

Considered and passed over: FireBeetle 2 ESP32-S3 (nice load-sharing battery
backup — revisit only if outage-riding becomes a requirement); LILYGO
T-ETH-Lite-S3 (integrated W5500 + optional PoE, ~3× price for the same job);
XIAO S3 (pin-starved); T3-S3/Heltec V3 (SPI LLCC68 radio — wrong interface
for the E220 modules in hand).

**Octal-PSRAM warning:** on any "R8" board (DevKitC N16R8 etc.), **GPIO 33–37
are reserved by the PSRAM** — do not assign them. An N8R2 (quad PSRAM) has no
such reservation, and 2 MB PSRAM is ample here. The defaults below are safe
on both variants, and also avoid strapping pins (0/3/45/46) and the USB pair
(19/20).

## Wiring (config.py `LORA_PINS` / `NETWORK["eth"]` / `OLED`, adjust to taste)

| Module | Signal | ESP32-S3 GPIO | note |
|---|---|---|---|
| E220 | RXD | 17 (TX) | |
| E220 | TXD | 18 (RX) | |
| E220 | M0 / M1 | 8 / 9 | driven, never floated |
| E220 | AUX | 10 | input |
| E220 | VCC | 5 V | **with 100–220 µF bulk + 100 nF at the module** — the lokki rule applies to the coordinator too |
| W5500 | SCK / MOSI / MISO | 12 / 11 / 13 | |
| W5500 | CS / INT | 14 / 21 | |
| W5500 | VCC | 3.3 V | module draws ~130–180 mA |
| OLED SSD1306 | SDA / SCL | 1 / 2 | 0.96" I2C, addr 0x3C; `OLED["enabled"] = True` |
| status LED | — | `STATUS_LED_PIN` | one flash per received frame |

The OLED and LED are fully optional (`display.py` degrades to headless with a
console note); when fitted, the panel shows the last frame's slug, RSSI, leaf
battery, and uplink state — enough to diagnose a site visit without a laptop.

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

## Ethernet / PoE

For an always-on box, wired beats WiFi. `net.py` supports three modes via
`config.NETWORK["mode"]`:

- `"wifi"` — default, no extra hardware.
- `"eth"` — W5500 SPI Ethernet module (~₹300 on Robu) wired per
  `NETWORK["eth"]`. Needs a MicroPython ESP32-S3 build with SPI-Ethernet
  (`network.PHY_W5500` — probe with `hasattr(network, "PHY_W5500")` in the
  REPL); if the build lacks it, net.py says so and falls back to WiFi.
- `"eth+wifi"` — Ethernet preferred, WiFi kept warm as automatic fallback.
  The recommended endgame: two independent physical paths.

PoE without exotic hardware: an **802.3af active PoE splitter** with a 5 V
USB output powers the ESP32-S3 over the same cable the W5500 uses for data —
one wire to the box. Integrated alternatives (Olimex ESP32-POE-ISO, WIZnet
W5500-EVB-Pico) exist but change the board/port; the splitter route keeps
this firmware unmodified.

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
| WiFi/eth down | frames still ACKed; readings spool to flash; `net.py` climbs its repair ladder: reconnect → interface power-cycle → failover to the other interface (if fitted) → full `machine.reset()` after `reboot_after_s` continuously offline |
| WiFi slowly degrading | RSSI logged every 5 min, flagged WEAK below `min_rssi_dbm` — visible in the console history before it becomes an outage |
| Broker down | same — spool drains on reconnect |
| Unknown unit_id | logged loudly, dropped (add it to STATIONS) |
| Duplicate frame (leaf retry) | ACKed again, published once |
| Coordinator reboot | LWT flips availability to `offline` until reconnect; rain baselines persist in `state.json` |
| Bad/corrupt frame | logged with length + RSSI, dropped — CRC decides, not optimism |
