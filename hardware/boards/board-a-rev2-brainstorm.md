# Board A — rev 2 brainstorming

**Status:** open debate, nothing decided (opened 2026-08-06). Rev 0 is fabricated, populated,
and has passed a full leaf → coordinator → cloud round-trip; nothing here is a defect report
against it. This sheet exists to argue the *next* board before anyone opens EasyEDA.
**Source of truth for rev 0 stays [board-a-core.md](board-a-core.md).**

Three questions were put on the table — one boost or two, whether to delete solar entirely,
and what a genuinely cold site wants. They turn out not to be independent: all three are
really arguments about **the PMS7003 and the AS3935**, which between them own the energy
budget. So the numbers come first.

---

## 1. What rev 0 actually costs

Everything below is *computed from the datasheet figures already logged* in
[architecture.md §5](../architecture.md) — **not bench-measured**. The firmware exists but
these currents have never been put on a meter, which is still open item #3 in §9. Treat this
table as the shape of the problem, not as truth. **[verify on bench before any of the
decisions below are made final]**

**Assumptions:** VBAT ≈ 3.3 V (LiFePO4 mid-discharge), boost efficiency η ≈ 0.87. Loads
specified at 5 V are converted to cell-referred drain by ×5/(3.3·0.87) = **×1.74** — rev 0's
docs quote the 5 V-side figures, which understate the drain on the cell by that factor.

### Sleep term (continuous, cell-referred)

| Contributor | Current | Source |
|---|---|---|
| AS3935 listening | 60–80 µA (take 70) | architecture §5 — **cannot be duty-cycled as designed** |
| CN3801 sleep path (BAT + CSP) | ~8 µA | CN3801 datasheet, panel dark |
| VBAT sense divider (1 M + 330 k) | ~2.7 µA | board-a-core §3.4 |
| DW01A PCM strip | ~3 µA | board-a-core §3.5b |
| ATtiny3226 asleep (RTC on ULP) | ~1 µA | architecture §5 |
| BME280 + SHTC3 idle | ~1 µA | negligible |
| **Total** | **≈ 86 µA** | **≈ 2.06 mAh/day** |

### Active term (per event, cell-referred)

| Event | 5 V-side | Cell-referred | Note |
|---|---|---|---|
| PMS7003 reading | 0.67 mAh | **1.16 mAh** | 80 mA × 30 s warm-up — the 30 s is mandatory, not tunable |
| E220 **T22D** report | 0.016 mAh | **0.028 mAh** | 110 mA × ~0.52 s |
| E220 **T30D** report | 0.090 mAh | **0.156 mAh** | 620 mA × ~0.52 s |
| MCU awake + I2C + pulses | — | ~0.003 mAh | ~3 mA × 1 s |

### Three duty-cycle profiles

| | AQI | Met/report | Radio | **mAh/day** | **Ah/year** |
|---|---|---|---|---|---|
| **A — frugal** | 6-hourly | 15 min | T22D | **9.7** | 3.5 |
| **B — nominal** | hourly | 10 min | T22D | **34.4** | 12.6 |
| **C — heavy** | hourly | 5 min | T30D | **75.7** | 27.6 |

**The finding that governs everything below:** in profile B the PMS7003 alone is **27.8 of
34.4 mAh/day — 81 % of the entire budget**. The AS3935 owns two thirds of what's left. The
MCU, the sensors, the radio at T22D and the whole charging chain are rounding error. Any
argument about power topology that does not change the AQI cadence or the lightning listener
is an argument about the last 15 %.

---

## 2. Debate 1 — one boost + load switches, or two boosts?

**The proposal:** delete one TPS61023; keep a single 5 V boost and gate it downstream into
`5V_RADIO` and `5V_AQI` with power switches.

### For

- **The architecture already guarantees mutual exclusion.** [architecture §2.3](../architecture.md)
  time-multiplexes one UART between the E220 and the PMS7003 precisely because *the two are
  never on at the same time*. A single shared rail simply makes the power topology mirror the
  bus topology — one resource, one user at a time. That is a real consistency argument, not a
  cost-saving dressed up as one.
- **The boost is already sized for the worse case.** U4 is specified for the T30D's 620 mA
  burst; the PMS7003's ≤100 mA disappears inside that. Nothing needs re-sizing.
- **Area and BOM.** Removes a TPS61023, a 5×5×4 mm shielded inductor (the largest passive in
  the boost stages), a 10 µF, two 22 µF and the second FB divider. Adds two load switches and
  their caps. Net saving is roughly **6 parts and ~50 mm²** — meaningful on a board whose
  zone map (§6a) is already three crowded neighbourhoods.
- **Load switches sequence better than a boost starts.** A slew-controlled switch
  (TPS22918-class, rise time set by a `CT` cap) charges the radio's mandated 100–220 µF bulk
  in a controlled ramp. Today that inrush is the boost's soft-start problem.

### Against

- **It spends the property we bought the TPS61023 for.** Rev 0's gating rests on the
  TPS61023's *true load disconnect* — "in shutdown the output is completely disconnected from
  the input, 0.1 µA" ([board-a-core §3.2](board-a-core.md)). That is what makes the lokki law
  enforceable: in sleep the radio is **unpowered, not idle**. A single boost keeps that
  property only if the boost is shut down whenever both switches are open — so the firmware
  now has to hold a three-way invariant instead of a one-way one.
- **GPIO cost.** Boost EN + two switch ENs = **3 pins where rev 0 uses 2**. PB5/`SPARE3` is
  free (the status LED is optional), so it fits — but it consumes the last spare on a
  SOIC-20 that architecture §2.1 already calls tight. The alternative, diode-OR'ing the two
  switch ENs into the boost EN, adds two diodes and a pulldown and gives most of the saved
  parts straight back.
- **Loses graceful degradation.** Two rails mean a dead AQI boost costs you AQI. One rail
  means a dead boost costs you the station. Weigh this honestly, though: the failure mode
  that has actually bitten this project is *brownout under TX surge* (bench, 2026-08-04 —
  and that turned out to be the bench supply's fold-back, not the boost). Neither topology
  helps there; bulk capacitance and current limit do.

### Verdict

**Sane, mildly favourable, not urgent.** The mutual-exclusion argument is genuinely elegant
and the area saving is real. But it is a ~₹50 and ~50 mm² win that costs a GPIO and makes the
power-sequencing invariant harder to state — and rev 0's two-boost arrangement is *already
proven on the bench* (leaf TX with no brownout, 2026-08-05). Do it **only as part of a rev 2
that is being re-laid out anyway** — which, if either debate below lands, it will be.

**Adjacent option worth recording:** the E220 runs 3.0–5.5 V, so a **boost-less radio build**
is possible — load-switch the module straight off VBAT and skip the 5 V rail entirely. The
manual's "≥5.0 V ensures output power" makes this a deliberate trade of range for
simplicity, confirmed on the bench at 3.3 V (memory: coordinator radios ran at 3.3 V with
reduced TX power). Viable for a short-path site; **not** compatible with the T30D at 30 dBm.
The PMS7003 still needs 5 V, so the boost never disappears entirely — it just stops being the
radio's problem.

---

## 3. Debate 2 — delete solar, strap on 10 000 mAh, swap yearly

**The proposal:** no panel, no charger, no MPPT, no charge-inhibit. A large Li-ion pack, and
the annual maintenance visit replaces it.

### For — and it is a stronger case than it first looks

- **It deletes a third of the board.** Not just the panel: U3 (CN3801), Q1, Q2, D1, D2, L3,
  R_CS and its Kelvin pair, the MPPT divider, the COM network, C11/C12, the CHRG/DONE LEDs,
  Q3 + R19 (charge inhibit), D5 (solar TVS) and J1 (GX12-2). That is **~20 parts and the
  entire "power corner"** of the zone map. The two hardest layout constraints on the board —
  the CN3801 commutation loop and the Kelvin sense pair — both vanish.
- **It deletes the most subtle failure modes.** MPPT mis-set for the panel actually bought;
  the 5 V-vs-6 V panel UVLO trap; D1 back-feed; the cold-charging plating risk and the whole
  `CHG_INHIBIT` firmware policy with its thresholds and survival override. Every one of these
  is a documented hazard in rev 0 §3.1/§3.5a. None of them can bite a board that cannot charge.
- **It removes 8 µA of permanent sleep drain** (CN3801 sleep path) — ~10 % of the sleep floor.
- **Panels are the field-maintenance item anyway.** A soiled, snowed-over or mis-aimed panel
  is a silent failure; a battery with a known replacement date is a scheduled one. Trading an
  unpredictable failure for a diarised task is often the right call for remote hardware.

### Against — the arithmetic

Nameplate capacity is not usable capacity over a year. Derating a 10 Ah Li-ion pack:

| Factor | Effect | Note |
|---|---|---|
| Self-discharge ~2 %/month | ×0.88 | ~1.2 Ah simply evaporates over 12 months |
| Cold derate | ×0.85 (0 °C) … ×0.65 (−20 °C) | see §4 |
| Unusable tail below cutoff | ×0.95 | boost/BOD floor |
| **Usable, temperate** | **≈ 8.0 Ah** | |
| **Usable, cold site** | **≈ 6.2 Ah** | |

Against the profiles from §1:

| Profile | Needs/year | 10 Ah pack, temperate | 10 Ah pack, cold |
|---|---|---|---|
| **A — frugal** | 3.5 Ah | ✅ ~2 years | ✅ comfortable |
| **B — nominal** | 12.6 Ah | ❌ **fails at ~7 months** | ❌ fails at ~6 months |
| **C — heavy** | 27.6 Ah | ❌ nowhere close | ❌ nowhere close |

**So the honest answer to "will 10 Ah run for a year?" is: only in profile A.** The idea is
not wrong — it is *conditional on dropping AQI to 6-hourly or slower*. Which, given the
PMS7003 owns 81 % of the budget, is the same conversation as §1's finding.

Two further consequences that must not be skipped:

- **Chemistry breaks the "no LDO" rule.** Rev 0's headline simplification is that the MCU and
  I2C sensors run **directly off the cell** ([board-a-core §1](board-a-core.md)). A Li-ion
  pack at 4.2 V full-charge violates the **BME280's 3.6 V operating maximum** outright — not
  the marginal 25 mV overshoot rev 0 accepted at LiFePO4 float, but 600 mV over. Going Li-ion
  therefore *forces* an LDO or a regulated sensor rail, giving back some of the simplicity the
  proposal was buying. Staying with LiFePO4 (3.65 V max) keeps the rule intact — at ~60 % of
  Li-ion's volumetric energy.
- **Safety.** A 10 Ah pack with no charger still wants protection: the DW01A/8205 strip stays,
  and the design must make it *impossible* to connect a panel to a non-rechargeable or
  unmanaged pack.

### Verdict

**Adopt as an explicit build variant, not as the only option** — and pair it with a cadence
policy, because the pack size alone does not carry it. See §6: one PCB, two populations.

**The better cell for this variant is probably not Li-ion at all** — see §4.

---

## 4. Debate 3 — cold climates: harvesting, supercaps, and what actually works

### 4a. The supercap proposal, costed

A 2.7 V / 500 F cell:

- **Stored:** E = ½CV² = ½ × 500 × 2.7² = **1822 J = 506 mWh**
- **Usable** (2.7 V → 1.8 V, leaving headroom for a converter's floor):
  ½ × 500 × (2.7² − 1.8²) = 1012 J = **281 mWh**
- **Daily need, profile B:** 34.4 mAh at 3.3 V = **113 mWh/day**

→ **≈ 2.5 days of autonomy**, for a part the size of a soda can.

That alone is disqualifying as primary storage, but the real killer is **leakage**. Large
supercaps leak on the order of **1–3 mA** continuously at rated voltage
(**[verify against the specific part's datasheet — quoted after 72 h, and it is
temperature- and age-dependent]**). Our entire sleep budget is **86 µA**. A 1 mA leak is
**twelve times the whole station's quiescent draw** — the bank would flatten itself in a
couple of weeks with the load disconnected. Series cells for higher voltage need balancing
resistors, which leak more still.

There is a third problem, structural rather than numeric: a supercap's voltage **slides
linearly from 2.7 V to nothing**. Rev 0's architecture depends on a *flat* cell — the ADC
reference, the resistor-ladder wind vane, the sensor rails and the "no LDO" rule all assume
VBAT sits in a narrow band. A supercap primary would force a buck-boost in front of
everything, adding a converter and its quiescent current to a design whose whole thesis is
one conversion stage fewer.

**Verdict: no, as primary storage. Yes, emphatically, as a pulse buffer** — which is the role
it should have had all along. Supercaps are a *ride-through* technology (seconds to hours),
not a *storage* one (days). A small cell or a hybrid-layer capacitor sitting at the radio rail
is exactly what lets a high-impedance source survive the T30D's 620 mA burst. That matters a
great deal for the next idea.

### 4b. What actually solves cold: LiSOCl₂ primary + pulse buffer

This is the standard industrial-sensor answer and it deserves to be the headline candidate,
because it solves debate 2 and debate 3 *simultaneously*:

- **Lithium thionyl chloride** (e.g. D-size ER34615: ~19 Ah at 3.6 V nominal) —
  **[verify capacity, current limits and stock domestically]**
- **Self-discharge under ~1 %/year** (against Li-ion's ~2 %/month) — the single biggest win
  for a one-year-unattended box. Over 12 months a Li-ion pack loses ~1.2 Ah to nothing at all;
  this loses ~0.2 Ah.
- **Rated to −55 °C.** No plating risk, because **nothing ever charges it** — which deletes
  `CHG_INHIBIT` (§3.5a), its temperature policy, its hysteresis, its survival override and the
  2N7002 with it.
- **3.6 V nominal, and remarkably flat** — it fits the "runs directly off the cell" rule
  better than Li-ion does, and sits at the LiFePO4 float voltage the board is already designed
  around. **[verify the fresh-cell open-circuit voltage against the BME280 3.6 V ceiling — it
  may sit slightly above, same discussion as rev 0 §1]**
- **19 Ah covers profile B (12.6 Ah/yr) for a year with margin**, and profile A for years.

**The catch, and it is the reason the supercap idea belongs here:** bobbin-construction
LiSOCl₂ cells have **poor pulse capability** — continuous current in the low hundreds of mA,
and high internal impedance that sags badly under a 620 mA surge. They are therefore *always*
paired with a **hybrid-layer capacitor (HLC) or a modest supercap** to serve the pulses while
the cell supplies the average. So the user's two ideas combine into one correct architecture:

> **primary cell for energy + capacitor for power.**

Second catch: **passivation.** LiSOCl₂ cells grow a resistive film in long low-current
storage; the first heavy pulse after a quiet spell may sag. Mitigation is the same buffer cap,
plus an optional firmware depassivation load. **[verify behaviour on the bench across a cold
soak before committing]**

Third: they are **not rechargeable**, so a panel must be made physically impossible to fit on
this variant — not merely undocumented.

### 4c. Other cold strategies, briefly

- **LTO (lithium titanate)** — charges down to ~−30 °C, ~20 000 cycles. Keeps solar viable in
  the cold. But 2.4 V nominal is below what the direct-off-cell architecture wants, forcing a
  boost for *everything*; and energy density is poor. Interesting, awkward, probably not.
- **Heat the cell to charge it.** Energy-negative by a wide margin against a 34 mAh/day
  budget. No.
- **Keep LiFePO4 + solar and simply inhibit charging when cold** — which is what rev 0 already
  does. The station then runs on stored charge through the cold snap, so the answer is just
  *more capacity*. Perfectly respectable, and the least new risk.
- **Wind harvesting.** Tempting — there is already a mast and an anemometer. Rejected: moving
  parts in ice, a rectifier and MPPT stage to design, nothing generated during the calm cold
  spells when reserves matter most, and a turbine co-located with the anemometer corrupts the
  measurement the station exists to make.
- **Thermoelectric.** Ambient-to-ground ΔT at a mast site is small and reverses daily. No.
- **Note in solar's favour:** cold *helps* photovoltaics — panel efficiency rises as
  temperature falls. The winter problems are **snow cover, low sun angle and short days**, none
  of which a different battery chemistry fixes. If solar is kept for cold sites, argue about
  **panel tilt (steep, to shed snow) and oversizing**, not about the cells.

---

## 5. Other rev-2 candidates

### 5a. The AS3935 is the whole sleep budget — make it adaptive

70 µA continuous is **2.06 mAh/day, 0.75 Ah/year** — 7.5 % of the proposed 10 Ah pack, and in
profile A it is **~21 % of everything**. Architecture §5 calls it "cannot be duty-cycled",
which is true of a lightning detector that must never miss a strike — but Forsyth already
measures the one signal that predicts whether strikes are even possible.

**Proposal: barometric- and season-gated listening.** Put the AS3935 on a switched rail and
let firmware decide: listen continuously when pressure is falling or convective conditions
are plausible, sleep it through settled high-pressure spells and the dry season. The
thresholds are LoRa-configurable, exactly like the charge-inhibit policy. Worst case it misses
a freak dry-season strike; best case it halves the sleep floor. **This is the highest-value
change on the list after the AQI cadence**, and it costs one FET and one GPIO.

### 5b. Switch the battery-sense divider

2.7 µA continuous to take a reading once every 10 minutes — **24 mAh/year** for a measurement
that is live for milliseconds. Rev 0 §3.4 already anticipates this: "a high-side-switched
divider is the upgrade if that ever matters." **In a battery-only build, it matters.** One
small FET.

### 5c. Connectors — smaller, and finally properly keyed

GX12/GX16 are chosen for glove-friendly field mating and IP rating, which is a real
requirement; they are also large and cost ₹80–150 apiece. A rev 2 could go **M8 circular** for
the sensor runs (smaller, IP67, industrial-standard) while keeping a GX for the solar entry on
that variant.

**Do this in the same pass as the unresolved keying defect.** The rev 0 layout review logged
it as must-fix #2 and it is the most dangerous item still open on the board:

> **BATTERY vs SOLAR keying**: identical adjacent 2-pin connectors; a swap puts panel Voc
> (~7.2 V) on VBAT (> ATtiny 5.5 V abs max).

Mixing families for the two power entries makes the mistake **physically impossible** rather
than silkscreen-deterred. Note that the battery-only variant deletes the solar connector
entirely — which is the cleanest fix of all, and one more argument for §3.

### 5d. Bring-up ergonomics — the lesson bench actually taught

From the 2026-08-04/05 bench sessions: *"the single biggest blocker is unreliable jumper
connections — every physical touch broke a different link"*, and UPDI flakiness was finally
cured by **giving the programmer a solid common-ground reference**. Rev 2 should design for
that:

- A **polarised, latching UPDI header** (not a 3-pin pad row) with a generous dedicated
  ground, and a ground test loop for scope probes.
- **Soldered header footprints for the E220**, not jumper wires — the module's config path is
  the most-touched interface during bring-up.
- Keep and extend the rev 0 test-point set; it earned its place.

### 5e. Reconsider the AQI sensor itself

Since the PMS7003 is 81 % of the budget and the sole reason a 5 V rail exists at all, rev 2
should at least price the alternatives: a PM sensor with a genuine low-power sleep mode, or
demoting AQI to a **separate solar-powered satellite** that reports on its own schedule and
leaves the met station frugal. Firmware already makes AQI cadence LoRa-configurable, so the
cheapest version of this fix needs no hardware at all — it is a **policy default change**, and
it should probably ship regardless of what the board does.

---

## 6. The shape this suggests

The three debates converge on one answer: **stop building one board and start building one
board with two populations.**

| | **Variant S — solar** | **Variant P — primary** |
|---|---|---|
| Source | 6 V panel + CN3801 + LiFePO4 | LiSOCl₂ primary + HLC/supercap buffer |
| Sites | temperate, sunny, serviceable | cold, snowy, hard to reach |
| Charge inhibit | populated | **deleted — nothing charges** |
| Power corner | populated | **depopulated (~20 parts)** |
| Solar connector | GX12-2 | **absent — keying hazard gone** |
| Service interval | opportunistic | **annual cell swap, diarised** |

Shared: MCU, radio, sensors, connectors, protection, and (probably) a single boost with two
load switches per §2.

This is worth doing *only* if the shared footprint is genuinely shared — a DNP block with
silkscreened variant markings, not two divergent layouts. **[decide: is one board with a
depopulated corner cheaper in practice than two board revisions? It usually is, but it costs
area on every unit built.]**

### Ordered by value, not by how interesting they are

1. **Change the default AQI cadence** (firmware, zero hardware) — the single biggest lever on
   every number in this document.
2. **Adaptive AS3935 listening** (§5a) — halves the sleep floor for one FET.
3. **Variant P: primary cell + pulse buffer** (§4b) — solves cold and yearly-swap together.
4. **Fix the battery/solar keying** (§5c) — the one live safety defect from rev 0.
5. Single boost + load switches (§2), switched sense divider (§5b), connector shrink,
   bring-up ergonomics (§5d) — all worth doing *in* a rev 2, none worth a rev 2 on its own.

### Open questions before any of this is real

| # | Question | Blocks |
|---|---|---|
| 1 | **Bench-measure the actual sleep and active currents.** Every number here is computed from datasheets. | Everything. Architecture §9 has had this open since the start; it is now the critical path. |
| 2 | What AQI cadence is actually *useful* to a reader? | §3, §5e, and the whole battery-sizing question |
| 3 | LiSOCl₂ domestic availability, price, and pulse behaviour cold-soaked | §4b |
| 4 | Real supercap/HLC leakage at the sizes considered | §4a, §4b |
| 5 | Is the annual visit a promise we can actually keep at every site? | §3 — a battery-only station that misses its visit is simply dead |

---

**Related:** [board-a-core.md](board-a-core.md) (rev 0, source of truth) ·
[../architecture.md](../architecture.md) §3 power gating, §5 power budget, §9 open items ·
[../BOM.md](../BOM.md) sourcing.
