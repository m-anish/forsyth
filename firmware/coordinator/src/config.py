"""config.py — every coordinator knob. Copy to the board and edit in place
(`mpremote cp src/config.py :config.py`); no rebuild, no toolchain.

Secrets note: this file lives on the device in plain text. Keep the repo copy
holding placeholders; the real credentials only ever go onto the ESP32.
"""

# ---- identity ----------------------------------------------------------------
COORDINATOR_ID = "coordinator-01"     # mosquitto username on the droplet
HOSTNAME = "forsyth"                  # → advertised as forsyth.local (mDNS is
                                      #   started by the ESP32 port for free
                                      #   once network.hostname() is set)

# ---- WiFi ----------------------------------------------------------------------
# Runtime credentials entered through the setup portal are saved to WIFI_FILE and
# WIN over these compiled defaults. Delete that file to fall back here.
#
# ⚠ SSIDs are matched byte-for-byte. iOS names hotspots with a TYPOGRAPHIC
# apostrophe (U+2019 ’), not ASCII ('): "Anish’s iPhone". Copy the SSID from a
# scan, don't retype it — this bites everyone exactly once.
WIFI_SSID = "CHANGE-ME"
WIFI_PASSWORD = "CHANGE-ME"
WIFI_FILE = "wifi.json"

# ---- network policy (see net.py for the repair ladder) --------------------------
NETWORK = {
    "mode": "wifi",           # "wifi" | "eth" | "eth+wifi" (eth preferred,
                              #  wifi kept warm as fallback)
    "check_s": 15,            # link check + one ladder rung per this interval
    "reboot_after_s": 900,    # continuously offline this long -> machine.reset()
                              #  (the MQTT spool makes this data-safe)
    "min_rssi_dbm": -85,      # below this, RSSI logs carry a WEAK warning
    "connect_wait_s": 25,     # per attempt. iOS hotspots routinely reject the
                              #  FIRST association with a bogus "wrong password"
                              #  while waking — the ladder's retry is what makes
                              #  them work, so never treat 202 as fatal.
    "ap_after_s": 120,        # no LAN for this long -> raise the setup AP (0=never)
    # W5500 SPI ethernet module wiring — only read in the eth modes.
    # ADJUST TO YOUR WIRING; needs a MicroPython build with network.PHY_W5500.
    # Same pin rules as LORA_PINS above (octal-PSRAM-safe defaults).
    "eth": {
        "spi_id": 2,
        "sck": 12, "mosi": 11, "miso": 13,
        "cs": 14, "int": 21,
        "phy_addr": 1, "baud": 20000000,
    },
    # Setup AP, raised when there's no LAN to be had. The web UI (below) runs on
    # it so you can hand over real credentials from a phone.
    "ap": {
        "ssid": "forsyth-setup",
        "password": "forsyth-setup",   # ≥8 chars, or the AP silently goes open
    },
}

# ---- on-board web UI + setup portal --------------------------------------------
# Read-only status of the device and the mesh, plus the wifi form in AP mode.
# Deliberately NOT a second dashboard: the cloud owns the data.
WEB = {
    "enabled": True,
    "port": 80,
}

# ---- bench mode ------------------------------------------------------------------
# With no LoRa module and no W5500 attached there is nothing to coordinate — so
# the board proves the REST of the chain instead: it invents a plausible station
# and publishes it to the cloud exactly as a real leaf's data would travel.
#   mode: "auto" = bench only when no peripherals are detected (the default;
#         plugging a radio in demotes it automatically)
#         "on"   = always bench, even with hardware attached
#         "off"  = never (a peripheral-less board just idles)
#   slug: MUST exist as a station in the cloud, is_simulated=True — the numbers
#         are invented and the dashboard should say so.
BENCH = {
    "mode": "auto",
    "slug": "bench",
    "interval_s": 60,
}

# ---- optional 0.96" SSD1306 OLED + status LED (I2C shares nothing above) --------
OLED = {
    "enabled": False,       # flip on when the display is fitted
    "sda": 1, "scl": 2,     # octal-PSRAM-safe; any free pair works
    "addr": 0x3C,
}
STATUS_LED_PIN = None       # e.g. 47; None = use console logging only

# ---- WS2812 status LED (on the DevKitC-1: GPIO48) ------------------------------
# One RGB pixel that shows the single most urgent unresolved state — colour =
# what, pattern = how urgent. Full scheme + priority order documented in led.py
# and firmware/coordinator/README.md. Brightness is low by default: a WS2812 at
# full tilt is a room-filling glare, and this box lives on a shelf.
RGB_LED = {
    "enabled": True,
    "pin": 48,
    "brightness": 0.15,     # 0.02–1.0
}

# ---- MQTT uplink (matches cloud/docs/deploy.md broker setup) -------------------
MQTT_HOST = "live.forsyth.starstucklab.com"
MQTT_PORT = 1883
MQTT_USER = COORDINATOR_ID
MQTT_PASSWORD = "CHANGE-ME"           # set when the broker credential is made
MQTT_KEEPALIVE = 60

# ---- station registry ----------------------------------------------------------
# unit_id (leaf STATION_ID / E220 ADDL) -> per-station facts.
#   slug            must exist as a station in the cloud (admin console creates it)
#   rain_mm_per_tip bucket calibration — lives HERE, not on the leaf, so it can
#                   be fixed without an OTA round-trip (see PROTOCOL.md bit6)
STATIONS = {
    1: {"slug": "leaf-01", "rain_mm_per_tip": 0.2794},
    # 2: {"slug": "leaf-02", "rain_mm_per_tip": 0.2794},
}

# ---- LoRa (must mirror the leaves' compiled config — PROTOCOL.md §1) -----------
LORA = {
    "channel": 15,          # 865.125 MHz; India NFAP band allows CH 15-16 only
    "air_rate": 2400,
    "tx_power_dbm": 22,
    "crypt_h": 0x0F,
    "crypt_l": 0x57,
}

# ---- E220 wiring ----------------------------------------------------------------
# ADJUST TO YOUR WIRING. Any free GPIOs work; these defaults avoid the S3's
# strapping pins (GPIO0/3/45/46), the USB pair (19/20), AND GPIO33-37 — which
# are reserved by octal PSRAM on any "R8" board (FireBeetle 2 ESP32-S3,
# DevKitC N16R8, etc.). Pins here are safe on both quad- and octal-PSRAM parts.
LORA_PINS = {
    "uart_id": 1,
    "tx": 17,               # ESP TX  -> E220 RXD
    "rx": 18,               # ESP RX  <- E220 TXD
    "m0": 8,
    "m1": 9,
    "aux": 10,
}

# ---- behavior -------------------------------------------------------------------
ACK_TLVS_MAX = 8            # cap TLVs piggybacked on one ACK
DEDUPE_WINDOW = 32          # remembered (station, seq) pairs
SPOOL_FILE = "spool.jsonl"  # offline buffer when broker is unreachable
SPOOL_MAX_LINES = 500       # ~a day of readings for a small fleet
STATE_FILE = "state.json"   # rain-tip baselines etc., survives reboot
LOCATION_FILE = "location.json"  # site-captured coordinates pending/synced to cloud
NTP_HOST = "pool.ntp.org"
NTP_EVERY_S = 6 * 3600   # re-sync cadence once the clock is set
NTP_RETRY_S = 60         # retry cadence BEFORE the first success — deliberately
                         # slow so a blocked NTP server (e.g. some phone
                         # hotspots) can't stall the main loop. The clock still
                         # works meanwhile from a preserved RTC / DS3231.
STATUS_LOG = True           # print per-frame lines to the USB console
