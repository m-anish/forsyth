"""net.py — network interface manager with an escalating repair ladder.

The coordinator is always-on; a link that quietly dies at 3 am must repair
itself without anyone noticing. Philosophy: try the cheap fix first, escalate
only when the cheap fix keeps failing, and treat a full reboot as a legitimate
tool of last resort (the MQTT spool means a reboot costs seconds of latency,
not data).

The ladder (per config.NETWORK["check_s"] tick while disconnected):
  streak 1   reconnect      re-issue connect() on the active interface
  streak 2   cycle          interface active(False) → active(True) → connect
  streak 3   failover       switch to the other interface, if one exists
  streak 4+  cycle & retry  alternate cycle/connect on whichever remains
  offline > reboot_after_s  machine.reset() — the nuclear option, spool-safe

Interfaces, per config.NETWORK["mode"]:
  "wifi"      STA only (the default; matches the original behavior)
  "eth"       W5500 SPI Ethernet only
  "eth+wifi"  Ethernet preferred, WiFi as warm fallback

Ethernet needs a MicroPython ESP32 build with SPI-Ethernet support
(network.PHY_W5500 — present in recent ESP32_GENERIC_S3 builds; we probe with
hasattr and fall back to WiFi loudly if absent, so a wrong firmware build
degrades to the old behavior instead of crashing).
"""
import time

import machine
import network

import config


def _cfg(key, default):
    return getattr(config, "NETWORK", {}).get(key, default)


class Net:
    def __init__(self):
        self._wlan = None
        self._eth = None
        self._active = None          # the interface currently in use
        self._streak = 0             # consecutive failed repair ticks
        self._offline_since = None   # time.time() when we noticed the outage
        self._last_tick = 0
        self._last_rssi_log = 0

        mode = _cfg("mode", "wifi")
        if mode in ("eth", "eth+wifi"):
            self._eth = self._init_eth()
            if self._eth is None and mode == "eth":
                print("net: eth-only requested but eth init failed — "
                      "enabling WiFi so the box stays reachable")
        if mode in ("wifi", "eth+wifi") or self._eth is None:
            self._wlan = network.WLAN(network.STA_IF)
            self._wlan.active(True)
        self._active = self._eth if self._eth is not None else self._wlan

    # ---- interface helpers -------------------------------------------------

    def _init_eth(self):
        e = _cfg("eth", None)
        if not e:
            print("net: mode wants ethernet but NETWORK['eth'] is missing")
            return None
        if not hasattr(network, "PHY_W5500"):
            print("net: this MicroPython build lacks SPI-Ethernet "
                  "(network.PHY_W5500) — flash a recent ESP32_GENERIC_S3 build")
            return None
        try:
            from machine import SPI, Pin
            spi = SPI(e["spi_id"], baudrate=e.get("baud", 20000000),
                      sck=Pin(e["sck"]), mosi=Pin(e["mosi"]),
                      miso=Pin(e["miso"]))
            lan = network.LAN(spi=spi, phy_type=network.PHY_W5500,
                              phy_addr=e.get("phy_addr", 1),
                              cs=Pin(e["cs"]), int=Pin(e["int"]))
            lan.active(True)
            print("net: W5500 ethernet up (mac %s)"
                  % ":".join("%02x" % b for b in lan.config("mac")))
            return lan
        except Exception as ex:
            # Broad on purpose: LAN() kwarg names have shifted between
            # MicroPython releases — degrade to WiFi, don't crash the box.
            print("net: eth init failed (%r) — check wiring/pins/µPy version"
                  % ex)
            return None

    def _name(self, iface):
        return "eth" if iface is self._eth else "wifi"

    def _connect(self, iface):
        if iface is self._wlan:
            iface.active(True)
            if not iface.isconnected():
                iface.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        # ethernet: DHCP starts on active(True); nothing else to do

    def _cycle(self, iface):
        print("net: cycling %s interface" % self._name(iface))
        try:
            iface.active(False)
        except OSError:
            pass
        time.sleep(1)
        iface.active(True)
        self._connect(iface)

    def _other(self):
        if self._eth is not None and self._wlan is not None:
            return self._wlan if self._active is self._eth else self._eth
        return None

    # ---- public ------------------------------------------------------------

    @property
    def isconnected(self):
        try:
            return self._active.isconnected()
        except OSError:
            return False

    def ensure(self, block_s=0):
        """Call from the main loop (cheap; rate-limits itself to check_s).
        Runs one rung of the repair ladder per tick while disconnected.
        block_s > 0: keep working the ladder for up to that long (boot path).
        Returns current connectivity."""
        deadline = time.time() + block_s
        while True:
            self._tick()
            if self.isconnected or time.time() >= deadline:
                return self.isconnected
            time.sleep(1)

    def _tick(self):
        now = time.time()
        if now - self._last_tick < _cfg("check_s", 15):
            return
        self._last_tick = now

        if self.isconnected:
            if self._streak or self._offline_since:
                print("net: %s link restored (ip %s)"
                      % (self._name(self._active),
                         self._active.ifconfig()[0]))
            self._streak = 0
            self._offline_since = None
            self._log_rssi(now)
            return

        # --- disconnected: climb the ladder ---
        if self._offline_since is None:
            self._offline_since = now
        self._streak += 1
        offline_for = now - self._offline_since
        print("net: %s down (streak %d, %ds offline)"
              % (self._name(self._active), self._streak, offline_for))

        if offline_for > _cfg("reboot_after_s", 900):
            print("net: offline past reboot_after_s — machine.reset() "
                  "(spool has the data)")
            time.sleep(1)
            machine.reset()

        if self._streak == 1:
            self._connect(self._active)
        elif self._streak == 2:
            self._cycle(self._active)
        elif self._streak == 3 and self._other() is not None:
            self._active = self._other()
            print("net: failing over to %s" % self._name(self._active))
            self._connect(self._active)
        else:
            # keep alternating: cycle current, and if there is another
            # interface, swap to it every other tick
            other = self._other()
            if other is not None and self._streak % 2 == 0:
                self._active = other
                print("net: trying %s again" % self._name(self._active))
            self._cycle(self._active)

    def _log_rssi(self, now):
        """Every 5 min on WiFi: log signal so a slowly-dying link is visible
        in the console history before it becomes an outage."""
        if self._active is not self._wlan or now - self._last_rssi_log < 300:
            return
        self._last_rssi_log = now
        try:
            rssi = self._wlan.status("rssi")
        except (OSError, ValueError):
            return
        warn = " — WEAK (below min_rssi_dbm)" \
            if rssi < _cfg("min_rssi_dbm", -85) else ""
        print("net: wifi rssi %d dBm%s" % (rssi, warn))
