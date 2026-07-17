"""bench.py — what the coordinator does with no radio and no ethernet attached.

A coordinator with no E220 has nothing to coordinate, which makes it useless for
proving the thing you actually want to prove early: that this board, on this
network, can reach the cloud and land a reading on the dashboard. So when no
peripherals answer, it invents a plausible station and publishes it down the
real path — same MQTT topic, same JSON, same broker, same bridge, same database.
Everything except the radio is exercised for real.

The numbers are honest about being invented: the bench slug is registered
is_simulated=True, so the dashboard badges it "rehearsal data". The two values
that ARE genuinely measured — the chip's own temperature and the WiFi RSSI —
are reported as such (`rssi_dbm`, and mcu temp on the web status page).

Detection is deliberately positive-evidence-only: a peripheral counts as
present when it *answers*, never merely because a pin floats the right way.
"""
import math
import time

import config


def probe_lora():
    """True only if an E220 echoes a register read. Nothing attached → the UART
    reads silence → False, which is exactly the bench-mode trigger."""
    try:
        from e220 import E220
        radio = E220()
        return bool(radio.configure())
    except Exception as e:
        print("bench: LoRa probe failed (%r)" % e)
        return False


def probe_eth():
    """True if a W5500 answers with its VERSIONR (always 0x04). Skipped unless
    the config actually wants ethernet — no point clocking SPI otherwise."""
    if _cfg_net("mode", "wifi") == "wifi":
        return False
    e = _cfg_net("eth", {}) or {}
    try:
        from machine import SPI, Pin
        cs = Pin(e["cs"], Pin.OUT, value=1)
        spi = SPI(e.get("spi_id", 2), baudrate=1000000, sck=Pin(e["sck"]),
                  mosi=Pin(e["mosi"]), miso=Pin(e["miso"]))
        cs.value(0)
        spi.write(bytes([0x00, 0x39, 0x00]))   # VERSIONR, common-register read
        ver = spi.read(1)[0]
        cs.value(1)
        return ver == 0x04
    except Exception as e:
        print("bench: eth probe failed (%r)" % e)
        return False


def _cfg_net(key, default):
    return getattr(config, "NETWORK", {}).get(key, default)


def decide(peripherals):
    """bench mode on/off, honouring the config switch."""
    mode = getattr(config, "BENCH", {}).get("mode", "auto")
    if mode == "on":
        return True
    if mode == "off":
        return False
    return not (peripherals["lora"] or peripherals["eth"])


class Bench:
    """Invents one station's weather. Cheap, deterministic-ish, and shaped like
    a Himalayan day rather than pure noise, so the dashboard's charts and the
    summary endpoint have something plausible to chew on."""

    def __init__(self, clock, net):
        self._clock = clock
        self._net = net
        self._t0 = time.time()
        self._rain_mm = 0.0
        self._last = 0
        b = getattr(config, "BENCH", {})
        self.slug = b.get("slug", "bench")
        self.interval = b.get("interval_s", 60)

    def mcu_temp(self):
        try:
            import esp32
            return round(esp32.mcu_temperature(), 1)
        except Exception:
            return None

    def _wave(self, period_s, phase=0.0):
        return math.sin((time.time() - self._t0) / period_s * 2 * math.pi + phase)

    def due(self):
        return time.time() - self._last >= self.interval

    def reading(self):
        """One synthetic reading, plus the genuinely-measured RSSI."""
        self._last = time.time()
        t = time.gmtime()
        hour = t[3] + t[4] / 60.0                      # UTC; good enough here

        # diurnal temperature, coolest ~05:00, warmest ~14:00
        temp = 18.0 + 7.0 * math.sin((hour - 9.5) / 24 * 2 * math.pi)
        rh = max(25.0, min(97.0, 70.0 - 1.8 * (temp - 18.0) + 6 * self._wave(900)))
        pressure = 79500 + 120 * self._wave(3600)      # ~2000 m, gentle tide
        wind = max(0.0, 2.2 + 1.8 * self._wave(420, 1.1))
        gust = wind * (1.5 + 0.4 * abs(self._wave(90)))
        wdir = (180 + 60 * self._wave(1800)) % 360

        # rain arrives in spells rather than as a drizzle of random numbers
        wet = self._wave(2700, 2.0)
        if wet > 0.65:
            self._rain_mm += 0.2

        r = {
            "ts": self._clock.iso(),
            "temp_c": round(temp, 2),
            "rh": round(rh, 1),
            "pressure_pa": round(pressure),
            "wind_avg_ms": round(wind, 2),
            "wind_gust_ms": round(gust, 2),
            "wind_dir_deg": round(wdir, 1),
            "rain_mm": round(0.2 if wet > 0.65 else 0.0, 2),
            "pm25": round(max(3.0, 18 + 12 * self._wave(5400)), 1),
            "pm10": round(max(5.0, 31 + 18 * self._wave(5400, 0.3)), 1),
            "batt_v": round(3.30 + 0.04 * self._wave(7200), 3),
            "solar_state": "charging-allowed",
        }
        # real measurement: the uplink's own signal strength
        st = self._net.status()
        if st.get("rssi") is not None:
            r["rssi_dbm"] = st["rssi"]
        return r
