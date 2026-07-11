# Board A — core

**Role:** MCU + radio + power. The only board with switching converters. Lives in the
sealed box under the Stevenson screen; carries every external connector.
**Status:** reference sheet v1 (2026-07-11) — designators are proposals until the first
KiCad pass reconciles them.

## 1. Power rails

| Rail | Range | Source | Feeds |
|---|---|---|---|
| **VBAT** | 2.5–3.65 V | LiFePO4 cell (charged by CN3801) | MCU, Board B sensors, Board D excitation, dividers |
| **5V_RADIO** | 5.0 V, gated | TPS61023 #1 (EN = `EN_RADIO`) | E22 module only |
| **5V_AQI** | 5.0 V, gated | TPS61023 #2 (EN = `EN_AQI`) | PMS7003 only |

**There is no LDO.** The ATtiny3226 (1.8–5.5 V) and the I2C sensors run directly off
the cell — one conversion stage fewer, µA saved. One consequence to log:
**BME280's spec'd operating max is 3.6 V** while LiFePO4 floats at 3.625 ± 0.04 V —
inside BME280's absolute max (4.25 V) but a hair over the operating spec during float.
Accept (common in LiFePO4 builds), or drop a small LDO on Board B later if readings
drift at full charge. **[decision logged; revisit if pressure data misbehaves at float]**

## 2. MCU pin map — ATtiny3226, SOIC-20

Logical assignment (physical pin numbers per the tinyAVR-2 20-pin datasheet table —
**[verify pin numbers against the datasheet before layout]**):

| Pin | Port | Net | Function |
|---|---|---|---|
| 16 | PA0 | `UPDI` | programming (J7) |
| 17 | PA1 | `EN_RADIO` | TPS61023 #1 enable |
| 18 | PA2 | `EN_AQI` | TPS61023 #2 enable |
| 19 | PA3 | `SPARE1` | future (display CS?) |
| 2 | PA4 | `ANEMO` | anemometer pulse → Event System |
| 3 | PA5 | `RAIN` | rain-gauge pulse |
| 4 | PA6 | `VANE_ADC` | wind-direction ladder (AIN6) |
| 5 | PA7 | `VBAT_SENSE` | battery divider (AIN7) |
| 11 | PB0 | `SCL` | TWI0 → Board B + Qwiic |
| 10 | PB1 | `SDA` | TWI0 |
| 9 | PB2 | `UART_TX` | shared UART → E22 RXD / PMS RX |
| 8 | PB3 | `UART_RX` | shared UART ← E22 TXD / PMS TX |
| 7 | PB4 | `SPARE2` | future |
| 6 | PB5 | `SPARE3` | future (status LED?) |
| 12 | PC0 | `AS3935_IRQ` | lightning interrupt (from Board B) |
| 13 | PC1 | `E22_M0` | mode select — driven, never floated |
| 14 | PC2 | `E22_M1` | mode select — driven, never floated |
| 15 | PC3 | `E22_AUX` | E22 ready/busy (input) |
| 1 / 20 | VDD/GND | `VBAT`/`GND` | 100 nF at pin 1 |

## 3. Reference sub-circuits

### 3.1 Solar charging — CN3801 (U3)

Topology: solar in → reverse-polarity P-FET (Q1) → CN3801-controlled buck (external
P-FET Q2 + catch schottky D1 + power inductor L3) → sense resistor R_CS → cell.
Sourced facts ([datasheet pages via alldatasheet](https://www.alldatasheet.com/html-pdf/1133240/CONSONANCE/CN3801/698/1/CN3801.html)):

- **Charge current:** `I_CH = 120 mV / R_CS` (CSP/CSN sense pins).
  R_CS = **0.12 Ω → 1.0 A** (our default for a 1.5–2 Ah cell); the
  [fadushin/solar-esp32](https://github.com/fadushin/solar-esp32) reference design uses
  0.24 Ω → 0.5 A for a 1.5 Ah cell — either is sane; pick to match the cell bought.
- **MPPT:** the MPPT pin is regulated to **1.205 V**; a divider from the panel sets the
  tracked panel voltage: `V_MPP = 1.205 × (1 + R_H/R_L)`. For a "6 V" panel with
  V_MPP ≈ 5 V: **R_H = 316 k, R_L = 100 k** → 5.01 V (reference design: 300 k/100 k →
  4.82 V for a 5.2 V-MPP panel). Adjust to the panel actually bought. **[verify panel V_MPP]**
- **CV point:** fixed **3.625 V ± 40 mV** — the reason this chip was chosen; no divider.
- Trickle at 17.5 % of I_CH below 66.5 % of CV; termination at 16 % of I_CH; automatic
  recharge below the datasheet's recharge threshold.
- L3, Q2, D1 sizing: take the datasheet's typical-application values from your paper
  copy **[verify — my datasheet mirrors were partial]**; family designs use ~22–33 µH,
  an SS34-class 3 A schottky, and a SOT-23/SOT-223 P-FET ≥ 2× I_CH.
- Status: CN3801's charge-status pin → `SPARE3`/LED footprint (DNP by default).

### 3.2 Gated 5 V rails — TPS61023 ×2 (U4, U5)

Straight from TI's 5 V design example
([datasheet §8.2, SLVSF14B](https://www.ti.com/lit/ds/symlink/tps61023.pdf)) — one copy
per rail:

```
VBAT ──┬── L 1.0 µH ──┬── SW│TPS61023│VOUT ──┬──────┬─── 5V rail
       │              │      │       │       │      │
      Cin 10 µF       └──────┤       │      R1     Cout 2×22 µF
       │                     │  EN   │     732k     │
      GND        MCU GPIO ───┤       │       ├── FB │
                             │  GND  │      R2      │
                             └───────┘     100k    GND
```

- FB reference **595 mV typ** → R1 732 k / R2 100 k sets 4.95 V ("5 V").
- **EN ≥ 1.2 V = on, ≤ 0.4 V = off**; in shutdown the output is *disconnected* from
  the input (0.1 µA) — this is the power gate; startup ≈ 700 µs (add a couple of ms
  margin in firmware before touching the peripheral).
- U4 (radio rail): add the §3-mandated bulk **100–220 µF low-ESR + 100 nF at the E22's
  VCC pin**, downstream. ≥3 A valley current limit covers the T30D burst.
- U5 (AQI rail): identical circuit; PMS7003 draws ≤ 100 mA, no extra bulk needed beyond
  Cout + 100 nF at the PMS connector.
- Package SOT-563: the one fine-pitch part — flux + drag solder.

### 3.3 E22 interface (U2)

- `E22_M0`/`E22_M1` **driven at all times** (module has weak pull-ups; floating = deep
  sleep = the lokki trap). `E22_AUX` is an input; wait for its rising edge after
  power-up, two-edge (LOW→HIGH) around TX. Sequence in architecture §3.2.
- UART is 3.3 V logic on the module regardless of VCC (manual). **Design note found
  while writing this sheet:** our MCU runs at VBAT (2.5–3.65 V), so (a) when the cell
  is low, MCU-high ≈ 2.6 V into the E22's Vih — expected fine but unspecified,
  bring-up check; (b) the E22's 3.3 V TXD into an MCU pin powered at < 3 V exceeds
  VDD + 0.3: **fit R14 = 10 k in series with `UART_RX`** to limit pin-clamp current to
  a safe < 100 µA. Costs nothing at 9600 baud.
- Antenna: SMA edge or u.FL per enclosure choice; 50 Ω trace per §8.

### 3.4 Battery sense

`VBAT ── R15 1 M ──┬── R16 330 k ── GND`, tap → `VBAT_SENSE`, **C? 100 nF at the tap**
(charge reservoir for the ADC sample cap). Full-scale: 3.65 V → 0.906 V against the
internal 1.024 V reference. Continuous drain ≈ 2.7 µA — accepted (smaller than the
AS3935's 60 µA floor); a high-side-switched divider is the upgrade if that ever
matters.

### 3.5 UPDI (J7)

3-pin header/pads: `UPDI · GND · VBAT`. The SerialUPDI adapter carries its own series
resistor; a 1 k series on the target pad is harmless insurance. No crystal, no reset
line — UPDI is the whole story.

### 3.6 Protection row (per architecture §8)

- Solar input: Q1 reverse-polarity P-FET (AO3401, gate to GND) + **SMAJ6.0A** TVS
  across the input (panel Voc ≈ 6–7 V — verify against the panel; use SMAJ10A if Voc
  is higher). **[verify panel Voc]**
- Every signal entering from outside (`VANE_ADC`, `ANEMO`, `RAIN`): 1 k series +
  100 nF to GND at the connector + bidirectional TVS/PESD to GND.
- GX shield pins: to GND at this end only.

## 4. Connectors (all on Board A)

| Ref | Type | Pinout |
|---|---|---|
| J1 | GX12-2 panel socket | 1 solar+, 2 GND(solar−) |
| J2 | GX12-3 panel socket | 1 rain pulse, 2 GND, 3 shield |
| J3 | GX16-5 panel socket | 1 VBAT(excitation), 2 GND, 3 vane analog, 4 anemo pulse, 5 shield |
| J4 | JST-XH-5 | 1 VBAT, 2 GND, 3 SDA, 4 SCL, 5 AS3935_IRQ → Board B |
| J5 | JST-XH-4 | 1 5V_AQI, 2 GND, 3 UART_TX (→PMS RX), 4 UART_RX (←PMS TX) |
| J6 | JST-SH-4 (Qwiic) | 3V3(VBAT) · GND · SDA · SCL |
| J7 | UPDI 3-pin | UPDI · GND · VBAT |
| BT1 | 18650 holder | on-board |

## 5. Board BOM (designators)

| Ref | Part | Value/pkg | Note |
|---|---|---|---|
| U1 | ATtiny3226-SU | SOIC-20 | |
| U2 | E22-900T22D (T30D per site) | DIP module | |
| U3 | CN3801 | SOP-8 | on hand |
| U4, U5 | TPS61023 | SOT-563 | Robu |
| Q1 | AO3401 | SOT-23 | reverse-pol |
| Q2 | P-FET ≥ 2×I_CH | per CN3801 datasheet | **[verify]** |
| D1 | SS34 schottky | SMA | buck catch |
| D2… | SMAJ6.0A + PESD row | | protection |
| L1, L2 | 1.0 µH, Isat > 4 A | per TI table | boost |
| L3 | 22–33 µH power | per CN3801 app | **[verify]** |
| R_CS | 0.12 Ω 1 % ≥ 0.5 W | 2512 | 1 A charge |
| R1,R3 / R2,R4 | 732 k / 100 k | 1 % | boost FB ×2 |
| R5, R6 | 316 k / 100 k | 1 % | MPPT divider |
| R14 | 10 k | | UART_RX clamp limiter |
| R15, R16 | 1 M / 330 k | 1 % | VBAT sense |
| C1–C4 | 10 µF ×2 (Cin), 22 µF ×4 (Cout) | X5R/X7R ≥ 10 V | boosts |
| C5 | 100–220 µF low-ESR | | at E22 VCC |
| C6… | 100 nF field | | every VDD pin + RC row |
| J1–J7, BT1 | per §4 | | |

## 6. Bring-up checklist

1. Populate power path only (U3, Q1/Q2, D1, L3, R_CS, dividers). Bench supply as
   "panel": confirm CV 3.625 V at the cell node, charge current = 120 mV/R_CS,
   MPPT knee at the divider's V_MPP.
2. Populate U1 + UPDI. `pymcuprog ping`, blink `SPARE3`.
3. Populate U4/U5. EN low → confirm **0 V** on both 5 V rails (the entire point);
   EN high → 4.95 V; measure shutdown leakage.
4. Populate U2 + bulk cap. Wake sequence per architecture §3.2; watch AUX on a scope;
   TX burst current on the VBAT rail (expect ≤ ~300 mA input-side for T22D).
5. Connect Boards B/D via harnesses; I2C scan; ladder voltage sanity; pulse counters.
6. Leave overnight on battery; measure sleep floor (target: AS3935 60–80 µA + ~5 µA).
