# Forsyth leaf firmware — ATtiny3226 (Board A)

Bare-metal C, no RTOS, no Arduino layer. ~2 KB of the 32 KB flash budget is
personality; the rest is negotiation with the physical world. Read
[`../PROTOCOL.md`](../PROTOCOL.md) first — it is the contract this code implements.

## Orientation for a future maintainer (human or AI)

| You want to… | Go to |
|---|---|
| change a pin after a board rev | `src/pins.h` — the only file with port/bit facts |
| tune anything (intervals, calibration, thresholds) | `src/config.h` — every knob, each marked `[C]`ompile / `[E]`EPROM-OTA / `[B]`ench |
| change the wire format | `../PROTOCOL.md` **first**, then `src/protocol.h` + `coordinator/src/protocol.py` in the same commit |
| understand the duty cycle | `src/main.c` header comment, then `do_report()` |
| add a sensor | driver in its own file; ISRs only count/flag, all bus traffic from the main loop |

Hardware context you must not violate (from `hardware/boards/board-a-core.md`):

1. **The UART is shared** between the E220 radio and the PMS7003, each behind its
   own gated boost. One rail at a time — `hal.c`'s `rail_*` functions are the only
   legal way to switch them, and they encode the ordering rules (TX low before EN
   drop; PB3 pull-up whenever both rails are down).
2. **The E220 is power-gated**, so its RAM registers evaporate every cycle. Config
   lives in module **NVRAM**, burned once by `radio_ensure_nvram()` (re-burned only
   when the compiled radio settings change). The lokki discipline — M0/M1 driven
   before power, AUX-high + 2 ms before UART, two-edge AUX waits — is implemented
   in `e220.c` and is not optional; removing any of it re-creates lokki's
   100-second boot hang.
3. **CHG_INHIBIT (PA3) fails safe to "charging allowed"** (100 k pulldown). The
   policy code only ever asserts it on positive evidence (temperature genuinely
   below the LiFePO4 limit, or an explicit OTA command).
4. **PB4 is a button, not reset** (silkscreen lies). Short press = read + transmit
   now. Hold 3 s = safe mode: compiled defaults, 30 s cadence, 10 minutes.
5. The MCU runs at **5 MHz** so it stays in spec at any cell voltage the BMS
   permits. If you raise the clock, re-check the datasheet's frequency-vs-VDD
   envelope at 2.5 V.

## Sensor tuning — where each number lives

- **Wind speed**: `ANEMO_MS_PER_HZ_X1000`, **667** for the SparkFun SEN-15901
  cup set — its datasheet closes the reed once per second at 2.4 km/h, i.e.
  0.6667 m/s per Hz. It was 2400 (a Davis-style default that read that 2.4 as
  m/s), which over-reported this meter by **3.6x**. Pulses are counted in the
  PA4 ISR (falling edges, noise-gated), bucketed per `WIND_GATE_S` seconds;
  gust = max bucket, average = whole interval. The datasheet's Chinese text
  contradicts its English, claiming 0.33 m/s per closure — exactly half, which
  would hold only for a rotor closing the reed twice per turn. **This rotor
  closes once per revolution (confirmed 2026-10-31), so 667 is calibrated, not
  assumed.** What remains unverified is cup aerodynamics, which needs a
  side-by-side against a reference anemometer in steady wind; `667` is the
  manufacturer's figure for an undamaged rotor. OTA-settable (TLV 0x06).
- **Wind direction**: `VANE_LUT_DEFAULT` in config.h, **bench-measured
  2026-10-31** and no longer computed. The vane is a SparkFun SEN-15901 /
  Fine Offset 16-position unit wired as its datasheet's example circuit: vane
  from `J3.1` VBAT to `J3.3` VANE_ADC, **7.5 k 1 % pulldown** to GND at the
  connector. The eight single-reed positions were read off the real vane; the
  eight between-reed positions (two reeds closed = two resistors in parallel)
  are derived from those neighbours in ratio space, so they carry the same
  calibration and assume no resistor value at all. Measured came in +5…+8
  counts above the datasheet prediction — an implied divider of ~7.59 k, the
  fitted part ~1.2 % high, which is the signature of a healthy divider; a
  *scattered* offset would mean a bad reed or a cable fault. `VANE_CODE()` and
  `VANE_DIV_R_OHMS` survive only to regenerate the table if you refit a
  different pulldown. `VANE_WINDOW` is 23, half the one tight gap (E/ENE).
- **Lightning sensitivity**: `AS3935_*` knobs — noise floor, watchdog, spike
  rejection, min strikes, indoor/outdoor gain, disturber masking. All six are in
  one OTA TLV (0x03), because tuning an AS3935 is *always* an iterative field
  job. Watch the `ltg_stats` diagnostic triple (strikes/disturbers/noise) in
  readings to see what the sensor is actually experiencing. `AS3935_TUNING_CAP`
  is bench-only: antenna resonance must hit 500 kHz ±3.5 %.
- **Temperature**: `SHTC3_TEMP_OFFSET_X100` (OTA, TLV 0x04) for the reported
  reading; `MCU_TEMP_OFFSET_X100` for the internal sensor that gates charging —
  bench-check the latter near 0 °C, it protects the battery. **The conversion
  itself was wrong until 2026-10-31**: the factory calibration is defined
  against a *10-bit* reading and the code fed it the raw 12-bit result scaled
  by 4096, compressing the whole scale 4x (a real ~30 °C reported as −200 °C).
  Shift to 10 bits first, then `(adc - offset) * slope`, `+0x80`, `>>8`, with
  the 1.024 V reference the calibration is tied to. If `mcu_temp_c` ever looks
  like a round, absurd number again, suspect the scaling before the sensor.
- **Charge inhibit** (`CHG_*`, OTA TLV 0x05): in `CHG_MODE_AUTO` the leaf
  asserts `CHG_INHIBIT` **below `CHG_LOW_LIMIT_C` (0 °C)** and releases at
  **limit + `CHG_HYSTERESIS_C` (+2 °C)**; `CHG_MODE_INHIBIT` forces it on and
  `CHG_MODE_ALLOW` forces it off. That flag is what the dashboard shows as
  `solar_state: inhibited` (coordinator `main.py` maps `F_CHG_INHIBIT`
  → `"inhibited"` / `"charging-allowed"`), so **a leaf reporting "inhibited" at
  room temperature is reporting a bad temperature, not a cold one.**
  Readings outside `MCU_TEMP_SANE_*` are now treated as sensor doubt and
  **allow** charging, matching the hardware pulldown — a guard, not a
  calibration. **Diagnose with `mcu_temp_c`**, which verbose readings already
  carry: watch the coordinator's `STATUS_LOG` line or the MQTT
  `forsyth/<slug>/reading` topic, since the cloud currently drops the field
  (it is not in `READING_FIELDS`, `cloud/api/app/ingest.py`).
- **Rain**: the leaf ships raw cumulative tips; mm-per-tip lives in the
  coordinator's per-station config (see PROTOCOL.md for why).
- **Battery**: `VBAT_DIV_NUM` — measure your actual 1 M/330 k parts.
- **Battery taper** (`BATT_TAPER_*`): the interval multiplies as the cell
  empties — ×2 below 3.15 V, ×4 below 3.05 V, ×8 below 2.95 V — instead of
  running at full cadence up to `BATT_CRIT_MV` and stopping dead. Because the
  multiplier scales `REPORT_INTERVAL_S`, AQI (every Nth report) slows with it.
  The step tightens the moment a threshold is crossed and only relaxes once the
  reading clears it by `BATT_TAPER_HYST_MV`, so the sag under a TX burst cannot
  oscillate it. Sampled from the **resting** voltage: radio off, before the PMS
  load. Set `BATT_TAPER_ENABLE 0` for the old cliff behaviour.
  **[B] The thresholds are guesses against LiFePO4's flat plateau — re-cut them
  from a real discharge curve for the cell in service.** Nothing is added to the
  payload: the cloud has `batt_mv` in every reading and can derive the step
  (all 8 flag bits are already spoken for).

## Build & flash

Two equivalent routes, same `src/`, same output:

- **Makefile** (reference build — verified with avr-gcc 14.3): toolchain setup
  in the Makefile header. `make STATION_ID=2 && make flash PORT=/dev/tty.usbserial-…`
- **PlatformIO in VSCode**: open *this folder* (`firmware/leaf/`) as the
  project; `platformio.ini` is pre-configured (`atmelmegaavr` platform,
  `board = ATtiny3226`, **no framework** — bare metal, f_cpu 5 MHz to match
  the prescaler hal.c sets at boot). Upload uses pymcuprog under the hood, so
  `pip install pymcuprog` once. Per-leaf IDs: use the `[env:leaf-N]` pattern.

**SerialUPDI wiring** (any CP2102/CH340/FT232 USB-serial adapter, 3.3 V logic):

```
adapter TX ─┐
            ├──── J7 UPDI pin      (tie TX+RX together AT THE ADAPTER —
adapter RX ─┘                       Board A's on-board 1 k in the UPDI line
adapter GND ───── J7 GND            is the series resistor the scheme needs)
board powered from its own battery (or bench 3V3) during flashing
```

Sanity first: `pymcuprog ping -t uart -u <port> -d attiny3226` should return
the device ID. Then check the oscillator fuse once per chip —
`pymcuprog read -t uart -u <port> -d attiny3226 -m fuses`. Only **FREQSEL,
bits [1:0] of OSCCFG (fuse 2), which must read 0b10 (20 MHz)** — the factory
default. The rest of the byte is reserved and reads back as ones, so a healthy
part prints `0x7E`, *not* `0x02`; mask before you judge it (`0x7E & 0x03 ==
0x02` ✓, verified on hardware 2026-10-31). If FREQSEL ever reads 0b01
(16 MHz), either write the fuse or rebuild with `F_CPU=4000000UL` — otherwise
every UART baud rate is 20 % off and nothing will speak.

**BODCFG (fuse 1) must read `0x44`** on a brought-up board — brown-out
detection at 2.6 V, active mode only. It is *not* the factory default (`0x00`,
no BOD); set it once per chip with
`pymcuprog write -t uart -u <port> -d attiny3226 -m fuses -o 1 -l 0x44`.
Without it a rail that sags under the TX surge produces an undefined hang with
no trace; with it you get a clean reset reported as `0x02` in the STATUS
packet's `reset_cause`. A full healthy fuse row reads
`00 44 7E FF FF F6 FF 00 00`.

Reflash caveat: `--erase` clears **EEPROM too** — OTA-applied config reverts
to the compiled defaults and the leaf re-burns its radio NVRAM on the next
boot (by design, self-healing; just re-send any OTA tweaks).

## Bring-up checklist (firmware side; boards' own checklists in hardware/)

1. Flash; expect two LED blinks at boot, then a STATUS packet on the
   coordinator's log (fw version, reset cause, boot count).
2. First boot burns the E220 NVRAM — verify `radio_nvram_ok=1` in the *second*
   boot's STATUS.
3. I2C scan sanity: SHTC3 + BME280 values appear in the first READING; if
   flags bit5 is set, check Board B harness and the pull-up total.
4. AS3935 antenna tune: temporarily set `AS3935_TUNING_CAP` candidates and use
   a scope/counter on the IRQ pin with `DISP_LCO` (see as3935.c register notes)
   — target 500 kHz ± 3.5 % (divided by LCO_FDIV, default ÷16 → 31.25 kHz).
   Then the piezo-lighter click test from a few metres.
5. Vane LUT: **done 2026-10-31** — 7.5 k fitted, all eight cardinals measured,
   the eight intermediates derived, `VANE_WINDOW` 23. Re-do only if the
   pulldown or the vane changes. Spot-check: W should read ~247, E ~3619.
6. Anemometer: drill-spin, verify pulse counting (wind_avg in readings), set
   `ANEMO_MS_PER_HZ_X1000`. If edges look lazy at high RPM on the scope, fit
   the DNP 10 k pull-up pad on Board A (board doc §6 item 5).
7. Charge-inhibit: freezer test — confirm PA3 asserts below the limit and the
   CN3801 CHG LED goes out; confirm it releases at limit + hysteresis.
8. Watch a full PMS7003 cycle: rail up, 30 s warm-up, pm values in the next
   reading, rail down. Confirm the radio still transmits afterwards (shared
   UART handover).

## Known hardware quirk the firmware can't fix

The vane divider is excited from VBAT permanently (no GPIO gates it). Standing
current depends on where the vane is pointing — from 26 µA at W (120 k) to
403 µA at ESE (688 R), averaging ~223 µA over the 16 positions — against a
sleep floor of roughly 80–100 µA, most of it the AS3935 that is never
duty-cycled. `VANE_DIV_R_OHMS` is the only lever the firmware has on it, and
7.5 k already spends a quarter less than the old Board D ladder did (~300 µA)
while keeping three times the tolerance stack between adjacent codes. Solar makes it
irrelevant in practice, but it is still the first thing to reclaim in a REV1:
gate the excitation from a spare pin and settle before sampling. Noted
2026-07-13 during firmware bring-up planning; re-measured against the
commercial vane 2026-10-31.

## Anemometer pulse path — OPEN, and how to narrow it (2026-11-05)

The dashboard reports a sustained wind of 0.01–0.04 m/s while gusts reach
4–5 km/h. Reading the code alone, that looked like a cup anemometer sitting
below its starting threshold: stalled most of the time, spun up by puffs. The
risk table below is still correct — every mechanism that could silently drop a
closure was checked and none of them bites.

**Then Anish watched the cups. They rotate continuously and barely stop.**

That settles it against the stall explanation, and it means a pulse is going
missing somewhere the code audit did not reach. Continuous rotation at a
plausible ~1.25 Hz is 375 revolutions in a 300 s report; the leaf reports a
number consistent with 4–18. The audit below was reasoning from the source and
the symptom; the cups are evidence, and evidence wins.

### What is ruled out

| Risk | Why it does not bite |
|---|---|
| Pin interrupt dead in POWER-DOWN | `hal.c` sets `PORT_ISC_BOTHEDGES_gc`. On AVR that is the fully asynchronous sense, the one that wakes from power-down on **any** pin — `RISING`/`FALLING` are synchronous and would have been dead on a partially-async pin. The ISR then filters to the falling edge in software. This is the classic trap and it was already avoided. |
| Both 5 V rails off between duties | The anemometer is a passive reed switch on the MCU's internal pull-up. It needs no rail. |
| Multi-second sleeps collapsing a gate | PIT runs at 1 Hz (32.768 kHz ÷ 32 ÷ 32768) with `RUNSTDBY`, and the main loop catches up one `wind_second_tick()` per elapsed second rather than one per wake. |
| Interrupts masked during radio TX | Only three short `ATOMIC_BLOCK`s, all around 16-bit reads. No long `cli()` anywhere, radio session included. |
| Debounce ceiling | `ANEMO_MIN_EDGE_MS` 4 → 250 Hz → 167 m/s. Nowhere near limiting. |
| 16-bit tick wrap in the debounce | Real, and the same flaw the rain path carries an explicit fix for — but the loss is window ÷ 65536, so 4/65536 = 0.006 % here against 150/65536 = 0.23 % for rain. That is why rain was fixed and this was not: ~0.1 pulses a day. |

### What is still suspect

Something between the reed closing and the number in the report packet. The
span splits into three, and `DIAG_WIND` tells them apart without a serial
console:

1. **The edge never reaches the ISR** — reed, cable, pull-up, the board RC, or
   a wake-from-power-down behaviour the datasheet reading did not predict.
2. **The ISR sees it and discards it** — the falling-edge level test or the
   `ANEMO_MIN_EDGE_MS` debounce.
3. **The ISR credits it and the bucketing loses it** — somewhere between
   `v_anemo_pulses` and `wind.rep_pulses`.

### `make DIAG_WIND=1` — the instrument

`DIAG_PULSE` cannot answer this: it runs with **no sleep** and a 100 ms
blocking blink, so it is a hand-speed bring-up test. `DIAG_WIND` keeps the
real power-down sleep and the real per-second bucketing, because the sleeping
path is the suspect.

```
make clean && make DIAG_WIND=1 && make flash PORT=/dev/tty.usbserial-…
```

| LED | Meaning |
|---|---|
| 4 flashes at boot | this build is running (2 = normal, 3 = `DIAG_PULSE`) |
| short, 25 ms | one revolution credited by the ISR |
| long, 250 ms | a 10 s gate closed **with** revolutions in it |
| double, 2 × 120 ms | a gate closed having credited nothing, **though edges did reach the ISR** and were discarded |
| flutter, 6 × 40 ms | pulses went missing *after* the ISR counted them |

Watch the cups and the LED together:

- **One short flash per revolution**, and N shorts between two longs where N is
  the revolutions in 10 s → cases 1–3 are all clear and the fault is
  downstream, in the report packet, the coordinator or the cloud. N × 0.24 is
  the km/h the firmware thinks it is seeing.
- **Flashes missing revolutions, no doubles** → case 1. The edge is not
  arriving. Electrical, or the pin is not waking.
- **Doubles** → case 2. Edges arrive and the firmware throws them away.
- **Flutter** → case 3, a firmware bug in the bucketing, and it has just been
  caught red-handed.

Silence and a double are different faults, which is the whole reason the
reject counter exists: "no edge arrived" and "an edge arrived and we binned
it" look identical from the dashboard and are hours apart in the debugging.

### One bias that is real but conservative

Gusts use fixed back-to-back 10 s gates, not a sliding window, so a gust
straddling a boundary is split across two gates and under-reported by up to
~2×. Real gusts are if anything higher than reported. This does not explain
the average.

### Worth doing regardless of the outcome

`wind_cms()` returns whole cm/s, so one revolution in five minutes moves the
average by 0.22 cm/s and is truncated away — it takes ~4.5 revolutions to
register 1 cm/s, which is why a 24 h average only ever takes a handful of
distinct values at this site. Reporting mm/s instead still fits `uint16`
(65 m/s ceiling) and gives 10× the resolution. Protocol change, so it belongs
with the next flash.
