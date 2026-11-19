# Board B rev0: buying the parts in India (hand assembly)

Checked 2026-11-15 against `board-b-rev0-bom.csv` and the rev0 gerbers. Prices are in Rs
per piece unless a pack is named. "incl" means the shop shows the price with 18 % GST;
"as listed" means the shop doesn't say whether GST is included, so check at the cart.
Stock is what the shop showed on 2026-11-15. Nothing was added to a cart, so the
shipping charges here come from the shops' policy pages, not from a checkout.

This covers hand assembly only. JLCPCB assembly is costed separately.

## Short version

- **Two new shops, plus one order you're already placing.**
  - **Hubtronics:** the sensor and the Qwiic socket.
  - **Sunrom:** the PMS7003 socket, the PH socket, and every XH part for the cable.
  - **Quartz:** the GX16-8 pair and all the passives. Add these to the Quartz order already in the station BOM (inserts and vent), so they don't add a second shipping charge.
- **Use the SHT41 instead of the SHT40.** No shop has the SHT40-AD1B-R2 in stock. Hubtronics has the **SHT41-AD1B-R2** (64 in stock, Rs 160 incl). It uses the same footprint and the same 0x44 address, and it is more accurate. §3 of the design sheet already lists it as a drop-in.
- **The PMS7003 socket (J3) can be bought here.** Sunrom's B2B 1.27 2x5 female socket is 4.3 mm tall and its pads land on our pads. Buy the version **without side pins**: the board has no holes for the pegs.
- **The module sockets S1, S2 and S3 are not available here.** No Indian shop had a single-row SMD 2.54 mm female header in stock. Get the hanxia parts from LCSC, or wait for Hubtronics to restock.
- **You can skip J4 (PicoBlade).** It is only for a PMS5003. You have a PMS7003, which plugs into J3, and the two are fitted either/or.
- **The 8-core shielded cable is a local purchase.** None of the maker shops sell shielded multi-core cable by the metre.

## Cost of the basket

Excludes the cable and shipping. Pack minimums are included, so one board and five boards cost almost the same for the small parts.

| Shop | 1 board | 5 boards | Notes |
|---|---:|---:|---|
| Hubtronics | 212 | 899 | SHT41 x1 / x5, SH socket, one 1x40 SMD male strip. Add Rs 160 for a spare SHT41 (DFN, hot air) |
| Sunrom | 359 | 574 | J1, J3 and PH socket per board, plus minimum packs of XH housings and crimps. The packs cover five cables |
| Quartz (added to the station order) | 149 | 424 | GX16-8 pair per board, plus 20-packs of R and C |
| **Total** | **~720** | **~1,900** | Plus two shipping charges (Hubtronics, Sunrom) and the cable |

The 1-board column already includes 10 J1 headers, 10 of each housing and 100 crimps,
because those are Sunrom's minimum quantities. That's why 5 boards cost much less than 5 x 720.

## Per part

### U1: SHT40-AD1B-R2 (DFN-4 1.5 x 1.5)

| Option | Price | Stock | Link |
|---|---:|---|---|
| **Hubtronics SHT41-AD1B-R2** (drop-in substitute) | **160 incl** | **64** | [hubtronics.in/sht41-ad1b-r2](https://hubtronics.in/sht41-ad1b-r2) |
| Hubtronics SHT40-AD1B-R2 / -R3 | 103 incl | 0 | [sht40-ad1b-r2](https://hubtronics.in/sht40-ad1b-r2), [-r3](https://hubtronics.in/sht40-ad1b-r3) |
| Evelta SHT40-AD1B-R2 | 218.30 incl | 0 (sold out) | [evelta](https://evelta.com/16bit-humidity-sensor-0-2c-i2c/) |
| Lion Circuits SHT40-AD1B-R2 | 217 (10+: 194) | 22,500 at DigiKey; ships in 7 to 10 days | [lioncircuits](https://lioncircuits.com/parts/SHT40-AD1B-R2) |
| Hubtronics SHT45-AD1B-R2 | 425 incl | 0 | [sht45-ad1b-r2](https://hubtronics.in/sht45-ad1b-r2) |

Robu listed the SHT40-AD1B at Rs 249 on 2026-11-12 (design sheet §2). I couldn't check it
today because Robu sits behind a "verify you are human" check (see the end).
**Substitute:** the SHT41 has the same package, pinout and address, so nothing on the
board or in the firmware changes. Buy one spare: a DFN this small is easy to lose while
reflowing it with hot air.

### J1: XH-8 right-angle, through-hole (XH-8AW footprint, 2.5 mm)

| Option | Price | Stock | Link |
|---|---:|---|---|
| **Sunrom 5397** 8-pin XH 2.5 mm side entry | **10.86** as listed, **min 10** | orderable (no live count) | [sunrom](https://www.sunrom.com/p/8-pin-jst-xh-25mm-side-entry-header) |
| Evelta LA250108A0008, XH 2.5 mm 8-pin right angle | 8.99 incl | 802 | [evelta](https://evelta.com/xh-2-5mm-8pin-wafer-male-connector-dip-right-angle-tin-plated/) |
| Hubtronics XH2515 8-pin right angle | 4.72 incl | 59 | [hubtronics](https://hubtronics.in/8p-xh2515-ra-male-connector) |

Take J1 from the same shop and family as the XH-8 housings, here Sunrom's 2.5 mm series.
Hubtronics and Quartz call their XH parts "2.54 mm". Real XH is 2.50 mm, and across 8 pins
a true 2.54 mm part would be 0.28 mm out at the end pin. Buying the header and the
housing from one family avoids having to find out.

### J3: 2x5, 1.27 mm SMD female socket, 4.3 mm (HCTL PM127-2-05-S-4.3)

From the board's bottom paste layer, J3's pads are **0.74 x 2.20 mm** at 1.27 mm pitch,
with the rows 3.6 mm apart centre to centre (**5.8 mm** over the outer pad ends). The
board has no holes for locating pegs (the NPTH drill file has only the two tie slots).

| Option | Price | Stock | Height | Pads (from drawing) | Link |
|---|---:|---|---|---|---|
| **Sunrom 8171** B2B 1.27 2x5 female, **without side pins** | **40** as listed | 48 | 4.3 mm | 0.76 x 1.95, 5.8 mm outer: lands inside our pads | [sunrom](https://www.sunrom.com/p/b2b-127-25p-10p-female-board-to-board-connector-without-side-pins) |
| Sunrom 7728, same socket **with** side pins | 42.55 (50+: 40.42) as listed | 371 | 4.3 mm | same, plus Ø0.8 / Ø1.2 pegs | [sunrom](https://www.sunrom.com/p/b2b-127-25p-10p-female-board-to-board-connector) |
| Evelta XKB X1321FVS-2x05-C43D48 | 50.21 incl | 0 (sold out) | 4.3 mm | 0.74 x 2.20, 5.8 mm: identical to ours | [evelta](https://evelta.com/2x5-pin-1-27mm-pitch-female-square-pin/) |

Drawings: [Sunrom B2B 1.27](https://www.sunrom.com/download/1110.pdf),
[XKB X1321FVS](https://evelta.com/content/datasheets/345-X1321FVS-2x05-C43D48.pdf).

- **Sunrom 8171** is the one to buy. Its height matches, so the foam-tape gap behind the PMS7003 stays as designed. Its 1.95 mm solder tails sit inside our 2.2 mm pads.
- **For 5 boards**, the 48 in stock is enough. If it sells out, buy 7728 and cut the two pegs flush before reflow, since the board has no holes for them.
- **The XKB part** matches our pads exactly, but it is sold out.

### J4: Molex PicoBlade 53398-0871, 1x8 SMD (only for a PMS5003)

The pads on the board (0.8 x 1.3 mm at 1.25 mm pitch, two 2.1 x 3.0 mm mounting pads)
are for **53398, the vertical (top-entry) part**. The design sheet's §8 calls J4
"right-angle". The footprint is right; the wording isn't.

| Option | Price | Stock | Link |
|---|---:|---|---|
| Skip it: with the PMS7003 in J3, J4 stays empty | 0 | | |
| Sunrom 6202 8-pin SMD "JST 1.25 mm" top entry (generic PicoBlade-type) | 21.71 as listed | 935 | [sunrom](https://www.sunrom.com/p/8-pin-smd-jst-125mm-top-entry-header) |
| Lion Circuits genuine Molex 53398-0871 | 146.66 for 1; **10 for 364.90** | 3,440 (LCSC); ships in 7 to 10 days | [lioncircuits](https://lioncircuits.com/parts/53398-0871) |

- **Sunrom's generic part:** compare its drawing with the 53398 pad pattern before relying on it.
- **Robu's 8-pin PicoBlade at Rs 26** (from search results) is the 53261, which is the **right-angle** part. Its footprint is different, so don't buy it for this board.

### S4: JST SH 4-pin SMD right-angle, Qwiic (SM04B-SRSS-TB)

| Option | Price | Stock | Link |
|---|---:|---|---|
| **Hubtronics** "JST-SH 4Pin Socket, 1 mm, surface mount" (generic) | **11.80 incl** | 2,864 | [hubtronics](https://hubtronics.in/4pin-jst-sh-connector) |
| Evelta EQ-SM04B-SRSS-TB-W (generic, Qwiic) | 14.16 incl | 0 (sold out) | [evelta](https://evelta.com/jst-4pin-1mm-pitch-male-connector/) |
| Lion Circuits genuine JST SM04B-SRSS-TB(LF)(SN) | 10 for 295.92 | 70,295 (LCSC); ships in 7 to 10 days | [lioncircuits](https://lioncircuits.com/parts/SM04B-SRSS-TB%28LF%29%28SN%29) |

Hubtronics doesn't say whether its socket is side-entry or top-entry. The Qwiic generics
are almost always side-entry with two mounting tabs, the same as SM04B-SRSS-TB, but check
the product photo before ordering.

### S5: JST PH 4-pin SMD vertical (B4B-PH-SM4-TB), Gravity AS3935 socket

| Option | Price | Stock | Link |
|---|---:|---|---|
| **Sunrom 6334** 4-pin PH 2.0 SMT vertical, top entry (generic) | **13.57** as listed | 1,448 | [sunrom](https://www.sunrom.com/p/4-pin-jst-ph-20mm-smt-header-vertical-straight-top-entry) |
| Lion Circuits genuine JST B4B-PH-SM4-TB(LF)(SN) | 10 for 380.69 | 4,355 (LCSC); ships in 7 to 10 days | [lioncircuits](https://lioncircuits.com/parts/B4B-PH-SM4-TB%28LF%29%28SN%29) |

A generic PH SMD header usually copies JST's pattern, but its tab size can differ.
Compare it with the S5 pads when it arrives; the tabs only need to land on copper.

### S1, S2 (1x6) and S3 (1x4): 2.54 mm SMD female sockets, single row, 8.5 mm (hanxia)

**Not in stock in India.**

| Option | Price | Stock | Link |
|---|---:|---|---|
| Hubtronics 1x40 female header, SMD, 2.54 mm | 44.84 incl | 0 | [hubtronics](https://hubtronics.in/connectors/pin-header-connectors/1575) |
| Robu 1x40 female single-row SMT, pack of 5 | (search results only) | out of stock, "25 to 30 days" | [robu](https://robu.in/?p=535955) |
| Sunrom / Hubtronics / Evelta 2x40 SMD female | 69 to 80 | in stock | dual row: **doesn't fit** a single-row footprint |
| LCSC hanxia C48641755 (1x6), C48641754 (1x4) | | | add them to the LCSC/JLCPCB order |

- **The footprints** have alternating feet with a 4.7 mm lead span.
- **A generic 1x40 SMD strip** (Hubtronics, if it restocks) does fit, as long as its lead span is close to 4.7 mm. Each cut costs one pin, so one strip gives about two boards' worth (6 + 6 + 4).

### S6 (1x5) and S7 (1x2): 2.54 mm SMD male headers, single row

| Option | Price | Stock | Link |
|---|---:|---|---|
| **Hubtronics** 1x40 male berg strip, surface mount | **40 incl** | 144 | [hubtronics](https://hubtronics.in/1293) |
| Evelta 1X40 male SMD berg, 14 mm (stock not checked) | | | [evelta](https://evelta.com/1x40-male-smd-berg-14mm-height-2-54-mm-pitch/) |

- **One strip covers five boards** (7 pins each, and male strips cut without losing a pin).
- **Footprint:** the board's is hanxia PZ2.54 with a 5.0 mm lead span. Generic SMD strips have alternating feet at about that span, but check the strip before reflow.

### Passives (0805)

Quantities fitted per board: 6 x 10 k (R1 to R6; R7 and R8 are DNP), 2 x 0 R (JP1, JP2;
JP3 is DNP), 7 x 100 nF, 1 x 10 uF.

| Part | Quartz (20-pack, in stock) | Sunrom (min 100) | Hubtronics (50-pack, incl) |
|---|---|---|---|
| 10 k 1 % | [Rs 13](https://quartzcomponents.com/products/10k-ohm-103-1-smd-resistor-0805-pack-of-20-pieces) | [0.46 ea = 46](https://www.sunrom.com/p/10k-1-0805-pack-of-100) | [38.35](https://hubtronics.in/10-k-smd-resistor) (910) |
| 0 R | [Rs 6](https://quartzcomponents.com/products/yageo-0-ohm-0805-package-1-8w-smd-resistor-1-tolerance-pack-of-20-pieces) (Yageo RC0805FR-070RL) | [46](https://www.sunrom.com/p/0r-0805-smd-jumper-2) | [29.50](https://hubtronics.in/0805s8j0000t5e) (3,974) |
| 100 nF X7R | [Rs 26](https://quartzcomponents.com/products/kemet-100nf-50v-0805-smd-pack-x7r-multilayer-ceramic-capacitor-10-tolerence-pack-of-20) (Kemet C0805C104K5RACTU) | [1.50 ea = 150](https://www.sunrom.com/p/100nf-104-0805-2012-metric-50v-x7r-mlcc) | [49](https://hubtronics.in/walsin-0805b104k500ct) (Walsin, 7,982) |
| 10 uF | [Rs 45](https://quartzcomponents.com/products/kemet-10uf-50v-0805-smd-pack-x5r-multilayer-ceramic-capacitor-20-tolerence-pack-of-20) (Kemet C0805C106M8PACTU, **10 V** X5R) | [1.73 ea = 173](https://www.sunrom.com/p/10uf-106-0805-2012-metric-50v-x7r-mlcc-smd) (listed 50 V X7R) | none |

**Quartz is the cheapest** for both one board and five boards. For five boards you need
2 packs of 10 k, 1 of 0 R, 2 of 100 nF and 1 of 10 uF: Rs 129.

**The 10 uF part differs from the BOM.** The BOM part (Samsung CL21A106KAYNNNE) is rated
25 V; Kemet's is 10 V. Both rails J1 carries (VBAT, 5V_AQI) are well under 10 V, so it is
safe. At 5 V the 10 V part keeps less of its 10 uF than the 25 V one. That's acceptable
for a bulk capacitor at the connector.

Quartz's 10 uF 50 V X7R 5-pack was out of stock.

## The cable (Anish builds it)

Per cable: 8 crimps at Board B's end, plus 5 + 4 for the pigtail inside the box: 17 crimps,
1 XH-8 housing, 1 XH-5, 1 XH-4, 1 GX16-8 pair.

| Part | Best option | Price | Stock | Also |
|---|---|---:|---|---|
| XH-8 housing | [Sunrom 5650](https://www.sunrom.com/p/8-pin-jst-xh-25mm-housing) | 5.43, min 10 | orderable | [Evelta](https://evelta.com/xh-2-5mm-8pin-housing-connector-female/) 3.71 incl, 468 in stock |
| XH-5 housing | [Sunrom 5338](https://www.sunrom.com/p/5-pin-jst-xh-25mm-housing) | 3.39, min 10 | orderable | |
| XH-4 housing | [Sunrom 5229](https://www.sunrom.com/p/4-pin-jst-xh-25mm-housing) | 2.71, min 10 | orderable | |
| XH crimp terminals | [Sunrom 5139](https://www.sunrom.com/p/crimping-pins-for-jst-xh-25mm) | 0.82, min 100 (Rs 82) | orderable | Robu about 0.40 incl (search results only, 24 to 30 AWG) |
| GX16-8 plug + panel socket | [Quartz](https://quartzcomponents.com/products/gx-16-8-pin-16mm-metal-aviation-plug-male-and-female-panel-connector) | **59** | in stock | [Flyrobo](https://www.flyrobo.in/gx16-8-pin-circular-aviation-socket-plug-male-and-female-panel-connector) 94; [Sunrom 5600](https://www.sunrom.com/p/8p-metal-mini-round-shell-aviation-male-and-female-circular-connectors-gx16-16mm) 123. Hubtronics stops at 7 pins |
| 8-core shielded cable | local CCTV / alarm or network shop | | | see below |

- **GX16-8 pair.** Quartz is cheapest, and the station BOM already has a Quartz order that doesn't reach Quartz's Rs 500 free-shipping line. Adding the GX16-8 there costs no extra shipping. If you'd rather keep all the GX parts one brand, Flyrobo's set (Rs 94) can go into the Flyrobo station order instead, which also costs no extra shipping.
- **Cable.** None of the shops checked (Robu, Quartz, Sunrom, ElectronicsComp, Hubtronics) sell shielded multi-core cable by the metre. Sunrom sells 4- and 6-core **unshielded** cable only.
  - **Online:** what turned up are 100 m reels (RR Kabel, Havells, Belden-type at about Rs 540 to 690/m) and IndiaMART listings.
  - **Locally:** a CCTV or alarm shop sells 8-core shielded alarm cable, or Cat5e/Cat6 **STP/FTP** by the metre. That is the practical source. Measure the route down the mast first (§5 of the design sheet).
  - **Avoid a ready-made Cat5e/Cat6 patch lead.** The cheap ones (Quartz's 3 m Cat5e at Rs 67, or 10 m outdoor Cat6 on Amazon) are UTP, which has no shield.
- **Crimper.** XH contacts need a small open-barrel crimper (SN-28B / PA-09 type). Sunrom's YAC12 is Rs 4,750. A generic ratcheting one is far cheaper, but I didn't price one. Skip this if you already crimp XH for Board A.

## Suggested basket

**Hubtronics** (no COD; shipping shown at checkout)
- 1 (or 6) Sensirion SHT41-AD1B-R2: 160 each
- 1 (or 5) JST-SH 4-pin SMD socket: 11.80 each
- 1 x 1x40 SMD male berg strip: 40

**Sunrom** (ships within 48 h, courier 2 to 7 days, flat-rate shipping)
- 1 (or 5) B2B 1.27 2x5 female **without side pins** (8171): 40 each
- 1 (or 5) 4-pin PH 2.0 SMT vertical (6334): 13.57 each
- 10 x 8-pin XH side-entry header (5397): 108.60
- 10 x XH-8 housing (5650), 10 x XH-5 (5338), 10 x XH-4 (5229): 115.30
- 100 x XH crimp pins (5139): 82
- Optional: 1 x 8-pin SMD 1.25 mm top entry (6202), only if a PMS5003 is ever fitted: 21.71

**Quartz** (added to the station-BOM order)
- 1 (or 5) GX16-8 pair: 59 each
- 10 k, 0 R, 100 nF and 10 uF 0805 in 20-packs: Rs 90 for one board, Rs 129 for five

**Local:** 8-core shielded cable, enough for the mast route plus about 0.5 m.

**From LCSC (with a JLCPCB order) or Lion Circuits:** S1, S2, S3.

## What can't be had in India (put these on the LCSC/JLCPCB order)

| Ref | Part | LCSC | Why |
|---|---|---|---|
| S1, S2 | hanxia HX PM2.54-1x6P TP H8.5-ZQ | C48641755 | no single-row SMD female header in stock at any Indian shop checked |
| S3 | hanxia HX PM2.54-1x4P TP H8.5-ZQ | C48641754 | same |
| (J3, if you want the exact part) | HCTL PM127-2-05-S-4.3 | C3975131 | the Sunrom socket works, so this is optional |

**Lion Circuits** is an Indian storefront for LCSC and DigiKey stock, priced in rupees
(7 to 10 days). It is the import route without a JLCPCB order, and it sells genuine
SM04B-SRSS-TB, B4B-PH-SM4-TB, 53398-0871 and SHT40.

- **Quantity matters.** Its price for one piece of a cut-tape part is several times its price for 10.
- **The hanxia sockets aren't listed there.**

## Shops and how far each was checked

| Shop | How it was checked | Good for |
|---|---|---|
| Sunrom | live pages: price tiers, minimums; ready stock where shown | XH family, PH and 1.25 mm SMD, J3 socket, GX16, passives (min 100) |
| Hubtronics | live pages: price incl GST, stock count | SHT41, SH socket, SMD male strip, passives in 50s |
| Quartz | live store search: price, in-stock flag | passives in 20s, GX16-8 |
| Evelta | live pages: price incl GST, stock count | XH-8 header and housing; its J3, SHT40 and SH listings are sold out |
| Flyrobo | live search: price only | GX16-8 (Rs 94), GX16-8 panel socket alone (Rs 36) |
| Lion Circuits | live pages: price tiers, LCSC/DigiKey stock | genuine JST/Molex/Sensirion, imported |
| ElectronicsComp | live search | nothing useful: no SMD headers, no shielded cable |
| Robu | **not checked live.** Cloudflare asks for a human click, so prices come from search results and may be stale | 8-pin PicoBlade (wrong orientation for J4), XH housings and crimps, SHT40 (Rs 249 on 2026-11-12) |

**To check Robu yourself:** open robu.in in the built-in browser and pass the check. Then
compare its XH crimps and its 1x40 SMD female strip (`?p=535955`, which would fill the
S1 to S3 gap if it is back in stock).

**Not checked:** Probots and Robocraze (no matching parts found in a quick search) and
Stackskb (genuine SM04B at Rs 70 incl, from search results only).

## Update 2026-11-18: hand-soldered parts on the trimmed board (JLC fits the rest)

JLC's Economic assembly fits U1, U2 and the passives. Only these three are left to buy and
hand-solder; S1-S7, J4 and the module sockets are gone from the board.

| Ref | Part | Buy | Price (Rs) | Note |
|---|---|---|---|---|
| J1 | XH-8 right angle, through-hole, 2.5 mm | [Sunrom 5397](https://www.sunrom.com/p/8-pin-jst-xh-25mm-side-entry-header) | 10.86, min 10 | As above; match the XH-8 housings' brand |
| J2 | **5-pin** JST PH 2.0 SMT, vertical, top entry (B5B-PH-SM4-TB footprint) | [Sunrom 6335](https://www.sunrom.com/p/5-pin-jst-ph-20mm-smt-header-vertical-straight-top-entry) | 16.96, from 1; 456 in stock (checked 2026-11-18) | Generic part: check its tab size against the J2 pads before soldering, as with the old 4-pin S5 |
| J3 | 2x5 1.27 mm SMD female, 4.3 mm, **without side pins** | [Sunrom 8171](https://www.sunrom.com/p/b2b-127-25p-10p-female-board-to-board-connector-without-side-pins) | 40 | As above; pads land inside ours |

The J2 cable to the DFRobot lightning module needs a PH-5 plug at the board end:

| Part | Buy | Price (Rs) |
|---|---|---|
| 5-pin PH 2.0 housing | [Sunrom 6353](https://www.sunrom.com/p/5-pin-jst-ph-20mm-housing) | 2.88, min 10 |
| PH 2.0 crimp pins (7/38 wire, 1 A) | [Sunrom 6331](https://www.sunrom.com/p/crimping-pins-for-jst-ph-20mm) | 1.36, min 100 |

The simplest cable reuses the Gravity lead that comes with the SEN0290:

- **Module end:** keep its PH-4 plug as it is.
- **Board end:** crimp the four wires into the PH-5 housing in J2's order (VBAT, GND, SCL, SDA, IRQ).
- **IRQ:** run a fifth wire from the module's IRQ header pin, ending in a Dupont female.
- **Crimper:** PH contacts take the same small open-barrel crimper as XH. If you'd rather not
  crimp, a ready-made PH 2.0 5-pin pigtail works too (not price-checked).

Sunrom order for 5 boards (J1-J3 plus J2's plug):
5 x 6335 (84.80) + 5 x 8171 (200) + 10 x 5397 (108.60) + 10 x 6353 (28.80) + 100 x 6331 (136),
about **Rs 558 before GST and shipping**. It can go in the same Sunrom order as the XH housings
and crimps listed above.

## Cable and crimping (checked 2026-11-18)

### The screen-to-box cable: Spectra (Mumbai)

| Item | Buy | Price | Stock |
|---|---|---|---|
| **Spectra 8-core shielded, 7/0.18 tinned copper** (8003-8GY-7) | [spectra.in](https://spectra.in/spectra-8003-8gy-7-8-core-cable-shielded-7-36-t-c) | **Rs 81 per metre + 18 % GST** | 372 m |

- **Construction:** 8 cores of 0.18 mm² (about 25 AWG), PVC insulated, 1.0 mm core OD.
- **Shield and jacket:** tinned-copper braid shield, PVC jacket 6.0 mm OD.
- **Ratings:** 300 V, 65 °C, 10 Ω per 100 m. That's 0.4 Ω round trip on 2 m, so negligible drop
  at the PMS7003's ~100 mA.
- **Fits:** 6 mm passes the screen base's 9 mm cable hole. Check it fits the GX16-8 plug's cable
  clamp (most take up to about 6.5 mm).
- **Outdoors:** PVC isn't sold as UV-rated, so keep the run short and shaded under the crossarm,
  or sleeve it.
- **Length:** order 2-3 m per station. The off-cuts make the pigtail inside the box.
- **Shipping:** Spectra ships free only above Rs 5,000.

### Crimping tool

| Tool | Where | Price | Note |
|---|---|---|---|
| **IWISS SN-28B** (ratcheting, open barrel, 0.1-1.0 mm², 28-18 AWG) | [Spectra](https://spectra.in/catalogsearch/result/?q=crimping+tool+JST) | **Rs 2,100** | Genuine IWISS; does XH (2.5), PH (2.0) and Dupont. Same Spectra order as the cable |
| Generic "SN28B/48B/58B" dual-head | [Fruugo India](https://www.fruugoindia.com/crimping-tool-sn28b-sn48b-dual-head-wire-crimper-for-harness-power-terminals-sn58b/p-449964374-947584672) | Rs 2,699 | Dearer and unbranded; skip |
| Robu, Quartz, Evelta | | none | No JST-type crimper listed: only ferrule, lug, MC4 and RJ45 crimpers |
| Generic SN-28B on Amazon India | | (not checked) | Usually cheaper, quality varies |

### Crimp parts per station (Sunrom, as listed above, or Evelta loose)

| Cable | Parts |
|---|---|
| Board B J1 end of the screen cable | 1 x XH-8 housing, 8 x XH crimps |
| GX16-8 plug and socket | solder cups, no crimps |
| Pigtail in the box, GX16-8 socket to Board A J4 + J5 | 1 x XH-5 + 1 x XH-4 housing, 9 x XH crimps |
| Lightning: J2 end | 1 x PH-5 housing, 5 x PH crimps |
| Lightning: IRQ wire at the module | 1 x Dupont female crimp + 1-pin housing (or a ready female jumper lead) |

**Loose crimps without the 100-piece minimum:**

- **XH:** [Evelta](https://evelta.com/search.php?search_query=crimping+tool), LDCONN XH 2.5 mm,
  Rs 1.46 ex GST, 2,857 in stock.
- **PH:** Evelta, PH 2.0, Rs 1.23 ex GST.

**Wire size:** the Spectra cable's 0.18 mm² cores (about 25 AWG, 1.0 mm insulation) sit at the
thick end of what XH crimps take. Genuine JST SXH-001T-P0.6 is rated AWG 30-26; generic XH
crimps usually say 22-28 or 24-30 AWG. Check the listing, and crimp one test lead before doing
all eight.

**No-crimp option:** Robu sells ready-crimped XH pigtails, ~15 cm with a plug, from about Rs 13
(3-pin) to Rs 19 (5-pin). Splice them onto the cable with solder and heat-shrink. I didn't see an
8-pin pigtail there.
