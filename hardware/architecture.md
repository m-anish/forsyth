# Forsyth — Hardware Architecture

**Status:** planning document, v1 — 11 July 2026
**Scope:** component-level architecture, power design, and layout guidance. **No PCB
CAD lives here** — schematics, layouts, and footprints are done by hand (Anish) in KiCad;
this document is the reference to design against.

Companion documents: [BOM.md](BOM.md) (parts + India sourcing),
[../research/competitive-landscape.md](../research/competitive-landscape.md) (datasheet
numbers with sources).

---

## 1. System overview

```
                        LEAF (×N, solar, LiFePO4)                COORDINATOR (×1+, mains + backup)
  ┌────────────────────────────────────────────────┐       ┌──────────────────────────────────┐
  │  wind vane ──┐ (1 ADC, resistor ladder)         │       │                                  │
  │  anemometer ─┤ (1 pulse pin, event system)      │       │   ESP32-S3-WROOM-1               │
  │  rain gauge ─┘ (pulse, same pattern)            │ LoRa  │     ├─ E22 UART (gated 5V)       │
  │                                                 │ ~~~~> │     ├─ DS3231 RTC (I2C)          │
  │  ATtiny3226 ── I2C ── BME280 (pressure)         │ 868M  │     ├─ WiFi → MQTT/HTTPS         │
  │   (SOIC-20)        ── SHTC3/SHT4x (temp/RH)     │       │     │    ├─ self-hosted dashboard│
  │      │             ── AS3935 (lightning, +IRQ)  │       │     │    └─ Weather Underground  │
  │      │             ── [expansion: Qwiic]        │       │     └─ battery backup (LiFePO4)  │
  │      │                                          │       └──────────────────────────────────┘
  │      └─ shared UART ─┬─ PMS7003 (gated 5V boost)│
  │                      └─ E22-900T22D/T30D        │
  │                          (gated 5V boost)       │
  │  power: solar 1–2W → CN3801 → LiFePO4 18650     │
  └────────────────────────────────────────────────┘
```

- **Topology:** private point-to-multipoint LoRa. Leaves speak only to the coordinator;
  the coordinator timestamps on receipt and uploads. No multi-hop routing in v1 (payload
  schema leaves room for it, §7).
- **Not LoRaWAN — documented decision.** The E22 "D" variants run Ebyte's own UART
  protocol over the SX1262 radio, not the LoRaWAN MAC. For a single-owner mesh this is
  simpler and sufficient. If TTN/Helium interop is ever wanted, that is a different radio
  firmware stack (or module), not a config change — noted here so it's a choice, not an
  accident.

---

## 2. Leaf node

### 2.1 MCU — ATtiny3226 (tinyAVR-2, SOIC-20, UPDI)

Decided, with rationale recorded:

- Genuine wide **SOIC-20** (1.27 mm pitch) — hand-solderable, no adapter needed; the bare
  chip goes directly on the leaf PCB. No breakout/carrier module exists that solves the
  one hard problem (raw-LiFePO4 power path), so a module would add cost without removing
  design work.
- **UPDI** single-wire programming (existing programmer on the bench; SerialUPDI from any
  USB-serial adapter + one resistor is the fallback recipe).
- 32 KB flash / **3 KB SRAM** — more SRAM than an ATmega328P; headroom is real.
- **Integrated RTC on the internal 32.768 kHz ULP oscillator** — ±10 % raw, calibratable
  to ±2 %; ample for periodic wake intervals since the coordinator timestamps on receipt.
  **No external crystal, no crystal pins, no external RTC on the leaf.**
- **Event System + TCB** counts anemometer pulses in hardware while the CPU sleeps; the
  CPU wakes to read an accumulated count, not on every rotation.
- Classic ATmega328P is disqualified on package alone (no SOIC variant exists — PDIP-28,
  TQFP-32, QFN-32 only, per Microchip ordering info). The 14-pin ATtiny3224 is one GPIO
  too tight once AQI is included. megaAVR-0 (ATmega4808, 3 hard UARTs, SSOP-28) is the
  escape valve if shared-UART multiplexing ever proves painful — known, not planned.
- **Cross-check against lokki (done, 2026-07-11):** lokki runs MicroPython on an RP2350
  (Pico 2/2 W) — different architecture, different language, zero toolchain overlap
  either way. Reuse from lokki is *patterns* (AUX two-edge discipline, wire-key payload
  style), not code. No reason to displace the ATtiny3226. User confirmed.

**Pin budget (18 GPIO available on SOIC-20):**

| Function | Pins |
|---|---|
| I2C (SDA/SCL): BME280, SHTC3, AS3935, expansion | 2 |
| Shared UART (TX/RX): E22 + PMS7003, time-multiplexed | 2 |
| E22 control: M0, M1, AUX (in), power-gate EN | 4 |
| PMS7003 power-gate / boost EN | 1 |
| Wind speed pulse (Event System input) | 1 |
| Wind direction ADC (resistor ladder) | 1 |
| Rain gauge pulse | 1 |
| AS3935 IRQ | 1 |
| Battery voltage ADC (divider, high-side switched) | 1 |
| **Total** | **14** |
| Spare (future display, second gate, debug) | 4 |

### 2.2 Sensor suite

| Quantity | Sensor | Interface | Notes |
|---|---|---|---|
| Wind speed | magnet + reed switch | pulse → Event System | RC debounce at connector (§8) |
| Wind direction | magnet + 8 reed switches | **1 ADC pin, resistor ladder** | see below |
| Rain | tipping bucket + reed | pulse | same debounce pattern as wind |
| Pressure | BME280 | I2C | **pressure only** — see decision below |
| Temp/RH | SHTC3 or SHT4x | I2C | owns ambient temp + humidity |
| Particulates | Plantower PMS7003 | UART (shared), own gated 5 V boost | 30 s warm-up before valid data |
| Lightning | DFRobot SEN0290 (AS3935) | I2C + IRQ | **never duty-cycled**; 60–80 µA listening |

**Temp/humidity decision (made, 2026-07-11):** BME280's humidity element has a small
reconditioning heater and the module runs slightly warm in an enclosure — a known warm
bias in outdoor builds. **Forsyth uses the BME280 for pressure only and pairs it with an
SHTC3/SHT4x for ambient temp/RH.** Costs ~₹150–250 and one more I2C address per leaf;
worth it for a station whose entire personality is being right. (SHTC3 domestic stock is
the least certain item on the BOM — verify before ordering; SHT40 breakouts are an
equivalent substitute.)

**Wind direction — resistor ladder:** each of the 8 reed switches is in series with a
distinct resistor; all common to one ADC pin. Direction reads as one analog voltage;
the mast cable drops to **power / ground / signal(s)** instead of 8+ cores. Choose ladder
values so that adjacent-switch overlap (vane between two reeds closing both) still
produces a distinguishable voltage — E12-series values spread roughly logarithmically,
verified on the bench, is the standard trick. *Upgrade note:* an AS5600 magnetic angle
sensor (I2C, contactless, ~12-bit) is a plausible future drop-in on the expansion I2C
bus. Nothing in the architecture may preclude it — and nothing does: it's one more I2C
address on a bus that auto-detects (§7).

**AS3935 siting:** the antenna is layout-sensitive and dislikes switching noise. Per its
application notes it may want its own small daughter board (§6), away from the boost
converters, with the SEN0290 module's tuned antenna preferred over untuned clones —
jigawatt's experience (see `../../jigawatt/README.md`) says the same.

### 2.3 Shared UART — PMS7003 and E22, time-multiplexed

One hardware UART serves both, because the two are **never on at the same time** — each
is behind its own power gate, and the wake cycle sequences them:

```
wake → read I2C sensors + pulse counters
     → gate PMS7003 boost ON → wait 30 s warm-up → read frame(s) over UART → gate OFF
     → gate E22 boost ON → (E22 sequence, §3) → transmit → gate OFF
     → sleep
```

This is not just a pin-count trick; it's the same always-power-gated discipline the
radio needs anyway, applied uniformly. Bus contention is impossible when only one device
is powered. (If AQI cadence should ever need to differ from met cadence — PM readings
cost ~35× a LoRa burst in energy, see §5 — the schedule can simply skip the PMS7003 leg
on most wakes; nothing about the sharing changes.)

---

## 3. LoRa integration & power gating — the lokki lesson, made law

lokki's E220 (same M0/M1/AUX family, LLCC68 vs SX1262) took **60–100 s after power-on**
before register writes were reliable. Diagnosis, from lokki's own commit history
(`b4d5037`, `ce33ac9`, `9dbeab4` in `../../lokki`) and ROADMAP:

1. **No bulk capacitance at the module's V+** — fed straight from an LM2596 buck;
   switching ripple + cold-start cap-charge transient + the module's internal-LDO warm-up
   corrupted borderline-timing register exchanges. (The same module on a clean USB supply
   worked first try, every time.)
2. **Non-atomic M0/M1 GPIO init** — pins driven OUT before being driven LOW glitched the
   module through a hidden mode bounce. The E22 datasheet confirms M0/M1 have **weak
   pull-ups**: floating pins = M0=M1=1 = deep sleep. During MCU reset, tri-stated pins
   float high. Drive them, always, from before the module has power.
3. **Blind delays instead of AUX edges** — the fix that worked was a two-edge wait
   (AUX LOW = module processing, AUX HIGH = done), not longer sleeps.
4. **The module was never power-gated** — permanently on the 5 V rail, so a bad state
   persisted until someone cycled power by hand.

Forsyth's requirements (non-negotiable, applies to **both** leaf and coordinator):

1. **Full power gating.** The E22's rail comes from its own 5 V boost converter behind a
   load switch / P-MOSFET (TPS22918-class), controlled by a dedicated GPIO. In sleep the
   module is **off** — not in M0/M1 sleep mode, unpowered. (Sleep-mode current would be
   2 µA, but off is off; no state to go stale, no lesson to relearn.)
2. **Wake sequence, every cycle, not just cold boot:**
   ```
   drive M0/M1 to the intended mode (outputs LOW/defined BEFORE power-en)
   → assert power-enable → wait rail settle (ms, per boost + bulk cap)
   → wait AUX HIGH (module self-check done; datasheet: wait the rising edge)
   → +2 ms guard (datasheet: mode effective after AUX high ≥2 ms)
   → UART traffic (config write if needed, then payload)
   → wait AUX LOW→HIGH two-edge (TX accepted → TX complete), + small guard
   → de-assert power-enable → sleep
   ```
3. **Bulk capacitance after the switch:** 100–220 µF low-ESR + 100 nF ceramic **at the
   module's VCC pin, downstream of the load switch** (so it gates off with the module and
   still absorbs the TX burst). This is the component lokki's Rev0 board was missing.
4. **Current sizing — real numbers, pulled 2026-07-11 from current Ebyte manuals:**
   - E22-900**T30D**: TX current **650 mA typ** (instantaneous) at 30 dBm; RX 16 mA;
     operating voltage 3.3–5.5 V with the manual noting **"≥5.0 V ensures output power."**
   - E22-900**T22D**: TX current **140 mA typ** at 22 dBm; RX 11 mA; "≥3.3 V ensures
     output power."
   - Applying the ≥2× datasheet-peak rule: **T30D ⇒ design the 5 V rail and battery
     discharge path for ≥1.3 A momentary; T22D ⇒ ≥300 mA.** The T30D requirement lands
     right where the brief predicted ("clears 500 mA, headroom toward 1 A" — in fact
     beyond it; 1.3 A capability is the design target).
5. **5 V boost rail for the E22** (own gated boost, same pattern as the PMS7003): the PA
   runs at the top of its supply range, which the manual explicitly ties to delivering
   rated output power — this matters most for the T30D. **Boost converters reflect
   power, not current:** a 5 V × 650 mA burst is ≈ 3.25 W, which at a 3.2 V battery node
   and ~85 % efficiency is ≈ **1.2 A momentary from the LiFePO4 side**. Size the
   input-side bulk capacitance, the CN3801 output cap, and the cell's discharge rating
   for that input-side figure, not the 5 V figure.
6. **Logic levels:** the manual states communication level is **3.3 V regardless of VCC**
   (module has its own internal regulator for logic) and only warns 5 V-TTL hosts to add
   level conversion. The ATtiny3226 at 3.3 V connects directly — no shifter. Caveat for
   the record: the manual gives no numeric Vih/Vil table, so this is confirmed at
   user-manual level; if a silicon-threshold answer is ever needed, measure or ask Ebyte.
7. **T30D vs T22D per node type — recommendation (confirm before ordering):** default
   leaves to **T22D** (4.6× smaller TX burst, easier power path, 22 dBm is generous for
   line-of-sight km with decent antennas); reserve **T30D** for the worst RF path — a
   leaf behind terrain, or the coordinator if uplink symmetry matters. Both variants are
   drop-in identical in footprint and protocol, so the choice can be per-site.

---

## 4. Coordinator

- **MCU: ESP32-S3-WROOM-1** (module, not bare chip — RF matching done). Dual-core: one
  core services the E22 UART link without ever blocking on TLS; the other runs
  WiFi/MQTT/HTTPS and the Weather Underground uploader.
- **RTC: DS3231** (I2C) — survives reboots, bridges NTP outages, allows local
  timestamping if the uplink is down. The coordinator is the mesh's clock; leaves don't
  keep wall time at all.
- **LoRa:** same E22 module, same gating circuit, same wake discipline as the leaf
  (§3.7 of the brief: consistency avoids a second class of bugs, and an unpowered radio
  is an RF-quiet radio). The coordinator's radio is on far more often (it listens), so
  "gated" here means *gateable* — bring-up sequencing and recovery power-cycles under
  MCU control, not duty-cycled sleep.
- **Power:** mains (USB-C 5 V) + battery backup sized for **hours, not weeks** — a small
  LiFePO4 pack for chemistry-consistency with the leaves (one charger design to
  understand, one cell type to stock), with an appropriate charge/boost path. Chemistry
  formally open per the brief; LiFePO4 is the default absent a reason otherwise.
- Timestamps on receipt; leaf packets carry sequence numbers, not clock time.

---

## 5. Power budget — methodology (numbers TBD with real firmware)

Average current:

```
I_avg = (I_sleep × T_sleep + Σ I_active_phase × T_phase) / T_total
```

**What is known now (datasheet-level, sourced in research/competitive-landscape.md):**

| Contributor | Current | Duration / duty | Note |
|---|---|---|---|
| AS3935 listening | 60–80 µA | **continuous** | cannot be duty-cycled; the dominant *sleep-term* line item, larger than the MCU asleep |
| ATtiny3226 sleep (RTC on ULP osc) | ~1 µA class | continuous | verify on bench |
| BME280 / SHTC3 idle | ~0.1–1 µA each | continuous | negligible |
| PMS7003 reading | ~80 mA at 5 V (boost input side higher) | ~30 s per reading | **the dominant active-term item: ≈0.67 mAh per reading — ~35× one LoRa burst** |
| E22 T22D TX | 140 mA at 5 V | <1 s | ≈0.02 mAh per report |
| E22 T30D TX | 650 mA at 5 V | <1 s | ≈0.09 mAh per report; sizing case, not energy case |
| MCU awake + I2C reads | ~few mA | ~1 s | small |

**Consequences already visible without fabricated precision:**
- The sleep budget is an **AS3935 problem** (~0.07 mA floor ⇒ ~1.7 mAh/day before
  anything else happens).
- The active budget is a **PMS7003 problem**: at hourly AQI readings, ~16 mAh/day — an
  order of magnitude above everything else combined. AQI cadence is the single biggest
  battery-life knob on the leaf. (Met readings can run more often than AQI; the shared
  UART schedule already permits this, §2.3.)
- A 1500 mAh LiFePO4 18650 therefore holds **weeks of autonomy** with zero sun on any
  sane schedule — but publish no figure until firmware currents are measured. A
  worked spreadsheet (`power-budget.ods` or `.md` table) belongs here **after** bench
  measurements; placeholder intentionally left, per the brief.
- Solar: 1–2 W panel, Voc 5–6 V nominal into the CN3801, sized for the worst realistic
  season (monsoon overcast) — to be checked against the measured I_avg, not guessed.

**Leaf charging — CN3801 (decided).** Consonance's LiFePO4-native sibling of the CN3791:
same MPPT solar-buck topology, CV point **fixed at 3.625 V ±40 mV at the factory** —
no resistor-divider retargeting, unlike the 4.2 V-fixed CN3791 breakouts common in the
Indian market (wrong chemistry). SOP-8, hand-solderable, already on hand.

**Two gated 5 V boost rails on the leaf** (PMS7003, E22) — both fully off between uses.
Nothing on a Forsyth leaf is powered while idle except the MCU's sleep domain, the two
I2C ambient sensors, and the AS3935 doing its one perpetual job.

---

## 6. Modularity — core board + daughter boards

Feature modularity is a **PCB and protocol** concern, not an excuse for more MCUs:

- **Core/brain board** (every leaf): ATtiny3226 + E22 (+gating) + power path (solar in,
  CN3801, protection, battery) + **expansion connector**: Qwiic/JST-SH-style 4-pin
  (3.3 V, GND, SDA, SCL) + a small header carrying a few spare GPIO and the gated rails.
- **Daughter boards**, optional per site:
  - *Environmental*: BME280 + SHTC3 (the AS3935 may sit on its own small board for
    antenna isolation, §2.2).
  - *Wind/rain interface*: reed debounce RCs + the direction resistor ladder, living at
    the mast-cable connector.
  - *Future*: display, soil moisture, extra rain gauge — anything I2C rides the bus;
    anything pulse-shaped follows the wind/rain pattern on a spare GPIO.
- **Firmware auto-detects population** by I2C scan at boot and builds its payload
  accordingly (§7). A leaf with no AQI board is still a station; a leaf can grow senses.

---

## 7. LoRa payload schema (documented now, implemented later)

LoRa payloads are small and airtime is precious; the packet must describe itself rather
than assume full sensor population.

```
byte 0      : schema version (upper 4 bits) | flags (lower 4 bits)
byte 1      : leaf id (1–255; coordinator = 0)
byte 2      : sequence number (wraps; coordinator detects gaps)
byte 3–4    : sensor-presence bitmask (little-endian), one bit per field group:
              bit 0  temp (SHTC3)          bit 6  wind gust
              bit 1  humidity              bit 7  rain count
              bit 2  pressure (BME280)     bit 8  PM1/PM2.5/PM10
              bit 3  battery voltage       bit 9  lightning events
              bit 4  wind speed avg        bit 10 solar/charge state
              bit 5  wind direction        bits 11–15 reserved
byte 5…     : field groups, in bit order, fixed-width scaled integers each
              (e.g. temp: int16 centi-°C; pressure: uint16 = Pa/10 − 30000;
               PM: 3 × uint16 µg/m³; lightning: uint8 count + uint8 nearest-km)
```

- **Routing headroom:** flags bits are reserved for a future hop/TTL nibble, and leaf id
  0 is reserved for the coordinator — enough space that adding relay metadata later is
  an extension, not a redesign. (Explicit non-goal now.)
- Transport addressing (E22 fixed mode `[ADDH][ADDL][CHAN]` prefix, ≤200-byte payloads,
  optional trailing RSSI byte) follows the same conventions lokki proved out — see
  `../../lokki/docs/lora-protocol.md` for the working precedent.
- The coordinator ACKs configuration pushes only; routine reports are fire-and-forget
  with gap detection via sequence numbers.

---

## 8. Layout notes (for the KiCad pass — guidance, not CAD)

- **Decoupling:** 0.1 µF ceramic at every IC power pin, closest component to the pin,
  short low-inductance ground return; one per pin on multi-VDD packages, never shared.
  1–10 µF bulk near each regulator output and each dense IC cluster.
- **The gated bulk cap goes after the switch:** the 100–220 µF + 100 nF from §3.3 sits
  **downstream of the load switch, at the E22's VCC pin** — before the switch it would
  stay energized in sleep and do nothing for the TX burst. Same rule for the PMS7003's
  bulk cap on its boost rail.
- **Ground plane:** solid, unbroken under the RF section; no routed traces slicing the
  plane under the E22 or the antenna feed.
- **RF trace:** module-to-antenna short and at the E22 app-note's controlled impedance
  for the chosen stack-up; no digital lines near or under it; component/pour keep-out
  around the antenna.
- **Crystals:** the leaf has none (internal ULP oscillator — that's the point). The
  coordinator's DS3231 has its crystal integrated. If any discrete crystal ever appears,
  short symmetric traces, load caps per datasheet, guard ring, away from switchers/RF.
- **Reed inputs:** ~1 kΩ series + 10–100 nF to ground at each reed input, **right at the
  connector** — outdoor reeds on a mast chatter in wind; debounce in hardware first.
- **External line protection:** wind-vane cable and solar leads leave the enclosure —
  reverse-polarity protection on power inputs, TVS/clamp diodes on every line that goes
  outside. This is a *lightning-monitoring* project; assume the wiring will one day
  experience the subject matter.
- **Boost converters vs quiet things:** keep both 5 V boosts (and the CN3801's switch
  node) physically away from the AS3935 and the ADC ladder input; the lightning sensor's
  application notes are explicit about switching-noise isolation.
- **Test points:** battery voltage, 3.3 V rail, both gated 5 V rails, E22 VCC, UART
  TX/RX, both power-gate control lines, AUX. Bring-up happens on pads, not on SOIC legs.
- **Silkscreen:** label every connector pinout and the battery/solar polarity. Future
  daughter boards — and future you — should not have to consult this file to plug in
  a cable.

---

## 9. Open items

| Item | Owner | State |
|---|---|---|
| T30D vs T22D per node type | Anish | recommendation in §3.7; confirm against site RF paths before ordering |
| SHTC3 vs SHT4x availability | Anish | either works; check live domestic stock (BOM.md) |
| Bench-measured sleep/active currents | firmware phase | replaces §5 placeholders |
| Resistor-ladder values + overlap behavior | design phase | pick E12 spread, verify on bench |
| AS3935 own-board vs environmental-board placement | design phase | default: own small board |
