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

All values below from the **CN3801 datasheet Rev 1.0** (Consonance, on file) and the
fadushin/solar-esp32 schematic (both reviewed 2026-07-11). Package correction: CN3801
is **SSOP-10**, not SOP-8 as earlier drafts said.

Topology (datasheet Figure 1): panel → input cap bank → series block schottky D1 →
P-FET Q2 (gate from DRV) → freewheel schottky D2 to GND → L3 → **R_CS (Kelvin-sensed
by CSP/BAT)** → cell.

```
SOL+ ──┬─C_in bank─┬── D1 SS34 ──╥ Q2 AO3407 ──┬── L3 33 µH ──┬─ R_CS 0.24Ω ─┬── BAT+ (cell)
       │           │      DRV ───╨ (gate)      │              │  CSP ─┘ └─ BAT│ (Kelvin pair)
      R3 390k     VCC(9)                   D2 SS34            C_out bank      │
       ├── MPPT(6)                             ▼           10 µF el + 10 µF X7R
      R4 100k     VG(1)─100nF─VCC          GND
       │          COM(5)─120Ω+220nF─GND · CHRG(3)/DONE(4)─LEDs+1k (DNP option)
      GND
```

- **Charge current:** `I_CH = 120 mV / R_CS` (CSP–BAT pins, 120 mV internal ref).
  **R_CS = 0.24 Ω 1 % ≥ 1 W → 0.5 A** — matches the reference schematic, and is the
  right *ceiling* for a 1–2 W panel (I_MP ≈ 0.17–0.33 A: MPPT, not CC, governs).
  Drop to 0.12 Ω → 1 A only if the panel ever grows to ~5 W.
- **MPPT:** pin regulated to **1.205 V**; `V_MPP = 1.205 × (1 + R3/R4)`; charging only
  starts once the MPPT pin exceeds 1.23 V. For the common Indian "6 V" epoxy panel
  (V_MP ≈ 6 V, Voc ≈ 7.2 V): **R3 = 390 k, R4 = 100 k → 5.90 V**. (fadushin's
  300 k/100 k → 4.82 V suits a 5 V-MP panel.) Set to the label of the panel bought.
- **Panel floor — datasheet constraint:** VCC range 4.5–28 V, **UVLO 3.8 V typ /
  4.4 V max**, and charging needs VCC > V_BAT + 0.32 V. A "5 V" panel sags into UVLO
  territory under load; **buy a 6 V-class panel**, not 5 V.
- **CV:** fixed 3.625 V ± 40 mV. Trickle 17.5 % of I_CH below 66.5 % of CV; terminate
  at 16 % of I_CH; auto-recharge at 91.66 % of CV; sleep mode when panel < battery.
- **Q2 = AO3407** (SOT-23 P-ch, 30 V/4.1 A, Robu-stocked): the datasheet itself lists
  "3407A" among suggested FETs. DRV's internal clamp holds V_GS ≤ 8 V — low-voltage
  FETs are safe by design.
- **D1, D2 = SS34** (3 A schottky, Robu-ubiquitous). **D1 stays populated:** the
  datasheet allows omitting it, but without it the cell back-feeds ~18 µA through the
  FET body diode all night — real money in our sleep budget; D1's cost is one Vf
  during charging, which the panel margin absorbs.
- **L3 = 33 µH, I_sat ≥ 1 A** (datasheet method: ΔI_L = V_BAT·(1−V_BAT/VCC)/(f·L) at
  f = 300 kHz, target ΔI_L ≈ 0.3·I_CH → 32 µH for 0.5 A at VCC = 6 V).
- **Caps (datasheet-specified structure):** input = electrolytic (100 µF/25 V) ∥
  10 µF ceramic ∥ 100 nF; output = 10 µF electrolytic ∥ 10 µF ceramic.
  **VG→VCC: 100 nF** (pins 1→9). **COM: 120 Ω + 220 nF in series to GND** (pin 5).
- **Status LEDs:** CHRG (red) + DONE (green) via 1 k, populated for bring-up (they
  draw from the panel only — dark at night); datasheet: an *unused* status output
  should be tied to GND, so if DNP'd, fit the tie-off jumpers instead.
- **Layout (datasheet §PCB, feeds §8):** R_CS right at the inductor output; CSP/BAT
  routed as a tight Kelvin pair on one layer to the resistor's terminals; analog and
  power grounds return to the star separately; generous copper on GND pins (they heat-sink).

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
| U3 | CN3801 | **SSOP-10** | on hand |
| U4, U5 | TPS61023 | SOT-563 | Robu |
| Q1 | AO3401 | SOT-23 | reverse-pol (solar input) |
| Q2 | **AO3407** | SOT-23 | buck pass P-FET — datasheet-suggested "3407A"; Robu |
| D1, D2 | **SS34** ×2 | SMA | series block + freewheel; D1 stays (night back-feed) |
| D5… | SMAJ6.0A + PESD row | | protection |
| D3, D4 | LED red/green + R7,R8 1 k | 0805 | CHRG/DONE status (bring-up; tie-off if DNP) |
| L1, L2 | 1.0 µH, Isat > 4 A | per TI table | boost |
| L3 | **33 µH power, Isat ≥ 1 A** | CDRH/radial | datasheet ΔI_L method @ 0.5 A |
| R_CS | **0.24 Ω 1 % ≥ 1 W** | 2512, Kelvin | 0.5 A charge (0.12 Ω if panel ≥5 W) |
| R1,R3 / R2,R4 | 732 k / 100 k | 1 % | boost FB ×2 |
| R5, R6 | **390 k / 100 k** | 1 % | MPPT → 5.90 V (set to panel V_MP) |
| R10 + C10 | 120 Ω + 220 nF | | COM compensation (datasheet pin 5) |
| C11 | 100 µF electrolytic 25 V | | CN3801 input LF |
| C12 | 10 µF electrolytic | | CN3801 output LF |
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
