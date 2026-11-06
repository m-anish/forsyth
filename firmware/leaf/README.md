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

**BODCFG (fuse 1) must read `0x24`** on a brought-up board — brown-out
detection at 2.15 V, active mode only. **It was 0x44 (2.6 V) until
2026-11-06**, on the mistaken belief that only 1.8 / 2.6 / 4.2 V were
available; datasheet 7.8.2.2 lists eight levels and 2.15 V is the one this
design wanted. 2.6 V was tripping on the transient sag from the boost inrush
plus the E220 TX pulse, resetting into the same sequence forever. It is *not* the factory default (`0x00`,
no BOD); set it once per chip with
`pymcuprog write -t uart -u <port> -d attiny3226 -m fuses -o 1 -l 0x24`.
Without it a rail that sags under the TX surge produces an undefined hang with
no trace; with it you get a clean reset reported as `0x02` in the STATUS
packet's `reset_cause`. A full healthy fuse row reads
`00 24 7E FF FF F6 FF 00 00`.

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

## AS3935 IRQ floats when the sensor is absent (REV1 wants a resistor)

`gpio_init()` sets the lightning IRQ to `PORT_ISC_BOTHEDGES_gc` with **no
pull-up**, which is right while the SEN0290 drives the line — it idles low and
pulses high, so a pull-up would just fight it. Unplug the sensor and that pin
floats, and a floating input with edge interrupts fires on noise. Every one of
those is a wake from power-down, so the part never reaches its ~80-100 µA
sleep floor and sits in the milliamps instead. On a marginal cell that is
brown-out fuel, and it looks like a firmware hang: the board is awake and busy
but appears not to answer the button.

**Firmware guard (2026-11-06).** When `as3935_init()` fails twice, the IRQ pin
is switched to `PORT_ISC_INPUT_DISABLE_gc` — the same thing `gpio_init()` does
for every unused pin. No float, no interrupts, no drain, and nothing changes
when the sensor is present. It is one-way: plug the sensor in later and the
board needs a reboot, same as every other sensor here.

**What the board should do instead.** This part has no internal pull-downs, so
software cannot define the line without a pull-up that costs ~90-100 µA
forever against a driven-low idle. A **1 MΩ pull-down on the IRQ net** solves
it in hardware for ~3 µA: the line is defined with no driver, the SEN0290
still overpowers it easily, and the firmware guard becomes belt-and-braces.
Worth doing in REV1 alongside gating the vane excitation.

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

## Anemometer: two closures per revolution, and the 2x it caused

**Settled 2026-11-06 with `DIAG_WIND`.** The dashboard reported a sustained
wind near zero against gusts of 4–5 km/h. Reading the code, that looked like
cups stalled below their starting threshold. Then Anish watched the cups:
they rotate continuously. The diagnostic firmware then showed the LED
blinking **twice per revolution, 180 degrees apart** — two magnets, two reed
closures per turn, evenly spaced rather than one closure counted twice.

### What that fixed

`ANEMO_MS_PER_HZ_X1000` was 667, chosen from the datasheet's English line
("2.4 km/h causes the switch to close once per second") with the Chinese
line's 0.33 m/s per closure dismissed, on the grounds that it "would be right
only if the rotor closed the reed twice per turn". It does. The old comment
even named the condition that would overturn it, and then recorded the
opposite as settled on a 2026-10-31 check that was simply wrong.

The two texts actually agree once "closure" is read carefully: 0.667 m/s per
**revolution**-Hz, two closures per revolution, therefore **0.333 m/s per
closure-Hz**. The firmware counts closures, so the constant is now **333**.

**Every wind reading this leaf has ever produced is 2x high.** Both
`wind_avg` and `wind_gust`, back to first light. Anything comparing data from
before 2026-11-06 with data after it has to halve the earlier half, and any
calibration conclusion drawn from the old numbers is void.

### What was ruled out along the way

| Risk | Why it does not bite |
|---|---|
| Pin interrupt dead in POWER-DOWN | `hal.c` sets `PORT_ISC_BOTHEDGES_gc`, the fully asynchronous sense that wakes from power-down on **any** pin. `RISING`/`FALLING` are synchronous and would have been dead on a partially-async pin. The ISR filters to the falling edge in software. The classic trap, already avoided. |
| Both 5 V rails off between duties | The anemometer is a passive reed on the MCU's internal pull-up. It needs no rail. |
| Multi-second sleeps collapsing a gate | PIT runs at 1 Hz with `RUNSTDBY`, and the main loop catches up one `wind_second_tick()` per elapsed second, not one per wake. |
| Interrupts masked during radio TX | Three short `ATOMIC_BLOCK`s around 16-bit reads. No long `cli()` anywhere. |
| Debounce double-counting one closure | Ruled out by the 180-degree spacing: a bounce would pair the flashes, not space them evenly. `ANEMO_MIN_EDGE_MS` stays at 4. |
| 16-bit tick wrap in the debounce | Real, but the loss is window ÷ 65536: 4/65536 = 0.006 % here against 150/65536 = 0.23 % for rain. That is why rain was fixed and this was not — ~0.1 pulses a day. |
| Coordinator scaling | `wind_avg_ms` and `wind_gust_ms` are both ×0.01 (cm/s on the wire), so the avg/gust asymmetry on the dashboard was never a unit bug. |
| Pin reconfigured later | `ANEMO_CTRL` is written once in `hal_init()` and never touched again. |

### Still open: the near-zero averages

Halving the constant does not explain them. A gust is a `max` over 10 s gates
and survives sparse data; the average is a `sum` over the 300 s report and
collapses. So most production gates were empty while every diag gate was
full. That may not be a fault at all — the 24 h sample was mostly genuine
night calm and the diag run was at peak afternoon valley-breeze. **Settle it
by comparing the dashboard against a DIAG_WIND flash count in the same
wind**, not by reasoning about it.

Also worth doing: `wind_cms()` returns whole cm/s, so at this site the 24 h
average only ever takes a handful of distinct values. Reporting mm/s instead
still fits `uint16` (65 m/s ceiling) and gives 10x the resolution.

### `make DIAG_WIND=1` — the instrument

`DIAG_PULSE` cannot answer questions like these: it runs with **no sleep** and
a 100 ms blocking blink, so it is a hand-speed bring-up test. `DIAG_WIND`
keeps the real power-down sleep and the real per-second bucketing.

```
make clean && make DIAG_WIND=1 && make flash PORT=/dev/tty.usbserial-…
```

| LED | Meaning |
|---|---|
| 4 flashes at boot | this build is running (2 = normal, 3 = `DIAG_PULSE`) |
| short, 25 ms | one closure credited by the ISR |
| long, 250 ms | a 10 s gate closed **with** closures in it |
| double, 2 × 120 ms | a gate credited nothing, **though edges did reach the ISR** and were discarded |
| flutter, 6 × 40 ms | closures went missing *after* the ISR counted them |

Count the shorts between two longs: that is N closures per 10 s. **× 0.12
gives km/h** — N/10 closure-Hz × 0.333 m/s × 3.6. Two closures per
revolution, so the cups turned N/2 times in those 10 s.

Silence between gate marks and a double are different faults — "no edge
arrived" versus "an edge arrived and we binned it" look identical from the
dashboard and are hours apart in the debugging.

**A diagnostic can lie.** The first cut of this mode compared an instant ISR
counter against buckets that only update at 1 Hz, so it reported its own
sampling lag as a fault: it fluttered continuously, and the half-second
blocking blink it then ran every iteration made the catch-up loop close whole
gates empty, which manufactured the doubles too. One bug, two false symptoms,
both pointing at innocent code. The invariant now includes the undrained
remainder in `v_anemo_pulses` and is checked only at a gate boundary.

### Flashing gotchas that cost time here

- The **UPDI adapter flaps**: it drops off the USB bus and re-enumerates
  ~8 s later. Expect several retries per flash; it is not a dead board.
  `tty.*` and `cu.*` perform identically (12/12 each), so that is not the
  variable.
- `make flash` alone flashes **whatever is already in `build/`**. Restoring
  production after a diag session needs
  `make clean && make STATION_ID=1 && make flash PORT=…`, or the station
  silently stays dark while looking flashed.
