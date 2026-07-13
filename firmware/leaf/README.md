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

- **Wind speed**: `ANEMO_MS_PER_HZ_X1000`. Pulses are counted in the PA4 ISR
  (falling edges, noise-gated), bucketed per `WIND_GATE_S` seconds; gust = max
  bucket, average = whole interval. Calibrate by drill-spinning the cups at a
  known RPM, or side-by-side with a handheld anemometer, then update the knob —
  it's also OTA-settable (TLV 0x06) so a deployed mast doesn't need a ladder trip.
- **Wind direction**: `VANE_LUT_DEFAULT` in config.h. The compiled table is
  computed from Board D's *candidate* resistor set and the board doc explicitly
  says not to trust it: at bring-up, rotate the vane through all 16 positions,
  read the raw ADC (the leaf transmits `vane_adc` while `VERBOSE_DEFAULT=1` —
  you can calibrate from the dashboard without touching the mast), and paste the
  measured centers in. The NW+N wrap-around entry ships disabled (the documented
  ladder wart); resolve per board-d-wind.md §1 options a/b/c.
- **Lightning sensitivity**: `AS3935_*` knobs — noise floor, watchdog, spike
  rejection, min strikes, indoor/outdoor gain, disturber masking. All six are in
  one OTA TLV (0x03), because tuning an AS3935 is *always* an iterative field
  job. Watch the `ltg_stats` diagnostic triple (strikes/disturbers/noise) in
  readings to see what the sensor is actually experiencing. `AS3935_TUNING_CAP`
  is bench-only: antenna resonance must hit 500 kHz ±3.5 %.
- **Temperature**: `SHTC3_TEMP_OFFSET_X100` (OTA, TLV 0x04) for the reported
  reading; `MCU_TEMP_OFFSET_X100` for the internal sensor that gates charging —
  bench-check the latter near 0 °C, it protects the battery.
- **Rain**: the leaf ships raw cumulative tips; mm-per-tip lives in the
  coordinator's per-station config (see PROTOCOL.md for why).
- **Battery**: `VBAT_DIV_NUM` — measure your actual 1 M/330 k parts.

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
`pymcuprog read -t uart -u <port> -d attiny3226 -m fuses`; **OSCCFG (fuse 2)
must be 0x02 (20 MHz)**, which is the factory default. If a part ever reads
0x01 (16 MHz), either write the fuse or rebuild with `F_CPU=4000000UL` —
otherwise every UART baud rate is 20 % off and nothing will speak.

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
5. Vane LUT: rotate through 16 positions, record `vane_adc` per position,
   update `VANE_LUT_DEFAULT` and `VANE_WINDOW`.
6. Anemometer: drill-spin, verify pulse counting (wind_avg in readings), set
   `ANEMO_MS_PER_HZ_X1000`. If edges look lazy at high RPM on the scope, fit
   the DNP 10 k pull-up pad on Board A (board doc §6 item 5).
7. Charge-inhibit: freezer test — confirm PA3 asserts below the limit and the
   CN3801 CHG LED goes out; confirm it releases at limit + hysteresis.
8. Watch a full PMS7003 cycle: rail up, 30 s warm-up, pm values in the next
   reading, rail down. Confirm the radio still transmits afterwards (shared
   UART handover).

## Known hardware quirk the firmware can't fix

The vane ladder is excited from VBAT permanently (no GPIO gates it). With the
N reed closed that's ~300 µA continuous through 11 k — several times the rest
of the sleep floor. Solar makes it irrelevant in practice, but it's the first
thing to reclaim in a REV1 (gate the excitation from a spare pin and sample
before reading). Noted 2026-07-13 during firmware bring-up planning.
