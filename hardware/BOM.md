# Forsyth — First-Pass BOM (planning, not purchasing)

**Status:** v1 — 11 July 2026. Planning-level snapshot: **verify live stock and pricing
before ordering anything.** Prices are INR, qty 1–10, rounded. Sourcing is India-first
(assembly happens there); LCSC+JLCPCB noted where it's the practical fallback.

Decisions already made (see [architecture.md](architecture.md) for rationale):
ATtiny3226 leaf MCU · ESP32-S3 coordinator · E220 (LLCC68) UART LoRa on both · CN3801 charging ·
BME280-for-pressure + SHTC3/SHT4x for temp/RH · PMS7003 AQI · DFRobot SEN0290 lightning.

---

## 1. Leaf node

Organized by **physical PCB** (partition in architecture §6): Board A (core, sealed box),
Board B (environment, in the Stevenson screen), Board D (wind interface, masthead),
plus off-board items and the interconnect set.

> **Designator-level BOMs, reference sub-circuits (CN3801, TPS61023, E22, battery
> sense, protection), pin maps, and bring-up checklists live in the per-board sheets:
> [boards/](boards/README.md)** — this file stays the sourcing/pricing view. After each
> KiCad pass, reconcile the exported BOM against both.

### Board A — core (sealed box under the screen; the only board with switchers)

| # | Component | Function | India availability | ~₹ (qty 1–10) | Rationale / notes |
|---|---|---|---|---|---|
| A1 | **ATtiny3226-SU** (SOIC-20) | Leaf MCU | **Robu.in — domestic stock confirmed**; LCSC fallback | 150–300 | Bare chip on PCB; UPDI programming (programmer on the bench). Architecture §2.1 |
| A2 | **Ebyte E220-900T22D** (LLCC68) | LoRa radio (default) | Robu.in, HubTronics; Ebyte store | 450–650 | **In hand (decided 2026-07-12).** 110 mA TX burst. E220-900T30D (620 mA, ₹700–1100) per-site where 22 dBm can't close the link — rail sized for it either way |
| A3 | **CN3801** (SSOP-10) | Solar MPPT charger, LiFePO4-native | **already on hand** | — | Factory-fixed 3.625 V CV. Full sub-circuit w/ datasheet values in [boards/board-a-core.md §3.1](boards/board-a-core.md) |
| A4 | **LiFePO4 18650** + on-board holder | Battery | Robu.in LFP category | 200–300 + ~50 | Holder on Board A — no battery cable to get wrong. T30D sites need honest ≥1.5 A discharge |
| A5 | **TPS61023** ×2 (bare SOT-563) + 1 µH-class inductors + caps | Both gated 5 V rails — **EN pin is the power gate** | **Bare IC on Robu (user-confirmed)**; LCSC/JLCPCB for volume | ~₹40–90 ea + passives | True load disconnect ([datasheet](https://www.ti.com/lit/ds/symlink/tps61023.pdf)). **Bare IC decided** — the 7semi/Evelta breakout masks EN (ties it to VIN), which defeats the entire gating design. SOT-563 fine pitch: flux + drag solder |
| A5a | *(fallback)* AO3401/SI2301 P-FET + 2N7002 | Discrete high-side gate on a boost's input | [Robu](https://robu.in/product/ao3401-hxy-mosfet-30v-4-2a-1-2w-54m%CF%8910v4-2a-700mv-1-p-channel-sot-23-3l-mosfets-rohs/) ₹3–7 | <₹20/rail | Only if TPS61023 sourcing fails. TPS2041B acceptable on the AQI rail only (0.75–1.25 A limit, [datasheet](https://download.mikroe.com/documents/datasheets/TPS2041B_datasheet.pdf)); TPS22918 not stocked domestically |
| A6 | **Bulk caps** 100–220 µF low-ESR ×2 + ceramics | Post-gate rail support at the loads' VCC | any | <100 | Downstream of the gated boost stages — lokki's missing component |
| A7 | TVS row + series Rs + reverse-polarity P-FET, rain-input RC | Protection behind every external port | LCSC/local | 100–250 | Architecture §8; every line that leaves the box |
| A8 | Panel-mount connector set (see Interconnect below) + Qwiic expansion | All ports | Robu/Sharvi | see below | GND always pin 2 on GX ports |

### Board B — environment (inside the Stevenson screen; passive-quiet)

| # | Component | Function | India availability | ~₹ | Notes |
|---|---|---|---|---|---|
| B1 | **DFRobot SEN0290** (AS3935) | Lightning | Robu.in, MakerBazar, element14 | 700–950 | Tuned antenna > CJMCU clones. Lives here for isolation from Board A's switchers (§2.2/§6) |
| B2 | **BME280 breakout** | Pressure (only) | SmartElex (India-made) preferred | 150–300 | Humidity/temp deliberately unused from this part |
| B3 | **SHTC3 or SHT4x breakout** | Ambient temp/RH | check Mouser India / LCSC / Evelta | 150–250 (est.) | Least-certain stock item — verify before ordering |
| B4 | I2C pullups (4.7 kΩ) + XH-5 header | Bus + harness to core | any | <30 | ≤0.5 m run at 100 kHz — comfortably in spec |
| — | **Plantower PMS7003** (module, beside Board B) | Particulates/AQI | Robu.in, Evelta | 1600–1900 | Own XH-4 pigtail to the core's gated-5V port; needs the screen's airflow |

### Board D — wind interface (masthead junction; fully passive)

| # | Component | Function | ~₹ | Notes |
|---|---|---|---|---|
| D1 | Reed switches ×9 (8 vane + 1 anemometer) | Direction + speed sensing | 10–20 ea | +1 reed if the rain gauge is home-built |
| D2 | Resistor ladder (8 × E12 spread) + RC debounce | One-wire analog direction, clean pulses | <50 | Values verified on bench (§2.2) |
| D3 | GX16-5 plug + shielded 5-core outdoor cable | The one mast run | ~₹80 + cable | GND pin 2; shield pin 5 |

### Off-board + interconnect

| Item | ~₹ | Notes |
|---|---|---|
| Solar panel 1–2 W, **6 V-class** (V_MP ≈ 6 V, Voc ≈ 7.2 V) | 150–400 | 5 V panels sag into the CN3801's UVLO (≤4.4 V) under load — buy 6 V. Sized for monsoon overcast once I_avg is measured |
| Rain gauge (tipping bucket, bought or printed) | 0–500 | Dumb reed + magnet; debounce lives on Board A |
| **GX12-2 + GX12-3 + GX16-5 panel/plug pairs** | ~₹200–300 total | Robu/Sharvi/local. **Pin count = physical key** — no two external cables can swap (§6.1). RJ11 rejected for the mast: identical jacks + reversible cords + unshielded |
| JST-XH-4 + XH-5 harness sets (internal) | <₹50 | Polarized, different sizes — can't reverse, can't swap |
| Outdoor shielded multicore (alarm/security cable) | ~₹30–60/m | One 5-core mast run + two 2-core runs |

**Leaf subtotal (fully populated, T22D):** roughly **₹4,300–6,400** including the
connector set. A met-only leaf (no PMS7003, no SEN0290) lands nearer ₹1,900–3,100.

## 2. Coordinator

| # | Component | Function | India availability | ~₹ | Notes |
|---|---|---|---|---|---|
| 1 | **ESP32-S3-WROOM-1** (N8R8 or N16R8) | Coordinator MCU | Robu.in, Campus Component — same-day dispatch | 300–500 | Module, not bare chip (RF done). PSRAM variant for TLS headroom |
| 2 | **Ebyte E220-900T22D** (or T30D) | LoRa | as above | 450–1100 | Same gating circuit as leaf — one design, twice used |
| 3 | **DS3231 breakout** | RTC | ubiquitous | 80–150 | Survives reboots; bridges NTP gaps |
| 4 | **LiFePO4 cell + charger/boost path** | Backup (hours) | Robu.in | 250–450 | Chemistry-consistent with leaves by default; formally open |
| 5 | Load switch, bulk caps, USB-C 5 V input, protection | Power path | as above | 150–300 | Same §3 discipline |

**Coordinator subtotal:** roughly **₹1,500–2,500**.

## 3. Not in these totals

PCB fabrication/assembly (JLCPCB typical), enclosures (Onshape, printed —
`enclosures/`), mast/vane mechanicals, antennas beyond the module's SMA whip, shipping.

## 4. Sourcing notes

- **Robu.in is the primary domestic source** — it now stocks the ATtiny3226 directly, so
  the previous LCSC-only assumption for the MCU is retired.
- **LCSC + JLCPCB assembly** remains the practical route for TI parts awkward to buy
  retail in India — the bare TPS61023 especially (JLCPCB places it as part of a PCBA
  order; no B2B Mouser account needed). The 7semi breakout via Evelta is the
  domestic-retail alternative for prototypes.
- The **UPDI programmer already exists** on the bench; no line item. (For a second
  bench: any CH340/CP2102 USB-serial adapter + one ~470 Ω–4.7 kΩ resistor = SerialUPDI.)
- Multiply leaf quantities by the intended mesh size before ordering — and re-check
  SEN0290 and SHTC3 stock across at least two sellers each; they are the two items most
  likely to force a substitution or a wait.
