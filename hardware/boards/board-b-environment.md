# Board B — environment

**Role:** the quiet senses, inside the Stevenson screen: pressure (BME280), ambient
temp/RH (SHTC3/SHT4x), lightning (AS3935 via DFRobot SEN0290). Passive supply only —
its distance from Board A's switchers *is* the AS3935's noise isolation.
**Status:** reference sheet v1 (2026-07-11).

## 1. What's on it

Breakout modules socketed/soldered onto a carrier PCB (cheapest, swappable), or their
circuits copied onto the carrier later — v1 uses modules as bought:

| Ref | Module | Bus addr | Notes |
|---|---|---|---|
| M1 | DFRobot SEN0290 (AS3935) | I2C **[verify — set by the module's interface + address selectors per the DFRobot wiki]** | interface switch → I2C; IRQ out → `AS3935_IRQ` |
| M2 | BME280 breakout | 0x76 (0x77 alt) | **pressure only** by policy |
| M3 | SHTC3 (or SHT4x) breakout | 0x70 (SHT4x: 0x44) | owns temp/RH |

## 2. Bus & harness

- **One set of I2C pullups for the whole leaf lives here: R1, R2 = 4.7 kΩ to VBAT.**
  Many breakouts ship with their own 10 k pullups — if M1–M3 all have them, the
  parallel result gets stiff; desolder the extras or omit R1/R2. **[check the actual
  modules bought; target 3–5 kΩ effective]**
- J1: JST-XH-5 to Board A — `1 VBAT · 2 GND · 3 SDA · 4 SCL · 5 AS3935_IRQ`
  (≤ 0.5 m, fine at 100 kHz).
- 100 nF at each module's VDD; one 10 µF bulk at J1.

## 3. Placement inside the screen

- **SHTC3 is the reading that matters most** — mount M3 with free airflow, away from
  the PMS7003's fan exhaust and above/beside (not downwind of) the BME280.
- AS3935 antenna axis vertical per its application note; keep M1 the farthest of the
  three from the cable entry and the PMS fan motor. No ground pour under M1's antenna
  end of the carrier.
- PMS7003 mounts beside the carrier (not on it — vibration): its own pigtail runs to
  Board A's J5. Sensor-end pinout (from the
  [Plantower PMS7003 manual V2.5](https://download.kamami.pl/p564008-PMS7003%20series%20data%20manua_English_V2.5.pdf)):
  PIN1/2 = VCC 5 V · PIN3/4 = GND · PIN5 = RESET (leave NC) · PIN7 = RX ·
  PIN9 = TX · PIN10 = SET (leave NC = normal; we hard-gate its rail instead).
  All logic pins are 3.3 V TTL.

## 4. Board BOM

| Ref | Part | Note |
|---|---|---|
| M1 | DFRobot SEN0290 | Robu/MakerBazar |
| M2 | BME280 breakout | SmartElex preferred |
| M3 | SHTC3/SHT4x breakout | verify stock |
| R1, R2 | 4.7 k | bus pullups (see §2 caveat) |
| C1–C3 | 100 nF | at each module |
| C4 | 10 µF | at J1 |
| J1 | JST-XH-5 | to Board A J4 |

## 5. Bring-up checklist

1. Harness to a bench Board A; I2C scan should show three addresses.
2. BME280 pressure vs a phone barometer (±2 hPa sanity), SHTC3 vs a room thermometer.
3. AS3935: run its antenna auto-tune/calibration routine; then a piezo lighter click
   test at a few metres — IRQ should fire (disturber or event); log noise-floor level
   with Board A's boosts running a TX cycle to confirm the isolation actually isolates.
