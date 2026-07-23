# Insight roadmap — from data to judgment

Written + Phase A implemented 2026-07-18. The dashboard's job so far has been to
show what the sky is doing. This document is the plan for the harder half of the
tagline: knowing what it will do — for Himalayan valleys where weather turns fast,
official infrastructure is thin, and the nearest reliable answer to "should I move
the apples under cover?" has historically been to look up.

## 1. The problem, honestly framed

Around Dharamsala (and most of the Indian Himalaya), the forecasting stack looks
like this:

- **Global models** (ECMWF, GFS, ICON) run at 9–25 km. A grid cell that size
  averages a ridge, two valleys, and a 2000 m elevation span. They are genuinely
  skillful at synoptic scale ("a western disturbance arrives Thursday") and
  genuinely blind at valley scale ("your valley gets 40 mm of it").
- **IMD** has been closing the radar gap — Doppler radars now sit at Kufri, Jot,
  and Murari Devi in HP, with district-level nowcast warnings behind a
  registration-gated API. But mountain radar suffers beam blockage in exactly
  the valleys people live in, and a district-level warning is still not a
  valley-level answer.
- **Commercial apps** (Windy, AccuWeather et al.) are re-presentations of the
  same global models. None of them have a thermometer in the valley.

Forsyth is the inverse: nothing but thermometers in the valley. A mesh of 3–50
stations will never out-model ECMWF and should not try. What it can do — uniquely —
is four things:

1. **Hyper-local truth.** The mesh knows what actually happened, hour by hour,
   at points no model resolves.
2. **Verification and correction.** Free model output, joined against local
   truth, yields per-valley skill scores ("here, the model runs 2 °C warm and
   misses a third of rain hours") and eventually per-station bias correction.
   This is what WeatherFlow's cloud "Nearcast" does; nobody does it self-hosted.
3. **Divergence detection.** When the stations contradict the model *right now* —
   rain falling that was never forecast, pressure crashing faster than modeled —
   that disagreement is itself the warning, and it is available hours before any
   external product notices. In cloudburst country this is the honest, achievable
   version of "early warning": not predicting better, noticing failure faster.
4. **Human ground truth.** People see hail size, snow-line height, a blocked
   road, a rising stream — things no sensor in the BOM measures.

Every phase below is one of those four, in order of leverage.

## 2. What exists as of Phase A (2026-07-18)

- `jobs/forecast.py` pulls open-meteo point forecasts for every sited station
  every 3 h (two batched HTTP calls per cycle regardless of station count):
  four deterministic models (`best_match`, `ecmwf_ifs025`, `gfs_seamless`,
  `icon_seamless`) plus GEFS ensemble reduced to mean ± spread (`ens_gefs`).
- **Every run is kept** in the `forecasts` hypertable (2-year retention,
  `FORECAST_RETENTION_DAYS`). Columns mirror `readings`; lead time is
  `valid_at − run_at`. The archive of (lead, forecast, observed) triples is the
  project's long-term dataset — it starts accruing the day this deploys, even
  with simulated stations.
- `GET /stations/{slug}/forecast` serves the latest run (uPlot-shaped);
  `GET /stations/{slug}/skill` publishes forecast-vs-observed verification per
  lead bucket — the "show your work" endpoint. The station page and the
  `forecast` board widget render both.
- The summary banner now speaks in three tenses: observed events, `*_expected`
  events from the stored forecast (rain within 12 h, frost, big swings, wind),
  and `model_divergence` when the gauges contradict the model.

## 3. Phase B — human reports (mPING for the valley) — ✅ shipped 2026-07-18

*The people side of Phase B — accounts, reputation, tiers, outreach — has its
own document: [engagement-roadmap.md](engagement-roadmap.md).*

Shipped as designed below (`app/reports.py`, `dashboard/js/report.js`): the
"report the sky" button on every page, anonymous-first with DB-backed rate
limiting, inline sensor QC, a 👀 map layer, a board widget, `human_report`
events in the banner, and a `REPORTS_ENABLED` kill switch. Still pending from
the engagement side: event-moment prompts.

**Extended 2026-07-23 — composite reports + weighted alerts.** A submission now
carries *many* observations (fog *and* rain *and* a blocked road, each with its
own intensity) in one `report_group`, and the rate limit counts submissions,
not observations. A report may also raise a yellow/orange/red **weather alert**,
resolved per station as a **weighted consensus** so no single voice — least of
all an anonymous one — can escalate the valley alone (weights anon 1.0 /
signed-in 1.5 / trusted 3.0, 6 h decay, thresholds 1.5 / 3.0 / 5.0, computed on
read in `reports.station_alerts` and surfaced via `GET /alerts`, a map ring, and
the head of the banner). Full math and design rationale:
[forecasting-whitepaper.md §4.3](forecasting-whitepaper.md). Self-serve accounts
and trusted-observer weighting shipped 2026-07-18.

Precedents: NOAA's mPING (anonymous phone reports of precipitation type, used
operationally to tune radar algorithms), CoCoRaHS (20k+ volunteers feeding NWS),
the Met Office WOW (citizen gauges demonstrably infill the official network),
USGS "Did You Feel It?" (the shape of the idea), and — closest to home —
ICIMOD's community-based flood early warning systems in Nepal/India, whose
documented lesson is that the *social* architecture (a known local observer, a
simple channel) matters as much as the sensor.

Sketch (a future PR's spec, not a promise):

- `obs_reports` table: `ts, lat, lon, kind` (precip | hail | fog | snow_line |
  wind_damage | road_blocked | flood), `intensity 0–3, note ≤140, reporter,
  client_hash` (HMAC of ip+UA — rate limiting without storing PII), `qc_flag`.
- `POST /api/v1/reports` — anonymous, DB-backed rate limit (3 per 10 min per
  client); inline QC cross-checks the nearest fresh station (rain report vs
  `rain_mm`, fog vs RH, wind damage vs gust) → `corroborated` / `contradicted`
  (a *contradicted* report near a station is interesting, not spam).
- PWA report dialog (big tap targets, geolocation, one thumb), a reports layer
  on the map, a `human_report` event kind in the summary when ≥2 reports agree.

## 4. Phase C — divergence alerts as a channel, not just a banner

Phase A already *detects* divergence; Phase C makes it actionable:

- `jobs/nowcast.py` on a 10-min interval: rain/pressure divergence plus
  station-only hazard heuristics (3 h pressure crash, RH jump + wind shift,
  `lightning_events` distance trend closing).
- `alerts` table for dedupe (same station+kind within 6 h fires once) and audit.
- Publish `forsyth/alert/{slug}` on the existing mosquitto broker — Home
  Assistant users get sirens for free; `GET /api/v1/alerts` for a feed widget.

## 5. Phase D — bias correction (trigger: ~90 days of pairs)

When `/skill` shows a stable sample (n in the thousands, a season of weather),
add `jobs/bias.py`: per (station, model, lead-bucket, variable) rolling
corrections — start with the mean bias `/skill` already computes, graduate to
sklearn-class regressors (predictors: lead, hour-of-day, season, ensemble
spread) only if the numbers justify it. Serve as a `corrected` series on
`/forecast`. Literature says 20–30 % error reduction is the realistic prize
(Hieta et al. 2025, Met. Apps; "Adaptive Bias Correction", PNAS 2023). No
schema change needed — the table was shaped for this join from day one.

Non-goals, stated plainly: no deep-learning nowcaster on the droplet, no
pretending to out-model ECMWF, no satellite ingestion before the simpler layers
have proven themselves.

## 6. Sky-vision track — insight from the cameras (and one cheap sensor)

The camera stations currently *show* the sky; this track makes them *read* it.
Decided 2026-07-18. Three steps, software-first, BOM change last:

- **V1 — software only (days, not weeks).**
  - *LCL cloud base* (✅ shipped 2026-07-18): estimated cloud base ≈ 125 m per
    °C of temp/dew-point spread, computed from sensors every station already
    has — on the station page as "Cloud base (est.)". In a valley where the
    ceiling decides paragliding and mountain-road judgment, a formula is
    worth a panel.
  - *Vision-LLM sky observer*: the summary engine already talks to an LLM;
    send the latest frame every 30 min ("cloud fraction, type, visibility,
    precipitation visible?") → a `sky_observed` event, and — the quiet asset —
    an archive of LLM sky labels paired with simultaneous sensor readings,
    which later trains cheaper local methods.
- **V2 — classical CV in a worker job.** Red/blue-ratio cloud-fraction
  estimation (the all-sky-imager standard for decades; benchmarks show simple
  thresholding gets most of the way before any CNN), frame-to-frame cloud
  motion (drift over the ridge is the valley's own nowcast), fog on/off from
  edge contrast against each camera's clear-day baseline, and a **painted snow
  stake in frame** as a snow gauge (operational webcam snow networks do
  exactly this). Pillow/numpy on the droplet; no GPU, no new hardware.
- **V3 — one BOM line, not a camera.** A zenith-pointed IR thermopile
  (MLX90614, ~₹300–500, I²C, µA-class) reads sky temperature: clear sky is
  20–40 °C colder than ambient, cloud radiates back warm — the amateur-
  astronomy cloud-detector standard (AAG CloudWatcher lineage). Quantitative
  cloud cover **day and night**, covering the visible camera's blind spot;
  rain/dew on its window blanks it, so the rain sensor gates validity.
  Candidate for the Board B revision (see `hardware/architecture.md` §2.2).
  Explicitly rejected: thermal imagers (₹15k+ for nothing the thermopile +
  camera pair doesn't give); NoIR camera noted as a cheap coordinator-skycam
  option for moonlit nights, not a leaf part.

Power discipline note: cameras belong on **coordinators** (a capture+upload
costs orders of magnitude more energy than a LoRa burst — same math as the
PMS7003 warm-up in `research/competitive-landscape.md` §4); the thermopile's
µA listening budget is leaf-compatible, like the AS3935.

## 7. Parallel track — data in, data out, allies

- **IMD APIs** (api.imd.gov.in): district nowcast warnings + city forecasts,
  registration-gated. An IMD warning chip on the map is instant credibility.
  *API key requested 2026-07-18; integration unblocks when it arrives.*
- **MOSDAC** (mosdac.gov.in): INSAT-3D/3DR products, GSMaP-ISRO gauge-corrected
  rain (0.1°, hourly). Free with an account; a later satellite-vs-mesh check.
- **Give the data away**: the CSV export already exists; a season of dense
  valley observations paired with archived forecasts is exactly the dataset
  regional researchers lack (IIT Mandi sits *in* HP and works on landslides and
  flash-flood ML; ICIMOD works this exact problem transboundary). Publishing it
  is both a research contribution and how a small mesh earns collaborators.
- Directional references, for later reading: MetNet-3 (station observations
  assimilated directly into a neural forecaster — "densification"), Global
  MetNet (satellite+NWP nowcasting aimed at radar-sparse regions), cloudburst
  ANN studies for the Indian Himalaya (Natural Hazards, 2025), and the HP
  flash-flood GNN with conformal uncertainty (arXiv:2603.15681).

## 8. Sequence, restated

| Phase | What | Status / trigger |
|---|---|---|
| A | Pull + store forecasts, `/forecast` + `/skill`, forward-looking banner, widget | ✅ 2026-07-18 |
| B | Human reports: POST/GET, QC vs sensors, PWA dialog, map layer | ✅ 2026-07-18 |
| C | Nowcast job, `alerts` table, MQTT publish | after B, or sooner if a monsoon demands it |
| D | Per-station bias correction, `corrected` series | ~90 days of `/skill` pairs |
| V1 | LCL cloud base (✅ 2026-07-18) · vision-LLM sky observer | LLM part: any time |
| V2 | R/B cloud fraction, cloud motion, fog contrast, snow stake | first real camera outdoors |
| V3 | MLX90614 sky thermopile on the leaf | Board B revision |
| ∥ | IMD/MOSDAC registration, dataset publishing, IIT Mandi / ICIMOD outreach | IMD key requested 2026-07-18 |

The quiet win of Phase A shipping first: the moment real hardware lands in a
valley, the insight layer is already running — and the dataset already has a
head start.
