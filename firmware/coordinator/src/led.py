"""led.py — the box's only face: one WS2812, saying one true thing at a time.

The coordinator has several independent things that can be wrong at once (no
peripherals, no LAN, no broker, no clock) and exactly one LED. So the scheme is
built on two decisions:

  COLOUR says WHAT state,  PATTERN says HOW URGENT.
  The LED shows the single most urgent UNRESOLVED condition (see PRIORITY).

That priority order matters more than the palette: a box with no network and no
broker is really just "no network" — showing the deepest failure is what tells
you where to start. Once a rung is fixed the next one down surfaces on its own,
so walking the LED up from red to green is a debugging procedure you can follow
without a laptop.

  state      colour    pattern      meaning / what to do
  ---------- --------- ------------ ---------------------------------------
  BOOT       white     solid        powering up; probing peripherals
  ERROR      red       fast blink   the loop died — read the REPL
  AP         magenta   slow blink   NEEDS YOU: join "forsyth-setup", set wifi
  NO_NET     red       slow blink   no LAN; the repair ladder is climbing
  SPOOLING   amber     slow blink   LAN ok, broker unreachable — buffering
  BENCH      cyan      breathe      healthy, but the data is invented
  OK         green     breathe      healthy; listening for leaves
  (activity) white     brief blip   a frame was heard / a reading published

Breathing = alive and content. Blinking = attention. Fast = broken. A dark LED
means the firmware isn't running at all — which is itself the loudest signal.

Rendering is time-based and non-blocking: `tick()` is called from the main loop
and computes the colour for *now*. Nothing here ever sleeps — a leaf's ACK
window is measured in milliseconds and the LED does not get a vote.

Brightness defaults low on purpose. A WS2812 at full output is a room-filling
blue-white glare, and this box may end up on a shelf in someone's house.
"""
import math
import time

import config

# states, worst first — index IS the priority
ERROR, AP, NO_NET, SPOOLING, BENCH, OK, BOOT = range(7)
PRIORITY = (ERROR, AP, NO_NET, SPOOLING, BENCH, OK, BOOT)

_COLOUR = {
    BOOT:     (255, 255, 255),
    ERROR:    (255, 0, 0),
    AP:       (255, 0, 160),      # magenta: nothing else uses it → "act on me"
    NO_NET:   (255, 0, 0),
    SPOOLING: (255, 140, 0),
    BENCH:    (0, 200, 200),
    OK:       (0, 255, 60),
}


class Status:
    def __init__(self):
        self.np = None
        self._state = BOOT
        self._blip_until = 0
        self._blip_rgb = (255, 255, 255)
        self._last = None            # last bytes written; skip redundant writes

        c = getattr(config, "RGB_LED", {}) or {}
        if not c.get("enabled", True):
            return
        try:
            import neopixel
            from machine import Pin
            self.np = neopixel.NeoPixel(Pin(c.get("pin", 48), Pin.OUT), 1)
            self.brightness = min(1.0, max(0.02, c.get("brightness", 0.15)))
            self._write(_COLOUR[BOOT])
            print("led: WS2812 on GPIO%d" % c.get("pin", 48))
        except Exception as e:
            # a missing/miswired LED must never be fatal — it's decoration
            print("led: unavailable (%r)" % e)
            self.np = None

    # ---- output ------------------------------------------------------------

    def _write(self, rgb, scale=1.0):
        if self.np is None:
            return
        s = self.brightness * scale
        out = (int(rgb[0] * s), int(rgb[1] * s), int(rgb[2] * s))
        if out == self._last:
            return                    # WS2812 writes are bit-banged; don't spam
        self._last = out
        try:
            self.np[0] = out
            self.np.write()
        except OSError:
            pass

    # ---- input -------------------------------------------------------------

    def set(self, state):
        """Set the base state. Cheap to call every loop pass."""
        self._state = state

    def from_status(self, st):
        """Derive the state from the same dict the web UI serves — one source
        of truth for 'how are we doing', rendered two ways."""
        net, up = st["net"], st["uplink"]
        if net.get("ap"):
            self.set(AP)
        elif not net["connected"]:
            self.set(NO_NET)
        elif not up["connected"]:
            self.set(SPOOLING)
        elif st["mode"] == "bench":
            self.set(BENCH)
        else:
            self.set(OK)

    def blip(self, rgb=(255, 255, 255), ms=60):
        """Momentary activity flash on top of the base state."""
        self._blip_rgb = rgb
        self._blip_until = time.ticks_add(time.ticks_ms(), ms)

    # ---- render ------------------------------------------------------------

    def tick(self):
        """Call every main-loop pass. Computes the colour for this instant."""
        if self.np is None:
            return
        now = time.ticks_ms()
        if time.ticks_diff(self._blip_until, now) > 0:
            self._write(self._blip_rgb)
            return

        s, rgb = self._state, _COLOUR[self._state]
        if s in (BOOT,):                             # solid
            self._write(rgb)
        elif s == ERROR:                             # fast blink, 5 Hz
            self._write(rgb, 1.0 if (now // 100) % 2 else 0.0)
        elif s in (AP, NO_NET, SPOOLING):            # slow blink, ~1 Hz
            self._write(rgb, 1.0 if (now // 500) % 2 else 0.05)
        else:                                        # breathe, ~4 s
            phase = (now % 4000) / 4000 * 2 * math.pi
            self._write(rgb, 0.25 + 0.75 * (0.5 + 0.5 * math.sin(phase)))

    def selftest(self):
        """Walk the palette once at boot: proves the LED works and teaches the
        colours to whoever is watching. ~2 s, boot-time only."""
        if self.np is None:
            return
        for s in (ERROR, AP, NO_NET, SPOOLING, BENCH, OK):
            self._write(_COLOUR[s])
            time.sleep_ms(220)
        self._write((0, 0, 0))
        time.sleep_ms(120)
