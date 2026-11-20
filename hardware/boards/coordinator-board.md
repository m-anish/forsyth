# Coordinator carrier board — reference sheet

**Started 2026-11-20.** Replaces the hand-soldered perfboard (firmware/coordinator/README.md,
"Carrier board"). A two-layer carrier that the coordinator's modules plug into: the dev
board, the LoRa radio, the Ethernet module, the RTC, a charger and one 18650 that carries
the station's gateway through a power cut. Designed in EasyEDA Pro (`forsyth-coordinator`).

Status (2026-11-20): **schematic drawn, ERC clean** (0 errors, 2 minor warnings, no floating
pins; every net checked against §2–3). EasyEDA Pro project `forsyth-coordinator`
(`72172190064947adb14801d54671a5b3`), schematic page P1. Not laid out yet: footprints marked
**[measure]** need the module in hand first.

Designators as drawn: H1/H2 dev-board headers P1/P2, H3 E220, H4/H5 Core1262 rows, H6/H7 W5500
rows, H8 ZS-042, H9 OLED, H10 spare GPIO, H11/H12/H13 TP4056 IN/B/OUT, BT1 18650 holder
(Keystone 1042P), U1 Qwiic, U2 USB-C, U3 5 V terminal, U4 TPS61023, U5 AMS1117-3.3, F1 PTC,
D1 SMAJ5.0A, D2 SS34, Q1/Q2 CJ3407, Q3 2N7002, L1 SWPA5040S1R0NT, RF1 SMA (Core1262 antenna,
DNP until it is fitted). The headers use 2.54 mm pin-header footprints; fit female headers.

## 1. What plugs in

| Ref | Module | Interface | Footprint | Notes |
|---|---|---|---|---|
| U1 | **YD-ESP32-S3 N8R2** (VCC-GND Studio; FlyRobo) | — | 2 × 22-pin female headers, 2.54 mm, rows **25.40 mm** apart | Board 27.94 × 57.15 mm, antenna end 6.2 mm past it. Pin 1 (3V3) at the antenna end. Both USB-C at the far end: keep that edge clear and at the board edge. **Leave its IN-OUT jumper open** (the carrier feeds its 5V pin; the open jumper's diode stops that reaching a laptop's USB). Its RGB jumper must be closed for the WS2812 on GPIO48. |
| U2 | **Ebyte E220-900T22D *or* T30D** (UART, LLCC68) | UART1 | one 1 × 7 female header, 2.54 mm, both module outlines in silk (as on Board A) | Same pin order on both: M0, M1, RXD, TXD, AUX, VCC, GND. T30D outline is the larger; antenna (SMA on the module) toward the board edge. |
| U3 | **Waveshare Core1262-HF** (SX1262, SPI) — future | SPI (shared) | 2 × 8 castellated / 2.54 mm **[measure row spacing]**, module 19 × 22 mm | Left: GND, GND, RXEN, TXEN, DIO2, DIO1, GND, 3V3. Right: ANT, GND, CS, CLK, MOSI, MISO, RESET, BUSY (Waveshare Core126X schematic). Optional edge SMA from ANT (50 Ω, DNP); the module also has an IPEX. |
| U4 | **W5500 mini** (green, Ethernet) | SPI (shared) | 2 × 1 × 6 headers **[measure row spacing]**, module 28.5 × 23.5 mm | Left: GND, GND, MOSI, SCK, CS, INT. Right: GND, 3V3, 3V3, NC, RST, MISO. **3.3 V only.** RJ45 at the board edge. |
| U5 | **DS3231 ZS-042** (RTC + AT24C32) | I2C | 1 × 6 header (32K, SQW, SCL, SDA, VCC, GND) **[measure position]** | Has its own 4.7 k pull-ups. Its coin-cell "charger" (a resistor and diode) cooks a CR2032: remove the resistor, or fit an LIR2032. |
| U6 | **TP4056 + DW01 module** (USB-C, with protection) | — | IN+ / IN− / B+ / B− / OUT+ / OUT− pads **[measure]** | Charges at 1 A (its 1.2 k R_PROG). OUT± is the protected cell. |
| BT1 | **18650 Li-ion**, SMD holder (e.g. Keystone 1042 pattern) | — | SMD | Li-ion, 4.2 V: the TP4056 is a Li-ion charger, **not** LiFePO4 like the leaves. |

## 2. Power

```
5 V in (USB-C power-only, or 2-pin terminal from a PoE splitter)
  └─ F1 PTC 2 A ─ D1 SMAJ5.0A ─┬──────────────── VBUS ── U6 TP4056 IN+ ── BT1 (via B+/B−)
                               │                                  OUT+ = VBAT (protected)
                               ├── D2 SS34 ──┐
  VBAT ── Q1 CJ3407 (P-FET, gate on VBUS) ───┴── SYS (3.0–4.8 V)
                                                  └─ U7 TPS61023 boost ── 5V (4.95 V)
5V ─┬─ U1 5V pin (its own LDO makes the ESP32's 3.3 V)
    ├─ Q2 CJ3407 high-side switch ── 5V_LORA ── U2 VCC (+ 220 µF + 100 nF at the pin)
    └─ U8 AMS1117-3.3 ── 3V3P ── U3, U4, U5, OLED/Qwiic
```

- **Load sharing:** with 5 V present, Q1's gate is held high (off) and the load runs from
  VBUS through D2 while the TP4056 charges the cell. Without it, Q1's 100 k gate pull-down
  turns it on and the cell carries everything. No gap at the hand-over beyond D2's drop.
- **One 5 V rail from the boost** (Board A's TPS61023 circuit, R1 732 k / R2 100 k):
  the dev board's LDO and the E220 both want a real 5 V, which a 3.0–4.2 V cell can't give.
  Its 3.7 A switch limit covers the T30D's 620 mA burst on top of the ESP32 and W5500.
- **3V3P** for the peripherals comes from its own LDO, not the dev board's 3V3 pin, so a
  W5500 (150–180 mA) and a Core1262 TX don't share the ESP32's regulator through WiFi peaks.
- **E220 power switch** (Q2 + Q3 2N7002, `LORA_PWR`): firmware can power-cycle a hung
  radio. Off at boot (gate pull-up, GPIO pull-down) until firmware turns it on.
- **Supply sizing:** up to about 1.5 A for the load plus 1 A charging: use a ≥ 2.5 A 5 V
  supply or a 12 W PoE splitter.
- **Backup time:** about 0.4 A average from the cell (WiFi or Ethernet up, radio in RX):
  roughly 6 to 8 hours on a 3000 mAh 18650.

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
| DS3231 SQW (alarm / 1 Hz) | 6 | input, pulled up on the module |
| `VBAT_SENSE` | 4 | ADC1: 100 k / 100 k from VBAT + 100 nF |
| `VBUS_SENSE` | 5 | 100 k / 100 k from VBUS: high = on mains |
| spare | 15, 35, 36, 37 | to a 1 × 6 header with 3V3 and GND |

## 4. Connectors and the rest

- **J1** USB-C power-only receptacle (CC1/CC2 5.1 k to GND) and **J2** 2-pin 5 V terminal
  (PoE splitter), both into F1.
- **J3** OLED, 4-pin (GND, VCC, SCL, SDA: the common SSD1306 order). **J4** Qwiic JST-SH
  (GND, 3V3, SDA, SCL, as on Board A). **J5** spare GPIO.
- Test points: VBUS, SYS, VBAT, 5V, 3V3P, GND.
- Four M3 holes. No copper under the E220's and Core1262's antenna ends; the
  W5500's RJ45 and both LoRa antennas on opposite edges.

## 5. Open before layout

1. **[measure]** W5500 mini: row spacing and header position; Core1262: row spacing;
   ZS-042: header position and board outline; TP4056 module: pad positions.
2. Choose the 18650 holder part (SMD, one cell) and check its pads.
3. Firmware: `config.py` pins for the Core1262, W5500 RST, `LORA_PWR`, the two sense pins.
