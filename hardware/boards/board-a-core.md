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
| 19 | PA3 | `CHG_INHIBIT` | charge-inhibit NFET gate (§3.5a; 100 k pulldown = fail-safe charge-on) |
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

### 3.3 Radio interface — E220-900T22D (U2; decided 2026-07-12)

- LLCC68-based Ebyte E220 family. Manual-confirmed: TX 110 mA typ @22 dBm (T30D
  variant: 620 mA @30 dBm — the rail is sized for it), sleep 5 µA (moot — we hard-gate),
  logic fixed at 3.3 V, "≥5.0 V ensures output power", M0/M1 weak pull-ups, 200-byte
  packets. **lokki's E220 config code and register map
  (`../../lokki/firmware/micropython/src/comms/lora_config.py`) are the working
  reference** — same family, already debugged.
- `E22_M0`/`E22_M1` (net names kept) **driven at all times**; `E22_AUX` input; two-edge
  AUX wait around TX. Sequence in architecture §3.2.
- MCU-at-VBAT notes stand: (a) low cell ⇒ MCU-high ≈ 2.6 V into the module's Vih —
  bring-up check; (b) module 3.3 V TXD into a <3 V-powered MCU pin exceeds VDD + 0.3:
  the **10 k series in `UART_RX` (R2)** limits clamp current. Costs nothing at 9600 baud.
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

### 3.5a Charge inhibit — cold-weather protection (added 2026-07-12)

LiFePO4 must not be charged below 0 °C (lithium plating). Mechanism: **one 2N7002 on
the CN3801's MPPT pin node** — datasheet: charging requires MPPT > 1.23 V, so grounding
the pin is a clean enable/disable that never touches the power path.

```
MPPT node (R9/R12 junction) ── D  2N7002  S ── GND
            CHG_INHIBIT (PA3) ──┬── G
                                └── R19 100 k → GND    ← the fail-safe
```

- Drive high → charging inhibited. MCU dead/reset/tri-state → 100 k holds the FET off
  → **charging proceeds** (the dead-battery + sun edge case is satisfied structurally).
- **Do NOT gate Q1 for this** — its body diode (drain-to-panel by design) conducts
  panel→load regardless of gate state; inhibiting there needs back-to-back FETs.
- Temp source: the ATtiny3226's internal sensor (box interior ≈ cell temperature;
  the screen's SHTC3 is a cross-check, not the primary). Firmware policy, thresholds
  LoRa-configurable: inhibit < ~0 °C, resume > +3 °C (hysteresis); optional survival
  override if VBAT < ~2.9 V in a prolonged cold snap (accepts cell wear to keep the
  station alive — a policy knob, logged when used).
- Pin map change: **PA3 = `CHG_INHIBIT`** (was SPARE1).

### 3.5b Cell protection (added 2026-07-12)

Covered already: overcharge + charge current (CN3801 CV/OVP + R_CS). Not covered until
now: over-discharge and discharge short-circuit. Two layers:

1. **DW01A + FS8205A, as a ready-made 1S PCM strip** (KTRON/Robu ₹30–60 — decided
   2026-07-12: reserve a footprint on Board A beside BT1 rather than laying out the
   discrete circuit). Wiring: `B+` → cell+/VBAT node, `B−` → BT1 negative terminal,
   `P−` → board GND; on most strips B+ doubles as P+ (only the − path is switched) —
   **verify the pad markings on the actual unit** before finalizing the footprint
   (~46 × 6 mm typical; measure). BT1− must reach the plane **only through the strip**
   — silkscreen "CELL− VIA BMS". The DW01's Li-ion 4.25 V overcharge threshold never
   fires (CN3801's LFP limits act first); what it buys is the **~2.40 V undervoltage
   cutoff + short-circuit protection** (parachute — LFP holds almost nothing between
   2.8 and 2.4 V). Recovery from UV lockout happens through the 8205 body diode when
   solar returns; adds ~3 µA to the sleep floor.
2. **Firmware soft-UVLO** via `VBAT_SENSE`: park radio/PMS below ~2.9 V, deep-sleep
   below ~2.8 V — the DW01 should never be the routine path.

### 3.6 Protection row (per architecture §8) — wiring detail (2026-07-12)

- **Solar reverse-polarity, Q1 = AO3407 high-side** *(changed from AO3401,
  2026-07-12)*: panel + → **drain**, **source** → VSOL, **gate** → GND. Correct
  polarity: body diode conducts momentarily, V_GS goes negative, FET enhances and
  shorts its own diode (mΩ, no drop). Reversed: blocks completely. Drain-toward-panel
  is the part everyone gets backwards. **Why AO3407 not AO3401:** during a clamped
  surge the SMAJ8.5A holds the line at up to ~14.4 V, and with the gate at GND that
  entire voltage appears as V_GS — over the AO3401's ±12 V abs max, inside the
  AO3407's ±20 V ([AOS datasheet](https://www.aosmd.com/res/datasheets/AO3407.pdf)).
  Bonus: AO3407 is already on this BOM as Q2 — one P-FET part number for the board.
  (SOT-23 pinout: 1 = G, 2 = S, 3 = D — verify pin 3 faces the connector.)
- **Solar TVS = SMAJ8.5A**, line-to-GND at the connector, cathode to panel +.
  *(Corrects the earlier SMAJ6.0A call — a 6 V-class panel's Voc ≈ 7.2 V sits inside
  the 6.0A's 6.67 V min breakdown; the 8.5A stands off any realistic Voc and clamps
  ~14 V, far under the CN3801's 28 V max.)*
- **Signal lines (`VANE_ADC`, `ANEMO`, `RAIN`): SMAJ5.0A each**, line-to-GND at the
  connector (cathode to signal), alongside the existing 1 k + 100 nF. Standoff 5 V >
  3.65 V logic; ~9.2 V clamp through 1 k series ⇒ <1 mA into MCU clamps during events;
  unidirectional also clamps negative excursions at −0.7 V. Capacitance irrelevant at
  these speeds; one part number to stock.
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
| Q1 | **AO3407** | SOT-23 | reverse-pol (solar input) — ±20 V V_GS survives the TVS clamp; same part as Q2 |
| Q2 | **AO3407** | SOT-23 | buck pass P-FET — datasheet-suggested "3407A"; Robu |
| Q3 | 2N7002 | SOT-23 | charge-inhibit, MPPT-pin pulldown (§3.5a) + R19 100 k |
| U8 | **1S PCM strip (DW01A + 8205A)** | ~46×6 mm module | soldered onto reserved footprint beside BT1 (§3.5b); KTRON/Robu ₹30–60; verify B+/B−/P− pads |
| D1, D2 | **SS34** ×2 | SMA | series block + freewheel; D1 stays (night back-feed) |
| D5 | **SMAJ8.5A** | SMA | solar input TVS (Voc-safe for 6 V panels; supersedes SMAJ6.0A) |
| D6–D8 | **SMAJ5.0A** ×3 | SMA | vane/anemo/rain line clamps |
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

## 6. Schematic review — forsyth-board-a V1.0 (EasyEDA, reviewed 2026-07-12)

**Correct and confirmed ✓:** MCU pin map matches §2 exactly (all 18 GPIO, UPDI, STATUS
LED on PB5 active-low); 10 k series clamp on `UART_RX` present (R2); M0/M1 MCU-driven;
E22 bulk 100 µF + 100 nF at module VCC, downstream of the gate; PMS shares the UART with
its TXD joining on the module side of R2 (so it, too, is clamped); the whole CN3801
section is right — MPPT 390 k/100 k, R_CS 0.24 Ω with Kelvin CSP/BAT, COM 120 Ω+220 nF,
VG–VCC 100 nF, input trio 100 µF∥10 µF∥100 nF, D1+D2 SS34 in the correct series/freewheel
positions, L 33 µH, AO3407, output 2×10 µF, 1 M/330 k battery divider; both TPS61023 FB
dividers 732 k/100 k; RC conditioning (1 k + 100 nF) on rain/anemo/vane at the connector
side; UPDI header with 1 k; GND on pin 2 of the GX connectors.

**Issues found — status after V1.0-rev-b (2026-07-12):**

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | ❗ | U2 drawn as E220-900T22D vs the design's E22. | **RESOLVED ✓ — E220 is the part in hand (decided 2026-07-12); all docs re-based** (architecture §1 decision note, §3.4 numbers: T22D 110 mA / T30D 620 mA TX). Net names `E22_*` in the schematic are cosmetic; rename at leisure |
| 2 | ❗ | No reverse-polarity FET + TVS on solar input. Wiring detail now in §3.6 (AO3401 drain-to-panel + **SMAJ8.5A**). | open — wiring supplied |
| 3 | ❗ | No TVS on vane/anemo/rain lines; GX shield pins NC. §3.6: SMAJ5.0A each + shields to GND. | open — user fixing |
| 4 | ⚠ | Boost inductor placement / VIN net. | **FIXED ✓** (VBAT→L→SW, FB at divider midpoint, verified rev-b) |
| 5 | ❗ | VBAT_SENSE tap capacitor. | **FIXED ✓** (C20 100 nF) |
| 6 | ⚠ | UART_TX back-powering gated-off peripherals. | **FIXED ✓** (R7 1 k series; PMS joined on the _H side — clamped symmetrically) |
| 7 | nit | Qwiic expansion missing. | **FIXED ✓** (J1 added; confirm physical pin order GND·3V3·SDA·SCL before fab) |
| 8 | nit | Shared LED resistor. | intentional, fine |
| 9 | nit | Solar connector. | **FIXED ✓** (CN4 is now GX12-2 — keying story restored) |

### Rev-e changes (2026-07-12, user-found + verified)

- **CHG_INHIBIT added** per §3.5a (2N7002 on the MPPT node, 100 k pulldown, PA3).
- **Bug found by Anish, fixed:** C10 (the VG–VCC 100 nF) was tied to the post-R18 LED
  node instead of VSOL/VCC. That reference bounces ~1–2 V with LED current and puts
  1 k inside the decoupling loop — weak/erratic gate drive to Q2 as the failure mode.
  Datasheet is explicit: 100 nF between VG (1) and VCC (9). Now correct. Related rule:
  the post-R18 node carries **LED anodes only**; VCC and the input trio live on VSOL.

### Final review — rev-d, 2026-07-12: **CLEARED FOR LAYOUT** ✓

Full-sheet pass (MCU · LoRa · connectors · charger · boosts · surge row): every finding
from rounds 1–3 verified fixed in the drawing — Q1 = AO3407, D3 = SMAJ8.5A at the
connector, SMAJ5.0A ×3 + RC on all field lines, shields grounded, boost topology
correct, Kelvin CSP/BAT, VBAT_SENSE cap, UART series pair, Qwiic, GX12-2 solar entry.
No circuit changes remain. Carry-forward items (verify, don't redraw):

1. **Q1/Q2 pin orientation** — hover pins in EasyEDA: pin 3 (D) toward CN4 on Q1 /
   toward VSOL on Q2. Bring-up check: millivolts across Q1 under load, not 0.6 V.
2. **TVS footprints** — SMA package band = cathode = toward the line on all four.
3. **Qwiic physical pin order** — GND · 3V3 · SDA · SCL against the JST-SH footprint.
4. Firmware notes born from this schematic: enable PB3 (UART_RX) internal pull-up while
   both peripherals are gated off (the 10 k leaves it floating otherwise); drive
   UART_TX low before de-asserting either EN.
5. Anemometer line note: the pulse line now carries **two** 100 nF (Board D + C18)
   against the MCU's ~35 k internal pull-up → τ ≈ 7 ms. Fine for expected pulse rates;
   if bench edges look lazy at high RPM, fit a 10 k external pull-up at `ANEMO_CON`
   (pad it in the layout now, DNP).

## 6a. Pre-routing layout checklist (Board A specifics; general rules in architecture §8)

**Two-layer strategy:** all *circuitry* top-side; the bottom layer is an (almost)
unbroken **ground plane** — every bottom-side part or long bottom trace slices the
return path for three switching loops. If cornered, only flat quiet R/C (FB dividers,
sense divider, connector RC/TVS) may go bottom-side; never magnetics, module,
connectors, LEDs. Route top, jog-under short, stitch vias generously.

**Exception (decided 2026-07-12): BT1 + the BMS strip go bottom-side.** The cell is a
pure DC node (no switching loop touches it) and the holder's plastic body doesn't cut
the plane — only two through-holes do. Rules: position under the **quiet middle**, not
the power corner and never under the E220 antenna end (45 g of metal detunes it);
**through-hole-pin holder only** (bottom-side SMD pads + 45 g + mast vibration = pad
tear), with mounting holes near the holder ends; 2–3 vias each for cell+ → VBAT and
P− → plane; "CELL− VIA BMS" moves to bottom silk; standoff height (~18–20 mm) and the
battery-swap face become enclosure inputs.

**Zone map** (three neighbourhoods on one face, connectors along one wall — the wall
that becomes the box's downward-facing gland/bulkhead face):

```
│ POWER CORNER          │ QUIET MIDDLE       │ RF END              │
│ CN4 → D3/Q1 →         │ U1 + C1            │ U2 E220 + C5/C6     │
│ U6·Q2·D1·D2·L3·R8     │ sense divider+C20  │ U3 boost (SW away   │
│ C11-C13 · LEDs · BT1  │ R11/UPDI           │  from antenna)      │
│                       │ U4 boost → CN2     │ SMA edge + keep-out │
│ CONNECTOR WALL: CN4 · U5 · CN3 · CN1 · CN2 · J1 · U7 · CN5      │
```

No-copper keep-out (both layers) under the E220's antenna end and around the SMA;
unbroken plane under the rest of the module. Nothing top-side under BT1's body; nothing
under the module body. Enclosure note (architecture §6): the box is **separate from the
screen**, below and offset on the mast — thermal plume must not feed the louvres; CN1/
CN2 leave the box through glands as fixed pigtails.

**Hot loops first — place these before anything else:**
- CN3801 buck loop: Q2 → D2 → L3 with C11/C12/C13 at Q2's source node — minimum area,
  no via detours. D2's anode-to-ground and the caps' grounds into one tight pour.
- Each TPS61023: C4(C9) at VIN, L1(L2) VIN↔SW short and fat, C2/C3 (C7/C8) at VOUT —
  the whole stage in ~1 cm²; FB divider and its trace away from L and SW.
- **SW nodes and DRV small** — they're the noisiest copper on the board.

**Precision analog:**
- R8 (240 mΩ) right at L3's output; **CSP/BAT routed as a tight pair** (same layer,
  minimum spacing) to R8's pads — Kelvin, per CN3801 datasheet §PCB.
- VBAT_SENSE divider + C20 near the MCU's PA7, away from both boosts.
- `VANE_ADC` from R17 to PA6: shortest practical, not parallel to any SW node.

**RF:**
- E220 antenna pin → SMA: 50 Ω trace, ground pour keep-out around the connector,
  unbroken plane under the module; C5/C6 at the module's VCC pin, not at the boost.

**Zoning (one board, three neighbourhoods):**
- Power (CN3801 + both boosts) in one corner near CN4/BT1; MCU + logic in the middle;
  the E220 + antenna at the far edge; all field connectors (GX/XH) along one face with
  their TVS + RC parts **at the connector pins**, not near the MCU.
- Battery holder: silkscreen polarity oversized; holder pads carry charge current —
  thick traces to R8/GND.

**Grounding:**
- One solid plane; CN3801's analog returns (MPPT divider, COM network, CSP/BAT) tie in
  near U6's GND pin rather than across the buck loop, per datasheet ("analog and power
  ground return separately").
- GX shield pins → plane at the connector.

**Trace widths (1 oz outer copper):** charge path (VSOL→Q1→Q2→D1→L3→R8→VBAT, D2 leg,
cell connections) 1.0–1.5 mm (2 mm where free); VBAT trunk to boost VINs 1.5 mm (TX
bursts); boost VIN→L→SW and VOUT 1.0–1.5 mm and short; 5V_RADIO 1.0 mm; all signals
0.25–0.3 mm; **CSP/BAT Kelvin pair deliberately thin (0.25 mm)** and landed on R8 pad
ends away from the power entry; GND is pours + stitching, never traces; power-path
vias 0.6/0.3 mm, 2–3 in parallel.

**The one loop that matters (CN3801 buck):** the commutation ring is
C_in(ceramics) → Q2 → D1 → D2 → C_in ground — close it in ~1 cm²; C11 electrolytic may
stand a step back. R8 touches L3's output pad (datasheet rule). MPPT island (R9, R12,
Q3 drain) within a few mm of U6 pin 6, away from switch nodes. Analog ground vias
(R12, R14/C16, R13/C20) near U6's GND pin, offset from the D2/C_in power-ground vias.

**Bring-up hooks:** test points on VBAT, VSOL, both 5 V rails, UART_TX/RX, AUX, both
EN lines, MPPT, VBAT_SENSE; the DNP 10 k anemometer pull-up pads; LED1 visible once
boxed.

## 7. Bring-up checklist

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
