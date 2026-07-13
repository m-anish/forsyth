"""display.py — optional 0.96" SSD1306 OLED status panel + status LED.

Entirely optional: with config.OLED["enabled"] = False and
config.STATUS_LED_PIN = None this module is inert and the coordinator runs
headless exactly as before. Enable after fitting the hardware; a missing or
mis-wired display degrades to a console message, never a crash.

Driver comes from micropython-lib: install.sh runs `mip install ssd1306`.
"""
import time

import config


class Panel:
    def __init__(self):
        self._oled = None
        self._led = None

        o = getattr(config, "OLED", {})
        if o.get("enabled"):
            try:
                from machine import I2C, Pin
                import ssd1306
                i2c = I2C(0, sda=Pin(o["sda"]), scl=Pin(o["scl"]))
                self._oled = ssd1306.SSD1306_I2C(128, 64, i2c,
                                                 addr=o.get("addr", 0x3C))
                print("oled: online")
            except Exception as e:
                print("oled: init failed (%r) — running headless" % e)

        pin = getattr(config, "STATUS_LED_PIN", None)
        if pin is not None:
            from machine import Pin
            self._led = Pin(pin, Pin.OUT, value=0)

    def blink(self):
        """One short flash — called per received frame. Blocking 30 ms is
        fine at LoRa frame rates."""
        if self._led:
            self._led.value(1)
            time.sleep_ms(30)
            self._led.value(0)

    def show(self, lines):
        """Up to 6 lines of 16 chars on the 128x64 panel."""
        if not self._oled:
            return
        try:
            self._oled.fill(0)
            for i, line in enumerate(lines[:6]):
                self._oled.text(str(line)[:16], 0, i * 10)
            self._oled.show()
        except OSError as e:
            print("oled: write failed (%r)" % e)
