# Board B rev0: JLCPCB costing

Checked 2026-11-15 on jlcpcb.com without signing in. All money is USD. Board: 58 x 70 mm,
2 layers, 1.6 mm, green, OSP (JLC's current default finish), 1 oz, no special options.

**Recommendation:** use option (c). Order Economic PCBA, top side only. JLC places U1
(SHT40) and the 16 fitted 0805 passives. You hand-solder every connector and socket
(J1, J3, J4, S1 to S7). This costs about **$28 for 5 boards** or **$36 for 10**, before shipping.
Of that, roughly $13.5 is the assembly premium over bare boards. The rest is parts you would
buy anyway. Full assembly costs $61 to $77 on one side, or $140 to $160 if JLC also fits the
two back-side connectors.

## Where the numbers come from

| Source | What it gave |
|---|---|
| Live: `jlcpcb.com/partdetail/<C#>` (each BOM line) | class, price tiers, stock, attrition, minimum, assembly mode |
| Live: `cart.jlcpcb.com/quote`, 58 x 70 mm, ship to India | bare-PCB price and courier options |
| JLC help: "PCB Assembly Cost" (updated 2026-10-22) | setup, stencil, loading, joint and hand-solder fees |
| JLC capabilities page | Economic = one side only, 2-50 pcs; Standard = both sides, min board 70 x 70 mm |
| **Estimate** (marked *est.* below) | Standard edge-rail cost, Standard fixture fee, PCB price inside a PCBA order, PCBA shipping |

I did not run a full PCBA quote. That needs a sign-in plus a Gerber/BOM/CPL upload, and the
JLC review can still change two things. It may charge tall or odd connectors as hand-placed
("pre-reflow soldering", $0.016/joint), and it may add X-ray. U1's part record has
`xrayFlag: false`, so I assumed no X-ray. Neither change affects option (c) much.

## Per-part table

Prices are JLC's own (from the LCSC stock it holds). "Buy" is what JLC charges you for: per-board
quantity x boards, plus JLC's attrition, raised to its minimum where one applies. The loading fee is
the Economic Extended fee of $3.07 per unique part.

| Ref | Part | LCSC | /board | Class | Unit $ (5 / 10 boards) | Stock | Attrition / min | JLC can place? | Buy @5 → $ | Buy @10 → $ |
|---|---|---|---|---|---|---|---|---|---|---|
| U1 | SHT40-AD1B-R2 | C2909890 | 1 | Extended | 1.7491 / 1.5445 | 13,986 | 0 / 0 | Yes, SMT top. No X-ray flag | 5 → 8.75 | 10 → 15.45 |
| J1 | XH-8AW (THT, R/A) | C10395 | 1 | Extended | 0.028 | 7,281 | 0 / 2 | Hand-solder only ("manualWeld"): 8 manual joints + $3.58/order labour | 5 → 0.14 | 10 → 0.28 |
| J3 | HCTL PM127-2-05-S-4.3 | C3975131 | 1 | Extended | 0.1879 | 15,727 | 0 / 0 | SMT, but on the **bottom**: Standard only | 5 → 0.94 | 10 → 1.88 |
| J4 | Molex 53398-0871 | C471413 | 1 | Extended | 0.2373 | 2,755 | 2 / 0 | SMT, but on the **bottom**: Standard only | 7 → 1.66 | 12 → 2.85 |
| S4 | JST SM04B-SRSS-TB | C160404 | 1 | Extended | 0.2147 | 70,648 | 0 / 5 | Yes, SMT top | 5 → 1.07 | 10 → 2.15 |
| S5 | JST B4B-PH-SM4-TB | C160354 | 1 | Extended | 0.2754 | 2,090 | 0 / 2 | Yes, SMT top | 5 → 1.38 | 10 → 2.75 |
| S1, S2 | hanxia 1x6 SMD female H8.5 | C48641755 | 2 | Extended | 0.2592 | **805** | 0 / 2 | Yes, SMT top. Tall (8.5 mm): JLC may hand-place | 10 → 2.59 | 20 → 5.18 |
| S3 | hanxia 1x4 SMD female H8.5 | C48641754 | 1 | Extended | 0.2033 | 3,941 | 0 / 2 | Yes, SMT top (same caveat) | 5 → 1.02 | 10 → 2.03 |
| S6 | hanxia 1x5 SMD male | C41417362 | 1 | Extended | 0.065 | 4,749 | 0 / 2 | Yes, SMT top | 5 → 0.33 | 10 → 0.65 |
| S7 | hanxia 1x2 SMD male | C41417359 | 1 | Extended | 0.0282 | 46,245 | 6 / 5 | Yes, SMT top | 11 → 0.31 | 16 → 0.45 |
| R1-R6 | 10k 0805 | C17414 | 6 | **Basic** | 0.0034 | 47.9 M | 10 / 20 | Yes | 40 → 0.14 | 70 → 0.24 |
| JP1, JP2 | 0R 0805 | C17477 | 2 | **Basic** | 0.0046 | 3.8 M | 10 / 20 | Yes | 20 → 0.09 | 30 → 0.14 |
| C1-C7 | 100 nF X7R 0805 | C49678 | 7 | **Basic** | 0.0138 | 24.3 M | 10 / 20 | Yes | 45 → 0.62 | 80 → 1.10 |
| C8 | 10 uF X5R 0805 | C15850 | 1 | **Basic** | 0.0311 | 8.8 M | 10 / 20 | Yes | 20 → 0.62 | 20 → 0.62 |

Leave R7, R8 and JP3 out of the uploaded BOM (or mark them DNP) so JLC does not fit them.

- **None of the Extended parts is "Preferred".** Every part record has `preferredComponentFlag`
  unset, so each one pays the $3.07 Economic loading fee.
- **The minimum quantities barely matter here.** The Basic passives have a 20-piece minimum plus
  10 attrition, which still comes to cents. S7 and J4 carry a few extra pieces of attrition.
- **S1/S2 stock is thin (805 pieces).** That is plenty for 20, but check it again before ordering.
- **JLC will not ship parts on their own.** Parts bought into a JLC parts library can only be
  assembled. The parts you hand-solder must come from LCSC or an Indian shop (the other session
  is covering those).

## Fees used (from JLC's fee table)

| Fee | Economic | Standard |
|---|---|---|
| Setup | $8.18 | $25.56 one side / **$51.12 both sides** |
| Stencil | $1.53 | $8.21 one side / **$16.42 both sides** |
| Part loading | $3.07 per unique **Extended** part | $1.53 per unique part, Basic **and** Extended |
| SMT joints | $0.0016/joint | $0.0016/joint, at least $0.48/board |
| Manual (THT) joints | $0.0164/joint + $3.58/order hand-solder labour | same |
| Fixture | none | *est.* 2 fixtures = $16.42 for 1-29 boards (assumed to apply because J1 is THT) |
| Board size | min 10 x 10 mm | **min 70 x 70 mm**: JLC adds edge rails to the 58 mm side (*est.* +$3 on the PCB) |
| Confirm parts placement | $0.45 (optional; worth it for U1 orientation) | $0.45 (worth it for the mirrored J3) |

Economic places parts on one side only. J3 and J4 are on the back, so any order that has JLC
fit them must be Standard, double-sided.

## Option totals (JLC charges, before shipping)

PCB price is the live web price: **$4.00 for 5, $5.00 for 10**. JLC's desktop app showed $2 and
$3. I assumed the same PCB price inside a PCBA order (*est.*).

| | (a) Bare PCB | (b1) Economic, all top parts incl. J1 | (b2) Standard, both sides, everything | (c) Economic, U1 + passives |
|---|---|---|---|---|
| **5 boards** | **$4.00** | **$60.58** | **$139.63** (*est.*) | **$27.74** |
| **10 boards** | **$5.00** | **$76.81** | **$159.80** (*est.*) | **$36.37** |
| You still hand-solder | everything | J3, J4 | nothing | J1, J3, J4, S1-S7 |
| Hand parts at JLC prices (@5 / @10) | $19.65 / $35.77 (all parts) | $2.60 / $4.73 | $0 | $9.43 / $18.23 |

How each total breaks down at 5 boards (10 boards in brackets):

- **(b1)**: PCB 4.00 (5.00) + setup 8.18 + stencil 1.53 + 8 Extended x 3.07 = 24.56
  + parts 17.05 (31.05) + SMT joints 0.58 (1.15) + J1 manual 0.66 (1.31) + hand-solder labour
  3.58 + confirm 0.45. Leaving J1 for you to solder saves $7.44 ($8.24). That gives **$53.14**
  (**$68.57**).
- **(b2)**: PCB with rails *est.* 7.00 (8.00) + setup 51.12 + stencil 16.42 + 14 unique x 1.53 =
  21.42 + parts 19.65 (35.77) + SMT minimum 2.40 (4.80) + J1 4.24 (4.89) + fixture *est.* 16.42 +
  packing 0.51 + confirm 0.45.
- **(c)**: PCB 4.00 (5.00) + setup 8.18 + stencil 1.53 + 1 Extended (U1) 3.07 + parts 10.22
  (17.55) + joints 0.30 (0.59) + confirm 0.45.
- **(c0)**, the same as (c) but with U1 soldered by you too: **$15.89** (**$17.77**). It saves only
  the $3.07 loading fee, because you still have to buy the SHT40.

### Shipping to India (live quote, ship-to India, separate from the totals)

| Method | 5 bare (0.19 kg) | 10 bare (0.26 kg) | Time | Note |
|---|---|---|---|---|
| UPS Worldwide Express Saver | $9.57 | $9.57 | 5-7 business days | JLC's default for India; **not DDP** |
| E-POST | $8.00 | n/q | 10-18 business days | parcels up to 1.5 kg and $150 declared value |
| DHL Express | $25.31 | n/q | 2-5 business days | |
| FedEx Express | $26.80 | n/q | 6-7 business days | |

n/q: not quoted at 10 boards; only the default method was read.

- **PCBA shipping is an estimate.** Assembled boards come in a bigger box. Expect UPS at about
  $10-15 for 5-10 boards (*est.*).
- **Indian customs are not included.** None of the India options is DDP, so the courier collects
  import duty and IGST on delivery. I did not quote that amount.
- **Monthly coupons are not counted.** JLC hands out monthly SMT coupons; per its 2024 notice,
  a $9 one covers the Economic setup fee. If your account holds one, (c) drops by about $8.

## The "arm and a leg" parts

The comparison is the $3.07 Economic loading fee against what that part actually costs for the
whole run.

| Part | Part cost @5 / @10 | JLC fee to fit it | Verdict |
|---|---|---|---|
| J1 XH-8AW (THT) | $0.14 / $0.28 | $3.07 + 8 manual joints/board + **$3.58 labour** = $7.31 / $7.96 | **50x the part.** It is a two-minute iron job, so solder it yourself |
| S7 1x2 header | $0.31 / $0.45 | $3.07 | 10x. Hand-solder |
| S6 1x5 header | $0.33 / $0.65 | $3.07 | 9x / 5x. Hand-solder |
| J3, J4 (back side) | $0.94 + $1.66 / $1.88 + $2.85 | **About $79 (5) / $83 (10)**: (b2) minus (b1), for Standard double-sided, rails and fixture | The worst offender. Also, you never want both: with a PMS5003, J3 stays off (design sheet §8), so having JLC fit both is wrong for half the builds |
| S3, S4, S5 | $1.0-1.4 / $2.0-2.8 | $3.07 each | 2-3x / about 1.2x. Hand-solder. S4 (JST SH, 1.0 mm pitch) is the fiddliest, but it is fine with flux and a fine tip |
| S1/S2 1x6 sockets | $2.59 / $5.18 | $3.07 (one fee covers both) | About break-even at 10. Hand-solder anyway, since it is your time against $3 |
| U1 SHT40 | $8.75 / $15.45 | $3.07 | **Worth paying.** A 1.5 mm DFN with an exposed pad, on a slotted tongue, gets a stencil and reflow for $3 |

Moving from (b1) to (c) saves **$32.84 at 5 / $40.44 at 10** in JLC charges. You then buy the
seven hand-soldered Extended parts elsewhere ($6.83 / $13.50 at JLC prices), so the net saving
is **about $26 / $27**. Dropping the back side ((b2) to (b1)) saves **about $79 / $83**.

### Would a Basic swap help?

Not for this board.

- **Nothing to swap to.** I searched JLC's library by keyword (sensor, "Female Header",
  "Pin Header", JST, Molex, wire-to-board, the first 500 results each). It turned up no Basic or
  Preferred humidity sensor, 2.54 mm SMD socket, JST SH/PH, XH or PicoBlade part.
- **The passives are already Basic.** In option (c) the only Extended part is U1, and it has no
  substitute.
- **Swaps would not cut the cost anyway.** The real cost in (b) is the number of unique Extended
  connectors and the back side, and hand-soldering removes both.

## Recommendation

1. Order **10 PCBs, Economic PCBA, top side**, with JLC fitting **U1 and the passives** only.
   Upload a BOM with every S/J line removed (or marked DNP). Pick "Confirm Parts Placement" ($0.45)
   to check U1's pin 1.
   - You can assemble fewer than all 10 (Economic allows 2-50); 5 assembled out of 10 costs about
     $29.
   - Expected bill: **$36.37 + about $10-15 UPS + Indian duty**.
2. **Hand-solder J1, S1-S7 and the back-side J3 or J4**, whichever the board's PM sensor needs,
   from LCSC or Indian stock.
3. **Do not order (b2).** The back-side connectors alone cost about $80 in Standard setup,
   stencil, rails and fixture for roughly $2.60 of parts. JLC would also fit both J3 and J4, which
   a PMS5003 build must not have.
4. **Re-quote before paying.** Signed in, upload the Gerber, BOM and CPL. JLC's DFM review settles
   the estimates above: PCB price inside a PCBA order, any X-ray on U1, and shipping weight.

## Follow-up: an all-soldered rev1? (checked 2026-11-15)

The idea: drop the module sockets (S1-S7). JLC solders the SHT4x, a pressure sensor and the
AS3935 straight onto Board B. The back stays as it is (J3/J4 for the PMS) and so does J1.

### SHT4x alternatives on JLC (all Extended, all in stock)

| Part | LCSC | $ @1 / @10 | Stock | Verdict |
|---|---|---|---|---|
| **SHT40-AD1B-R2** (current) | C2909890 | 1.75 / 1.54 | 13,984 | Keep. Best value, has a heater for fog, same footprint as SHT41/45 |
| SHT40-AD1B-R3 | C2848306 | 1.85 / 1.57 | 13,096 | The same chip on a different reel: the fallback if R2 runs out |
| SHT45-AD1B-R2 | C5221601 | 5.72 / 4.94 | 6,530 | ±1.0 %RH vs ±1.8: the drop-in upgrade, +$3.4 per board |
| SHT41-AD1B-R2 | C7461861 | 3.26 / 2.78 | 11,237 | No real gain over the SHT40 for this job |
| SHTC3 | C194656 | 2.24 / 1.90 | 6,421 | Different footprint, no better than the SHT40 |
| SHT30/31-DIS | C77361 / C80862 | 2.81 / 4.59 | 15k each | Older, larger, dearer |
| HDC2080 (TI) | C918141 | 1.64 / 1.36 | 1,649 | Fine, different footprint, no heater advantage |
| HDC3020 (TI) | C7472806 | 5.54 / 5.04 | 6,750 | Condensation-tolerant high end; only if fog proves a problem |
| AHT20 / AHT30 | C2757850 / C45354925 | 0.80 / 0.72 | 30k / 4.6k | Cheap, but drifts in sustained high RH (design sheet §2) |
| Nyfea SHT41-P-NF, GXHT30 | C55108905 / C2913569 | 1.57 / 0.99 | 9k / 13k | Clones of unknown long-term RH stability; not for the reference sensor |

### Pressure and lightning on JLC

| Part | LCSC | JLC stock | Note |
|---|---|---|---|
| BMP280 | C83291 | **0** | Out of stock at JLC |
| **BMP580** | C22391138 | 11,321, $1.21 | **The in-stock pick.** Newer and lower power than the BMP280, but it needs a different firmware driver |
| BMP388 (Bosch) / Tokmas clone | C779278 / C54582187 | 12,887 / 8,135 | $6.83 / $1.58 |
| BME280 | C92489 | 151, $9.07 | Too dear; the SHT40 already covers RH |
| **AS3935-BQFT** | C3178344 | **0** (15 on backorder); LCSC shows no stock | Active part, stocked at Mouser/DigiKey for about $9-13 each, so JLC can only fit it through its **Global Sourcing** service |
| **Coilcraft MA5532-AE** (antenna) | C5361233 | **0** | Also Global Sourcing only. Generic 100 uH power inductors are in stock but are not antennas |

What Global Sourcing means here:

- **You need to be signed in.** JLC buys the parts into its warehouse first, and they can only be
  used in an assembly order, never shipped loose.
- **It adds time.** Expect a week or two before the parts arrive.
- **It adds fees.** JLC charges handling and, for some categories, inspection fees. I put
  *est.* $10 per order in the table below.

The AS3935 support circuit (datasheet, I2C, regulator off on the 3.0-3.6 V supply) is small:

- **Supply:** 1 uF on VDD/VREG and 10 uF on ACG.
- **Antenna tank:** about 1 nF C0G across the coil, minus the chip's own 0-120 pF trim, plus a
  few-kΩ resistor that sets Q to about 15.
- **I2C:** the existing bus pull-ups serve it, and the AS3935 is a QFN-16 (4 x 4 mm).

All of those passives are Basic-class.

### Cost, Economic PCBA top side (*est.*)

JLC fits the SHT40, BMP580, AS3935, MA5532-AE and passives. You hand-solder J1 and J3 or J4.
The four Extended parts cost 4 x $3.07. The AS3935 is priced at about $10.36 each (about $9 at
10) and the coil at about $2.

| | 5 boards | 10 boards |
|---|---|---|
| All-soldered rev1, JLC charges *est.* + J1/J3/J4 parts | **about $118** (about $24/board) | **about $182** (about $18/board) |
| rev0 option (c) + hand parts + DFRobot AS3935 module (Rs 2359) + BMP280 module (Rs 31), at Rs 88/$ | about $173 (about $35/board) | about $326 (about $33/board) |

The saving comes almost entirely from replacing the Rs 2359 DFRobot module with a $10 chip and a
$2 coil.

### Problems to settle before redesigning

- **AS3935 placement.** Design sheet §3.5 put the module under the screen cap, deliberately far
  from the PMS fan motor. On Board B the coil would sit about 10-15 mm above the PMS on the other
  side of the board.
  - It probably works. The PMS is power-gated (5V_AQI) and runs only briefly, so firmware can
    put the AS3935 in power-down, or ignore its interrupts, while the fan runs.
  - Keep the coil at the top edge, away from J1's cable entry, with no copper pour under it.
  - The datasheet's named noise sources are inductor DC-DC converters and displays; Board B has
    neither.
- **Antenna tuning is now yours.** Firmware must run the TUN_CAP routine (count IRQ at
  500 kHz/16 on Board A), which the DFRobot module made someone else's job.
- **BMP580 instead of BMP280** means a firmware driver change. Otherwise it is a better part.
- **The outline does not shrink.** 58 x 70 mm is set by the PMS on the back and the screen
  rails (design sheet §1). What shrinks is the BOM and the connector count.
- **Keep one escape hatch.** Leave the Qwiic footprint (S4) on the board, unfitted. If a chip
  goes out of stock later, a module can still go on.
- **Cheaper still, if Global Sourcing is a hassle.** Buy the AS3935 and coil yourself and
  hand-solder them; the 0.65 mm-pitch QFN-16 is easier with hot air than the SHT40's DFN-4.
  JLC then fits only the SHT40, BMP580 and passives (option (c) plus about $9).

## Follow-up 2: the trimmed board (2026-11-16)

This supersedes the all-soldered rev1 above: the AS3935 stays a DFRobot module under the cap.

**The board:**

- SHT40 on the tongue, as now.
- One soldered pressure sensor.
- One connector for the DFRobot lightning module's cable.
- J3 for the PMS7003 on the back, as now.
- J1 to the box, as now.
- 4 fallback pads.
- Nothing else.

### Pressure sensor pick: Bosch BMP580

> **Correction (live quote, 2026-11-16):** JLC lists the BMP580 as **"Standard Only"**, so the Economic
> cost below, with JLC fitting the BMP580, is not possible. See "Live JLCPCB quotes" further down:
> either hand-solder U2 on an Economic order, pay about $45-56 more for Standard, or swap to an
> Economic-eligible part such as the TE MS5607 (C97627).

**BMP580 (C22391138).** On lcsc.com today: 11,281 in stock, $1.21 each, $1.01 at 10+. JLC's own
warehouse has 11,321, so JLC can fit it straight from stock.

- **Package:** LGA-10, 2 x 2 mm, with no visible leads, so let JLC fit it; it is not a
  hand-solder part.
- **Supply:** 1.71-3.6 V, so it runs straight from VBAT.
- **I2C:** CSB to VDDIO selects I2C. SDO to GND gives address 0x46, clear of the SHT40's 0x44.
- **Firmware:** it needs the BMP5 driver; the BMP280 driver will not work.
- **Upgrade:** the BMP581 (C5362283, $2.32, 10,835 in stock) is the same Bosch family and LGA-10
  2 x 2 footprint.

Rejected:

| Part | Why not |
|---|---|
| BMP280 | Zero stock at JLC |
| BMP388 | $6.83 |
| DPS368 | $4.13 |
| LPS22HH | $6.67 |
| MS5611 | $6.14 |
| ICP-10111 | 88 in stock |
| SPL07-003 | $0.88 and 24k in stock, but a Goertek part with less of a track record |
| Tokmas clones | Unknown quality |

### Lightning connector: one JST PH 5-pin instead of S5 + S7

**JST B5B-PH-SM4-TB (C265085).** SMD vertical, $0.30, 28,091 in stock. Pins: VBAT, GND, SCL,
SDA, IRQ. The right-angle version is S5B-PH-SM4-TB (C265104, 6,559 in stock).

The cable to the cap is custom whatever you do. A single locking PH plug at the board end, split
at the module end into a Gravity 4-pin plug plus the IRQ wire, is one connector instead of two.

### Fallback: 4 pads, unfitted

Use a 1 x 4, 2.54 mm SMD header footprint (the hanxia part already in the library), left unfitted.

- **Pin order:** VBAT, GND, SCL, SDA, the order most GY modules use, so one could plug straight
  in.
- **Placement:** in a corner, clear of the 2.5 mm rail keep-outs and the PMS outline. SMD pads keep
  the back flat.

### What goes, what stays

**Deleted:** S1-S7, R3-R6, JP1-JP3.

- **J1, J3:** unchanged.
- **R1, R2:** keep the 10 k bus pull-ups, without the jumper.
- **R7, R8:** stay unfitted.
- **Decoupling:** 100 nF each at U1, the BMP580 and the PH connector; 10 uF at J1.
- **J4 (PMS5003):** user's call. Its footprint is already routed and costs nothing left unfitted.

### Cost (Economic PCBA, top side; JLC fits U1, BMP580 and the passives)

| | 5 boards | 10 boards |
|---|---|---|
| JLC charges | $36.37 | $48.56 |
| Hand parts: J1, J3, PH-5 (JLC prices) | $2.57 | $5.14 |
| **Total** (DFRobot modules extra, as before) | **$38.94** | **$53.70** |
| rev0 option (c) + its hand parts + BMP280 modules, same basis | $38.93 | $58.12 |

At 5 boards it costs the same as rev0, and $4 less at 10. The gain is not money:

- **Fewer things to fail:** 7 sockets and 4 Extended part lines fewer.
- **Nothing to choose at build time.**
- **No module stock-hunting** for T, RH or P.

## Live JLCPCB quotes, trimmed Board B (2026-11-16)

**Quote basis**

- **Files:** quoted from the trimmed board's export, `board-b-rev0-gerber-2026-11-13.zip` (as
  regenerated 2026-11-16), plus the matching BOM and CPL.
- **Gerber set used:** to get the zip into the quote page, I uploaded only the copper, mask,
  paste, outline and drill layers. Silkscreen, the drill drawing and EasyEDA's flying-probe JSON
  were left out; none of them changes the price. Upload the full zip when actually ordering.
- **What JLC read:** a 2-layer board of 70 x 58 mm.
- **PCB options:** FR-4 TG135, 1.6 mm, green, white silkscreen, OSP (JLC's current default),
  1 oz, tented vias, flying-probe test, 2-day build.
- **Not signed in:** no coupons are applied.
- **"Live"** means read off cart.jlcpcb.com today, shipping to India.

### (a) Bare PCB: live

| | 5 boards | 10 boards |
|---|---|---|
| PCB, web price | **$4.00** | **$5.00** |
| PCB, JLCONE desktop-app price | $2.00 | from $3.00 |
| 24-hour build instead of 2 days | +$7.60 | +$7.60 |
| Weight | 0.19 kg | 0.26 kg |

Shipping to India (live). None of these options is DDP, so Indian duty and IGST come on top,
collected by the courier.

| Method | 5 boards | 10 boards | Transit |
|---|---|---|---|
| E-POST (up to 1.5 kg and $150 declared value) | **$8.00, cheapest** | $10.14 | 10-18 business days |
| UPS Worldwide Express Saver | $9.57 | **$9.57, cheapest** | 5-7 business days |
| DHL Express | **$25.31, fastest** | **$25.31, fastest** | 2-5 business days |
| FedEx Express | $26.80 | $26.80 | 6-7 business days |

| Bare PCB total, delivered to India before duty | 5 boards | 10 boards |
|---|---|---|
| Cheapest | **$12.00** (E-POST) | **$14.57** (UPS) |
| Fastest (24 h build + DHL) | **$36.91** | **$37.91** |

### Assembly quotes: live, signed in (2026-11-16)

**How these were quoted**

- **Account and flow:** read off JLC's own PCBA flow while signed in to Anish's account: quote page,
  BOM, placements, then "Quote & Order". Nothing was added to the cart or ordered.
- **Draft left behind:** the PCBA draft JLC auto-saved (`board-b-rev0-gerber`) is still in the
  account.
- **Terms:** a "We've updated our Terms" privacy and marketing pop-up appeared and was left
  unanswered.
- **BOM and CPL:** JLC-format copies of the repo files, one BOM per option.
- **Prices:** in USD, before coupons and before Indian duty and IGST.

#### Two things the live quote changed

1. **OSP finish blocks Economic PCBA.** With the default OSP finish, JLC greys out Economic ("The
   PCB specs you chose are not supported for Economic PCBA"). Every assembled quote below therefore
   uses **lead-free HASL**, which adds $1.20 at 5 boards and $1.30 at 10 to the PCB.
2. **The BMP580 (U2) is "Standard Only" at JLC.** JLC's reason: "Due to limits in package (0201),
   temperature and other certain conditions, this part is only available for Standard PCBA
   service." Economic PCBA cannot place U2 at all, so it has two kinds of quote:
   - **Economic** quotes (b, c) leave U2 for you to hand-solder.
   - **Standard** quotes (b', c', d) include U2. They pay the $25.75 Standard setup, a larger
     stencil, a feeder fee on every part line, and an X-ray charge ($8.25 at 5 boards, $16.50 at
     10). Standard also adds edge rails, because the board is under 70 x 70 mm.

#### PCB and PCBA totals (live)

| Option | What JLC fits | 5 boards | 10 boards |
|---|---|---|---|
| (a) Bare PCB, OSP | nothing | **$4.00** | **$5.00** |
| (a) Bare PCB, lead-free HASL | nothing | $5.20 | $6.30 |
| **(b) Economic, top** | U1, R1-R2, C1-C3, C8 (**not U2**) | **$27.36** | **$36.70** |
| **(c) Economic, top** | (b) + J1 (THT) + J2 (**not U2**) | **$36.42** | **$48.11** |
| (b') Standard, top | U1, **U2**, passives | $71.91 | $92.45 |
| (c') Standard, top | U1, **U2**, passives, J1, J2 | $79.43 | $102.31 |
| **(d) Standard, both sides** | everything incl. U2 and J3 on the back | **$132.56** | **$156.47** |

Every total includes the PCB: $5.20 at 5 boards, $6.30 at 10 (lead-free HASL).

**(b) Economic, U1 + passives**

| Line | 5 boards | 10 boards |
|---|---|---|
| Setup | 8.24 | 8.24 |
| Stencil | 1.55 | 1.55 |
| Components | 9.14 | 16.24 |
| Extended-part fee (U1) | 3.09 | 3.09 |
| SMT assembly | 0.14 | 0.29 |
| Nitrogen reflow (added by JLC at 10) | n/a | 0.99 |
| **PCBA** | **22.16** | **30.40** |

**(c) Economic, adds J1 and J2**

| Line | 5 boards | 10 boards |
|---|---|---|
| Setup | 8.24 | 8.24 |
| Stencil | 1.55 | 1.55 |
| Components | 10.78 | 19.51 |
| Extended-part fee (U1, J2) | 6.18 | 6.18 |
| SMT assembly | 0.20 | 0.41 |
| Hand-soldering labour (J1) | 3.61 | 3.61 |
| Manual assembly | 0.66 | 1.32 |
| Nitrogen reflow | n/a | 0.99 |
| **PCBA** | **31.22** | **41.81** |

**(b') Standard top, U1 + U2 + passives**

| Line | 5 boards | 10 boards |
|---|---|---|
| Setup | 25.75 | 25.75 |
| Stencil | 8.27 | 8.27 |
| Components | 15.84 | 26.81 |
| Feeder loading | 7.75 | 7.75 |
| SMT assembly | 0.35 | 0.56 |
| X-ray | 8.25 | 16.50 |
| Packaging | 0.50 | 0.51 |
| **PCBA** | **66.71** | **86.15** |

**(c') Standard top, everything on top**

| Line | 5 boards | 10 boards |
|---|---|---|
| Setup | 25.75 | 25.75 |
| Stencil | 8.27 | 8.27 |
| Components | 17.48 | 30.07 |
| Feeder loading | 9.30 | 9.30 |
| SMT assembly | 0.41 | 0.68 |
| Hand-soldering labour | 3.61 | 3.61 |
| Manual assembly | 0.66 | 1.32 |
| X-ray | 8.25 | 16.50 |
| Packaging | 0.50 | 0.51 |
| **PCBA** | **74.23** | **96.01** |

**(d) Standard, both sides**

| Line | 5 boards | 10 boards |
|---|---|---|
| Setup (double-sided) | 51.50 | 51.50 |
| Stencil (double-sided) | 16.54 | 16.54 |
| Components | 18.42 | 31.95 |
| Feeder loading | 10.85 | 10.85 |
| SMT assembly | 0.49 | 0.85 |
| Hand-soldering labour | 3.61 | 3.61 |
| Manual assembly | 0.66 | 1.32 |
| PCB assembly fixture | 16.54 | 16.54 |
| X-ray | 8.25 | 16.50 |
| Packaging | 0.50 | 0.51 |
| **PCBA** | **127.36** | **150.17** |

Notes on the quotes:

- **Part quantities:** in Economic, JLC charged exact quantities. In Standard it charged minimums:
  25 x 100 nF, 20 x 10 uF and 20 x 10 k at 5 boards.
- **Build times quoted:**
  - PCB: 2 days.
  - Assembly: Economic 1-3 days; Standard 3-5 days (2-3 days for +$49.63 on (b')).
- **Faster PCB for assembly orders:** the quote page also offers "24 hours, PCBA Only" for the PCB
  at $0.00 on assembled orders.

#### Delivered to India (cheapest and fastest)

- **Bare-PCB shipping is live** (section above).
- **Assembly shipping is an estimate.** I read JLC's India rates at matching weights from the PCB
  quote page; the actual courier price is only fixed at checkout.
- **Weights from the assembly quotes:** 0.35-0.56 kg at 5 boards, 0.59-0.99 kg at 10.
- **Rates at those weights:**
  - UPS Worldwide Express Saver: $9.57 at 0.55 kg, 0.83 kg and 1.19 kg alike, 5-7 business days.
    It is the cheapest for every assembled option.
  - DHL Express: $25.31 at the same weights, 2-5 business days. It is the fastest.
  - E-POST is no longer cheaper at these weights: $9.81 at 0.55 kg, $19.65 at 0.83 kg.

| Option | 5 boards cheapest (UPS) | 5 boards fastest (DHL) | 10 boards cheapest (UPS) | 10 boards fastest (DHL) |
|---|---|---|---|---|
| (a) bare, OSP | $12.00 (E-POST) | $36.91 (24 h build) | $14.57 | $37.91 (24 h build) |
| (b) Economic, U1 + passives | **$36.93** | $52.67 | **$46.27** | $62.01 |
| (c) Economic, + J1, J2 | **$45.99** | $61.73 | **$57.68** | $73.42 |
| (b') Standard top, + U2 | $81.48 | $97.22 | $102.02 | $117.76 |
| (c') Standard top, all top | $89.00 | $104.74 | $111.88 | $127.62 |
| (d) Standard, both sides | $142.13 | $157.87 | $166.04 | $181.78 |

The assembly rows are estimates in the shipping part only; Indian duty and IGST are extra
throughout.

#### What it means

- **Having JLC fit the BMP580 costs about $45 at 5 boards and $56 at 10**, comparing (b') with (b).
  That pays for the Standard setup, stencil, feeders, X-ray and packaging.
- **The back side (J3) costs another $53-54** ((d) against (c')). That covers the double-sided
  setup, the double stencil and the fixture, for a $0.19 connector.
- **J1 + J2 cost about $9 at 5 boards and $11 at 10** ((c) against (b)), including $3.61
  hand-soldering labour for J1. Those are two easy hand-solder joints.

**Cheapest sensible build: (b), Economic, $27.36 for 5 or $36.70 for 10 (about $37-46 delivered).**
You then hand-solder J1, J2, J3 and **U2**.

The catch is U2. The BMP580 is an LGA-10, 2 x 2 mm, with no leads showing. It can be done with
hot air, paste and a good eye, but it is the hardest joint on the board.

**If you would rather not hand-solder U2, swap it for a sensor JLC lists as "Economic and
Standard"** (checked on each part page today):

| Part | LCSC | Package | Price @1 | Stock | Note |
|---|---|---|---|---|---|
| TE MS5607-02BA03 | C97627 | 5 x 3 mm SMD | $4.38 | 3,253 | Proven barometer, 1.8-3.6 V, I2C |
| TE MS5611-01BA03 | C15639 | 5 x 3 mm | $6.14 | 4,456 | Higher-resolution sibling |
| Tokmas BMP388 / DPS368 clones | C54582187 / C55090144 | 2 x 2 / 2 x 2.5 LGA | $1.58 / $2.16 | 8k / 10k | Clones of unknown long-term stability |

Also "Standard Only": BMP581, BMP585, Bosch BMP388, Infineon DPS368, SPL07-003, LPS22HH,
ICP-10111, BME280.

Moving to a MS5607 keeps Economic at roughly (b) + $3.09 extended fee + $4.38 per board
(*est.* about $52 for 5). That is still well under (b'). It is a footprint and firmware change,
and the layout session's call.

**Other things to check before ordering:**

- **J2 footprint name:** it reads `CONN-SMD_5P-P2.00_B6B-PH-SM4-TB-LF-SN` ("5P" and "B6B" in one
  name). JLC matched the 5-pin part and the placement export has 7 pads (5 + 2 tabs), so it is
  probably only a naming slip, but confirm it in EasyEDA.
- **Leave J4, J5, R7 and R8 out of the uploaded BOM.** If they are in the placement file, JLC
  ignores them as unplaced.

## Swap U2 to an Economic-eligible part: TE MS5607-02BA03 (2026-11-16)

**Part:** TE MS5607-02BA03 (`MS560702BA03-50`), LCSC **C97627**.

**JLC listing (live):**

- PCBA type: "Economic and Standard".
- Class: Extended.
- Stock: 3,253 at JLC.
- Price: $4.38 each at 1, $3.88 at 10+, $3.58 at 30+.

**Datasheet:** TE, rev 06/2017.

### Is it fit for a weather station?

| Spec (datasheet) | Value | For Board B |
|---|---|---|
| Full-accuracy range | 300-1100 mbar (linear 10-1200) | Covers every surface pressure, including stations up to about 3 km |
| Absolute error, no calibration | ±1.5 mbar at 25 °C (700-1100 mbar); ±2.0 mbar over 0-50 °C | Fine after a one-time offset check against a nearby IMD or airport reading |
| Error after a one-point offset | ±0.5 mbar at 25 °C; ±1.0 mbar over 0-50 °C | Good enough for station and sea-level pressure |
| Resolution | 0.024 mbar RMS at OSR 4096 | Far finer than the 0.1 hPa weather reports use; trends are clean |
| Long-term stability | ±1 mbar per year | Re-check the offset once a year |
| Operating temperature | -40 to +85 °C | OK in a Stevenson screen |
| Reflow shift | +0.4 mbar, about 66 % recovered after 7 days | Calibrate the offset a week or more after assembly |
| Supply | 1.8-3.6 V, 100 nF on VDD | Runs straight from VBAT (LiFePO4 3.0-3.6 V) |
| I2C | PS pin to VDD selects I2C. Address bit = complement of CSB: 0x76 with CSB to VDD, 0x77 with CSB to GND. CSB must not float | No clash with the SHT40 at 0x44 |
| Package | 5.0 x 3.0 mm, 8 pads, stainless-steel cap | Visible side metallisation, easier to inspect than the BMP580's LGA |

Assembly notes from the datasheet:

- **No washing.** Cleaning might damage the sensor, so use no-clean paste and do not pick JLC's
  "Board Cleaning" option.
- **Keep dust out of the opening** during assembly.

### Power

| State | Current (datasheet, VDD 3 V) |
|---|---|
| Standby | **0.02 µA typ, 0.14 µA max** at 25 °C |
| One reading per second, OSR 4096 | 12.5 µA average |
| One reading per second, OSR 1024 | 3.2 µA average |
| During a conversion | 1.4 mA peak, 8.22 ms at OSR 4096 |

One OSR-4096 reading per minute averages about 0.2 µA plus standby. That is noise next to Board
B's other loads (the 470 µA baseline under investigation is elsewhere).

### Supply risk

- **DigiKey:** lists the part "Active", but out of stock with a 22-week factory lead time.
- **element14:** marks it no longer stocked.
- **JLC:** holds 3,253, plenty for this board. Buy the boards' worth now rather than relying on it
  later.
- **Fallback:** the MS5611-01BA03 (C15639, $6.14, 4,456 in stock, also Economic) is the same
  family and pin-out class, with higher resolution.

### Cost with the MS5607 (*est.*: option (b) live, plus the MS5607 at its live price)

| | 5 boards | 10 boards |
|---|---|---|
| (b) Economic + MS5607: U1, U2, passives | **about $52.40** | **about $78.70** |
| (c) Economic + MS5607, + J1, J2 | about $61.50 | about $90.10 |
| (b') Standard with the BMP580, for comparison (live) | $71.91 | $92.45 |
| (b) Economic, BMP580 hand-soldered, for comparison (live, BMP580 bought separately) | $27.36 + about $6 | $36.70 + about $12 |

Shipping to India: about $9.57 by UPS on top of every row; Indian duty is extra.

- **Against Standard with the BMP580:** the swap saves about $19.50 at 5 boards and $13.80 at 10,
  and needs no X-ray or edge rails.
- **Against hand-soldering the BMP580:** it costs about $19-30 more. That is the price of not
  hand-soldering a 2 x 2 mm LGA.
- **Why the saving is modest:** the MS5607 itself is $3.9-4.4 a piece, against $1.2 for the
  BMP580.

**Layout and firmware change**

- **Footprint:** U2 becomes the MS5607 footprint. Pins: VDD, PS, GND, CSB, CSB, SDO, SDI/SDA,
  SCLK; check the datasheet pin table.
- **Straps:** PS to VDD, CSB to VDD (address 0x76), SDO left unconnected in I2C mode.
- **Decoupling:** 100 nF at VDD.
- **Firmware:** an MS5607 driver. It reads the PROM coefficients C1-C6, checks the CRC-4 (AN520),
  and does the second-order temperature compensation.

### Live re-quote with the MS5607 (2026-11-17)

**Basis**

- **Files:** the refreshed fab files with U2 = MS5607 (C97627), at (45.001, 55.499) mm, top
  side, 0°.
- **Gerber set:** copper, mask, paste, outline and drills; silkscreen and drawings left out, which
  doesn't change the price.
- **PCB options:** lead-free HASL, Economic PCBA, top side.
- **Account:** signed in. Nothing was added to the cart.

**Result:** JLC accepted the MS5607 on Economic, with no "Standard Only" flag and no X-ray line.

| Option (Economic, top side) | 5 boards | 10 boards |
|---|---|---|
| **(b) U1, U2 (MS5607), R1-R2, C1-C3, C8** | **$53.35** | **$78.74** |
| **(c) (b) + J1 (hand-solder service) + J2** | **$62.40** | **$90.14** |

**(b), line by line**

| Line | 5 boards | 10 boards |
|---|---|---|
| PCB | 5.20 | 6.30 |
| Setup | 8.24 | 8.24 |
| Stencil | 1.55 | 1.55 |
| Components | 31.06 | 55.05 |
| Extended-part fee (U1, U2) | 6.18 | 6.18 |
| SMT assembly | 0.21 | 0.42 |
| Nitrogen reflow (added by JLC) | 0.91 | 0.99 |
| **Total** | **53.35** | **78.74** |

**(c), line by line**

| Line | 5 boards | 10 boards |
|---|---|---|
| PCB | 5.20 | 6.30 |
| Setup | 8.24 | 8.24 |
| Stencil | 1.55 | 1.55 |
| Components | 32.69 | 58.32 |
| Extended-part fee (U1, U2, J2) | 9.27 | 9.27 |
| SMT assembly | 0.27 | 0.54 |
| Hand-soldering labour | 3.61 | 3.61 |
| Manual assembly | 0.66 | 1.32 |
| Nitrogen reflow | 0.91 | 0.99 |
| **Total** | **62.40** | **90.14** |

- **The 10-board quotes used yesterday's Gerber draft** with this same BOM. That draft lost its
  Gerber link before the 5-board re-run. Price depends only on size, layers, finish and BOM, all
  identical, and the (c) result at 10 matched the estimate to $0.04.
- **Build time:** the PCB showed "24 hours" at no charge on the assembly order; assembly 1-3 days.
- **Delivered to India** (UPS $9.57 at these weights, the cheapest; DHL $25.31, the fastest;
  duty extra):

| Option | 5 boards, UPS | 10 boards, UPS | 5 boards, DHL | 10 boards, DHL |
|---|---|---|---|---|
| (b) | about $62.92 | about $88.31 | about $78.66 | about $104.05 |
| (c) | about $71.97 | about $99.71 | about $87.71 | about $115.45 |

- **Against Standard with the BMP580 ((b'): $71.91 / $92.45):** the MS5607 on Economic saves
  $18.56 at 5 boards and $13.71 at 10. Nothing is left for you to hand-solder except the
  connectors, and there is no X-ray, edge rails or Standard setup.
- **Still yours to hand-solder:** J1, J2 (in (b)) and J3.
