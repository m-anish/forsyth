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
(`72172190064947adb14801d54671a5b3`), schematic pages P1 and P2.

Fourth pass (2026-11-21): an optional **LTE module** (§2a) and **power gating** for each
optional radio (E220, Core1262, LTE). Every module header is now an **SMD female strip**, so no
through-hole pins sit over the battery holder on the back. Layout started (§7): **100 × 100 mm**,
the dual 18650 holder on the bottom side, module mounting holes where the module's drawing gives
them. Placed and DRC-clean for clearance; **not yet routed**.

Designators as drawn: H1/H2 dev-board headers P1/P2, H3 E220, H4/H5 Core1262 rows, U6 W5500
module (EasyEDA `W5500_MODULE`, 25 × 23 mm, 2 × 6), H8 ZS-042 (4-pin side), H9 OLED, H10 spare
GPIO, BT1 dual 18650 holder (Keystone 1048P pattern, cells in parallel), U9 3.81 mm terminal for
external cells, U1 Qwiic, U2 USB-C, U3 5 V terminal, U4 MT3608 boost,
U5 AMS1117-3.3, U7 TP4056 (ESOP-8), U8 DW01A protection (SOT-23-6) + Q4 FS8205A dual N-FET (TSSOP-8), F1 PTC, D1 SMAJ5.0A,
D2 SS34 (load sharing), D3 SS34 (boost), Q1/Q2 AO3401A, Q3 2N7002, L1 4.7 µH SWPA6045S
(Isat 5.5 A), LED1 red (charging), LED2 green (charged), RF1 SMA (Core1262 antenna, DNP until
it is fitted). Page P2: Q5/Q6 + R19/R20 Core1262 3.3 V switch, Q7/Q8 + R21/R22 LTE supply
switch, C16 220 µF + C17 22 µF on the LTE supply, U10 XC6206P182MR (1.8 V) + C18/C19, R23/R24
logic-level links, Q9 + R25 PWRKEY driver, Q10/Q11 BSS138 + R26–R29 UART level shifters, H11 the
LTE module's 6-pin header. Module headers H1–H5 and H8–H11 are Mill-Max 310-43-1xx SMD female
footprints (alternating legs; any SMD female strip with the same leg pattern fits).

## 1. What plugs in

| # | Module | Interface | Footprint | Notes |
|---|---|---|---|---|
| 1 | **YD-ESP32-S3 N8R2** (VCC-GND Studio; FlyRobo) | — | 2 × 22-pin female headers, 2.54 mm, rows **25.40 mm** apart | Board 27.94 × 57.15 mm, antenna end 6.2 mm past it. Pin 1 (3V3) at the antenna end. Both USB-C at the far end: keep that edge clear and at the board edge. **Leave its IN-OUT jumper open** (the carrier feeds its 5V pin; the open jumper's diode stops that reaching a laptop's USB). Its RGB jumper must be closed for the WS2812 on GPIO48. |
| 2 | **Ebyte E220-900T22D *or* T30D** (UART, LLCC68) | UART1 | one 1 × 7 female header, 2.54 mm, both module outlines in silk (as on Board A) | Same pin order on both: M0, M1, RXD, TXD, AUX, VCC, GND. T30D outline is the larger; antenna (SMA on the module) toward the board edge. |
| 3 | **Waveshare Core1262-HF** (SX1262, SPI) — future | SPI (shared) | 2 × 8, 2.54 mm pitch, rows **15.24 mm** apart (Waveshare drawing; pads 1.6 × 2.8), module 19 × 22 mm | Left: GND, GND, RXEN, TXEN, DIO2, DIO1, GND, 3V3. Right: ANT, GND, CS, CLK, MOSI, MISO, RESET, BUSY (Waveshare Core126X schematic). Optional edge SMA from ANT (50 Ω, DNP); the module also has an IPEX. |
| 4 | **W5500-lite** (Ethernet) | SPI (shared) | 2 × 6, 2.54 mm pitch, rows **20.32 mm** apart (LilyGO T-Lite W5500 drawing); module 23.00 × 24.92 mm, top pin about 6.3 mm below its top edge, Ø2.0 mm hole 1.61 mm from the left and 2.50 mm from the top edges. Schematic part: EasyEDA `W5500_MODULE`, footprint checked against all of this (§5) | Left: GND, GND, MOSI, SCK, CS, INT. Right: GND, 3V3, 3V3, NC, RST, MISO. **3.3 V only.** RJ45 at the board edge. |
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

## 2a. Optional LTE, and gating the optional radios

- **LTE module: 7Semi EG800AK-CN Pico** (Hubtronics, about ₹860; Quectel EG800AK-CN, Cat 1 bis).
  26 × 23 mm, u.FL main antenna, 3.4–4.3 V supply, one 6-pin header on its right edge, top to
  bottom RST, KEY, RX, TX, GND, VIN (H11; RST left unconnected), two mounting holes on its left
  edge. Bands B1/3/5/8/34/38/39/40/41 cover Jio (B3/5/40), Airtel (B3/8/40) and Vi (B1/3/8/40/41).
- **Supply straight from VBAT**, not the 5 V boost: the module wants 3.4–4.3 V and draws up to
  about 2 A in bursts. Q7 AO3401A high-side switch (R21 100 k gate pull-up), driven by Q8 2N7002
  from GPIO46 (`LTE_PWR`, R22 100 k pull-down: off at boot). C16 220 µF + C17 22 µF at the header.
  Below about 3.4 V on the cells the module will drop out; firmware should not start it there.
- **Logic level:** Quectel UARTs are usually 1.8 V, the 7Semi board's level is not documented. Q10/Q11
  BSS138 bidirectional shifters between the ESP32 (3.3 V, R27/R29 10 k) and `LTE_IO` (R26/R28 10 k).
  `LTE_IO` = 1.8 V from U10 (R23 0 Ω fitted) or 3V3P (R24 0 Ω, DNP): measure the module's TX idle
  level first and fit the matching link.
- **PWRKEY:** Q9 2N7002 open-drain on KEY, driven by GPIO36 (`LTE_KEY`, R25 pull-down): firmware
  pulses it low for the module's power-on time.
- **Core1262 3.3 V switch:** Q5 AO3401A from 3V3P to `3V3_SX`, Q6 2N7002 on GPIO45 (`SX_PWR`,
  R20 100 k pull-down: off at boot). The E220 already has its own switch on GPIO7.
- GPIO45 and 46 are strapping pins; the 100 k pull-downs hold them at their safe boot level and
  the switches stay off until firmware drives them high.

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
| LTE TXD → module RX / RXD ← module TX | 15 / 35 | through the BSS138 shifters |
| `LTE_KEY` (PWRKEY) | 36 | high pulls KEY low through Q9 |
| `SX_PWR` (Core1262 3.3 V) | 45 | strapping pin; high = on; 100 k pull-down |
| `LTE_PWR` (LTE supply) | 46 | strapping pin; high = on; 100 k pull-down |
| spare | 6, 37 | H10, 1 × 4 with 3V3 and GND |

## 4. Connectors and the rest

- **J1** USB-C power-only receptacle (CC1/CC2 5.1 k to GND) and **J2** 2-pin 5 V terminal
  (PoE splitter), both into F1.
- **J3** OLED, 4-pin (GND, VCC, SCL, SDA: the common SSD1306 order). **J4** Qwiic JST-SH
  (GND, 3V3, SDA, SCL, as on Board A). **J5** spare GPIO.
- Test points: VBUS, SYS, VBAT, 5V, 3V3P, GND.
- Four M3 corner holes plus module holes (§7). No copper under the ESP32's antenna end.

## 5. Open before layout

1. W5500-lite: 2 × 6 pins confirmed (J1 and J2, RJ45 at the top; the T-Lite drawing's extra
   pads belong to the T-Lite, not the module). Rows 20.32 mm = 8 × 2.54, so on the 0.1" grid.
   Pin names checked against the module's labels (2026-11-20): seen on the RJ45 face with the
   jack at the top, left column GND, GND, MOSI, SCLK, nSS, nINT and right column GND, VIN3.3,
   VIN3.3, N.C., nRESET, MISO, which is the schematic's wiring. The module plugs in **RJ45 up**
   (pins leave the chip side), so that is also the view from above the carrier: jack opening
   toward the board edge, the GND-GND-MOSI row on the left. The jack overhangs the module's
   PCB at the opening end, so let it hang over the carrier's edge. **Library footprint
   checked (2026-11-20):** `COMM-TH_L25.0-W23.0_W5500_MODULE` has rows 20.32 mm apart, 2.54 mm
   pitch, 1.6 mm pads, 1.0 mm drills; pin 1 (GND) top-left, 1–6 down the left, 7–12 up the
   right, outline 23.0 × 25.0 mm with the pins 0.7 mm nearer the bottom end, as on the module.
   So the jack-opening end is the pin 1/12 end: put that end at the board edge. Its silk does
   not show the jack; add an "RJ45 →" mark there in layout.
2. The dual 18650 holder: laid out on the Keystone 1048P footprint as a working estimate
   (Anish, 2026-11-20: fix later if the Robocraze holder differs). Four 7.3 × 6.4 mm pads at
   x ±40.0, y ±9.55 mm (cells 19.1 mm apart); the cells sit head-to-tail, so pins 1 and 4 (+)
   are on opposite corners, as are 2 and 3 (−). The footprint also drills 3.2–3.5 mm holes for
   Keystone's locating pegs; drop them if the generic holder has none.
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

## 7. Layout (started 2026-11-21)

**100.0 × 100.0 mm, two layers** (under JLCPCB's 100 × 100 price step). Coordinates below are
from the bottom-left corner, y up, in mm.

- **Bottom side:** BT1 dual 18650 holder only, centred at (51.0, 78.0), rotated 180°. The 1048P
  footprint drills five locating holes (Ø3.5 at (23.4, 95.5) and (78.6, 60.5), Ø3.2 at
  (23.4, 78.0) and (78.6, 78.0), Ø2.4 at (15.2, 60.5)); the headers above are placed clear of
  them. Its body covers x 8–94, y 58–98, so nothing through-hole sits there.
- **Top side, modules on SMD female headers** (2026-11-21, re-placed so the three optional
  radios fit at once; module bodies checked for overlap against the starred EasyEDA footprints):
  - ESP32 rows at y 71.1 and 96.5, pins x 40.5–93.8; body x 38.6–95.7, y 69.8–97.8; USB end at
    the right edge, antenna end to the left over a copper keepout (x 30–38.6, y 69–98.5).
  - **E220** header H3 vertical at x 41.5, y 48.9–64.1, M0 (pin 1) at the bottom; the body runs left
    along the edge: T30D x 0–43, y 44.5–68.5 (T22D x 7–43, y 46–67), SMA hanging ~5.5 mm off the
    left edge. Both outlines in silk.
  - **Core1262** rows horizontal at y 73.7 and 89.0, pins x 2.5–20.3, pin 1 (and ANT) at the left
    end next to RF1; body about x 0.4–22.4, y 72–91.
  - **EG800AK** header H11 vertical at x 68.8, centred y 38.7; body about x 44–70, y 27–50 (outline
    estimated from 26 × 23 mm: measure the module).
  - ZS-042 4-pin row at x 38.8, body x 2–40, y 21–42.5. W5500 at the right edge, rows y 30.8 and
    51.2, RJ45 end pointing right; body x 75–100, jack 2 mm past the edge.
  - Core1262 3.3 V switch (Q5/Q6/R19/R20) at x 27.5, y 76–88; RF1 SMA at the left edge, y 80.3.
- **Power** along the bottom edge: USB-C at the right edge (x 96.5, y 20), the 5 V terminal and
  the external-cell terminal at the bottom edge, charger and protection x 57–93, boost x 37–55,
  3V3P LDO and the E220 switch at the bottom left. LTE supply switch and logic under the
  EG800AK footprint.
- **Holes:** four Ø3.2 mm (M3) corner holes 3.5 mm in from each edge; W5500 Ø2.2 mm at
  (97.6, 50.9) (from the W5500-lite footprint); ZS-042 three Ø1.8 mm (M1.6) at (10.2, 41.0), (10.2, 22.6), (36.5, 41.0). Still to add,
  once their positions are known: YD-ESP32-S3, E220 (T22D/T30D), Core1262 and EG800AK holes.
- **Copper:** GND pours on both layers. Net rules: 0.8 mm tracks for VBAT, BAT_CELL_N, SYS,
  BOOST_SW, 5V, VBUS, VIN_RAW and VBAT_LTE; 0.5 mm for GND, 3V3P, 5V_LORA and 3V3_SX; 0.254 mm
  for signals.
- **Routing:** the first autoroute (2026-11-21) predates the re-placement and has to be redone
  with "keep existing" off. The 1048P footprint keeps the bottom pour out from under the whole
  holder body, so there is no bottom GND plane under the modules (stitching vias there float).
- **Footprint checks against the starred EasyEDA parts:** W5500-lite matches (rows 20.32 mm, pin 1
  at the jack end). The E220 T22D/T30D 7-pin row matches; both modules also have 3–4 pins at the
  SMA end (mounting/GND) that this carrier leaves unsupported: a 1 × 4 SMD socket or a standoff
  there would stop the module rocking. The starred "SX1262 core" footprint is the castellated
  Core1262 with rows 16.2 mm apart, not the 15.24 mm used here (Waveshare drawing for the pinned
  board): measure the module before ordering. The YD-ESP32-S3 and EG800AK footprints had no
  geometry to read.
- **To do:** reroute, rebuild pours, join any GND islands, widen SYS, final DRC.
