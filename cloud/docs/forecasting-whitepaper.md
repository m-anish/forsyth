# Forecasting in Forsyth: sources, method, and reasoning

**Version 1.0 · 2026-07-20 · status: living document.**
This paper describes, at implementation fidelity, how the Forsyth weather mesh
turns data into forecasts and warnings — what goes in, what the "algorithm"
actually is, what comes out, and *why* each decision was made. It is written to
be critiqued: every threshold is stated, every assumption is flagged, and the
known weaknesses have their own section. Corrections and challenges are welcome
as pull requests against this file; parameters marked ⚙ are tunable and their
values are opinions, not laws.

Companion documents: [insight-roadmap.md](insight-roadmap.md) (technical
phasing), [engagement-roadmap.md](engagement-roadmap.md) (the human side),
[../../research/competitive-landscape.md](../../research/competitive-landscape.md)
(hardware context). Implementation: `cloud/api/app/` — primarily
`jobs/forecast.py`, `forecast.py`, `summary.py`, `reports.py`.

---

## 1. Setting and constraints

Forsyth operates in Himalayan valley terrain near Dharamsala, Himachal Pradesh.
The design constraints, in order of influence:

1. **Global NWP is blind at valley scale.** The best operational models (ECMWF
   IFS at 9 km, GFS/ICON at 11–25 km) average a ridge, two valleys, and a
   2,000 m elevation span into one grid cell. They carry genuine skill at
   synoptic scale ("a western disturbance arrives Thursday") and none at the
   scale where decisions are made ("does *this* orchard get the hail").
2. **Radar exists but does not resolve the problem.** IMD has commissioned
   Doppler weather radars in Himachal (Kufri, Jot, Murari Devi) as part of a
   Himalayan expansion. This is materially better than nothing — but mountain
   radar suffers beam blockage and overshoot in precisely the valleys people
   inhabit, the imagery is published as pictures rather than a public data
   API, and the composite aggregators (e.g. RainViewer) have partial,
   advisory-grade coverage over the subcontinent. Design consequence: the
   system must be *useful with zero radar* and *better with some*.
3. **The mesh is small and its sensors are cheap.** A network of 3–50 stations
   built from ₹4–6k of parts cannot claim reference-grade absolute accuracy
   and must not pretend to (see §3.1 for what it *can* claim).
4. **Compute is one small VPS.** No GPUs, no model training pipelines. Any
   method must run in Python on a 1 GB droplet beside the database.
5. **Weather here escalates quickly.** Cloudbursts and flash floods are
   documented, recurring hazards in Himachal; the literature is unambiguous
   that their small spatial scale and short lead time defeat conventional
   forecasting. The honest goal is not to out-predict them but to *notice
   sooner* (§4.4).

From these constraints, four theses (the whole design is their consequence):

- **T1 — Localize, don't model.** A small mesh's edge is hyper-local truth,
  used to verify and correct free global forecasts, not to replace them.
- **T2 — Divergence is the alert.** When live observations contradict the
  model's expectation for *right now*, that disagreement is itself the most
  actionable short-horizon signal available without radar.
- **T3 — People sense what sensors cannot.** Hail size, snow line, a blocked
  road, a rising stream: crowdsourced reports fill the impact gap, if (and
  only if) they are quality-controlled and reputation-weighted.
- **T4 — The archive is the asset.** Storing every forecast next to every
  observation builds the training set for statistical correction — and the
  only dataset of its kind for these valleys.

## 2. Data sources

| Source | What | Cadence | Cost | Trust model |
|---|---|---|---|---|
| Forsyth stations | temp, RH, pressure, wind avg/gust/dir, rain, PM1/2.5/10, lightning (distance) | ~minutes | owned | §3.1 |
| [Open-Meteo](https://open-meteo.com) NWP | ECMWF IFS 0.25°, GFS "seamless", ICON "seamless", and its `best_match` blend; GEFS 0.25° ensemble | pulled every 3 h ⚙ | free (non-commercial) | §3.2 |
| Human reports | 7 kinds: rain, hail, fog, snow line, wind damage, road blocked, flood; optional 1–3 intensity, 140-char note | event-driven | free | §3.3 |
| *Planned:* IMD | district nowcast warnings, city forecasts (API key requested 2026-07-18); DWR imagery | — | free, registration-gated | overlay, not input, at first |
| *Planned:* MOSDAC / ISRO | INSAT-3D/3DR products; GSMaP-ISRO gauge-corrected rain (0.1°, hourly) | — | free, registration-gated | satellite-vs-mesh cross-check |

The forecast pull (`jobs/forecast.py`) makes exactly **two batched HTTP
requests per cycle regardless of station count**: one multi-model
deterministic call (hourly 2 m temperature, RH, surface pressure, 10 m
wind/gust/direction, precipitation, precipitation probability, cloud cover;
3 forecast days ⚙; station elevation passed for terrain downscaling) and one
GEFS ensemble call reduced immediately to per-hour mean and standard
deviation (members are not stored). Every run is kept for **730 days** ⚙ in a
`forecasts` hypertable whose columns deliberately mirror the observations
table, keyed by `(station, model, run_at, valid_at)` so that *lead time* —
`valid_at − run_at`, the dimension any correction scheme conditions on — is a
subtraction, not a schema migration.

## 3. Why these sources — the reasoning

### 3.1 Can cheap sensors be trusted?

Partially, and the design only leans on the part that can. The sensor suite
(SHTC3/SHT4x for temp/RH, BME280 for pressure only — a documented decision,
since its humidity element self-heats and reads warm outdoors; reed-switch
anemometer; tipping-bucket rain; Plantower PMS7003 particulates; AS3935
lightning) is consumer-grade. Known failure modes: radiation-shield error in
strong sun (afternoon temp reads high), tipping-bucket undercatch in intense
rain and wind, PMS7003 optical counting differing from gravimetric reference,
AS3935 giving distance without bearing.

The mitigations are structural rather than metrological:

- **Tendencies over absolutes.** The highest-value signals used anywhere in
  the pipeline are *changes* — 3-hour pressure fall, humidity jump, wind
  shift — which cancel static bias entirely. A barometer that reads 2 hPa low
  still measures a 3 hPa crash perfectly.
- **Coherence over calibration.** With multiple stations in one valley, a
  reading that disagrees with its neighbours *and* the forecast is suspect; a
  network-wide tendency is credible even if every absolute value is off.
- **Verification in public.** The `/skill` endpoint (§4.2) scores the
  *forecast* against the station — but the same join, read the other way,
  flags a station whose "errors" suddenly change character (drift, blockage).
- **No NIST cosplay.** Absolute-accuracy claims are explicitly not made
  (see the competitive landscape doc); Davis owns that market at 30× the
  price. Forsyth's claim is density and honesty, not traceability.

### 3.2 Why Open-Meteo (and not raw model feeds, or a commercial API)?

Open-Meteo provides, free for non-commercial use, exactly the four things
this design needs: multiple independent models at one endpoint (model
disagreement is information), ensemble members (uncertainty is information),
an elevation-aware downscaling of grid values to a point, and batched
multi-location queries (two calls serve the whole mesh — being a polite
free-tier citizen is a design requirement, not an afterthought). The
alternative paths — pulling ECMWF open data GRIBs directly, or a commercial
API — cost either engineering (GRIB decoding, storage, regridding on a 1 GB
box) or money, and add nothing at this scale. The dependency risk (terms
change, service dies) is contained by the schema: any point-forecast source
can fill the same table.

### 3.3 Why accept input from anonymous humans?

Because the operational precedents are unambiguous. NOAA's **mPING** has run
for over a decade on anonymous, one-tap precipitation-type reports and is
used to tune radar algorithms; **CoCoRaHS** feeds the US National Weather
Service from >20,000 volunteers; the UK Met Office's **WOW** demonstrably
infills gaps in the official network; and — the closest analogue —
**ICIMOD's community-based flood early warning systems** in the Hindu Kush
Himalaya raised warning lead times on the Karnali from 2–3 h to 7–8 h with
local observers and low-cost sensors. People reliably observe what no
affordable sensor measures: hail size, snow-line elevation, road and stream
state.

The known failure modes (spam, error, gaming) are handled mechanically, not
socially (§4.3): rate limiting without identity, inline cross-checking
against the nearest station, and a reputation that can only be earned by
being *reliably right about the weather* — which is the desired behavior, so
gaming it is indistinguishable from contributing.

### 3.4 What about radar, satellites, IMD?

Treated as *future overlays and cross-checks*, not current inputs, for three
reasons: access friction (IMD's API is registration-gated — key requested;
MOSDAC requires an account; DWR imagery has no public data API), coverage
honesty (composite radar over the subcontinent is partial), and dependency
ordering (the mesh-plus-NWP core must stand alone first; each external layer
then *adds* rather than props). The IMD district nowcast, once the key
arrives, will render as a warnings overlay — high credibility, zero coupling.

## 4. The method

### 4.1 Acquisition and storage

Described in §2. One convention matters for everything downstream:
Open-Meteo's hourly precipitation at time *t* is the accumulation for the
hour **ending** at *t*, while instantaneous fields (temperature, wind,
pressure) are valid **at** *t*. The schema stores them in one row per hour
and the verification join (§4.2) compensates.

### 4.2 Verification — `GET /stations/{slug}/skill`

Every stored forecast hour that has since come true is joined against the
station's hourly observation rollup:

- temperature: forecast at *t* vs the observed hourly average for the bucket
  starting at *t* (a deliberate ±30 min blur, documented in code);
- precipitation: forecast for the hour ending *t* vs rain summed in the
  bucket starting *t − 1 h* (exact alignment).

Pairs are grouped into **6-hour lead buckets** ⚙ and scored: temperature mean
bias and MAE; precipitation as a contingency table at **0.2 mm/h** ⚙ —
probability of detection (POD) and false-alarm ratio (FAR). These numbers are
*public, per station*, and surfaced on station pages ("past 30 days here:
temperature within ±2.1 °C about a day out; 85 % of rainy hours called in
advance"). The reasoning: a forecast product that shows its own error record
earns the trust it asks for — and this join *is* the future bias-correction
training query, so credibility and capability share one piece of SQL.

### 4.3 Human reports — QC and reputation

Reports are anonymous-first (friction kills reporting; mPING's design), rate
limited per HMAC of IP + user-agent (3 per 10 min, 20 per day ⚙ — no raw PII
stored), and cross-checked at insert against the nearest station within
**5 km** ⚙ heard from in the last **15 min** ⚙:

| Kind | Corroborated when | Contradicted when |
|---|---|---|
| rain | station rain > 0.2 mm in 30 min | station dry *and* intensity ≥ moderate |
| fog | station RH > 95 % | station RH < 70 % |
| wind damage | station gust > 10 m/s | — |
| hail, snow line, road, flood | no sensor rule — human-only truth | — |

A **contradicted report is stored, not rejected** — near a station it is a
signal that either the human or the sensor is wrong, and both cases are worth
knowing about. Signed-in reporters with **≥5 corroborated** and **≤25 %
contradicted** ⚙ over 90 days become *trusted observers*: their single report
of a severe kind (hail, wind damage, road blocked, flood) can raise the
banner alone, where anonymous reports need two independent voices within
25 km of the same station. Public coordinates are rounded to ~100 m.

### 4.4 The event engine — observed, expected, divergent, human

The summary engine (`summary.py`) detects events in four tenses. All
thresholds ⚙:

**Observed** (from live readings): lightning within the last hour; rain
> 2 mm/h; gusts > 10 m/s in 30 min; pressure falling > 2.5 hPa over 3 h
(30-min means, 3 h apart); PM2.5 > 90 µg/m³.

**Expected** (from the latest stored `best_match` run): rain — anchored to
the **first hour with > 0.5 mm** (probability alone must not start the clock,
else a 100 %-chance drizzle masquerades as an imminent downpour; the event
carries the 12 h total, the peak hourly amount, and the max probability as
separate, separately-labeled numbers); overnight minimum < 2 °C (frost);
24 h temperature range > 12 °C; gusts > 15 m/s within 24 h.

**Divergent** (T2, the honest nowcast): observed rain > 1 mm in the last
hour while the forecast for the covering hours says < 0.2 mm; observed 3 h
pressure fall exceeding the forecast's own 3 h trend by > 1.5 hPa. Phrased
in the product as it is meant: *"trust the sky, not the model."*

**Human** (§4.3): two same-kind reports near one station within 3 h, or one
corroborated/trusted severe report.

**Derived quantities** shown alongside: dew point (Magnus formula,
a = 17.62, b = 243.12) and estimated cloud base via the lifting-condensation
approximation **h ≈ 125 m × (T − T_d)** — a textbook estimate for convective
cloud base, presented with "(est.)" because it is one.

### 4.5 Composition — how events become sentences

Detected events are structured JSON. A language model (currently GPT-5.1,
optional) phrases them into one 20–30-word banner sentence under strict
instructions: `_expected` events must read as expectation, divergence means
the stations win, every number's meaning is spelled out in the prompt
(mm_12h is a total; probability is never "confidence"), and adjectives must
scale with the peak hourly amount. A deterministic rule-based composer
produces the same content when no LLM is configured, and is the fallback on
any failure — **the LLM only ever phrases; it never decides**. Responses are
cached 5 minutes per (station, language); Hindi is offered as a first-class
banner language. Every summary carries its generation timestamp, and the UI
degrades it honestly (a "may be stale" warning past 15 min, dimming past an
hour — reachable only when a service worker serves a cached summary offline).

## 5. Outputs

1. **The banner** — one sentence, four tenses, freshness-stamped, EN/हिं.
2. **`GET /stations/{slug}/forecast`** — the latest run, chart-ready, with
   ensemble spread; rendered as an hourly strip + temperature/precip chart
   with the model name and run age always displayed.
3. **`GET /stations/{slug}/skill`** — the public verification record (§4.2).
4. **Map layers** — stations (live values), lightning range rings, human
   report pins (age-fading, QC-badged), rain radar composite (advisory).
5. **CSV export** of all raw observations; the full API is public.
6. *Planned:* MQTT alert topics (`forsyth/alert/{station}`) for the
   divergence/nowcast engine — Phase C.

## 6. Known limitations (critique targets)

- **Short record.** Skill scores and the forthcoming bias correction need
  seasons, not weeks; until then `/skill` self-reports its pair count.
- **Rehearsal data.** Until physical stations deploy, observations are
  simulated (against real forecasts, at real coordinates) — the pipeline is
  exercised end-to-end, but no claims transfer to real skill.
- **Single-cell blindness.** All stations in one valley may share one NWP
  grid cell; model-relative statistics then measure the *cell's* error, not
  spatial structure within it. Density across valleys is the fix.
- **Thresholds are priors.** Every ⚙ value above was chosen by reasoning and
  literature, not fitted to local data. They should be revisited when a
  season of pairs exists.
- **The 60/25 km radii and planar distance math** are valley-scale
  approximations; fine for QC gating, wrong for anything geodetic.
- **Open-Meteo dependency** (terms, availability) — contained by schema, not
  eliminated.
- **LLM phrasing risk** — bounded by structured events and a deterministic
  fallback, but a wrong adjective is still possible; the prompt constraints
  in §4.5 exist because one was observed (a 12 h total read as a 1 h fall).

## 7. Roadmap for the logic

Near-term (see [insight-roadmap.md](insight-roadmap.md) for status):

- **Phase C — alerts as a channel**: a 10-minute nowcast job running the
  divergence + hazard heuristics (pressure crash, RH jump + wind shift,
  lightning distance trend), deduplicated in an `alerts` table, published
  over MQTT.
- **Phase D — statistical correction** (trigger: ~90 days of real pairs):
  per (station × model × lead-bucket × variable) rolling bias first — the
  mean bias `/skill` already computes — then, only if the numbers justify
  it, small regressors (features: lead, hour-of-day, season, ensemble
  spread). Literature on ML post-processing of NWP at stations reports
  20–30 % RMSE reduction; that is the realistic ceiling. Served as a
  `corrected` series beside the raw model, never replacing it.
- **Sky vision**: vision-LLM sky description from station cameras; classical
  red/blue-ratio cloud fraction and frame-to-frame cloud motion (buildup
  crossing the ridge is the valley's own nowcast); a painted snow stake; a
  zenith IR thermopile (MLX90614) for quantitative day/night cloud cover.
- **External layers**: IMD district warnings overlay (key requested);
  GSMaP-ISRO satellite rain vs mesh gauges as a standing cross-check.

Longer-term:

- **Analog forecasting** once the archive is deep: find historical days
  whose synoptic pattern + mesh state resemble today's, report what followed.
- **Dataset publication** (CC-BY proposed): dense valley observations paired
  with archived forecasts is precisely the dataset Himalayan nowcasting
  research lacks; publishing it is both a contribution and how a small mesh
  earns collaborators (IIT Mandi and ICIMOD work these exact problems).
- **MetNet-class assimilation** remains a *direction, not a build*: current
  research (station-densified neural forecasters, satellite+NWP nowcasting
  aimed at radar-sparse regions) indicates where the field is going; a
  50-station valley mesh's role in that future is as ground truth, which is
  what T4 has been accumulating since day one.

## 8. Reproducibility

The entire pipeline is open source (this repository), self-hostable via one
docker-compose file, and exercised end-to-end by a simulator that speaks the
real APIs. All observational data is public via the API and CSV export; all
thresholds are in code with the values stated here. To challenge a decision
in this paper: open a PR against this file, or against the threshold in code
— both are equally welcome.

## References

- mPING: Elmore et al., *BAMS* (2014) — [crowd-sourced precipitation-type reports](https://www.researchgate.net/publication/273656669_MPING_Crowd-Sourcing_Weather_Reports_for_Research)
- CoCoRaHS — [NOAA on citizen-science precipitation networks](https://www.noaa.gov/stories/story-map-citizen-science-and-power-of-crowd)
- Met Office WOW gap-infill: [*Hydrology Research* (2023)](https://iwaponline.com/hr/article/54/4/547/94226/Filling-observational-gaps-with-crowdsourced)
- ICIMOD community-based flood early warning: [CBFEWS](https://www.icimod.org/mountain/cbfews/)
- ML post-processing of NWP at stations: [Hieta et al., *Met. Apps* (2025)](https://rmets.onlinelibrary.wiley.com/doi/10.1002/met.70074); [Adaptive Bias Correction, *PNAS* (2023)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10272189/)
- Radar-sparse deep nowcasting: [Global MetNet (arXiv 2510.13050)](https://arxiv.org/html/2510.13050v1); [MetNet-3](https://research.google/blog/metnet-3-a-state-of-the-art-neural-weather-model-available-in-google-products/)
- Himalayan cloudburst prediction: [ANN, *Natural Hazards* (2025)](https://link.springer.com/article/10.1007/s11069-025-07374-1); [HP flash-flood GNN (arXiv 2603.15681)](https://arxiv.org/pdf/2603.15681)
- All-sky camera cloud methods: [low-cost sky camera, *Remote Sensing* (2020)](https://www.mdpi.com/2072-4292/12/9/1382); [segmentation benchmark, *Solar Energy* (2020)](https://www.sciencedirect.com/science/article/abs/pii/S0038092X2030147X)
- [Open-Meteo documentation](https://open-meteo.com/en/docs) · [IMD APIs](https://mausam.imd.gov.in/responsive/apis.php) · [MOSDAC open data](https://www.mosdac.gov.in/open-data)
