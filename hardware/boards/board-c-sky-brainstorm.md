# Board C — the eye (sky-vision hardware)

**Status:** open debate, nothing decided (opened 2026-11-03). No board exists; no camera
has been bought. This sheet argues the *visual* member of the family before anyone opens
EasyEDA, and it argues against itself in §9, where the honest answer to "does a camera
improve the forecast?" is *less than you'd hope, and not where you'd expect*.

**Board C is the free letter.** A is core, B is environment, D is wind (§6 of
[../architecture.md](../architecture.md)); C was never allocated. The eye gets it.

Two prior decisions bound everything here, and one of them is overturned below:

- [`cloud/docs/insight-roadmap.md` §6](../../cloud/docs/insight-roadmap.md) — the sky-vision
  track (LCL cloud base shipped; vision-LLM observer, classical CV, MLX90614 thermopile
  queued), with the power note: **"cameras belong on coordinators."**
- The uplink contract **already exists and already works** (§1). Nothing in the cloud needs
  to change for a camera to start posting today.

The overturned one is "cameras belong on coordinators". It is right about the energy and
wrong about the siting: cameras belong wherever there is **a view and a fat pipe**, which is
usually a *host's roof*, and almost never a ridge where a leaf wants to be (§8).

---

## 1. What the cloud already accepts — the contract is built

Read before designing anything, because it removes most of the design space:

| Fact | Where | Consequence for Board C |
|---|---|---|
| `POST /stations/{slug}/frames`, multipart, **JPEG only**, **≤ 5 MB** | [`cloud/api/app/ingest.py`](../../cloud/api/app/ingest.py) | The node needs an HTTP client and a JPEG. That is the whole uplink spec. |
| Auth = the **station's own bearer key** (admin key also accepted, for the simulator) | same | A camera is a station. No new auth path, no new key type. |
| `?ts=ISO` sets capture time, explicitly "used by backfill" | same | **Store-and-forward is already supported server-side.** A node may upload a frame hours late and the timelapse still lands on the right day. This is the single most important line in the file. |
| Frames land at `frames/<slug>/<date>/<HHMMSS>.jpg`; daily job encodes 24 fps mp4 | [`jobs/timelapse.py`](../../cloud/api/app/jobs/timelapse.py) | Cadence, not resolution, decides whether the timelapse reads well. |
| `StationCreate.sensors` defaults to `0` | `ingest.py` | **A camera-only station is already legal.** No schema change to register an eye with no instruments. |
| `FRAME_RETENTION_DAYS = 14`; timelapses kept forever | [`jobs/retention.py`](../../cloud/api/app/jobs/retention.py), [`config.py`](../../cloud/api/app/config.py) | ⚠️ See the fuse in §1a. |
| Simulator renders **640×360** every **180 s** | [`cloud/simulator/skycam.py`](../../cloud/simulator/skycam.py) | The dashboard's layout was built against that. Match it for the uploaded frame; keep anything larger on the card. |

### 1a. The quiet asset is on a 14-day fuse — fix this before buying a camera

The insight roadmap calls the archive of sky frames paired with simultaneous sensor
readings "the quiet asset", the substrate that later trains cheap local methods. Retention
deletes every raw frame at **14 days**. The timelapse mp4 survives, but a 24 fps mp4 is not
a training set — frames are re-compressed, re-stamped, and no longer joinable to a
`readings` row by timestamp.

So the asset currently self-destructs a fortnight after it is created, and nobody will
notice for a year.

Arithmetic for the fix, per camera, at 3-minute daylight cadence (240 frames/day, ~30 kB each):

| Policy | Volume | Verdict |
|---|---|---|
| Keep everything forever | 7.2 MB/day → **2.6 GB/yr** | ×5 cameras breaks a small droplet's disk |
| Keep **one frame per hour** forever, drop the rest at 14 days | 0.7 MB/day → **0.26 GB/yr** | ✅ the labeled-pairs dataset survives at a cost nobody will feel |
| Keep every frame within ±30 min of an alert/report/lightning event | small, bursty | ✅ worth adding — the interesting minutes are exactly the ones retention eats |

**Recommendation: a `FRAME_KEEP_HOURLY` exemption in `retention.py` before the first real
camera ships.** Pure cloud work, no hardware, and it is the cheapest item in this document.

---

## 2. Pixels on the LoRa mesh — the arithmetic, corrected 2026-11-03

**Correction to the first draft of this sheet**, which computed a raw PHY rate of 1.76 kbps
from `Rb = SF × BW/2^SF × CR` at SF9/BW125. That is roughly the physics behind the module's
slowest setting, but it is **not the knob**. The E220 does not expose SF and BW at all. It
exposes a **labelled air data rate in the SPED register (02H)**, and
[Ebyte's own range is 2.4 kbps to 62.5 kbps](https://ebyteiot.com/products/e220-900t22-5km-long-distance-communication):
codes `000`/`001`/`010` all select **2.4 kbps (the default and the floor)**, then 4.8k, 9.6k,
19.2k, 38.4k, and `111` = 62.5k
([register table](https://pypi.org/project/ebyte-lora-e220-rpi/0.0.2); the sibling
[E220-900T22S manual](https://manualshive.com/en/manual/ebyte/e220-900t22s/530503?page=5)
agrees, and notes both ends must match).

So the floor is **2400 bps**, and — far more interestingly — **there is a 26× ceiling above
it that the first draft never considered.**

### 2a. Seven settings, and what each one costs

A 640×360 JPEG at q70 is ~30 kB = 245,760 bits. Bulk-transfer efficiency derated to ~65 %
for the module's 3-byte fixed-mode header, sub-packet framing, AUX handshaking and UART
flow control:

| SPED | Air rate | Airtime, one 30 kB frame | ≈ SF/BW behind it **[verify — Ebyte does not publish the mapping]** | Sensitivity | Range vs floor |
|---|---|---|---|---|---|
| `010` | **2.4k** (default) | **≈ 157 s** | SF9/BW125 | **−129 dBm** (LLCC68's quoted peak) | 1× |
| `011` | 4.8k | ≈ 79 s | SF8/BW125 | ~−126 | ~0.7× |
| `100` | 9.6k | ≈ 39 s | SF7/BW125 | ~−123 | ~0.5× |
| `101` | 19.2k | ≈ 20 s | SF7/BW250 | ~−120 | ~0.4× |
| `110` | 38.4k | ≈ 10 s | SF7/BW500 | ~−117 | ~0.3× |
| `111` | **62.5k** | **≈ 6 s** | SF5–6/BW500 | ~−111 to −114 | **~0.15–0.3×** |

The sensitivity column is the whole story. LLCC68's rated peak is
[−129 dBm at SF9/BW125](https://lora-alliance.org/wp-content/uploads/2020/07/S68F_SPECEN_Ver.A.pdf),
and ~2.5 dB is lost per SF step. Floor to ceiling is **≈ 17–19 dB** — which at a terrain path-loss
exponent of 3–4 is **three to eight times less range**, and LLCC68 at wide bandwidth is
anecdotally *worse* than its datasheet: one tester reports
[packets dropping above −110 dBm at BW500/SF7](https://forum.lora-developers.semtech.com/t/llcc68-poor-sensitivity/1480).
Also note LLCC68 is the cost-reduced part with **restricted SF/BW combinations** (roughly
SF7–9 at BW125, SF7–11 at BW500), so the mapping above is constrained, not free.

> **Small frames are preamble-dominated, bulk transfers are not.** A 20-byte sky-feature
> frame costs ~0.39 s regardless of the labelled rate, because preamble and header dominate —
> consistent with architecture §5's documented 0.52 s leaf report. Divide by the labelled rate
> only for bulk payloads; for short frames, use symbol math. Both figures in this sheet are
> computed that way.

### 2b. The missing layer: any image transfer needs ARQ, delta or not

At the module's 200-byte sub-packet, a 30 kB image is **154 packets**. Probability that all
of them arrive:

| Per-packet loss | 1 % | 2 % | 5 % |
|---|---|---|---|
| P(complete image) | **21 %** | 4.5 % | 0.04 % |

FLP is explicitly fire-and-forget with one retry, idempotent server-side, on the stated
principle that "losing one costs a data point, not correctness"
([PROTOCOL.md](../../firmware/PROTOCOL.md) §2). **An image is the first payload in this system
for which that premise is false.** Before any compression question, image-over-LoRa needs a
chunked transfer with selective retransmission — a missing-chunk bitmap in the ACK and a
resend pass. That is the actual prerequisite, and it is a bigger job than the codec.

### 2c. Delta frames with periodic sync — what the idea does and doesn't buy

It is a real technique (this is MPEG's I/P structure), it would work, and the gain is
**2–4×, not 10×** — concentrated in exactly the conditions where you need it least. The
arithmetic, because it is not obvious:

**How fast does a sky frame decorrelate?** Cloud base 1500 m, drift 20 km/h (5.6 m/s), 100°
horizontal FOV. The frame spans 2 × 1500 × tan 50° ≈ 3575 m at cloud level, so a 640 px wide
image pans at **≈ 1 px/s**:

| Frame spacing | Cloud displacement | Inter-frame correlation |
|---|---|---|
| 180 s (routine cadence) | ~180 px = **28 % of frame width** | poor — beyond naive differencing |
| 30 s | 30 px = 4.7 % | good |
| **10 s (event burst, TLV 0x08)** | 10 px = **1.6 %** | **excellent** |

That single table sets the design rule. **Clouds decorrelate in minutes, so a delta against
a 3-minute-old reference is nearly a full frame — but a delta inside a 10-second burst is
almost free.**

Four more things the idea runs into, two of them fatal and two of them fixable:

- **JPEG does not subtract.** DCT coefficients shift wildly under small changes and the
  entropy coding is context-dependent, so you must decode the reference (640×360 RGB565 =
  460 kB — fine in the XIAO's 8 MB PSRAM), difference in the pixel domain, and re-encode a
  residual that is high-frequency and noise-like, which is the signal JPEG handles *worst*.
- **AEC/AWB drift makes every pixel differ.** Two frames 3 min apart differ *everywhere*
  from exposure and white-balance hunting alone. Fixable, and worth fixing regardless:
  **lock exposure and white balance**, which the R/B-ratio cloud metric (§4a) needs anyway
  for photometric consistency. Then deadband the residual.
- **Error propagation.** Chained deltas mean one lost packet corrupts every frame until the
  next sync — on a link where §2b shows loss is near-certain. Fixable: delta against the
  last *acknowledged* sync frame rather than the previous frame, so a loss is contained to
  one image. The cost is that savings then decay as the sky diverges from that sync — per
  the table above, to nil within ~10 minutes.
- **Convection is the worst case and the important case.** Cumulus grows and dissipates on
  1–5 minute timescales, so residuals are largest exactly during the weather worth
  photographing. Delta coding is most efficient on calm, boring skies.

**The part of the idea that is unambiguously good, and should be done regardless:** the
camera is *fixed*, so send a **static-region mask once** and transmit only the sky ROI
thereafter. No inter-frame dependency, no error propagation, no codec work. And the saving
is better than its pixel share — a detailed ridge line is high-frequency and therefore
*expensive* in JPEG while smooth sky is cheap, so masking a third of the pixels may remove
**40–50 % of the bytes**. Spatial delta, not temporal; all of the benefit, none of the risk.

**And the better fit for routine cadence than delta: progressive/layered encoding.** Send a
base layer (~3 kB), then refinement layers while the channel stays idle. Each layer is
independently useful, so a lost layer *degrades* the image instead of corrupting it — which
is FLP's own reliability philosophy applied to pixels, and it means whatever airtime happens
to be available yields a usable frame.

### 2d. Verdict — and the one mode where pixels on the mesh genuinely work

Compression does not repeal the airtime arithmetic. A twenty-leaf mesh reporting every five
minutes puts ~125 s/hour on the channel; one image at the default 2.4k costs **157 s**, or
~300 leaf reports. Even a generous 4× saving leaves one hourly image eating a quarter of the
mesh's existing traffic. **Compression moves routine imagery from impossible to merely
expensive; it does not make it possible.**

What *does* work is the combination the first draft missed — **high air rate plus
compression plus a scheduled window**:

> 30 kB → ~12 kB (static mask + progressive base layer) at **62.5 kbps ≈ 2.5 s of airtime** —
> a leaf-report-class transaction.

The reason this matters is subtler than speed. The coordinator must **retune to 62.5k to
receive**, going deaf to the 2.4k mesh for the duration. At 157 s that deafness is
unacceptable; at **2.5 s** it is schedulable between leaf report windows. So compression's
real purchase is not bandwidth — it is **bounding how long the coordinator can afford to
look away.** Pair it with the burst TLV (§4a) and delta coding earns its keep precisely
where the decorrelation table says it should: 60 frames at 10 s intervals, one sync and 59
cheap deltas, ~5–10× on the burst that matters most.

The price is the 17–19 dB in §2a, so this is a **short-link mode**: the camera must be near
the coordinator, or on terrain where 868 MHz at SF5–6 still beats 2.4 GHz ESP-NOW LR through
foliage — a real niche, and a narrow one. Where that doesn't hold, §4's WiFi and LTE paths
remain better than any codec.

**Revised conclusion, which is still the hinge of this document:** the mesh carries numbers
as a matter of course, and pixels only as a **negotiated, rate-switched, compressed
exception** — never as routine traffic. The camera's picture path and its measurement path
remain separate instruments, which is the partition in §3.

---

## 3. The partition: a sky *sensor* and a sky *picture* are two different instruments

They share a lens and nothing else. Designing them as one device is what makes sky cameras
expensive and fragile.

| | **Sky sensor** | **Sky picture** |
|---|---|---|
| Output | ~20 B of features, every 5–10 min | 30–180 kB JPEG, every 2–5 min (daylight) |
| Audience | the divergence detector, `/skill`, the forecast | humans, the timelapse, the LLM observer, the archive |
| Path | **LoRa, via the existing mesh and coordinator** | WiFi / LTE / ESP-NOW — never LoRa |
| If the pipe is down | nothing lost; it rides the mesh | **store on microSD, backfill later via `?ts=`** |
| Latency it needs | minutes | hours is fine |
| Computed where | on the node (§4a) | nowhere; the droplet does the thinking |

The consequences are good ones. A sky node with *no internet at all* still contributes
cloud fraction, motion, fog and a snow reading to the forecast over LoRa, and hands over its
pictures whenever a pipe appears — or when someone walks up the hill with a phone hotspot.
A sky node with internet and no LoRa (the common case, §8) contributes pictures immediately
and features via a tiny HTTP post instead. Neither half blocks the other.

### 3a. One layout, two variants — the depopulated-corner trade, again

Board A rev 2 already debates whether one board with a DNP corner beats two revisions
([board-a-rev2-brainstorm.md](board-a-rev2-brainstorm.md)). For Board C the answer is
clearly yes, because the two variants differ only in the power and radio corner:

- **C-mains ("roof eye")** — USB-C 5 V in, WiFi uplink, no battery, no solar, no E220, no
  CN3801. Populated: MCU + camera + microSD + window heater FET. **~₹2,200.** This is the
  variant to build first, and probably the only one that ever ships in quantity.
- **C-solar ("ridge eye")** — adds the leaf's proven corner verbatim: CN3801, LFP cells,
  TPS61023 gated rails, E220 + antenna, protection row. **~₹5,500–6,500.** For a site with
  a view and no power.

Reusing Board A's power corner *as drawn* is the point. One charger design to understand,
one cell type to stock — the same argument architecture §4 makes for the coordinator's
backup pack.

---

## 4. Uplink options, costed

| Path | Throughput | Energy / 30 kB frame | ₹ | When it is the answer |
|---|---|---|---|---|
| **WiFi (2.4 GHz) to an existing AP** | Mbps | **~0.2 mAh** (connect + TLS + POST ≈ 5 s @ ~140 mA) | ₹0 (on-module) | ✅ **Default.** Any host roof, any coordinator site. |
| **LTE Cat-1, A7670C, gated** | 5 Mbps up | **~0.5 mAh** (cold attach 5–15 s + TX) | ₹450–1,700 module ([bare](https://www.theengineerstore.in/products/a7670c-gsm-4g-breakout-board-adiy) / breakout) + SIM | A ridge with 4G and nothing else. Band fit for Jio/Airtel **[verify the export variant's band list — the R5 part is a China-market SKU]** |
| **ESP-NOW long-range to the coordinator** | ~200 kbps gross, [plan on 100–200 kbps usable](https://developer.espressif.com/blog/esp-now-for-outdoor-applications/); [~500 m through trees, ≤1 km LOS](https://atomic14.com/videos/posts/oz0a7Ur7nko) | ~0.3 mAh (≈ 2–3 s on air) | ₹0 | A camera **within sight of the coordinator** but with no AP of its own. 2.4 GHz, not the LoRa channel — the mesh never notices. |
| **LoRa (pixels), 2.4k default** | 2.4 kbps labelled | — | — | ❌ Never — 157 s/frame, ~300 leaf reports' airtime (§2a). |
| **LoRa (pixels), 62.5k + compression, scheduled** | 62.5 kbps labelled | ~0.05 mAh (≈ 2.5 s on air) | ₹450–650 (E220) | ⚠️ **A real but narrow mode** (§2d): costs 17–19 dB of link budget, needs a chunked-ARQ layer that does not exist, and makes the coordinator deaf to the mesh while it runs. Only where the camera is close *and* 2.4 GHz is dead. |
| **LoRa (features)** | 20 B/frame | 0.028 mAh | ₹450–650 (E220) | ✅ Always, where a leaf's radio is already justified. |
| **Sneakernet (microSD, collected on a visit)** | ∞, eventually | 0 | ₹200 | The honest fallback, and `?ts=` already supports it. Not a plan. |

**Gate the LTE modem, do not trust its PSM.** A7670C-class idle in PSM is ~1–3 mA; at 2 mA
continuous that is 48 mAh/day — as much as the entire rest of the node. A cold attach costs
~0.5 mAh and happens 48 times a day for 24 mAh/day. **Powering the modem off between
uploads beats keeping it registered by 2×**, and it keeps architecture §3's law intact: an
unpowered radio is an RF-quiet radio.

Data volume: 30 kB × 48/day = **43 MB/month** at 15-min cadence; **216 MB/month** at 3-min.
The right product is an M2M SIM, whose tariff is not published — Jio and Airtel quote these
per enterprise account. **[verify: get a quote; consumer prepaid data packs are cheap but
play validity games that will silently kill a station in month four]**

### 4a. FLP type 0x04 — SKY (proposed)

Types 0x01–0x03 and 0x10 are taken; **0x04 is free**. Same 8-byte envelope, ~20 B payload,
comfortably inside the 56 B budget:

| field | enc | note |
|---|---|---|
| `cloud_frac` | u8 | 0–100 %, 255 = invalid (night, blinded, wet lens) |
| `cloud_frac_opaque` | u8 | thick vs thin split — the R/B threshold gives both for free |
| `sky_class` | u8 | 0 clear · 1 few · 2 scattered · 3 broken · 4 overcast · 5 fog · 6 precip · 7 night |
| `motion_u`, `motion_v` | i16 ×10 | px/min, image frame. Absolute velocity needs a cloud base — the LCL estimate already on the station page supplies one |
| `motion_conf` | u8 | block-match confidence. **Low in overcast *and* in clear sky** — both documented failure modes (§9) |
| `mean_lum` | u16 | exposure-normalised sky brightness |
| `rb_ratio` | u16 ×1000 | red/blue — the all-sky-imager standard for decades |
| `horizon_vis` | u8 | ridge-edge contrast ÷ clear-day baseline → **a visibility proxy for free** |
| `snow_stake_cm` | u8 | if a painted stake is in frame (§6c). 255 = no stake / not readable |
| `lens_state` | u8 | 0 clear · 1 droplets · 2 frost · 3 dirty · 4 spider. **Every other field's QC flag** |
| `frames_pending` | u16 | how many images are waiting on the SD card — tells the cloud the backhaul is sick |

And one new ACK TLV, since the downlink already exists and is otherwise idle:

| TLV | payload | meaning |
|---|---|---|
| `0x08` | `u8 n · u8 interval_s` | **burst capture**: take `n` frames `interval_s` apart, full resolution, upload when you can |
| `0x09` | `u8 sped_code · u16 window_ms` | **rate-switch window** (only if §2d is ever built): both ends move to the SPED air rate for `window_ms`, then fall back to 2.4k unconditionally on timeout. The unconditional fallback is the whole safety story — a camera that mis-hears this TLV must not be able to strand itself at 62.5k, mute to a mesh it can no longer reach. |

That TLV is the cheapest interesting thing in this document. A leaf reports lightning
(type 0x02, sent promptly) or a pressure crash; the coordinator fires `0x08` at every sky
node in the valley; a cloudburst gets photographed at 10-second intervals from three
angles by hardware that was asleep ninety seconds earlier. No sensor does that alone, and
it costs one byte of protocol.

---

## 5. Camera hardware, costed

| Option | Sensor | ₹ (India, qty 1) | Verdict |
|---|---|---|---|
| **ESP32-CAM (AI-Thinker)** | OV2640 2 MP | 400–600, Robu | **Buy two to burn.** Proves the pipeline this week. Then never deploy it: poor PCB antenna, no load-switch anywhere, and the brownout behaviour that is *already* the recurring leaf failure mode. |
| **[XIAO ESP32S3 Sense](https://www.electronicscomp.com/seeed-studio-xiao-esp32s3-sense-24ghz-wi-fi-ble-50-ov2640-camera-sensor-digital-microphone-battery-charge-supported-rich-interface-iot-embedded-ml)** | OV2640 2 MP + microSD | **1,450–1,750** | ✅ **Recommended for rev 0.** 8 MB PSRAM, microSD on board, 21×17.5 mm, **castellated** — solders onto a Forsyth-drawn carrier exactly as the coordinator's WROOM-1 does. Bare-XIAO deep sleep ~14 µA; the Sense expansion's camera and SD do **not** sleep usefully, so the carrier must gate that rail. **[verify gated sleep current on the bench — this is the one number that decides C-solar]** |
| **ESP32-S3-WROOM-1 (bare) + OV5640** | 5 MP, autofocus | 450–700 + 900–1,500 | The rev 1 answer. **Same module the coordinator already uses** — one RF-matched footprint, one toolchain, one set of debugged quirks. Costs a DVP bus (8 data + 5 control at ~20 MHz) through a hand-routed board. |
| **[Arducam Mega 5 MP SPI](https://www.digikey.in/en/products/detail/arducam/B0401/19116501)** | 5 MP, JPEG on-chip | **~5,250**, 5-week lead | Technically the most elegant: 4-wire SPI, JPEG out of the sensor, no PSRAM, MCU-agnostic. **Rejected on cost and lead time** — it is three XIAOs. Revisit if an all-sky node ever needs a non-ESP32 host. |
| **Pi Zero 2 W + Camera Module 3 / fisheye + dome** | IMX708 / IMX179 | ~2,500 + 2,800 + dome | **The coordinator-site instrument.** True 180° all-sky, and long night exposures read cloud against stars — which is the night coverage the MLX90614 was queued to buy. Costs 0.6–1.5 W *continuous* (~20 Wh/day ⇒ mains, or a 40–60 W solar install) and puts a Linux SD card on a Himalayan mast. Read-only rootfs + hardware watchdog, or don't. |
| **Consumer WiFi IP camera + a snapshot puller** | varies | 2,000–3,500 | Ugly, not ours, and **the correct answer for a host's roof today.** Zero engineering, mains+WiFi, 24/7. Two caveats that matter: confirm RTSP/ONVIF works with the vendor cloud *disabled* (otherwise the host's roof is streaming to Shenzhen), and note that **night IR-cut switching destroys every colour-based cloud metric** — such a camera is a picture source, not a sensor. |
| **MLX90614 zenith thermopile** | — | 300–500 | Not a camera and not on this board — insight-roadmap V3, Board B. Kept in view because §9 concludes it **outperforms any camera here on forecast value per rupee.** |

---

## 6. The window, the aim, and the heater — what actually decides whether this works

More sky cameras are ruined by their window than by their sensor. Droplets, dust, spiders,
condensation, and UV-hazed acrylic, in roughly that order.

### 6a. Flat tilted glass, not a dome — for rev 0

| | Dome (180° all-sky) | **Flat glass, 15–30° from horizontal, 100–120° lens** |
|---|---|---|
| Droplets | sit on it; needs a blower or heater | **run off** |
| UV at 2,000 m+ | acrylic yellows in a season; glass dome is pricey | flat glass is cheap and **replaceable as a consumable** |
| Condensation | fogs the whole hemisphere; needs continuous watts | one small heated pane |
| Framing | zenith — beautiful, and the wrong half of the sky | **the ridge sits in the bottom third of frame** |

That last row is the real argument. A ridge line in frame gives, free: a visibility and fog
reference (`horizon_vis`), a geometric anchor for cloud-motion vectors, a snow-line reading,
and something a human recognises as *their* valley. Zenith gives a prettier timelapse and
less information. **Aim at the valley's weather-approach azimuth**, accept ~2 h/day of sun
flare, and log the sun's azimuth so the CV job knows which frames to distrust.

### 6b. The heater is the dominant load — budget it as such

A 1.5 W window heater on a gated rail draws ~450 mA cell-referred. **10 min/day = 75 mAh/day;
30 min/day = 225 mAh/day** — one to three times *everything else on the node combined* (§7).
So: gate it hard (the TPS61023 `EN`-pin trick Board A already uses), trigger it only on
`lens_state ∈ {droplets, frost}` or RH > 95 %, cap it with a daily energy budget in firmware,
and let it lose to the camera when the battery is low. The heater is why C-solar wants 5 W of
panel where a leaf wants 1–2 W.

### 6c. Two near-free mechanical additions, both worth more than a sensor upgrade

- **A painted snow stake in frame** — ~₹200 of wood and paint. It makes the camera the
  *only* snow-depth instrument in the system, and operational networks do exactly this:
  [WebSnow](https://austria-in-space.at/en/projects/2017/websnow.php) validates satellite
  snow cover against ski-resort webcams at ~15-minute cadence, and a Finnish study pairing
  cameras with ultrasonic sensors reported 72–94 % accuracy. **Highest value per rupee in
  this entire document.**
- **Desiccant + a Gore-type vent**, with an indicator visible without opening the box —
  straight from the leaf enclosure practice.

---

## 7. Power budget — methodology per architecture §5

Cell-referred at VBAT ≈ 3.3 V. **Every figure below is datasheet arithmetic, not bench
measurement** — the same caveat Board A rev 2 carries, and it applies harder here because
the XIAO Sense's gated sleep current has never been measured.

### Per-frame cost (capture + features + WiFi upload)

| Phase | Current | Time | mAh |
|---|---|---|---|
| OV2640 + S3 @80 MHz, AEC/AWB settle + capture | ~115 mA | 1.5 s | 0.048 |
| On-node feature computation (§4a) @240 MHz | ~60 mA | 1.0 s | 0.017 |
| WiFi: associate + TLS + POST 30 kB | ~140 mA avg | ~5 s | 0.195 |
| **Per frame** | | | **≈ 0.26** |

JPEG is produced *in the sensor*, so there is no software encode term — one of the better
reasons to prefer OV-series DVP over a raw sensor.

### Daily total

| Term | mAh/day | Note |
|---|---|---|
| 240 frames (3-min cadence, 12 daylight hours) | **62** | |
| Sleep @ ~25 µA (camera **and SD** rails gated) | 0.6 | **[verify — ungated, the SD alone can idle at 0.2–1 mA, i.e. 5–24 mAh/day]** |
| Feature frames over LoRa, 10-min cadence (144 × 0.028) | 4 | only on C-solar |
| **Subtotal, no heater** | **≈ 67** | ≈ 0.22 Wh/day |
| Window heater, 10 / 30 min/day | +75 / +225 | **the swing term** |
| **With a realistic monsoon heater duty** | **≈ 140–290** | ≈ 0.5–1.0 Wh/day |

### Sizing C-solar

- **Cells:** 2 × LFP 32700 (6 Ah) — the holder change rev 2 already wants to try. **26 days**
  autonomy at the heavy heater figure, **90 days** without. Comfortable, which is the point:
  a camera that browns out is worse than no camera, because it browns out in the weather you
  wanted photographed.
- **Panel:** 1.0 Wh/day ÷ (0.5 effective peak-sun-hours in monsoon overcast × 0.6 system
  efficiency) ⇒ **≥ 3.3 W**. Specify **5 W, 6 V-class** (V_MP ≈ 6 V — 5 V panels sag into the
  CN3801's UVLO, per BOM). ₹400–700.
- Against a leaf: this node is **3–8× a leaf without the heater, 10–20× with it.** Real, and
  entirely affordable on 5 W. The leaf programme loses nothing — which is the condition §10
  attaches to building any of this.

---

## 8. Siting — decouple the eye from the station (the one real reversal here)

"Cameras belong on coordinators" is right that a capture-and-upload costs orders of
magnitude more than a LoRa burst. It is wrong that the coordinator is therefore where the
camera goes, because it quietly assumes a camera must be co-sited with Forsyth hardware.
It needn't be:

1. **Leaves and eyes want opposite sites.** A leaf wants exposure, wind-cleanliness, and
   distance from buildings. An eye wants a view, a roof, mains, and WiFi. Forcing them onto
   one mast compromises both.
2. **The forecast-relevant content is the *view*, not the co-location.** Cloud motion over
   the ridge and visibility down the valley do not care whether a BME280 is bolted below.
3. **The cloud already allows camera-only stations** (`sensors: 0`, §1). No code to write.
4. **The hosts are already in the schema** — `contact_name`, `contact_phone`, `installed_on`.
   The social machinery for "someone's roof" exists.
5. **For a camera-only, mains-powered, WiFi node the entire LoRa question evaporates**, and
   with it the solar, the charger, the cells, the gating, and the protection row. ₹2,200
   against ₹6,000, and a week of work against a month.

So: **a sky-node census distinct from the leaf census.** Five roof eyes across a valley —
each with a logged lat/lon, view azimuth and elevation — beat one heroic solar ridge eye on
coverage, on cost, on reliability, and on the date of first light. The ridge eye is still
worth building, for the site that has the view no roof has; it is just not the first one.

**Metadata a sky node needs that a leaf doesn't:** view azimuth, view elevation, horizontal
FOV, and a clear-day reference frame per camera (the baseline every contrast metric divides
by). None of that exists in `stations` yet — the smallest schema change this track implies.

---

## 9. How relevant is any of this to forecasting? — ranked, and honestly

The literature on ground-based sky imagery is mature, because solar-power forecasting has
funded it for fifteen years. It is worth reading *before* buying, because it is clear about
both the win and its boundaries.

### Tier 1 — things nothing else in Forsyth can do

1. **Cloud motion ⇒ a 15–60 minute nowcast.** This is the real prize, and the consensus is
   consistent: sky-imager forecasts are strongest *intra-hour*, with 15 minutes the typical
   sweet spot, because NWP and satellite products are
   [simply inadequate at that resolution](https://escholarship.org/content/qt5813b9j0/qt5813b9j0_noSplash_3acf69b58908ccb5243bdb6281009f95.pdf).
   Forsyth has **no sub-hour instrument of any kind** and sits in a valley the white paper
   already concedes has no usable radar. A camera is the only sub-hour instrument the budget
   can reach.
   The boundaries are equally well documented: the horizon is a function of cloud height and
   speed; error grows monotonically with lead time; multi-layer cloud breaks single-vector
   extrapolation; and motion vectors fail **in overcast and in near-clear skies both** — which
   is why `motion_conf` is in the payload rather than implied.
   And a valley-specific amplification: a camera aimed *up-valley* at an approaching cloud
   wall yields "that wall is 4 km out, moving 20 km/h" — twelve minutes of lead that a human
   reads off the picture with **no CV at all.** The cheapest useful version of this feature
   is a photograph on a web page.
2. **Precipitation type, and the tipping bucket's snow blindness.** A tipping bucket
   under-reports frozen precipitation badly. Forsyth's entire thesis is scoring forecasts
   against local truth — so a winter of silently wrong truth doesn't just lose data, it
   **poisons the `/skill` record and any bias correction built on it.** A camera (plus the
   stake in §6c) closes a measurement hole in the asset the project is actually accumulating.
   This is the strongest *honest* argument for a camera, and it is not a forecasting argument.
3. **Fog and visibility.** Directly measurable as ridge contrast against a clear-day
   baseline; nothing in the BOM measures it; RH near 100 % is only a hint. Little forecast
   skill, and the highest operational value in the system for anyone judging a mountain road.

### Tier 2 — real, modest

4. **Daytime cloud fraction as a divergence input.** Cloud cover is among a global model's
   weakest fields, and divergence — not prediction — is Forsyth's actual mechanism. "The
   model says overcast; the sky is clear" is a legitimate, cheap addition to the detector
   that already exists. This is the best *architectural* fit of anything in this document.
5. **The labeled archive.** Sky frames + simultaneous sensors + what happened next, for two
   seasons, in a radar-void Himalayan valley. Genuinely rare, zero forecast value today, high
   option value — and currently deleted every 14 days (§1a).

### Tier 3 — the honest nulls, stated so nobody has to rediscover them

6. **Night: a visible camera is blind.** The ₹400 MLX90614 beats a ₹5,000 camera for night
   cloud, outright. **Do not let the camera displace the thermopile from Board B.** (A Pi
   fisheye reading cloud against stars is the one exception, and it needs mains.)
7. **Cloud base height: a single camera cannot measure it.** The LCL estimate already shipped
   gives it for free from sensors every station has. Stereo parallax from two cameras on a
   known baseline is a research project, not a feature.
8. **Beyond roughly an hour, sky-imager skill is poor against NWP** — explicitly so in the
   literature. The camera therefore contributes to the banner's *observed* and *divergent*
   tenses and **never to the expected tense.** Advertising otherwise would be the one claim
   in this project that couldn't survive the white paper's own standards.
9. **Rain rate, wind, pressure, temperature: the camera adds nothing.** The existing sensors
   are better at all four.

### The blunt summary

> **Per rupee, per watt, and per hour of bench time, a camera's forecast contribution is
> modest and almost entirely confined to the first hour.** Its real returns are a winter
> measurement hole closed, fog and visibility made visible, public credibility, and an
> archive that doesn't exist anywhere else for these valleys.
>
> If the *only* goal were forecast skill, a ₹400 thermopile and a second leaf would beat any
> camera on this page, and it isn't close.
>
> Build the camera anyway — but build the **₹2,200 mains+WiFi roof eye**, for the view and
> for the record, and don't let it cost the leaf programme a single watt. "Trust the sky, not
> the model" is the project's own slogan; a station that shows people the sky is making an
> argument no chart can.

---

## 10. What I'd build, in order

Items 0–2 need no board at all.

0. **Fix the retention fuse** (§1a). Cloud-only, an afternoon, and it stops the asset from
   expiring. Do it before buying hardware.
1. **Buy an ESP32-CAM (₹500) and prove the whole path on the bench this week**: capture →
   `POST /frames` with a station key → frame on the station page → nightly timelapse. The
   contract is already live and the simulator is already exercising it, so this is a day's
   work and it retires every integration risk in this document.
2. **Point it out of a window for a fortnight** and look at what the *optics* do — flare,
   droplets, dawn exposure, IR-cut if any. Every remaining decision in §6 is settled by two
   weeks of ugly frames, and none of it by more reading.
3. **One XIAO ESP32S3 Sense (₹1,500) in a box with a tilted glass pane and a painted stake**,
   on a roof with mains and WiFi (§8). This is C-mains in prototype form. First real sky data,
   first snow-depth reading, ~₹2,500 all-in.
4. **Then the classical-CV job** (insight roadmap V2) against frames that actually have a
   ridge, a stake and real droplets in them — not against the simulator's synthetic sky.
   Feature extraction moves onto the node only once the cloud version works and the numbers
   are known to be worth sending.
5. **Draw Board C** — one layout, the depopulated corner of §3a — only when a roof eye has
   run through one monsoon and one winter. By then the window, the aim, the heater duty and
   the real sleep current are all measured instead of estimated.
6. **C-solar, and FLP 0x04** — the ridge eye, for the view no roof has. Last, because it is
   the most engineering for the least marginal sky.

## 11. Open items

- **[verify]** XIAO Sense deep-sleep current with camera + SD rails gated. Decides whether
  C-solar is a 2-cell or 4-cell design.
- **[verify]** A7670C export-variant band list against Jio and Airtel. The R5 SKU is
  China-market.
- **[verify]** M2M SIM tariff from Jio or Airtel Business — unpublished; needs a call.
- **[verify]** 865–867 MHz delicensing notification as it currently stands (§2 assumes ERP
  limits but no duty-cycle limit).
- **[verify]** The SPED air-rate → SF/BW → sensitivity mapping in §2a. Ebyte publishes the
  labelled rates and a single headline sensitivity, not the correspondence; the whole
  high-rate argument in §2d rests on a 17–19 dB estimate that should be measured on the
  bench with an attenuator before anyone designs around it.
- **[decide]** Build the chunked transfer + selective-ARQ layer at all? §2b shows every
  image path over LoRa needs it, and it is the one piece of work in this sheet that
  changes FLP's stated reliability model rather than extending it. If the answer is no,
  §2d closes permanently and the LoRa radio on C-solar carries only features — which is
  a perfectly good outcome, and should be chosen deliberately rather than by default.
- **[decide]** Is `horizon_vis` calibrated per camera against a stored clear-day frame in the
  cloud, or on the node? Cloud is easier and loses the ability to send the feature over LoRa
  when the pipe is down.
- **[decide]** Does the sky node get its own `stations` metadata (view azimuth/elevation/FOV)
  or a separate `sky_nodes` table? §8.
- **[decide]** Dome or flat glass, after step 2 above — not before.
- **Unresolved tension:** a Pi fisheye at the coordinator would read cloud at night and make
  the MLX90614 partly redundant, at ~20 Wh/day and a Linux SD card on a mast. The thermopile
  is ₹400 and needs nothing. Probably both, eventually, for different sites — but not before
  one of them has run a winter.

---

**Sources consulted for this sheet** (dated 2026-11-03, prices qty 1, INR, unverified against
live stock): DigiKey India (Arducam Mega
[B0401](https://www.digikey.in/en/products/detail/arducam/B0401/19116501) ≈ ₹5,251,
[B0436](https://www.digikey.in/en/products/detail/arducam/B0436/19116510) ≈ ₹5,650) ·
[ElectronicsComp](https://www.electronicscomp.com/seeed-studio-xiao-esp32s3-sense-24ghz-wi-fi-ble-50-ov2640-camera-sensor-digital-microphone-battery-charge-supported-rich-interface-iot-embedded-ml)
and [CheapestInIndia](https://www.cheapestinindia.com/price-history/seeed-studio-xiao-esp32s3-sense-24ghz-wi-fi-ble-50-ov2640-camera-sensor-digital-microphone-8mb-flash-8mb-psram-rich-interface-battery-charging-supported-iot-embedded-ml--66abfd983cd01a5a2063e095)
(XIAO Sense ≈ ₹1,463–1,750) · [The Engineer Store](https://www.theengineerstore.in/products/a7670c-gsm-4g-breakout-board-adiy)
and [Quartz Components](https://quartzcomponents.com/products/sim-a7670c-4g-lte-cat-1-gsm-development-board-with-lm39302-power-ic-v1-1) (A7670C) ·
[Espressif on ESP-NOW outdoors](https://developer.espressif.com/blog/esp-now-for-outdoor-applications/)
and [atomic14's walk test](https://atomic14.com/videos/posts/oz0a7Ur7nko) ·
[UCSD total-sky-imager intra-hour forecasting](https://escholarship.org/content/qt5813b9j0/qt5813b9j0_noSplash_3acf69b58908ccb5243bdb6281009f95.pdf) ·
[Assessment of sky-camera and satellite nowcasting methods](https://www.sciencedirect.com/science/article/abs/pii/S0306261921003354) ·
[DLR blended ASI/satellite/persistence model, 2025](https://elib.dlr.de/219406/1/202511_EnhancingIntra%E2%80%90HourSolarIrradianceForecastingForSolarApplicationsABlendedModelOSatelliteSkyImagerAndPersistence_Nouri.pdf) ·
[WebSnow (webcam snow validation)](https://austria-in-space.at/en/projects/2017/websnow.php) ·
[Community Snow Observations](https://arc.lib.montana.edu/snow-science/item/2566).
