# Forsyth — Project Brief for Claude Code (Fable 5)

> **How to use this doc:** paste this whole file as your opening message to Fable 5 in
> Claude Code, from inside a fresh local clone of the new `forsyth` repo (sitting in
> parallel to `../starstucklab`, `../lokki`, `../sirious`, `../jigawatt`). Tweak anything
> in brackets or marked "confirm with me" before sending. Suggested opening line:
> *"Read this brief fully, explore the sibling repos as instructed in Phase 1, then
> propose a short plan before writing any code."*

---

## 0. Context — read this first

This is a new project under **Starstuck Lab**, a small hardware lab whose house style
you should absorb before writing a word of copy or code. The lab's existing projects —
**Sirious** (a pompous finderscope daemon), **lokki** (a lighting controller for quiet
spaces), **jigawatt** (a lightning early-warning / appliance-switching monitor), and the
telescopes **M42**/**Elli** — all share a loose *Back to the Future meets Hitchhiker's
Guide to the Galaxy* sensibility: dry humor, machines with a bit too much personality for
their station in life, and copy that treats the hardware like a character rather than a
spec sheet. Read `../starstucklab/site` (or wherever the homepage cards live) to internalize
the actual tone before writing anything user-facing.

**The project is a low-power, solar-capable weather station mesh.** Small "leaf" nodes
scattered over a wide area measure wind speed/direction, rain, temperature, pressure,
humidity, AQI, and lightning, then talk over LoRa to a "coordinator" (or a few) that's
connected to the internet and pushes data to the cloud and to Weather Underground.

**The name is Forsyth.** It's a play on "foresight" — spoken aloud it's nearly identical
to the word, but it reads as a name, the way Sirious reads as a name rather than a pun you
have to explain. Lean into it as a dependable, slightly old-fashioned family name — the
relative who always somehow knew it was going to rain before anyone else did. Where
Sirious is pompous and jigawatt is jumpy, Forsyth is quiet, unhurried, and doesn't need to
brag — the showing-off is implied by the fact that its owner always seems to know the
weather before anyone else does. Copy should lean on that emotional register: the anxiety
that disappears when you already know what's coming, the quiet confidence to plan around
it, and a small, unstated flex.

---

## 1. Repo & environment setup

- Create a new GitHub repo `forsyth`. I'll create it and clone it myself; you'll be
  working inside that local clone, which sits alongside `../starstucklab`, `../lokki`,
  `../sirious`, `../jigawatt` on disk.
- The static site for this project lives in a `/site` directory inside this repo. It will
  be deployed via Cloudflare Pages at `forsyth.starstucklab.com` — I'll handle the
  Cloudflare Pages project setup myself; you just need to produce a properly structured
  static site build in `/site`.
- `../starstucklab` has media-generation tooling that uses my OpenAI API license to
  generate preview and high-quality images. Find it, understand its invocation (script
  location, expected env vars/config, output conventions), and use it for any imagery
  this project needs now or in the future. Don't hardcode a new image pipeline — reuse
  what's there.

---

## 2. Phase 1 — Explore before building

Before writing any code or copy, explore the sibling repos and report back what you find:

1. **`../starstucklab`** — how is the homepage's project grid built? (Static data file,
   CMS-like content collection, hardcoded HTML?) What static site generator/framework is
   in use across the lab's sites? How are project "cards" structured (tags like
   `Telescope`/`Instrument`, status badges like `Build to order`/`By enquiry`, CTA links
   like `VIEW DETAILS`/`READ THE STORY`/`ENQUIRE`, `source ↗` links)? You'll need to add a
   Forsyth card here matching this exact pattern.
2. **`../lokki`** — this uses the same or a similar Ebyte E22 LoRa module. Read its
   firmware for the LoRa integration specifically. I previously had a serious stability
   issue there: the E22 module took **up to 100 seconds to stabilize** before it could
   send packets. Find out how lokki currently powers/sequences the module and flag
   anything that looks like it could cause this (floating M0/M1 state at boot,
   insufficient bulk capacitance causing brownout resets, no power-cycling between
   transmissions, etc.) — see §6.3, this must not repeat here.
3. **`../sirious`, `../jigawatt`** — skim for tone/copy conventions and any shared
   tooling/config patterns (linting, CI, doc structure) worth reusing for consistency.

Report a brief summary of what you found before moving to Phase 2.

---

## 3. Phase 2 — Website & web presence

Two deliverables here:

### 3.1 Forsyth's own site (`/site` in this repo)
An independent marketing/landing site for Forsyth, in the same visual and tonal language
as the other project sites, living at `forsyth.starstucklab.com`. Should cover: what it
is, the sensor suite, the mesh architecture (leaf + coordinator, plain-language), the
emotional pitch (see §0), build-to-order/status framing consistent with how other
projects present availability, and the comparison piece from Phase 3 below.

### 3.2 Site card in `../starstucklab`
Add Forsyth's card to the main Starstuck Lab site's project grid, following the exact
structural and copy conventions used by the M42/Elli/jigawatt/lokki cards you studied in
Phase 1. Generate any needed preview imagery via the shared media-generation tooling.

---

## 4. Phase 3 — Market research & comparison

Do real research on what exists before writing the comparison. At minimum, look into:

- **Consumer personal weather stations**: Davis Instruments Vantage Pro (a genuinely
  useful precedent — its wind vane uses a similar magnet-over-switches approach),
  Ambient Weather, Ecowitt, WeatherFlow Tempest (solar-powered, no moving parts, its own
  mesh/hub concept).
- **Open-source / hobbyist mesh-sensor projects**: LoRaWAN-based weather/environmental
  projects on Hackaday and GitHub, The Things Network community weather stations,
  Sensor.Community (formerly Luftdaten), OpenSenseMap, Meshtastic-adjacent
  environmental-sensor builds.
- **What's genuinely differentiated about Forsyth**: integrated lightning detection (most
  consumer PWS lack this), AQI, solar + LiFePO4 autonomy, self-hosted + WU + custom
  cloud dashboard rather than vendor lock-in, and a mesh designed to scale geographically
  rather than a single backyard unit.

**Deliverables:**
1. A quirky, well-designed comparison table/infographic as a first-class element on the
   Forsyth site (tone: dry and a little self-aware, consistent with the lab's voice —
   not a dry vendor spec-sheet shootout).
2. The same research, well-documented, as a standalone markdown file in this repo (e.g.
   `research/competitive-landscape.md`) — sourced, dated, and reusable as reference
   material independent of the site.

Don't reproduce copyrighted marketing copy, logos, or trademarked imagery from competitors
— describe and compare functionally, cite sources by name/link.

---

## 5. Phase 4 — Hardware planning (components, BOM, architecture)

**Scope boundary — read carefully:** I am designing the actual circuit and PCB myself.
Your job in this phase is component research, BOM construction, power-budget
calculations, and a written architecture/block-diagram document. **Do not produce KiCad
schematics, PCB layouts, or footprints** — that's my work. Everything below is either an
already-made decision (encoded here so you don't re-litigate it) or a research task.

### 5.1 Sensor suite (as specified)
- Wind speed: magnet + single reed switch, pulse counting.
- Wind direction: magnet + 8 reed switches spread over 360°.
- Temp / pressure / humidity: BME280 and/or SHTC3x class sensors (I2C).
- Lightning: DFRobot SEN0290 (AS3935-based, I2C/SPI + IRQ pin).
- AQI: **Plantower PMS7003** (confirmed — UART interface, 3.3V logic levels, but the fan
  needs 5V, and wants roughly a 30-second warm-up before a reading is valid — this last
  point is a real, non-trivial chunk of the active-mode power budget, more than the LoRa
  TX burst).
- LoRa radio: Ebyte E22-900T30D or E22-900T22D (UART/"transparent" variant, not the SPI
  variant) — used on **both** leaf and coordinator.

**Shared UART between LoRa and the AQI sensor**: rather than requiring two hardware
UARTs, use one, time-multiplexed — power on the AQI sensor via its own gate, wait for
warm-up, read over UART, power it off, *then* power on the LoRa module and transmit. This
follows the same never-simultaneous, always-power-gated pattern already required for the
LoRa module in §5.3, and it's what keeps the pin count (and MCU choice, see §5.2) sane.

**Note on temp/humidity sensor choice:** BME280's humidity element has a small internal
reconditioning heater and the module runs slightly warm in an enclosure, which can bias
the temperature reading a touch high — a known issue in outdoor DIY weather station
builds. Worth deciding whether to use BME280 for pressure only and pair it with a
separate SHTC3/SHT4x purely for accurate ambient temp/humidity, or accept BME280's
built-in figure with a small enclosure-siting compensation. Flag this as a decision point
in the architecture doc rather than silently picking one.

**Note on wind direction wiring:** rather than routing 8 separate GPIOs (and 8+ wires up a
mast to the vane), design a resistor-ladder encoding — each reed switch in series with a
distinct resistor value, all commoned to a single ADC pin — so direction reads as one
analog voltage on one pin, cutting the mast cable down to power/ground/signal. Leave a
clear upgrade note that an AS5600 magnetic angle sensor (I2C, contactless, ~12-bit
resolution) is a plausible future drop-in replacement on the same I2C bus if finer
resolution is ever wanted — no need to design for it now, just don't paint the
architecture into a corner that prevents it later.

### 5.2 Microcontroller decisions (already made — encode these)
- **One MCU per leaf node**, not a constellation of independent ATTinys. Physical/feature
  modularity is handled at the PCB level (§5.6), not by splitting the brain across
  multiple chips — extra MCUs would add inter-chip comms and sleep-current overhead for
  no real benefit at this sensor count.
- **Leaf MCU: ATtiny3226** (tinyAVR-2 series, 20-pin **SOIC-20**, UPDI programming) —
  superseding the earlier ATmega328P/Pro Mini idea now that SOIC and UPDI are explicit
  requirements. Note for the record: classic ATmega328P **does not ship in SOIC at all**
  (only PDIP-28, TQFP-32, QFN-32 — confirmed against Microchip's own ordering
  information), so the Pro Mini path is disqualified by the SOIC requirement alone,
  independent of anything else below.
  - **Why this part specifically**: genuine SOIC-20 package (easy hand-solder, 1.27mm
    pitch — not the finer-pitch SSOP some larger AVRs use); UPDI single-wire programming
    (a programmer can be built from any USB-serial adapter + one resistor — no dedicated
    tool needed, and CH340/CP2102 adapters are trivially available in India); 32KB flash /
    3KB SRAM — more SRAM than even the classic ATmega328P had, so the "future headroom"
    concern from the earlier ATmega328P writeup is actually resolved, not traded away;
    an **integrated RTC peripheral with an internal 32.768kHz ULP oscillator** — no
    external crystal needed at all for wake-timing (±10%, calibratable to ±2%, plenty for
    a periodic wake interval), which is strictly better than the Timer2-async-plus-crystal
    approach classic AVR would have needed (see §5.4); and an Event System that can count
    the wind-speed reed switch's pulses in hardware, waking the CPU only to read the
    accumulated count rather than on every single pulse.
  - **Pin budget** (with the AQI sensor now included, shared UART per §5.1): I2C (2) +
    shared UART for LoRa + AQI (2) + LoRa control: M0/M1/AUX/power-gate (4) + AQI
    power-gate/boost-enable (1) + wind-speed interrupt (1) + wind-direction ADC (1) +
    lightning IRQ (1) + battery-voltage ADC (1) = **13 pins**, against 18 GPIO available
    on the 20-pin package — comfortable, with real headroom left for a future display.
    (The 14-pin sibling, ATtiny3224, is also genuine SOIC but only has 12 GPIO — too
    tight once the AQI sensor is in the picture; that's why the 20-pin part is the one to
    use, not the smaller one.)
  - **If dedicated, non-multiplexed UARTs are ever preferred over the shared-UART
    approach** (simpler firmware, no risk of bus-contention bugs, at the cost of hand-solder
    ease): the megaAVR-0 28-pin parts (ATmega4808/1608) have **three** independent hardware
    UARTs and the same UPDI programming and RTC-with-external-crystal-or-ULP-oscillator
    story, but only come in SSOP-28 (0.65mm pitch) — a step down from true wide SOIC.
    Worth knowing about, not needed for v1.
  - **Integration approach**: place the bare SOIC-20 chip directly on the leaf PCB rather
    than sourcing a pre-made carrier/breakout module. The one well-known community source
    for a Pro-Mini-style tinyAVR-2 breakout (Azduino, by the maintainer of the Arduino core
    for these chips) isn't currently reliably orderable — the listings show no shipping
    available. Adafruit sells two relevant things instead: bare SOIC-to-header carriers
    (8/14/20-pin — just a pitch adapter, no regulator or support circuit, doesn't save any
    design work) and a fully-populated **ATtiny1616 "seesaw" board** (regulator, LED, UPDI
    header, and STEMMA QT/Qwiic I2C connectors that happen to match the sensor-bus plan in
    §5.6) — but that's tinyAVR-**1**, not 2 (16KB flash/2KB RAM, a step down from the
    3226), ships pre-flashed with different firmware (reflash via UPDI, not a real
    obstacle), and is an international order.
  - **The power-regulation question doesn't actually depend on this choice.** No
    mainstream small MCU module — Pro Mini, Xiao, Feather, the Adafruit boards above, Blue
    Pill — has power regulation designed for a *raw LiFePO4* input. They either have a
    plain LDO expecting an already-regulated Vin (a battery pack, USB 5V) with zero charge
    management, or Li-ion/LiPo (4.2V) charging circuitry built in, which is the wrong
    chemistry — the same mismatch already flagged for the off-the-shelf CN3791 breakout
    modules in §5.7 (since resolved by switching to CN3801 instead — see §5.5). The
    LiFePO4-aware charging path has to live on the carrier PCB regardless of which MCU
    option is used — no module purchase removes that requirement. Given that, and given
    SOIC is already easy to hand solder, going bare-chip doesn't cost anything here: the
    module route wouldn't save the one piece of design work (battery-aware power) that
    actually matters.
  - **Sourcing update**: ATtiny3226 is confirmed available directly on Robu.in (domestic
    stock, not just via LCSC/JLCPCB) — Robu carries the tinyAVR-2 family broadly. This is
    simpler/faster than the earlier LCSC-only assumption; update §5.7 accordingly.
  - **Cross-check against what `../lokki` already uses** (Phase 1) regardless of the above
    — if lokki's on a different family already, weigh firmware/tooling reuse against
    everything above and present the tradeoff rather than silently overriding either way.
- **Coordinator MCU: ESP32-S3** — dual-core (needed to service the LoRa UART link and the
  WiFi/TLS/MQTT stack concurrently without one blocking the other), enough RAM/flash for
  HTTPS + MQTT + Weather Underground posting, mature ecosystem.

### 5.3 LoRa radio integration & power gating (critical — do not skip)
This is the fix for the lokki instability issue. Requirements, non-negotiable:
1. The E22 module's power rail must be **fully MCU-gated** via a MOSFET or dedicated
   load-switch IC (e.g. TPS22918-class), controlled by a dedicated GPIO — not just parked
   in the module's own low-power mode via M0/M1. During deep sleep the module should be
   **fully powered off**.
2. Boot/wake sequence: assert power-enable → wait for rail settle → hold M0/M1 in a
   defined mode → wait for AUX to indicate ready → only then issue UART commands/data →
   after AUX confirms TX complete, de-assert power-enable and return to sleep. This must
   be true every single wake cycle, not just at cold boot.
3. Provide real local bulk capacitance at the module's VCC pin (~100–220µF low-ESR plus a
   100nF ceramic) to absorb the TX current burst without sagging the rail.
4. Size the regulator/battery discharge path for **at least 2× the module's datasheet
   peak current** at the chosen TX power level (verify against the current E22-900T30D /
   T22D datasheet — T30D at 30dBm will draw meaningfully more than T22D at 22dBm; do not
   assume, pull the actual number). This must comfortably clear 500mA and likely needs
   headroom toward 1A for the T30D variant.
5. **Run the E22 off its own gated 5V boost converter, same pattern as the AQI sensor
   in §5.1/§5.5**, rather than directly off the 3.3V-ish system rail. Running the PA
   closer to the top of its supply range generally gives more headroom to hit rated
   output power reliably (especially the 30dBm variant), and for the same RF power
   delivered, current draw is somewhat lower at 5V than at 3.3V. Important: this does
   **not** reduce the load on the LiFePO4 cell — a boost converter reflects power, not
   current, so a 5V/600mA burst can mean *more* than 600mA momentarily drawn from the
   3.3V-ish input rail once conversion losses are accounted for. Size the LiFePO4
   discharge capability and the input-side bulk capacitance with that in mind, not just
   the 5V output side.
6. **Logic-level compatibility, 3.3V MCU → 5V-powered E22**: Ebyte's own support
   clarification states that although the module's VCC accepts up to 5.5V, the RXD/TXD
   communication levels are fixed at 3.3V internally regardless of VCC (it has its own
   onboard 3.3V regulator feeding the logic, decoupled from the power rail) — so the
   ATtiny3226's 3.3V logic should interface directly with the module with **no level
   shifter needed**, even though the module itself runs at 5V. That said, this is from
   support FAQ text, not a numeric table in the primary datasheet — **pull the actual
   E22 datasheet's electrical characteristics table and confirm the Vih/Vil thresholds**
   before finalizing, rather than relying on the FAQ alone.
7. Apply the same power-gating discipline on the **coordinator** side too, even though its
   power situation is less constrained — consistency avoids a second class of bugs later,
   and it keeps the LoRa module's RF noise isolated from the rest of the board when idle.
8. **Terminology note**: the E22-900T30D/T22D "D" variants use Ebyte's own UART/AT-command

   protocol on top of the SX1262 radio, not the standardized LoRaWAN MAC layer. This will
   be a private point-to-multipoint LoRa network, not certified LoRaWAN. That's the right
   call for a single-owner mesh — flag it in the architecture doc so it's a documented
   decision, not an accidental one, in case public network (TTN/Helium) interop is ever
   wanted later.

### 5.4 RTC
- **Leaf: no external RTC chip, and no external crystal either.** The ATtiny3226 has an
  integrated RTC peripheral that can run off its internal 32.768kHz ULP oscillator
  (±10%, calibratable to ±2%) — plenty of accuracy for a periodic wake interval, since
  absolute wall-clock accuracy on the leaf isn't load-bearing (the coordinator timestamps
  on receipt). This removes both the external crystal and its two dedicated pins from the
  design entirely — simpler than what classic AVR would have needed.
- **Coordinator: populate an external RTC** (DS3231-class — accurate, cheap, common) to
  survive reboots and bridge the gap before NTP resync, and to allow local timestamping
  if the internet link is briefly down.

### 5.5 Power: solar + LiFePO4 (leaf), battery backup (coordinator)
- **Leaf charging: CN3801, not CN3791.** I have access to the CN3801, which is
  Consonance's **purpose-built LiFePO4 sibling** to the CN3791 — same MPPT solar-buck
  topology, but its constant-voltage regulation point is **fixed at 3.625V ±40mV at the
  factory**, matching LiFePO4's float voltage directly with no custom resistor-divider
  retargeting needed (unlike the CN3791, which is fixed for 4.2V Li-ion and would have
  needed the resistor-value hack described in the earlier draft of this brief). SOP-8
  package, consistent with everything else being genuinely hand-solderable. This
  supersedes the CN3791-plus-custom-resistors approach — use CN3801 as the default.
  Small 1–2W panel (Voc comfortably above the battery voltage, e.g. 5–6V nominal) should
  be ample except in prolonged low-insolation conditions; size for the worst realistic
  season if year-round operation matters.
- **Two gated 5V boost rails on the leaf**, both off the 3.3V/LiFePO4 system, both fully
  powered off between uses: one for the AQI sensor (§5.1), one for the E22 LoRa module
  (§5.3.5). Same reasoning as everything else in this brief — never leave a peripheral
  powered when it isn't actively being used. Remember the input-side current on the
  LiFePO4 rail will be higher than either boost rail's own output current once
  conversion losses are factored in (see §5.3.5) — size the CN3801's output capacitor
  and the LiFePO4 cell's discharge rating accordingly, not just each boost converter in
  isolation.
- **Coordinator**: battery backup only (not solar) sized to bridge outages (hours, not
  weeks) — a small LiFePO4 or Li-ion pack with an appropriate charger, chemistry choice
  open, consistency with the leaf's LiFePO4 is a reasonable default unless there's a
  good reason otherwise.
- **Battery sizing methodology** (produce this as a real calculation once real firmware
  current-draw numbers exist, don't fabricate precision now): average current ≈
  (I_sleep × T_sleep + I_active × T_active) / T_total. Flag explicitly that the **AS3935
  lightning sensor cannot be duty-cycled** — it must stay in listening mode continuously
  between wake cycles (typically tens of µA, verify against datasheet), so it will likely
  dominate the sleep-current budget more than the MCU itself. TX bursts will dominate the
  *active* current term given the E22's few-hundred-mA-to-~1A draw over a very short
  window. Produce a spreadsheet/worked calculation once real numbers are available rather
  than presenting invented figures as final.

### 5.6 Modularity / scalability strategy
This is how "a station may not have all these functionalities and still function, and may
gain more later (e.g. a display)" gets solved — at the PCB and protocol level, not by
adding more MCUs:
- **Core/brain board**: MCU + LoRa module (with the power-gating circuit from §5.3) +
  power path (solar/battery in, charger, protection) + a standard expansion connector
  (I2C bus + a few spare GPIO + power rails — a Qwiic/JST-SH-style 4-pin connector is a
  sensible, widely-available standard to adopt) present on every leaf.
- **Sensor daughter boards**, optional, attached via the expansion connector: an
  environmental board (BME280/SHTC3 + AS3935 — note AS3935 may want to live on its own
  small board given antenna/PCB layout sensitivity and isolation-from-noise requirements
  per its application notes), a wind-sensor interface board (reed switches + the
  resistor-ladder direction encoder from §5.1), and room for future additions (display,
  rain gauge via the same pulse-counting approach as wind speed, soil moisture, etc.).
- **Firmware should auto-detect what's populated** (e.g. I2C bus scan) and adjust its data
  payload accordingly — which also implies a compact, bitmask-style LoRa payload schema
  (a header byte indicating which sensor fields follow, given LoRa payload size is
  constrained) rather than a fixed-format packet assuming full population. Document this
  schema even if you don't fully implement it yet.

### 5.7 India sourcing & availability (reference data — verify before ordering)

I'm sourcing/assembling from India, so availability and pricing below matter for the
final component choices. These numbers are a planning-level snapshot, not a quote —
confirm live stock and pricing before finalizing the BOM.

| Component | Role | India availability | Indicative price (INR, qty 1–10) | Notes |
|---|---|---|---|---|
| ATtiny3226 (20-pin SOIC, UPDI) | Leaf MCU | **Confirmed in stock directly on Robu.in** — domestic, no LCSC/JLCPCB workaround needed for this one | ~₹150–300 | Cross-check against lokki's existing MCU per §5.2 too |
| *(alternate, not default)* STM32L071/L052 | Leaf MCU, if flash/RAM headroom is needed later | Mouser India (mouser.in) exists but is awkward for individual/non-B2B ordering; **LCSC + JLCPCB assembly** is the practical consumer route — JLCPCB sources and places the chip as part of a PCBA order, no personal Mouser account needed | ~₹150–350 (chip cost via LCSC pricing) | Keep in mind as the escape valve per §5.2, not needed for v1 |
| Plantower PMS7003 (confirmed part) | Particulate/AQI | Robu.in, evelta.com, and others stock it directly | ~₹1,600–1,900 | Needs its own 5V boost converter — see §5.1/§5.5 |
| Small 5V boost converter ×2 (AQI sensor + E22 module, one each) | AQI power / LoRa power | Common, any basic boost module | ~₹30–80 each | Both gated the same way — see §5.3.5/§5.5 |
| ESP32-S3-WROOM-1 (N4R8/N8R8/N16R8 variants) | Coordinator module | Very well stocked domestically — Robu.in, Campus Component, others; same-day dispatch | ~₹300–500 depending on flash/PSRAM | Use the module, not the bare chip — RF matching/antenna already done for you |
| Ebyte E22-900T22D | Leaf/coordinator LoRa (lower power) | Robu.in, HubTronics.in (domestic stock), also Ebyte's own store (ships from China) | ~₹500–750 | |
| Ebyte E22-900T30D | Leaf/coordinator LoRa (long-range) | Same as above | ~₹800–1200 | Higher PA current draw — see §5.3.4 |
| DFRobot SEN0290 (AS3935 lightning) | Lightning sensor | Robu.in, MakerBazar, element14 India, DigiKey India | ~₹700–950 | Stock fluctuates by seller — check more than one before committing |
| BME280 breakout | Temp/pressure/humidity | Extremely common; a genuinely India-made option exists (SmartElex) | ~₹150–300 | Prefer the domestically-manufactured option for supply resilience |
| SHTC3 breakout | Optional secondary temp/humidity | Less commonly stocked domestically than BME280 — check Mouser India/LCSC first | ~₹150–250 (estimate) | Confirm live stock — less certain than the others on this list |
| **CN3801 (bare IC, SOP-8)** | Solar MPPT charge controller, **LiFePO4-native** | I already have access to this part | — | Fixed 3.625V CV point at the factory — no resistor tuning needed, unlike CN3791. This is now the default, superseding CN3791 |
| LiFePO4 single cell (18650 format) | Leaf battery | Robu.in has a dedicated LFP cell category; also on IndiaMART | ~₹200–300 | Verify actual mAh/discharge rating per seller — quality varies |
| DS3231 RTC breakout | Coordinator RTC | Extremely common | ~₹80–150 | |
| Reed switches (glass) | Wind speed + direction | Common, sold individually or in packs | ~₹10–20 each (×9 needed per leaf) | |

**Resolved: CN3801 supersedes CN3791.** The CN3791 breakout modules commonly sold in
India (Robu.in, KTRON, Zbotic, ~₹235–260) are all fixed for standard Li-ion at 4.2V — the
wrong chemistry for LiFePO4. That's moot now: I already have the CN3801, which is
purpose-built for LiFePO4 with a fixed 3.625V CV point, no resistor tuning required. Use
that instead — see §5.5.

**Rough all-in electronics BOM estimate** (excluding PCB fab/assembly, enclosure, and
passives/connectors — order-of-magnitude planning numbers only, now including the AQI
sensor and its boost converter):
- Leaf node (fully populated): roughly ₹4,200–6,200
- Coordinator: roughly ₹1,500–2,500

Build a proper itemized BOM with live pricing before ordering, especially given how many
leaf nodes this mesh implies — these are for planning, not purchasing.

### 5.8 PCB layout guidance to document (not lay out)

You're not doing the PCB layout (see the scope boundary at the top of §5), but your
architecture document should include a short, concrete "layout notes" section for me to
follow when I do the actual board. Include at least:

- **Decoupling**: a 0.1µF ceramic on every IC power pin, placed as close to the pin as
  physically possible with a short, low-inductance path to ground — not shared between
  pins on multi-VDD-pin packages. Add a larger bulk cap (1–10µF) near each regulator
  output and near each dense IC cluster for slower transient support.
- **Crystals** (32.768kHz LSE for the leaf's RTC, any HSE if used): short, symmetric
  traces, load caps close to the crystal pins per its datasheet spec, routed away from
  switching/RF traces, ideally with a local ground guard ring.
- **Ground plane**: solid, unbroken reference plane under the RF section especially —
  don't let routed traces slice the plane under the LoRa module or antenna feed.
- **RF trace**: keep the LoRa module-to-antenna trace short and at the module's specified
  controlled impedance (check the E22 application note for exact trace geometry at your
  board stack-up); no digital switching lines routed near or under it; keep a
  component/pour keep-out around the antenna itself.
- **Power-gate bulk capacitor placement**: the 100–220µF bulk cap from §5.3.3 goes
  **after** the load switch, right at the LoRa module's VCC pin — not before it — so it's
  actually gated off during sleep and still does its job absorbing the TX current burst.
- **Reed switch inputs**: a small series resistor (~1kΩ) + small cap (~10–100nF) at each
  reed switch input, right at the connector, as cheap RC debounce — outdoor reed switches
  on a mast will chatter in wind.
- **External connector protection**: since the wind vane cable and solar leads leave the
  enclosure, add basic reverse-polarity protection on power inputs and small TVS/clamping
  on lines that run outside — worth taking seriously given this is explicitly a
  lightning-monitoring project.
- **Test points**: unpopulated header pins or pads on battery voltage, the 3.3V rail,
  LoRa module VCC, UART TX/RX, the power-gate control signal, and AUX — makes bring-up
  debugging far easier than probing fine-pitch legs directly.
- **Silkscreen**: label connector pinouts and battery/solar polarity clearly — future
  daughter boards (and future me) shouldn't have to guess.

### 5.9 Deliverables expected from this phase
- A first-pass BOM (component + rough part number for each function: MCU, LoRa module,
  each sensor, charger IC, load-switch/MOSFET, RTC, connectors) with rationale notes and
  India-availability/pricing per §5.7, clearly marked as a starting point for me to
  verify against current stock — not a final purchasing list.
- A written architecture/block-diagram document (plain description or a diagram, your
  call) covering leaf and coordinator separately, the expansion-bus concept, and the
  power-gating sequence from §5.3.
- The "layout notes" section from §5.8, for me to reference during actual PCB layout.
- The power-budget methodology and a placeholder for the real numbers once firmware
  exists.
- Explicitly **no PCB CAD work** — see the scope boundary at the top of §5.

---

## 6. Phase 5 — 3D printed parts (placeholder only)

All mechanical/enclosure parts will be designed by me in Onshape. You don't need to design
anything here — just reserve a sensible directory (e.g. `/hardware/enclosures/`) with a
short README noting that Onshape document links and any exported files will land there
later. Nothing else needed in this phase.

---

## 7. Explicit non-goals for this pass

- No crude mesh/multi-hop routing logic yet (mentioned as a possible future direction,
  but out of scope now) — just don't design the payload schema in a way that forecloses
  adding routing metadata later.
- No PCB schematic/layout work (I'm doing that).
- No public LoRaWAN network-server integration (TTN/ChirpStack/Helium) — this is a
  private point-to-multipoint network for now (see §5.3.6).

---

## 8. Open questions to confirm with me before proceeding

1. BME280-for-pressure-only + separate SHTC3, or single BME280 for everything — pick one
   or present the tradeoff, but don't silently default.
2. Whether lokki's existing MCU family should override the ATtiny3226 recommendation for
   code-reuse reasons — report what you find, then ask.
3. Confirm whether I already have (or need to build) a UPDI programmer — a SerialUPDI
   built from a spare USB-serial adapter + one resistor is the cheap DIY route if not.
4. Confirm the exact E22-900T30D vs T22D choice per node type once peak-current numbers
   are pulled from current datasheets (T30D likely reserved for nodes needing the longest
   range / worst RF path to the coordinator).
