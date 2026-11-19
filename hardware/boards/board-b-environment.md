# Board B — environment

**Role:** the quiet senses, inside the Stevenson screen: temperature and humidity,
pressure, lightning (AS3935), and the PMS7003 particle sensor. Passive supply only;
its distance from Board A's switchers *is* the AS3935's noise isolation.
**Status:** rev0 laid out 2026-11-13 (EasyEDA Pro project `forsyth-board-b`), ordered
at JLCPCB 2026-11-18. v1 (2026-07-11) assumed three fixed modules and a separate PMS7003 pigtail;
v2 made Board B a carrier that takes whichever common modules are in stock. The rev0
layout then grew the board to 58 x 70 mm and the Stevenson screen with it (nothing
was printed yet), so the PMS7003 plugs straight into the back, a PMS5003 fits
instead, and one cable with one connector goes to the box. On 2026-11-16 it was trimmed:
the module sockets went, and the board now carries its sensors soldered on (SHT40,
MS5607), one connector for the DFRobot lightning module under the cap, J3 for the
PMS7003, J1 to the box, and four unfitted fallback pads.

## 1. Constraints that set the board

| Constraint | Value | From |
|---|---|---|
| Outline | **58 x 70 mm**, 1.6 mm, 2 layers | `hardware/enclosures/station/params.py` (`scr_pcb_w`, `scr_pcb_h`, `scr_pcb_t`) |
| Edge keep-out | 2.5 mm along both 70 mm edges, both sides | the screen holds the board in 2 mm-deep rail grooves |
| Bottom edge | 2 mm keep-out; no sill | the corners rest on the rails; J1's plug points down out of the bottom edge into 18 mm of free space (`scr_pcb_lift`) |
| Chamber | 76 mm across (`scr_r_in` 38) | set by the back: a PMS5003 (50 wide, 24 deep). The front now carries only low parts (J2 stands 6.6 mm); the 48 x 26 mm front envelope in `params.py` dates from the module-socket design and is generous |
| Rails stand proud | 4 mm either side of the board, from 27 mm off-centre outwards | screen rails; a 50 mm PMS5003 clears them by 2 mm a side, a PMS7003 by 3 mm |
| Link to Board A | must work with **Board A rev0 as built** | J4 `BOARD-B` XH-5 and J5 `AQI` XH-4, reached through one cable (§5) |

## 2. What the shops actually stock (checked 2026-11-12)

Prices in Rs, incl. GST where the shop shows it. "OUT" = listed but out of stock.

| Sensor | Module | Robu | Flyrobo | Quartz | Verdict |
|---|---|---|---|---|---|
| T + RH + P | AHT20 + BMP280 combo (purple, 4 pins) | 149 | 117 | — | **cheapest complete fallback** |
| T + RH | GY-SHT31-D | 399 | — | — | good module, Sensirion quality |
| T + RH | GY-SHT30-D | — | 161 OUT | 167 OUT | same pinout as SHT31-D |
| T + RH | GY-SHT40 / GY-SHT41 | 239 OUT / 559 OUT | 227 OUT | — | best sensor, poor module stock |
| T + RH | SHTC3 Qwiic (SparkFun / Adafruit) | 831 / 1109 | — | — | reliable, expensive |
| T + RH | AHT20 bare-ish modules | 158 (SmartElex) | — | — | drifts more in sustained high RH |
| T + RH | HTU21D (GY-21) | — | — | 136 | older part, still fine |
| T + RH | **SHT40 / SHT41 bare chip** | **249** (SHT40-AD1B, SHT41I-AD1B) | — | — | **best value Sensirion; needs SMD assembly** |
| T + RH | SHTC3 bare chip | 93 to 109 | — | — | cheapest Sensirion; needs SMD assembly |
| P | **GY-BMP280-3.3 / BMP280 module** | **31** | 36 | 33 | **pressure, near-free** |
| T + RH + P | BME280 modules | 419 to 652 | 586 to 699 | 464 | no longer worth it: BMP280 + a Sensirion part is cheaper and better |
| Lightning | DFRobot Gravity Lightning (AS3935, SEN0290) | 2359 | — | — | tuned antenna; the v1 choice |
| Lightning | CJMCU / MCU-3935 | 2669 | 2278 OUT | — | clone, dearer than DFRobot now |
| Lightning | SparkFun AS3935 | 4879 | — | — | too expensive |
| PM | PMS7003 | 1369 to 1881 (mostly OUT) | — | — | already owned |

Takeaways: Sensirion T/RH **modules** are patchy, while the bare chips are cheap and
in stock. BMP280 modules are everywhere at ~Rs 35. The AHT20 + BMP280 combo is the one
module that is cheap, in stock at two shops, and covers T, RH and P alone.

## 3. Decisions

1. **Primary T/RH is a bare SHT4x on the board** (SHT40/SHT41/SHT45 share one
   footprint and address 0x44), on a slotted peninsula at the top edge so the
   board's own warmth and the PMS7003 do not reach it. Assembled by JLCPCB or by hand
   with hot air.
2. **Pressure is a bare TE MS5607-02BA03 on the board** (U2, 5 x 3 mm, JLC-assembled),
   off the tongue. PS and CSB to VBAT select I2C at address 0x76, clear of the SHT4x at
   0x44; SDO is unused. Chosen 2026-11-17 over the BMP580 because JLC places it with
   Economic PCBA (every Bosch/Infineon/ST/TDK alternative was "Standard only"): ±1.5 mbar
   absolute, ±1 mbar/year drift, -40 to +85 °C, 0.14 µA max standby, 1.8 to 3.6 V. It
   needs an MS5607 driver (PROM C1 to C6, CRC-4, second-order compensation). Order with
   **no board washing**, which can damage the sensor. MS5611-01BA03 (C15639) is the same
   family as a fallback; check its footprint.
3. **No module sockets.** The v2 sockets (S1 to S7) were dropped on 2026-11-16: with T, RH
   and P soldered on there is nothing to choose at build time and nothing to hunt for in
   module stock.
4. **Fallback: four unfitted pads** (J5, a 1 x 4 2.54 mm SMD header footprint) in the top
   right corner, `VBAT GND SCL SDA`, the order most GY modules use, so a module can still
   go on if a chip is ever out of stock.
5. **AS3935: one JST PH 5-pin** (J2, B5B-PH-SM4-TB, SMD vertical) for the DFRobot Gravity
   module's cable, `VBAT GND SCL SDA IRQ`. The module itself does **not** sit on Board B:
   it is fixed under the screen cap, the farthest point from the PMS7003 motor and the
   cable entry. Its cable splits at the module end into a Gravity 4-pin plug and the IRQ
   wire.
6. **PMS7003 plugs straight into the back of Board B** (J3), label face to the board,
   vents towards the bottom edge, no ribbon. Foam tape fills the gap J3's 4.3 mm socket
   leaves under the sensor, and a cable tie through the two NPTH slots (TIE1, TIE2,
   1.6 x 4.2 mm) holds it. The board is wide enough that the sensor lies between the
   rails, not on them. Run the PMS only after the T/RH reading, as the firmware already
   does.
7. **J3 is a 2 x 5, 1.27 mm female SMD socket** (HCTL PM127-2-05-S-4.3), the board half
   of the Plantower "1.27 mm 2x5P" connector. Because the sensor is mirrored onto the
   back, J3's pads are wired by position, not by number: see the map in §4.
8. **PMS5003 instead: J4, a Molex PicoBlade 1x8** (53398-0871, SMD vertical top-entry, back
   side) for the PMS5003's stock cable. The PMS5003 lies where the PMS7003 would; leave
   J3 unfitted, since its socket would hold the sensor off the foam.
9. **Everything but J1 is SMD**, so nothing pokes through the back under the PMS. J1, the
   one through-hole part, sits below the PMS footprint.
10. **Board A link: one XH-8 on Board B** (J1, right-angle, mouth down out of the bottom
    edge), one 8-core cable to a **GX16-8 on the box**, and a short pigtail inside the
    box to Board A J4 and J5 (§5). Board A rev0 is unchanged.

## 4. Nets and pin maps

| Net | Board B J1 pin (= GX16-8 pin) | Board A | Board B users |
|---|---|---|---|
| VBAT (3.0 to 3.6 V, LiFePO4) | 1 | J4.1 | SHT4x, MS5607, J2.1, J5.1, pull-ups |
| GND | 2 | J4.2, J5.2 | all |
| SDA | 3 | J4.3 | SHT4x, MS5607, J2.4, J5.4 |
| SCL | 4 | J4.4 | SHT4x, MS5607, J2.3, J5.3 |
| AS3935_IRQ | 5 | J4.5 | J2.5 |
| 5V_AQI (gated by Board A) | 6 | J5.1 | PMS7003 pins 1, 2; PMS5003 pin 1 |
| PMS_RX (Board A TX) | 7 | J5.3 | PMS7003 pin 7; PMS5003 pin 4 |
| PMS_TX (Board A RX) | 8 | J5.4 | PMS7003 pin 9; PMS5003 pin 5 |

PMS RESET and SET are left unconnected (both default to normal running when floating),
each with an unpopulated 10 k to VBAT: R7 on PMS_RESET (PMS7003 pin 5, PMS5003 pin 6),
R8 on PMS_SET (PMS7003 pin 10, PMS5003 pin 3).

**J3 pad map.** The PMS7003 faces the board, so its connector lands mirrored: each J3
pad meets the PMS pin one column over. Pads were assigned to nets by where the PMS pins
land, which is why the pad numbers don't match the PMS pin numbers:

| J3 pad | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| PMS7003 pin | 2 | 1 | 4 | 3 | 6 | 5 | 8 | 7 | 10 | 9 |
| Net | 5V_AQI | 5V_AQI | GND | GND | NC | PMS_RESET | NC | PMS_RX | PMS_SET | PMS_TX |

**J4 (PMS5003, PicoBlade 1x8):** 1 5V_AQI, 2 GND, 3 PMS_SET, 4 PMS_RX, 5 PMS_TX,
6 PMS_RESET, 7 and 8 NC; mounting tabs to GND.

Bus pull-ups: R1, R2 = 10 k to VBAT on Board B. If the DFRobot module carries its own
pull-ups they simply parallel these; check the bus edges at bring-up (§9). J2 pins:
1 VBAT, 2 GND, 3 SCL, 4 SDA, 5 AS3935_IRQ (tabs to GND). J5 pins: 1 VBAT, 2 GND, 3 SCL,
4 SDA.

Decoupling: 100 nF at the SHT4x (C1), the MS5607 (C2) and J2 (C3); 10 uF at J1 (C8).

Power caveat: Board B runs everything from VBAT, not 5 V. Both soldered sensors are
happy there (SHT4x 1.08 to 3.6 V, MS5607 1.8 to 3.6 V). A module on the J5 fallback pads
should be a 3.3 V version; "5 V" GY modules have a 3.3 V regulator that drops out to
about 3.0 V at this supply, which usually still works.

## 5. Board B to Board A: the cable

```
Board B J1 (XH-8) ── one 8-core cable ── GX16-8 plug │ GX16-8 socket on the box (ENV port)
  in the screen        out of the screen base,        │   inside: short pigtail
                       along the crossarm, down       │     pins 1-5      -> XH-5 -> Board A J4
                       the mast                        │     pins 6,2,7,8  -> XH-4 -> Board A J5
```

- **Screen end: JST XH-8 crimped onto the cable**, plugged into J1. J1 is right-angle
  with its mouth pointing down out of the board's bottom edge, so the plug and the bend
  of the cable sit in the 18 mm under the board and the cable leaves through the screen
  base.
- **Box end: GX16-8 plug** on the cable, into a GX16-8 socket in the box's ENV port.
  GX pin n = J1 pin n (§4). Eight pins is unique among the box's GX ports (GX12-2,
  GX12-3, GX12-4, GX16-5, GX16-8), so the "pin count = key" rule still holds, and the
  screen can be unplugged and swapped without opening the box.
- **Inside the box: one pigtail** from the GX16-8 socket's solder cups: pins 1 to 5 to an
  XH-5 for Board A J4, and pins 6, 2, 7, 8 to an XH-4 for Board A J5 (GND from pin 2
  spliced to both). The XH-5 and XH-4 can't be swapped, by pin count.
- **Cable:** 8-core shielded (Cat5e STP or alarm cable). Pairs: SDA with GND, SCL with
  VBAT, PMS_RX with PMS_TX, 5V_AQI with IRQ; shield to GND at the box end only. v1
  planned 0.5 m or less; the route down the mast may be longer, so measure it and check
  the I2C edges at bring-up (§9).

Decided 2026-11-15: Anish orders the XH-8 and GX16-8 parts and builds this cable.
This replaces v2's plan of two XH headers on Board B with a split cable and a gland.
Rejected along the way: RJ45 (needs a Board A change, and the jack is bulky), and a
cable soldered to Board B (no field swap).

## 6. Layout (rev0, trimmed 2026-11-16; front = sensors and connectors, back = PMS)

```
 top   ┌──────────────┬─[U1 SHT4x]─┬──────────────┐   tongue 8 x 10 mm between
       │ J2 PH-5      │  C1 tongue │   J5 (DNP)   │   two 1.2 mm slots
       │ (lightning)  │            │   U2 MS5607  │
       │ C3                ◯ TIE2         C2      │
       │ brand block,                notes        │
       │ StarStuckLab logo                        │
       │                                          │
       │ C8 R1 R2              ◯ TIE1   R7 R8 (DNP)│
       │ J1 XH-8, mouth down ↓        (J4 behind) │
bottom └──────────────────────────────────────────┘
        back: PMS7003 footprint x 5.2 to 52.9, y 13 to 49.7 mm, J3 at (48.4, 19.4),
        vents to the bottom edge; J4 PicoBlade at (46, 7). 2.5 mm rail keep-out on both
        long edges, both sides.
```

- No copper pour under the SHT4x tongue; its four pins run on thin traces.
- U2 (MS5607) sits off the tongue at (45, 55.5) mm with C2 beside it; J2 at the top left with C3.
- Bottom GND pour; the tie strap path between the slots is kept free of parts on top.
- Branding (logo, StarStuckLab, URL, board name, revision) is on the front; the back
  carries only what you need while fitting the PMS.

## 7. Backups if parts disappear

| If this is gone | Use instead | Where it goes |
|---|---|---|
| SHT40 | SHT41 or SHT45 (same footprint, same 0x44) | U1 |
| | any 3.3 V T/RH breakout on `VBAT GND SCL SDA` | J5 fallback pads |
| MS5607 | MS5611-01BA03 (same family; check footprint) | U2 |
| | a BMP280 / BME280 breakout | J5 fallback pads |
| DFRobot AS3935 | any AS3935 board, on a cable wired to J2's `VBAT GND SCL SDA IRQ` | J2 |
| PMS7003 | PMS5003 | J4, on its stock PicoBlade cable; leave J3 off |
| | PMSA003 | same 2x5 1.27 mm connector as the PMS7003 but a smaller body; on a cable to J3, untested |

Firmware auto-detects by I2C scan (architecture §7). The MS5607 needs its own driver.

## 8. Board BOM

LCSC numbers as chosen in the EasyEDA Pro project `forsyth-board-b` (rev0, trimmed 2026-11-16, MS5607 2026-11-17).
"Basic" = JLCPCB basic part (no loading fee). Exported BOM: `hardware/fab/board-b/board-b-rev0-bom.csv`.
Costing and sourcing: `hardware/fab/board-b/jlcpcb-costing.md`, `hardware/fab/board-b/india-sourcing.md`.

| Ref | Part | LCSC | Note |
|---|---|---|---|
| U1 | Sensirion SHT40-AD1B-R2 | C2909890 | DFN-4 1.5 x 1.5, 0x44; SHT41/SHT45 drop in; JLC-fitted |
| U2 | TE MS5607-02BA03 (MS560702BA03-50) | C97627 | 5 x 3 mm, I2C 0x76; JLC-fitted (Economic); no board washing |
| J1 | XH-8AW right-angle (BOOMELE) | C10395 | the cable to the box (§5); the only through-hole part |
| J2 | JST B5B-PH-SM4-TB(LF)(SN), PH 5-pin SMD vertical | C265085 | DFRobot AS3935 cable: `VBAT GND SCL SDA IRQ`; tabs to GND |
| J3 | HCTL PM127-2-05-S-4.3, 2x5 1.27 mm SMD female, 4.3 mm | C3975131 | back side; PMS7003 plugs in directly; pads mapped in §4 |
| J4 | Molex PicoBlade 53398-0871, 1x8 SMD vertical (top entry) | C471413 | back side; PMS5003 only; fit J3 or J4, not both |
| J5 | 1x4 2.54 mm SMD female (hanxia HX PM2.54-1x4P TP H8.5-ZQ), DNP | C48641754 | fallback pads `VBAT GND SCL SDA` |
| R1, R2 | 10 k 0805 (UNI-ROYAL 0805W8F1002T5E) | C17414 basic | bus pull-ups to VBAT |
| R7, R8 | 10 k 0805, DNP | C17414 basic | PMS RESET, SET |
| C1, C2, C3 | 100 nF X7R 0805 (YAGEO CC0805KRX7R9BB104) | C49678 basic | U1, U2, J2 |
| C8 | 10 uF X5R 0805 (Samsung CL21A106KAYNNNE) | C15850 basic | at J1 |

Build notes (rev0 layout):
- **J3 sits on the back, mirrored, so its pads are wired by position** (§4). Checked on the
  PCB against the Plantower drawing's pin positions and a photo of the sensor's socket.
- **With a PMS5003, leave J3 off.** Its 4.3 mm socket sits under the PMS5003's body.
- Routing is autorouted, re-routed after the MS5607 swap. Ground is
  poured on the bottom; the SHT4x tongue has no pour.
- Tracks: 0.254 mm signal, 0.3 to 0.4 mm VBAT/GND/5V_AQI; clearance 0.2 mm; vias 0.6/0.3 mm.
- Silkscreen: designator and value at every part, pin names at J1, J2 and J5. Front carries
  the StarStuckLab logo and brand block; back carries the PMS7003 outline and orientation
  and the J4/PMS5003 note. ERC 0/0, DRC 0/0 at export.

## 9. Bring-up checklist

1. Harness to a bench Board A; I2C scan. Expect 0x44 (SHT4x), 0x76 (MS5607), plus the
   AS3935's address when the DFRobot module is plugged into J2.
2. SHT4x vs a reference thermometer, before and after the PMS7003 has run for 30 s:
   any rise is the PMS heating the peninsula.
3. MS5607 pressure vs a phone barometer (±2 hPa sanity).
4. AS3935: antenna auto-tune, then a piezo-lighter click at a few metres; repeat with
   the PMS7003 running to see whether its motor adds disturbers.
5. PMS7003 (or PMS5003 on J4): frames at 9600 baud on Board A's UART with the cable at
   full length.
6. I2C edges on a scope at Board A with the real cable fitted; slow edges mean a lower
   bus speed or stronger pull-ups.

## Open items

- Check the PMS7003 seats in J3 (PM127-2-05-S-4.3) and measure the gap under it for the
  foam tape, before ordering a batch.
- Check pin 1 of the PMS5003's PicoBlade cable against J4 before plugging it in.
- Make the lightning cable: PH 5-pin at J2, Gravity 4-pin (`+ - C D`) plus the IRQ wire at
  the module; confirm the Gravity pin order on the module first.
- Add an MS5607 driver to the firmware (PROM C1 to C6, CRC-4 per TE AN520, second-order
  compensation); the BMP280 driver will not work.
- JLC order: LeadFree HASL finish (OSP greys out Economic PCBA), and leave Board Cleaning
  unticked (the MS5607 must not be washed).
- Measure the AS3935 cable you have; the module needs to reach the screen cap.
- Make the GX16-8 to XH-5 + XH-4 pigtail for inside the box (§5).
