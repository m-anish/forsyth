"""clock.py — knowing what time it is, with or without help.

The coordinator timestamps every reading it forwards, so a wrong clock quietly
poisons the archive. Three sources, in order of trust:

  NTP        authoritative, needs the internet
  DS3931     optional battery-backed RTC on I2C — survives reboots and outages
  nothing    the ESP32's internal RTC starts at 2000-01-01 and drifts

Policy (per the brief): sync from NTP whenever there's connectivity, and keep
the internal RTC — and the DS3231 if one is fitted — up to date from it. With
no network at boot, seed the internal RTC *from* the DS3231 so timestamps are
still sane. With neither, we say so loudly rather than inventing the year 2000.

The DS3231 is optional on purpose: none is fitted today, so `present()` just
reports False and everything still works.
"""
import time

import machine

import config

DS3231_ADDR = 0x68


def _bcd2dec(b):
    return (b >> 4) * 10 + (b & 0x0F)


def _dec2bcd(d):
    return ((d // 10) << 4) | (d % 10)


class Clock:
    def __init__(self):
        self.rtc = machine.RTC()
        self.ds = None            # DS3231 I2C handle, when one answers
        self.synced = False       # NTP has landed at least once this boot
        self.last_sync = 0
        self._probe_ds3231()

    # ---- DS3231 (optional) -------------------------------------------------

    def _probe_ds3231(self):
        o = getattr(config, "OLED", {}) or {}
        try:
            from machine import I2C, Pin
            i2c = I2C(0, sda=Pin(o.get("sda", 1)), scl=Pin(o.get("scl", 2)))
            if DS3231_ADDR in i2c.scan():
                self.ds = i2c
                print("clock: DS3231 present at 0x68")
            else:
                print("clock: no DS3231 — internal RTC + NTP only")
        except Exception as e:
            print("clock: I2C probe failed (%r) — internal RTC + NTP only" % e)

    def present(self):
        return self.ds is not None

    def _ds_read(self):
        b = self.ds.readfrom_mem(DS3231_ADDR, 0x00, 7)
        return (2000 + _bcd2dec(b[6]), _bcd2dec(b[5] & 0x1F), _bcd2dec(b[4]),
                _bcd2dec(b[2] & 0x3F), _bcd2dec(b[1]), _bcd2dec(b[0] & 0x7F))

    def _ds_write(self, t):
        yr, mo, dy, hh, mm, ss = t[0], t[1], t[2], t[3], t[4], t[5]
        self.ds.writeto_mem(DS3231_ADDR, 0x00, bytes([
            _dec2bcd(ss), _dec2bcd(mm), _dec2bcd(hh), 1,
            _dec2bcd(dy), _dec2bcd(mo), _dec2bcd(yr - 2000)]))

    # ---- public ------------------------------------------------------------

    def seed_from_rtc(self):
        """No network yet: take what the DS3231 remembers, if anything."""
        if self.ds is None:
            return False
        try:
            y, mo, d, h, mi, s = self._ds_read()
            if y < 2024:                     # unset/dead battery — don't trust it
                print("clock: DS3231 reads %04d — ignoring (unset?)" % y)
                return False
            self.rtc.datetime((y, mo, d, 0, h, mi, s, 0))
            print("clock: seeded from DS3231 → %04d-%02d-%02d %02d:%02d:%02dZ"
                  % (y, mo, d, h, mi, s))
            return True
        except OSError as e:
            print("clock: DS3231 read failed (%r)" % e)
            return False

    def ntp_sync(self):
        """Pull time from NTP into the internal RTC, and mirror it into the
        DS3231 when one is fitted. Returns True on success."""
        import ntptime
        ntptime.host = getattr(config, "NTP_HOST", "pool.ntp.org")
        for _ in range(3):
            try:
                ntptime.settime()
                self.synced = True
                self.last_sync = time.time()
                t = time.gmtime()
                print("clock: NTP ok → %04d-%02d-%02d %02d:%02d:%02dZ" % t[:6])
                if self.ds is not None:
                    try:
                        self._ds_write(t)
                        print("clock: DS3231 updated from NTP")
                    except OSError as e:
                        print("clock: DS3231 write failed (%r)" % e)
                return True
            except (OSError, OverflowError):
                time.sleep(2)
        print("clock: NTP sync failed")
        return False

    def maybe_resync(self, connected):
        """Called from the main loop; re-syncs on the configured cadence (and
        as soon as connectivity returns if we've never synced)."""
        if not connected:
            return
        every = getattr(config, "NTP_EVERY_S", 6 * 3600)
        if not self.synced or time.time() - self.last_sync > every:
            self.ntp_sync()

    def iso(self):
        t = time.gmtime()
        return "%04d-%02d-%02dT%02d:%02d:%02dZ" % t[:6]

    def status(self):
        return {"utc": self.iso(), "ntp_synced": self.synced,
                "ds3231": self.present(),
                "last_sync_s_ago": (int(time.time() - self.last_sync)
                                    if self.last_sync else None)}
