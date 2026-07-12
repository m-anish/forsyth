# Forsyth Leaf Protocol (FLP) v1 — the air and uplink contract

This file is the **single source of truth** for how bytes move: leaf → coordinator
over LoRa (binary), coordinator → cloud over MQTT (JSON). Both implementations
(`leaf/src/protocol.h`, `coordinator/src/protocol.py`) mirror this document; if you
change one, change all three in the same commit.

Written 2026-07-13 for a future maintainer (human or AI): every choice below has its
reason attached, so you can tell load-bearing decisions from arbitrary ones.

---

## 1. Radio layer — E220-900T22D, fixed mode

Both ends run Ebyte **E220-900** modules (LLCC68). Register configuration follows the
scheme proven in lokki (`lokki/firmware/micropython/src/comms/lora_config.py`):

| Register | Setting | Why |
|---|---|---|
| ADDH/ADDL | coordinator `0xFFFF`, leaf `0x00<unit_id>` (unit_id 1–255) | `0xFFFF` is Ebyte monitor mode — the coordinator hears every frame on the channel regardless of destination. Leaves get real addresses so downlink can be directed. |
| REG0 | UART **9600 8N1**, air rate **2400 bps** | 9600 is what PROGRAM mode requires; keeping data mode at the same baud means never re-initializing the UART around mode changes (lokki learned this the hard way). 2400 air rate buys sensitivity/range; our packets are ≤64 B and rare, airtime doesn't matter. |
| REG1 | sub-packet **200**, ambient RSSI off, TX power **22 dBm** | defaults; power is a compile-time knob. |
| CHAN | **15** (850.125 + CH MHz → 865.125 MHz) | India NFAP de-licenses **865–867 MHz**. Valid channels are **15–16 only**; anything else is out of band in India. Knob on both ends — must match. |
| REG3 | RSSI byte **ON**, fixed mode **ON**, LBT **OFF**, WOR 2000 ms (unused) | RSSI byte on because receivers unconditionally strip + report the trailing byte — turning it off in registers would eat real payload. LBT off: the E220 silently drops frames when LBT can't find quiet air (lokki finding). |
| CRYPT | `0x0F57` project default | Ebyte XOR-grade scrambling, not security. Must match fleet-wide; mismatch = silent frame loss. Knob on both ends. |

**Addressing flow:** leaf transmits with destination `0x0000` (no leaf may use
unit_id 0) — only the monitor-mode coordinator hears it, sleeping leaves don't wake
each other. Coordinator transmits ACKs directed to `0x00<unit_id>`.

**Persistence:** the leaf power-gates its module, so volatile (RAM) register writes
would vanish every cycle. The leaf therefore programs **NVRAM once** (command `0xC0`)
on first boot — or whenever the compiled radio config changes — and records the
programmed payload's CRC in EEPROM. The coordinator is always powered and writes
**volatile** (`0xC2`) at every boot, lokki-style: one source of truth in its config.
Radio parameters (channel, power, air rate, crypt) are deliberately **not**
OTA-configurable — changing them mid-air orphans the link.

**Timing discipline (the lokki law, non-negotiable):** M0/M1 driven before the rail
comes up; wait AUX high + 2 ms before touching the UART; two-edge AUX wait
(low edge = module took it, high edge = done) after every TX and register command.

## 2. Frame format (LoRa payload, after the module's 3-byte fixed-mode header)

All multi-byte integers **little-endian**. Max frame 64 B (fits any sub-packet size).

```
offset  size  field
0       1     magic      0xF5
1       1     version    0x01
2       1     type       see below
3       1     station_id unit_id, 1–255
4       1     seq        per-leaf, increments every frame, wraps
5       1     flags      bitfield, see below
6       n     payload    type-specific
6+n     2     crc16      CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over bytes 0..6+n-1
```

`flags` (uplink): bit0 charge-inhibit currently asserted · bit1 low-battery mode ·
bit2 safe mode · bit3 first frame since reset · bit4 vane fault (no LUT match) ·
bit5 I2C sensor fault · bit6 PMS fault/timeout · bit7 config TLVs applied since last frame.

### Type 0x01 — READING (leaf → coordinator)

Payload: `u16 field_mask`, then only the present fields, packed in bit order:

| bit | field | encoding | notes |
|---|---|---|---|
| 0 | temp_c | i16 ×100 | SHTC3, after leaf-side offset/slope calibration |
| 1 | rh | u16 ×100 | SHTC3 |
| 2 | pressure_pa | u32 | BME280, station pressure (not MSL-reduced — server's job) |
| 3 | wind_avg | u16 cm/s | mean over the report interval, leaf-calibrated (m/s-per-Hz knob) |
| 4 | wind_gust | u16 cm/s | max WIND_GATE_S-second bucket in the interval |
| 5 | wind_dir | u16 deg ×10 | from vane LUT; absent when flags bit4 set |
| 6 | rain_tips | u16 | **cumulative tip count since boot, wraps.** Raw on purpose: lossless across dropped packets; the coordinator diffs consecutive values (wrap-aware) and applies mm-per-tip. Calibration lives server-side where it's editable without OTA. |
| 7 | pm1 | u16 µg/m³ | PMS7003 atmospheric values, averaged |
| 8 | pm25 | u16 µg/m³ | |
| 9 | pm10 | u16 µg/m³ | |
| 10 | batt_mv | u16 | via 1 M/330 k divider, leaf-calibrated ratio knob |
| 11 | vane_adc | u16 | raw 12-bit ADC — diagnostic, sent when verbose knob on. **This is how you calibrate the vane LUT remotely.** |
| 12 | mcu_temp_c | i16 ×100 | internal sensor; the charge-inhibit policy input, sent verbose |
| 13 | ltg_stats | u8×3 | strikes / disturbers / noise events since last reading |
| 14–15 | reserved | | |

Wind avg is engineering units but rain is raw counts — asymmetric on purpose: wind is
instantaneous (nothing accumulates, loss loses nothing), rain is cumulative (a counter
survives packet loss; a pre-computed delta doesn't).

### Type 0x02 — LIGHTNING (leaf → coordinator, sent promptly)

`u8 count · u8 distance` (AS3935 register raw: 1 = overhead, 63 = out of range →
coordinator maps 63 to null) `· u32 energy` (21-bit AS3935 "energy", unitless) `·
u16 age_s` (how stale the event is; coordinator computes `ts = now − age_s`, so the
leaf needs no wall clock).

### Type 0x03 — STATUS (leaf → coordinator, on boot and on request)

`u16 fw_version` (BCD, 0x0100 = 1.0) `· u8 reset_cause` (raw RSTCTRL.RSTFR) `·
u16 cfg_crc` (running EEPROM config CRC) `· u16 boot_count · u8 radio_nvram_ok ·
u16 vane_adc · u16 batt_mv`.

### Type 0x10 — ACK (coordinator → leaf, directed)

Sent after every valid uplink frame. `u8 acked_seq · u8 n_tlv ·` TLVs. The leaf keeps
its radio in RX for `ACK_WAIT_MS` after each TX; this window is the **only** downlink
opportunity — the leaf's radio is otherwise unpowered. TLV = `u8 type · u8 len · bytes`:

| type | payload | meaning |
|---|---|---|
| 0x01 | u16 | report interval, seconds (clamped 30–3600) |
| 0x02 | u8 | run the PMS7003 every Nth report (0 = never) |
| 0x03 | u8×6 | AS3935: afe_outdoor(0/1) · noise_floor(0–7) · watchdog(0–10) · spike_rej(0–11) · min_strikes code(0–3) · mask_disturbers(0/1) |
| 0x04 | i16 | SHTC3 temp offset, °C ×100 |
| 0x05 | u8·i8·u8 | charge policy: mode(0 auto/1 force-inhibit/2 force-allow) · low limit °C · hysteresis °C |
| 0x06 | u16 | anemometer calibration, m/s-per-Hz ×1000 |
| 0x07 | u8 | verbose diagnostics on/off |
| 0x7E | — | save config + soft reboot |
| 0x7F | — | factory-reset config to compiled defaults |

Applied TLVs land in EEPROM and are acknowledged by flags bit7 on the leaf's next
frame. Unknown TLV types are skipped by length — forward compatible.

**Reliability model:** fire-and-forget with `TX_RETRIES` (default 1) retry if no ACK.
Readings are periodic and idempotent server-side (`ON CONFLICT DO NOTHING`); losing
one costs a data point, not correctness. The coordinator dedupes on (station, seq).

## 3. Uplink layer — coordinator → cloud (MQTT)

Matches `cloud/api/app/mqtt_bridge.py` exactly. Authenticated broker
(per-device mosquitto passwords); topics:

```
forsyth/<slug>/reading      JSON, fields of cloud Reading model
forsyth/<slug>/lightning    JSON {ts, distance_km, energy, count}
forsyth/<slug>/availability online/offline (retained; LWT = offline)
```

The coordinator owns the unit_id → slug map and per-station `rain_mm_per_tip`.
Reading JSON example (fields omitted when absent):

```json
{"ts": "2026-07-13T09:30:00Z", "temp_c": 24.31, "rh": 71.2, "pressure_pa": 95210,
 "wind_avg_ms": 2.4, "wind_gust_ms": 5.1, "wind_dir_deg": 202.5, "rain_mm": 0.56,
 "pm1": 8, "pm25": 14, "pm10": 21, "batt_v": 3.29, "rssi_dbm": -87,
 "solar_state": "inhibited"}
```

`ts` is stamped by the coordinator at receipt (NTP time) — leaves have no wall clock,
and at a ≥30 s report cadence the receipt time is the truth anyway. `rssi_dbm` is
`-(256 − rssi_byte)` from the module's appended byte. `rain_mm` is the wrap-aware tip
delta × mm-per-tip; after coordinator state loss the first frame only re-baselines
(no rain reported) rather than inventing a flood.

**Downlink entry point:** publish JSON to `forsyth/<slug>/cmd` (e.g.
`{"report_interval_s": 600, "as3935": {"noise_floor": 3}}`) — the coordinator
converts it to TLVs and holds them until that leaf's next uplink. See
`coordinator/README.md` for the full key map.
