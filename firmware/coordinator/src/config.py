"""config.py — every coordinator knob. Copy to the board and edit in place
(`mpremote cp src/config.py :config.py`); no rebuild, no toolchain.

Secrets note: this file lives on the device in plain text. Keep the repo copy
holding placeholders; the real credentials only ever go onto the ESP32.
"""

# ---- identity ----------------------------------------------------------------
COORDINATOR_ID = "coordinator-01"     # mosquitto username on the droplet

# ---- WiFi ----------------------------------------------------------------------
WIFI_SSID = "CHANGE-ME"
WIFI_PASSWORD = "CHANGE-ME"

# ---- network policy (see net.py for the repair ladder) --------------------------
NETWORK = {
    "mode": "wifi",           # "wifi" | "eth" | "eth+wifi" (eth preferred,
                              #  wifi kept warm as fallback)
    "check_s": 15,            # link check + one ladder rung per this interval
    "reboot_after_s": 900,    # continuously offline this long -> machine.reset()
                              #  (the MQTT spool makes this data-safe)
    "min_rssi_dbm": -85,      # below this, RSSI logs carry a WEAK warning
    # W5500 SPI ethernet module wiring — only read in the eth modes.
    # ADJUST TO YOUR WIRING; needs a MicroPython build with network.PHY_W5500.
    "eth": {
        "spi_id": 2,
        "sck": 36, "mosi": 35, "miso": 37,
        "cs": 38, "int": 39,
        "phy_addr": 1, "baud": 20000000,
    },
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

# ---- E220 wiring on the Waveshare ESP32-S3 mini --------------------------------
# ADJUST TO YOUR WIRING. Any free GPIOs work; these avoid the strapping pins
# (GPIO0/3/45/46) and the USB pair (19/20).
LORA_PINS = {
    "uart_id": 1,
    "tx": 11,               # ESP TX  -> E220 RXD
    "rx": 12,               # ESP RX  <- E220 TXD
    "m0": 13,
    "m1": 14,
    "aux": 15,
}

# ---- behavior -------------------------------------------------------------------
ACK_TLVS_MAX = 8            # cap TLVs piggybacked on one ACK
DEDUPE_WINDOW = 32          # remembered (station, seq) pairs
SPOOL_FILE = "spool.jsonl"  # offline buffer when broker is unreachable
SPOOL_MAX_LINES = 500       # ~a day of readings for a small fleet
STATE_FILE = "state.json"   # rain-tip baselines etc., survives reboot
NTP_HOST = "pool.ntp.org"
STATUS_LOG = True           # print per-frame lines to the USB console
