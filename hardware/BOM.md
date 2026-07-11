# Forsyth — First-Pass BOM (planning, not purchasing)

**Status:** v1 — 11 July 2026. Planning-level snapshot: **verify live stock and pricing
before ordering anything.** Prices are INR, qty 1–10, rounded. Sourcing is India-first
(assembly happens there); LCSC+JLCPCB noted where it's the practical fallback.

Decisions already made (see [architecture.md](architecture.md) for rationale):
ATtiny3226 leaf MCU · ESP32-S3 coordinator · E22 UART LoRa on both · CN3801 charging ·
BME280-for-pressure + SHTC3/SHT4x for temp/RH · PMS7003 AQI · DFRobot SEN0290 lightning.

---

## 1. Leaf node

| # | Component | Function | India availability | ~₹ (qty 1–10) | Rationale / notes |
|---|---|---|---|---|---|
| 1 | **ATtiny3226-SU** (SOIC-20) | Leaf MCU | **Robu.in — domestic stock confirmed** (carries tinyAVR-2 family broadly); LCSC fallback | 150–300 | Bare chip on PCB; UPDI programming (programmer already on the bench). See architecture §2.1 |
| 2 | **Ebyte E22-900T22D** | LoRa radio (default leaf) | Robu.in, HubTronics; Ebyte store (ships CN) | 500–750 | 140 mA TX burst — easy power path. Default per architecture §3.7 |
| 2a | *(per-site alternate)* E22-900T30D | LoRa radio, worst RF paths | same sellers | 800–1200 | 650 mA TX ⇒ ≥1.3 A momentary discharge path required; only where 22 dBm can't close the link |
| 3 | **CN3801** (SOP-8) | Solar MPPT charger, LiFePO4-native | **already on hand** | — | Factory-fixed 3.625 V CV — no resistor retargeting. Supersedes CN3791 breakouts (4.2 V Li-ion, wrong chemistry) |
| 4 | **LiFePO4 18650 cell** (1×) | Battery | Robu.in LFP category; IndiaMART | 200–300 | Verify real mAh and discharge rating per seller — quality varies; T30D sites need honest ≥1.5 A discharge |
| 5 | **Solar panel 1–2 W, 5–6 V** | Charging | ubiquitous (Robu, local) | 150–400 | Voc comfortably above battery; size for worst season (monsoon) once I_avg is measured |
| 6 | **TPS61023 boost w/ true load disconnect** ×2 (bare SOT-563 + inductor, or 7semi breakout) | Gated 5 V rails: E22 + PMS7003 — **the boost's EN pin is the power gate** | Bare IC: LCSC/JLCPCB; **breakout sold domestically** ([7semi](https://7semi.com/tps61023-3-7a-5v-out-mini-boost-converter-breakout/), [Evelta](https://evelta.com/7semi-tps61023-3-7a-5v-out-mini-boost-converter-breakout/)) | ~₹40–90 (IC) / ~₹250–350 (breakout, est. — verify) | Datasheet-confirmed output disconnect in shutdown (0.1 µA); ≥3 A valley limit clears the T30D's ≥1.3 A input-side burst. Replaces the earlier load-switch + boost-module pair (architecture §3.1). SOT-563 is fine-pitch — the breakout is the hand-solder-friendly route |
| 6a | *(fallback, all Robu-stocked)* AO3401/SI2301 P-FET + 2N7002 driver | Discrete high-side gate on a boost's **input** | [Robu](https://robu.in/product/ao3401-hxy-mosfet-30v-4-2a-1-2w-54m%CF%8910v4-2a-700mv-1-p-channel-sot-23-3l-mosfets-rohs/) ₹3–7 ea | <₹20/rail | If TPS61023 sourcing ever fails. Gate the boost's input, never trust a generic boost's EN (pass-through — architecture §3.1) |
| 6b | *(AQI rail option)* TPS2041B switch + any 5 V boost | PMS7003 rail only | TPS2041 series is Robu-findable per user; verify exact suffix | ~₹40–80 | 500 mA continuous, 0.75–1.25 A limit ([datasheet](https://download.mikroe.com/documents/datasheets/TPS2041B_datasheet.pdf)) — fine for the PMS7003's ≤100 mA, **never for the radio rail**. TPS22918 itself: not stocked domestically (checked 2026-07-11) |
| 8 | **Plantower PMS7003** | Particulates / AQI | Robu.in, Evelta — direct stock | 1600–1900 | 5 V fan, 3.3 V logic, ~30 s warm-up per reading (dominant active-energy item) |
| 9 | **DFRobot SEN0290** (AS3935) | Lightning | Robu.in, MakerBazar, element14/DigiKey India | 700–950 | Stock fluctuates — check multiple sellers. Tuned antenna preferred over CJMCU clones (jigawatt's experience) |
| 10 | **BME280 breakout** | Pressure (only) | very common; **SmartElex (India-made) preferred** for supply resilience | 150–300 | Humidity/temp deliberately not used from this part |
| 11 | **SHTC3 or SHT4x breakout** | Ambient temp/RH | least-certain item — check Mouser India / LCSC / Evelta | 150–250 (est.) | Either part fits; same I2C bus. Confirm live stock before committing |
| 12 | **Reed switches (glass)** ×9 | Wind speed (1) + direction (8) | common, packs | 10–20 ea | Plus 1 more if the rain gauge is built rather than bought |
| 13 | Resistor ladder set (8 values, E12 spread) + debounce RCs | Wind direction encoding, input conditioning | any | <50 total | Values picked at design time, verified on bench (architecture §2.2) |
| 14 | **Bulk caps**: 100–220 µF low-ESR ×2 + ceramics | Post-gate rail support (E22, PMS7003) | any | <100 | **Downstream of the gated boost stages, at the loads' VCC pins** — the component lokki's Rev0 lacked |
| 15 | TVS/clamp diodes, reverse-polarity protection, Qwiic/JST-SH connectors, misc passives | Protection + expansion bus | LCSC/local | 100–250 | Every line leaving the enclosure gets a clamp — architecture §8 |

**Leaf subtotal (fully populated, T22D):** roughly **₹4,200–6,200** — matches the brief's
planning envelope. A met-only leaf (no PMS7003, no SEN0290) lands nearer ₹1,800–3,000.

## 2. Coordinator

| # | Component | Function | India availability | ~₹ | Notes |
|---|---|---|---|---|---|
| 1 | **ESP32-S3-WROOM-1** (N8R8 or N16R8) | Coordinator MCU | Robu.in, Campus Component — same-day dispatch | 300–500 | Module, not bare chip (RF done). PSRAM variant for TLS headroom |
| 2 | **Ebyte E22-900T22D** (or T30D) | LoRa | as above | 500–1200 | Same gating circuit as leaf — one design, twice used |
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
