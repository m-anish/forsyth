# Coordinator carrier board — reference sheet

**Started 2026-11-20.** Replaces the hand-soldered perfboard (firmware/coordinator/README.md,
"Carrier board"). A two-layer carrier that the coordinator's modules plug into: the dev
board, the LoRa radio, the Ethernet module, the RTC, a charger and one 18650 that carries
the station's gateway through a power cut. Designed in EasyEDA Pro (`forsyth-coordinator`).

Status (2026-11-20): **schematic drawn, ERC clean** (0 errors, 2 minor warnings, no floating
pins; every net checked against §2–3). Second pass the same day: TP4056 and protection as
chips instead of the module, an MT3608 boost (SOT-23-6) instead of the TPS61023 (SOT-563,
too fiddly to hand-solder), the ZS-042 on its 4-pin side, and the W5500 module as a library part.
Third pass: **every part must be easy to buy in India** (§6). The XB8089D gave way to a DW01A +
FS8205A pair, the parts every TP4056 module carries, and the CJ3407s became AO3401A. EasyEDA Pro project `forsyth-coordinator`
(`72172190064947adb14801d54671a5b3`), schematic page P1. Not laid out yet: footprints marked
**[measure]** need the module in hand first.

Designators as drawn: H1/H2 dev-board headers P1/P2, H3 E220, H4/H5 Core1262 rows, U6 W5500
module (EasyEDA `W5500_MODULE`, 25 × 23 mm, 2 × 6), H8 ZS-042 (4-pin side), H9 OLED, H10 spare
GPIO, BT1 dual 18650 holder (Keystone 1048P pattern, cells in parallel), U9 3.81 mm terminal for
external cells, U1 Qwiic, U2 USB-C, U3 5 V terminal, U4 MT3608 boost,
U5 AMS1117-3.3, U7 TP4056 (ESOP-8), U8 DW01A protection (SOT-23-6) + Q4 FS8205A dual N-FET (TSSOP-8), F1 PTC, D1 SMAJ5.0A,
D2 SS34 (load sharing), D3 SS34 (boost), Q1/Q2 AO3401A, Q3 2N7002, L1 4.7 µH SWPA6045S
(Isat 5.5 A), LED1 red (charging), LED2 green (charged), RF1 SMA (Core1262 antenna, DNP until
it is fitted). The headers use 2.54 mm pin-header footprints; fit female headers.

## 1. What plugs in

| # | Module | Interface | Footprint | Notes |
|---|---|---|---|---|
| 1 | **YD-ESP32-S3 N8R2** (VCC-GND Studio; FlyRobo) | — | 2 × 22-pin female headers, 2.54 mm, rows **25.40 mm** apart | Board 27.94 × 57.15 mm, antenna end 6.2 mm past it. Pin 1 (3V3) at the antenna end. Both USB-C at the far end: keep that edge clear and at the board edge. **Leave its IN-OUT jumper open** (the carrier feeds its 5V pin; the open jumper's diode stops that reaching a laptop's USB). Its RGB jumper must be closed for the WS2812 on GPIO48. |
| 2 | **Ebyte E220-900T22D *or* T30D** (UART, LLCC68) | UART1 | one 1 × 7 female header, 2.54 mm, both module outlines in silk (as on Board A) | Same pin order on both: M0, M1, RXD, TXD, AUX, VCC, GND. T30D outline is the larger; antenna (SMA on the module) toward the board edge. |
| 3 | **Waveshare Core1262-HF** (SX1262, SPI) — future | SPI (shared) | 2 × 8, 2.54 mm pitch, rows **15.24 mm** apart (Waveshare drawing; pads 1.6 × 2.8), module 19 × 22 mm | Left: GND, GND, RXEN, TXEN, DIO2, DIO1, GND, 3V3. Right: ANT, GND, CS, CLK, MOSI, MISO, RESET, BUSY (Waveshare Core126X schematic). Optional edge SMA from ANT (50 Ω, DNP); the module also has an IPEX. |
| 4 | **W5500-lite** (Ethernet) | SPI (shared) | 2 × 6, 2.54 mm pitch, rows **20.32 mm** apart (LilyGO T-Lite W5500 drawing); module 23.00 × 24.92 mm, top pin about 6.3 mm below its top edge, Ø2.0 mm hole 1.61 mm from the left and 2.50 mm from the top edges. Schematic part: EasyEDA `W5500_MODULE` (25 × 23 mm), **check its pads against 20.32 mm in layout, or use two 1 × 6 headers** | Left: GND, GND, MOSI, SCK, CS, INT. Right: GND, 3V3, 3V3, NC, RST, MISO. **3.3 V only.** RJ45 at the board edge. A user-contributed "W5500-lite" footprint can replace it once starred in EasyEDA (the bridge only reaches system, personal and favourite libraries). |
| 5 | **DS3231 ZS-042** (RTC + AT24C32) | I2C | 1 × 4 header, the module's right-hand row, top to bottom SCL, SDA, VCC, GND (confirmed). Board 38.00 × 21.50 mm; bottom pin of the 4-row 6.67 mm above the bottom edge, so the top pin is 14.29 mm above it; row about 1.2 mm in from the right edge (scaled from the drawing, not dimensioned). Ø1.70 mm holes at (8.15, 1.55) and (8.15, 19.95) from the left/top corner, and 3.55 mm in from the right edge, 1.55 mm from the top. The 6-pin row (unused) starts 4.47 mm from the top. | No SQW, so no alarm interrupt; firmware polls the RTC. Has its own 4.7 k pull-ups. Its coin-cell "charger" (a resistor and diode) cooks a CR2032: remove the resistor, or fit an LIR2032. |
| BT1 | **2 × 18650 Li-ion in parallel (1S2P)**, dual SMD holder (Robocraze; Keystone 1048P footprint, 86 × 40 mm) | — | SMD | Both + contacts to VBAT, both − to the protection. Li-ion, 4.2 V: the TP4056 is a Li-ion charger, **not** LiFePO4 like the leaves. Fit two matched cells at the same charge. |
| U9 | **External cells** (optional), 2-pin 3.81 mm screw terminal (KF128-3.81) | — | TH | Parallel with BT1, behind the same protection: a 1S Li-ion bank only (4.2 V max), at the same voltage as the fitted cells when connected, ideally with its own fuse. Mark + and − on the silk. |

## 2. Power

```
5 V in (USB-C power-only, or 2-pin terminal from a PoE splitter)
  └─ F1 PTC 2 A ─ D1 SMAJ5.0A ─┬──────────────── VBUS ── U7 TP4056 VCC ─ BAT ── VBAT = BT1 +
                               │      BT1 (2 cells ∥) + U9 ext. − ── U8 DW01A + Q4 FS8205A ── GND
                               ├── D2 SS34 ──┐
  VBAT ── Q1 AO3401A (P-FET, gate on VBUS) ──┴── SYS (3.0–4.8 V)
                                   └─ L1 4.7 µH ─ U4 MT3608 SW ─ D3 SS34 ── 5V (4.99 V)
5V ─┬─ dev board 5V pin (its own LDO makes the ESP32's 3.3 V)
    ├─ Q2 AO3401A high-side switch ── 5V_LORA ── E220 VCC (+ 220 µF + 100 nF at the pin)
    └─ U5 AMS1117-3.3 ── 3V3P ── Core1262, W5500, ZS-042, OLED/Qwiic
```

- **Load sharing:** with 5 V present, Q1's gate is held high (off) and the load runs from
  VBUS through D2 while the TP4056 charges the cell. Without it, Q1's 100 k gate pull-down
  turns it on and the cell carries everything. No gap at the hand-over beyond D2's drop.
- **Charger (U7 TP4056, ESOP-8):** R15 2 k on PROG = about 580 mA, gentler on a chip
  and cell in a closed box than 1 A (1.2 k gives 1 A). TEMP to GND (no NTC), CE to VBUS.
  LED1 red lights while charging (CHRG), LED2 green when done (STDBY), each with 1 k.
  10 µF at VCC (C15) and at BAT (C14).
- **Protection (U8 DW01A + Q4 FS8205A),** on the cell's negative side exactly as a TP4056
  module does it: DW01A VSS and the FS8205A's S1 pins to the cell's − (`BAT_CELL_N`), S2 pins
  to board GND, OD → G1 (discharge FET), OC → G2 (charge FET), CS to board GND through R18 1 k,
  VDD from VBAT through R14 100 Ω with C13 100 nF to the cell's −; TD (pin 4) unconnected. The
  FETs' common drain (pins 1 and 8, `PROT_D`) joins only the two pins. Board GND is therefore
  the cell's protected negative, not BT1 − directly. Trips at about 4.3 V, 2.4 V and 3 A
  (DW01A), well above the boost's ~2.5 A peak from a low cell.
- **One 5 V rail from the boost** (U4 MT3608, SOT-23-6, 1.2 MHz, 0.6 V reference; R8 732 k /
  R9 100 k = 4.99 V; L1 4.7 µH, Isat 5.5 A; D3 SS34): the dev board's LDO and the E220 both
  want a real 5 V, which a 3.0–4.2 V cell can't give. Its 4 A switch limit covers the T30D's
  620 mA burst on top of the ESP32 and W5500 (about 2.5 A peak in the inductor from a 3.0 V
  cell). Non-synchronous: with mains on, SYS ≈ 4.7 V and the boost barely switches.
- **3V3P** for the peripherals comes from its own LDO, not the dev board's 3V3 pin, so a
  W5500 (150–180 mA) and a Core1262 TX don't share the ESP32's regulator through WiFi peaks.
- **E220 power switch** (Q2 + Q3 2N7002, `LORA_PWR`): firmware can power-cycle a hung
  radio. Off at boot (gate pull-up, GPIO pull-down) until firmware turns it on.
- **Supply sizing:** up to about 1.5 A for the load plus 1 A charging: use a ≥ 2.5 A 5 V
  supply or a 12 W PoE splitter.
- **Backup time:** about 0.4 A average from the cells (WiFi or Ethernet up, radio in RX):
  roughly 12 to 16 hours on two 3000 mAh 18650s, more with an external bank on U9.
- **Recharge:** 580 mA refills two empty cells in about 11 hours; R15 1.2 k gives 1 A (about
  6 to 7 hours) if the TP4056 has a good copper pour under it.

## 3. Pin map (ESP32-S3 GPIO)

Avoids strapping pins (0, 3, 45, 46), the USB pair (19, 20), UART0 (43, 44) and GPIO48
(the dev board's WS2812). GPIO 39–42 give up JTAG, which the built-in USB-JTAG makes moot.

| Function | GPIO | Notes |
|---|---|---|
| E220 RXD ← TX | 17 | UART1, as the firmware has it today |
| E220 TXD → RX | 18 | |
| E220 M0 / M1 | 8 / 9 | driven, never floated |
| E220 AUX | 10 | input |
| `LORA_PWR` (E220 power switch) | 7 | high = on; 100 k pull-down |
| SPI SCK / MOSI / MISO | 12 / 11 / 13 | shared by W5500 and Core1262 |
| W5500 CS / INT / RST | 14 / 21 / 16 | CS pulled up 10 k |
| Core1262 NSS / RESET / BUSY / DIO1 | 38 / 39 / 40 / 41 | NSS pulled up 10 k |
| Core1262 RXEN / TXEN | 42 / 47 | RF switch |
| I2C SDA / SCL | 1 / 2 | DS3231, OLED, Qwiic; firmware's OLED pins |
| `VBAT_SENSE` | 4 | ADC1: 100 k / 100 k from VBAT + 100 nF |
| `VBUS_SENSE` | 5 | 100 k / 100 k from VBUS: high = on mains |
| spare | 15, 35, 36, 37 | to a 1 × 6 header with 3V3 and GND |
| unused | 6 | was DS3231 SQW; the 4-pin ZS-042 side has none |

## 4. Connectors and the rest

- **J1** USB-C power-only receptacle (CC1/CC2 5.1 k to GND) and **J2** 2-pin 5 V terminal
  (PoE splitter), both into F1.
- **J3** OLED, 4-pin (GND, VCC, SCL, SDA: the common SSD1306 order). **J4** Qwiic JST-SH
  (GND, 3V3, SDA, SCL, as on Board A). **J5** spare GPIO.
- Test points: VBUS, SYS, VBAT, 5V, 3V3P, GND.
- Four M3 holes. No copper under the E220's and Core1262's antenna ends; the
  W5500's RJ45 and both LoRa antennas on opposite edges.

## 5. Open before layout

1. W5500-lite: 2 × 6 pins confirmed (J1 and J2, RJ45 at the top; the T-Lite drawing's extra
   pads belong to the T-Lite, not the module). Rows 20.32 mm = 8 × 2.54, so on the 0.1" grid.
   Pin names checked against the module's labels (2026-11-20): seen on the RJ45 face with the
   jack at the top, left column GND, GND, MOSI, SCLK, nSS, nINT and right column GND, VIN3.3,
   VIN3.3, N.C., nRESET, MISO, which is the schematic's wiring. If the module plugs in with
   the RJ45 face down, the columns swap sides as seen from above the carrier: **check which
   face goes down** and place the footprint to match. Confirm the library footprint's pads
   too (else two 1 × 6 headers).
2. The dual 18650 holder: footprint is Keystone 1048P; **measure the Robocraze holder's
   pads** against it before layout.
3. Firmware: `config.py` pins for the Core1262, W5500 RST, `LORA_PWR`, the two sense pins.

## 6. Buying it in India

A hard requirement: every part must be easy to get in India. Checked 2026-11-20 (web
listings, not live stock):

| Part | Where |
|---|---|
| TP4056 ESOP-8 | Evelta, Quartz Components, Electronicscomp (check it is ESOP-8, not SOP-8) |
| DW01A (SOT-23-6), FS8205A (TSSOP-8) | DNA Tech, Probots, Quartz Components |
| MT3608 SOT-23-6 | Sunrom, DNA Tech, Electron Components, Quartz Components |
| SWPA6045S4R7MT 4.7 µH | Evelta (same part) |
| AO3401A, 2N7002, SS34, AMS1117-3.3, 0603 parts, 0603 LEDs | common: Quartz, DNA Tech, Robu |
| USB-C 6-pin power-only | Hubtronics, Evelta |
| Dual 18650 SMD holder | Robocraze (generic; measure pads against 1048P) |
| KF128 3.81 mm 2-pin terminal | common |
| JST-SH 4-pin (Qwiic) | Evelta |
| Pin headers, KF301 terminal, edge SMA, 220 µF SMD electrolytic | common |
| F1 1812 PTC, 2 A hold | Sophix: Weite WT1812-20030 (2 A, 30 V, 1812, drops into the same footprint) |
| D1 SMAJ5.0A TVS | Ktron: Vishay SMAJ5.0A-E3/61 (SMA, minimum order 7) |

Every part now has an Indian source. Replaced for availability: XB8089D → DW01A + FS8205A; CJ3407 → AO3401A (same SOT-23 pinout).
