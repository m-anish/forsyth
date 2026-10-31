# Forsyth radio bring-up — the incremental ladder (and the war stories)

First proven end-to-end **2026-08-05**: leaf (ATtiny3226 + E220) → LoRa →
coordinator (ESP32-S3 + E220) → decoded → MQTT → live.forsyth. Getting there
took most of three sessions, and **almost none of it was firmware or config** —
it was connections and power. This doc captures the diagnostics and the traps so
the next node comes up in an hour, not a week.

## The one rule: isolate one variable at a time

Bring the radio link up as a ladder, each rung adding exactly one thing. Don't
flash the full firmware and hope — you can't tell power from wiring from config
from RF when they fail together.

| Step | What | Tool |
|---|---|---|
| 0 | Both E220s **powered** and answering config reads | `diag/probe_both.py` |
| 1–2 | Two E220s on the coordinator: **no-config loopback**, both ways | `diag/cfg_loop.py` (or `listen_default.py`) |
| 3 | Write matched config, re-test send/recv | `diag/cfg_loop.py` |
| 4 | **Coordinator TX → leaf RX** (leaf receive draws no surge) | leaf `DIAG_LORARX` + `diag/coord_tx.py` |
| 5 | **Leaf TX → coordinator RX** (adds the leaf's TX current surge) | leaf `DIAG_LORATXC` + `diag/coord_rx.py` |

Step 4 before 5 is deliberate: **RX draws no current spike**, so it proves the
RF link + leaf wiring *without* the leaf's TX brownout in the way. Step 4 pass +
Step 5 fail ⇒ it's the leaf's TX supply, not RF.

## Leaf diagnostic builds (compile flags, see `leaf/Makefile`)

- `make DIAG_BOOST=1` — hold the E220 5 V boost on so you can meter the rail.
- `make DIAG_PULSE=1` — LED blinks per **counted** rain tip (long) / anemometer
  pulse (short). Hand-tip and hand-turn tests for the two reed inputs; see the
  rain-gauge section below.
- `make DIAG_LORARX=1` — real config (`radio_ensure_nvram`) + listen. **LED status:**
  - boot = 2 blinks
  - repeating **5-blink** groups = `radio_on()` failed (power/AUX — can't reach module)
  - repeating **3-blink** groups = config echo mismatch
  - **slow heartbeat** = configured OK, listening
  - **long flash** = received a packet
- `make DIAG_LORATXC=1` — real config + transmit every ~2 s (exercises the TX surge).
- (`DIAG_LORATX=1` is the older *factory-default, no-config* TX — kept, but it does
  NOT match the leaf's real fixed-mode config; prefer `DIAG_LORATXC`.)

Coordinator scripts live in `coordinator/diag/` — copy one to `:main.py` with
mpremote and power-cycle, or `mpremote run` it. They print to the console and
blink the WS2812 (GPIO48): green = clean RX, amber = bytes but garbled (crypt/
mode mismatch), purple = transmitted.

## Rain gauge — how it actually works, and how to test it

**The leaf never zeroes the tip counter.** `v_rain_tips` is free-running and
cumulative since boot, and it wraps at 65535 on purpose (PROTOCOL.md reading
bit 6). The *coordinator* diffs consecutive packets and multiplies by
`rain_mm_per_tip`, so the `rain_mm` in any one packet means **"rain since the
previous packet"**, not a running total and not the value of one tip.

So one tip in a reporting interval = 0.279 mm in that packet; three tips in the
same interval = 0.838 mm in **one** packet, not three packets of 0.279. If you
tip three times in ten seconds on a 300 s interval, they all land in the same
report. That alone explains most "it doesn't add up" readings.

Three more ways a hand test misleads you, all by design:

1. **A leaf reboot zeroes the counter.** The coordinator sees it go backwards,
   treats any delta > 1000 tips as a reboot, and returns `None` — publishing no
   `rain_mm` at all for that interval rather than inventing a cloudburst. Tips
   from before the reboot are *gone*. If you are also fighting resets (see
   below), every reset silently eats a test.
2. **First packet after a coordinator restart re-baselines** and publishes no
   `rain_mm`.
3. `rain_mm` can be legitimately absent while the counter underneath is moving
   perfectly. **Watch `rain_tips`, not `rain_mm`** — the coordinator now prints
   it on its own `diag:` line.

### The test: `DIAG_PULSE`

```
make clean && make DIAG_PULSE=1 && make flash PORT=/dev/tty.usbserial-XXXX
```

No radio, no I2C, no sleep, no reporting — just the two pulse ISRs and the LED.
One blink = one pulse **the firmware actually credited**, debounce and all, so
you are watching the counter's truth rather than the switch's.

| | blink |
|---|---|
| rain tip (PA5) | **long**, 250 ms |
| anemometer (PA4) | **short**, 40 ms |

Hand-tip the bucket. One physical tip must give **exactly one long blink**.

- **Two blinks per tip** → the bucket rocks after tipping and carries the magnet
  past the reed twice. Raise `RAIN_DEBOUNCE_MS` (300 is the usual answer); there
  is enormous headroom, since even 300 mm/h is one tip every 3.4 s.
- **No blink** → reed, cable or pull-up, not firmware. Meter J2 pin 1 to GND.
- **Erratic** → check the RC on the gauge line before touching the constant.

Turn the cups slowly **by hand** for the anemometer. The blinks block, so this
is a hand-speed test only — a drill-spin loses counts to the LED, not to the
ISR, and must not be read as a fault.

Then reflash the real firmware and confirm the pipeline end to end:

```
make clean && make && make flash PORT=/dev/tty.usbserial-XXXX
```

Hold the button 3 s for safe mode (30 s reports for 10 minutes), tip a known
number of times inside one interval, and check the coordinator's
`diag: rain_tips=` line advanced by exactly that number. Only then look at
`rain_mm`.

## When the button stops responding

Symptom: pressing the service button does nothing — **no LED, no packet** — and
it comes back on its own after a while. You can diagnose this without a UART,
because the leaf already reports what you need.

First, split the symptom. The LED blink in the button handler fires *before*
the report is attempted, so:

- **LED blinks but no packet** → the cell is under `BATT_CRIT_MV` (2800 mV).
  The button sets `next_report = now`, the hibernate branch runs instead of
  `do_report()`, and the next attempt is pushed out `BATT_HIBERNATE_RECHECK_S`
  (600 s). It looks dead for ten minutes and then "heals" — that is the cell
  recovering, exactly as designed. Check `batt_v` in the last reading.
- **No LED at all** → the MCU is not running your press. Either it reset, or it
  is hung.

`reset_cause` and `boot_count` in every STATUS packet tell you which, and the
coordinator already prints them (`rx leaf-01 STATUS fw=… reset=XX boots=N`).
`reset_cause` is `RSTCTRL.RSTFR` straight off the silicon:

| bits | meaning | what it tells you |
|---|---|---|
| `0x01` | power-on reset | **the rail collapsed** — supply, not firmware |
| `0x02` | brown-out | only if BOD is enabled; it is OFF by default here |
| `0x08` | watchdog | something blocked >8 s |
| `0x10` | software | the deliberate 5 s button-hold hard reset |
| `0x20` | UPDI | the programmer |

If `boot_count` climbs every time the button "fails", it is resetting, and
`0x01` means the supply folded under the TX surge — the failure mode this
project has now hit with three different supplies (see the trap list above). If
`boot_count` does **not** move, it is hanging rather than resetting.

Note `BTN_RESET_HOLD_S` is 5 s and `BTN_LONG_PRESS_MS` is 3 s: hold 3–5 s and
you get safe mode (5 blinks), hold past 5 s and you get a deliberate hard reset
— which also zeroes the rain counter. A heavy-handed press is easy to mistake
for a fault.

**BOD is disabled** (`BODCFG` fuse reads `0x00`), which is why a sagging rail
produces an unresponsive hang rather than a clean reset. Enabling it would
convert this exact failure from invisible into a reported `0x02` — a deliberate
trade (the Makefile notes the soft-UVLO and BMS parachute cover undervoltage),
but worth revisiting if the hangs persist.

## The production radio config (both ends must match)

Fixed mode, RSSI byte on, **channel 15**, air **2400**, crypt **0x0F57**.
- Leaf address = its `STATION_ID` (ADDL); `radio_tx` prepends `[0x00,0x00,ch]`.
- Coordinator address = **0xFFFF (monitor mode)** so it hears every frame on the
  channel. See `leaf/src/e220.c build_regs` and `coordinator/src/e220.py`.
- The `0xC2` volatile-write reply header varies by module — some echo `0xC1`,
  some `0xC2`. `e220.py` accepts either; the register **payload** is the real proof.

## Traps that cost us days (check these FIRST)

1. **Dead 5 V header pin on cheap DevKitC clones.** The board's "5V" pin had an
   **unbridged factory power-path ("IN–OUT") jumper**, so it delivered ~1.5 V
   (back-fed through the E220's 3.3 V logic pins) while the rail itself was live
   (LDO made 3.3 V, WS2812 lit). Under-powered E220s give exactly the confusing
   `None` / `AUX-low` / one-byte-reply symptoms. **Meter the 5 V pin against a
   known 5 V point (WS2812 +) on every clone.** Bridge the jumper, or run the
   E220 off 3V3 (it's 3.3–5.5 V; lower TX power, fine for bench).
2. **Loose Dupont jumpers.** Every reseat knocked a *different* wire loose
   (E220 UART, AUX, power). **Solder the E220 header** or use short strain-relieved
   links. The wiring isn't the test — it's the noise.
3. **E220 breakout TXD/RXD labels.** Some are host-referenced ("connect your TXD
   here"), not module-referenced — the orientation that works is empirical. If a
   module answers in only one `tx/rx` orientation, wire/config to that. Confirm
   with `diag/probe_both.py` (it tries both).
4. **SerialUPDI flakiness = ground reference.** UPDI needs a solid common ground
   between the dongle and target. Give the dongle a real GND to the board (or
   power the (unloaded) target from the dongle). Don't power the *whole* leaf +
   E220 from the dongle — it can't source the radio current and browns out.
5. **T30D power footgun.** The E220 power register is *relative to module max*:
   `0b00` = 22 dBm on a T22D, **30 dBm on a T30D** — same bits. Leaf config keeps
   `LORA_TX_POWER_DBM 22` which maps to `0b00` (max), so a T30D transmits at 30 dBm
   with no change. **Do NOT "correct" it to `30`** — `pwr_bits()` has no `case 30:`,
   so it falls through to `0b11` = *minimum* power. Add `case 30: return 0b00;`
   first if you ever want the literal value in the config.

## Success looks like

`rx leaf-01  STATUS fw=0100 ... nvram_ok=1 batt=3.66V` in the coordinator log,
`frames: {'leaf-01': 1}` in `/api/status`, and (once the station is registered on
the cloud) the reading on live.forsyth.
