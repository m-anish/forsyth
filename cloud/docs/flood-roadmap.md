# Google Flood Forecasting — what it offers and what we should do with it

Written 2026-11-02, after the API was enabled on the project. Nothing here is
built. §0 is the part to do first, and it may change everything below it.

---

## 0. The question everything depends on

**Is there a gauge near us, and is this grid square covered for flash floods?**

I could not answer that from the documentation. Google publishes a country list
(India is on it) but not a gauge list, and the flash-flood product says it covers
"urban areas, and some rural areas where available" — which Bir may well not be.
Three calls settle it. Run these before reading the rest as though it were a plan.

```bash
export FFKEY=...   # the key from the Cloud project, never committed
```

**(a) Which gauges exist in this corner of Himachal.** A loop around the Kangra
valley and the Beas from Mandi to Pong — wide on purpose, because the useful
gauge is almost certainly downstream of us, not here.

```bash
curl -s -X POST "https://floodforecasting.googleapis.com/v1/gauges:searchGaugesByArea?key=$FFKEY" \
  -H "Content-Type: application/json" -d '{
    "loop": {"vertices": [
      {"latitude": 31.6, "longitude": 75.9},
      {"latitude": 31.6, "longitude": 77.2},
      {"latitude": 32.5, "longitude": 77.2},
      {"latitude": 32.5, "longitude": 75.9}
    ]},
    "includeGaugesWithoutHydroModel": true
  }' | python3 -m json.tool | head -80
```

Look at: how many come back, which have `hasModel: true`, which are
`qualityVerified`, what `river` and `source` say (`CWC` would mean India's
Central Water Commission is behind it), and how far each `location` is from
32.03 N 76.72 E. Add `"includeNonQualityVerified": true` if the first answer is
empty — a lower-confidence gauge is still worth knowing about.

**(b) What those gauges say right now.**

```bash
curl -s "https://floodforecasting.googleapis.com/v1/floodStatus:queryLatestFloodStatusByGaugeIds?key=$FFKEY&gaugeIds=GAUGE_ID" \
  | python3 -m json.tool
```

**(c) Whether India has flash-flood events at all, and where.** Country-wide, so
in the monsoon this list is long; in November it may be empty, which proves
nothing either way. Worth running again in July.

```bash
curl -s -X POST "https://floodforecasting.googleapis.com/v1/flashFloods:search?key=$FFKEY" \
  -H "Content-Type: application/json" -d '{"countryCodes": ["IN"], "pageSize": 50}' \
  | python3 -m json.tool
```

Each event gives polygon IDs, not coordinates; `serializedPolygons.get` turns an
ID into KML. Whether any polygon has ever covered this valley is the real
coverage test, and only a monsoon answers it.

**If (a) comes back empty**, everything in §3 except idea 5 is dead and the
honest thing is to not pretend otherwise on the site.

---

## 1. What the API actually is

| | |
|---|---|
| Base | `https://floodforecasting.googleapis.com/v1` |
| Auth | API key, Cloud project must have the API enabled |
| Price | no charge |
| Quota | **200 requests per minute** |
| Status | **pilot** — "the version provided is preliminary, so expect updates and changes that may break your usage code" |
| Licence | **CC BY 4.0** — the same licence we just put on our own readings |

Resources: `gauges`, `gaugeModels`, `floodStatus`, `flashFloods`,
`serializedPolygons`, `significantEvents`.

**Gauge** — `location`, `river`, `source` (the owning agency), `countryCode`,
`qualityVerified`, `hasModel`. Both real gauges and virtual ones (HydroBASINS
reaches), so coverage can extend past places with physical instruments.

**GaugeModel** — the thresholds that make a number mean something:
`warningLevel`, `dangerLevel`, `extremeDangerLevel`, and `gaugeValueUnit`, which
is either `METERS` (stage) or `CUBIC_METERS_PER_SECOND` (discharge). A model can
be replaced, and then it gets a new `gaugeModelId` and new thresholds — so
forecasts either side of that boundary are not comparable. Worth storing the
model id alongside every value we keep.

**floodStatus** — `severity` (`EXTREME`, `SEVERE`, `ABOVE_NORMAL`,
`NO_FLOODING`, `UNKNOWN`), `forecastTrend` (`RISE`, `FALL`, `NO_CHANGE`),
`forecastChange` with lower and upper bounds in metres, and an
`inundationMapSet`. Queryable by gauge IDs or by area.

**queryGaugeForecasts** — up to 500 gauge IDs, `issuedTimeStart` /
`issuedTimeEnd` (no earlier than 2023-10-01, defaults to the past week).
Returns, per gauge, a list of forecasts each with an `issuedTime` and
`forecastRanges[]` of `{value, forecastStartTime, forecastEndTime}`. Ranges may
start *before* the issue time because the inputs lag, and their spacing varies —
so this is not a tidy fixed-step series and must not be treated as one.

**flashFloods** — probability of a flash flood in the next 24 h on a
**20 km × 20 km** grid, reduced to "likely" and "highly likely" polygons.
Searchable by country only. Documented limits that matter here: weather-caused
floods only — **not** glacial melt, GLOF, or dam failure — and "initially, it
covers only urban areas or areas with a history of flooding", bounded by what is
in Google's flood-history dataset.

**Inundation maps** — `PROBABILITY` or `DEPTH`, three nested levels
(`HIGH`/`MEDIUM`/`LOW`), fetched as KML by polygon ID.

---

## 2. The geography problem, stated honestly

Riverine flood forecasting is about river reaches with gauges. Our stations sit
at 1400–1700 m on the south face of the Dhauladhar — the **top** of the
catchment, not a floodplain. Bir does not flood the way Nadaun floods.

So a severity flag on a Beas gauge 50 km downstream tells a reader in Bir
nothing about their own doorstep. What it tells them is something else, and
better: **how much trouble the water leaving this hillside is about to cause**.
The hazards that actually threaten Bir itself — a cloudburst over the Binwa, a
nala coming down in twenty minutes — are flash-flood-shaped, which is the
product with the weakest coverage guarantees and a 20 km cell that contains the
whole village and much of the ridge besides.

That asymmetry is not a reason to skip this. It is the reason the interesting
idea is idea 2 rather than idea 1.

---

## 3. Ideas, best first

### 1. A `flood` widget: the river below

A new widget in the registry alongside `aqi` and `lightning`. For each gauge
within some radius: river name, distance and bearing from the reader's station,
current severity as a coloured state, trend arrow (we already have
`trendArrow`), and the forecast change in metres with its uncertainty bounds.
Thresholds give it the context a bare number lacks — "2.4 m, warning level is
3.1 m" reads; "2.4 m" does not.

Cheap, uses machinery that exists, and is the obvious first thing. Also the
least original: it is Flood Hub with our fonts on it.

### 2. "The water we are making" — upstream rain against downstream river

The one nobody else can build, because nobody else is measuring rain up here.

Put our `rain_mm` at the top of the catchment on the same time axis as Google's
forecast discharge at the gauge below, offset by the travel time. Over one
monsoon that becomes a local rainfall-to-river-rise relationship for this
specific valley — and it is checkable, because we will have both halves stored.

It also inverts who the site is for. Right now Forsyth answers "do I need a
jacket". This answers "the hills above you took 80 mm in six hours and the Beas
at Nadaun is forecast to rise 1.2 m tomorrow" — which is a thing a person
downstream would genuinely want, and which the existing `summary` banner is
already the right shape to say.

Needs: travel-time lag (start with a guess, then fit it from stored pairs — the
same move as the forecast-skill machinery), and honesty that our two stations
sample a catchment of hundreds of square kilometres.

### 3. Flash-flood probability, wired into the alert level we already have

`/api/v1/alerts` already returns `mesh_level` 0–3 with names
`none/yellow/orange/red`. A "likely" or "highly likely" polygon covering a
station is a natural input to that, so the banner and the alert plumbing light
up without inventing a parallel notification system.

Must say the resolution out loud. A 20 km cell is not a warning about your
house, and presenting it as one would be the single most harmful thing we could
do with this data. Wording closer to "flash flood conditions are forecast for
this part of the valley in the next 24 hours" than to "flooding expected".

Blocked on §0(c) — and realistically on a monsoon, since the only honest test is
whether a polygon ever lands here.

### 4. Inundation maps as a map layer

`map.js` already has a layer switcher (terrain, satellite, RainViewer). KML
polygons from `serializedPolygons` fit straight into it as another toggle,
`PROBABILITY` or `DEPTH`, three nested levels.

Genuinely useful — for the Kangra valley and the Pong floodplain, not for Bir.
Worth doing once idea 1 shows there is anything to draw.

### 5. Verify their forecasts the way we verify Open-Meteo

We already compare forecast against observation and publish the bias and error
per lead time (`/stations/{slug}/skill`). The same machinery applied to gauge
forecasts — stored issue-time series against what the gauge later read — gives a
local track record for flood forecasts, which as far as I can tell nobody
publishes.

**This one survives even if there is no gauge near us**, because a gauge
anywhere in the Beas basin can be verified. It is also the most in keeping with
what this site is: the place that checks the models against the ground.

Caveat: a new `gaugeModelId` resets the comparison.

### 6. Significant events, as context rather than a feature

`significantEvents` carries `affectedPopulation`, `areaKm2` and an event
polygon. One line in the banner during a real event — "the worst of it is 60 km
south, where 40,000 people are in the forecast area" — is worth more than
another widget nobody opens on a calm day.

---

## 4. How it would be built

**The key stays server-side.** Unlike the MapTiler key, which is referrer-locked
and safe to hand the browser, this one is a plain Cloud API key with no origin
restriction available. It goes in `cloud/.env` beside the others, the worker
talks to Google, and the dashboard talks only to us. That also puts one
cache in front of the 200/min quota instead of one per visitor.

**It is the forecast job again.** `cloud/api/app/jobs/forecast.py` already polls
an upstream model, stores rows, and serves them through our own API. A
`jobs/flood.py` of the same shape, with its own tables, is the whole of it —
plus a row in the admin console's manual-trigger list, which comes free.

**Polling and budget.** Gauge discovery once a day (their guidance: do not cache
the gauge list "for long periods of time", with "no more than a day" called
relatively safe). Status and forecasts every 15 minutes. Flash-flood search
every 15 minutes during monsoon, hourly otherwise, with polygon geometry fetched
only for IDs we have not seen and cached by ID thereafter. That is roughly a
dozen calls an hour against a budget of twelve thousand — the quota is not a
constraint, our droplet is.

**Storage.** Forecast values keyed by `(gauge_id, gauge_model_id, issued_time,
forecast_start_time)`, so a model change is visible rather than silently
corrupting a comparison. Thresholds stored per model id, not per gauge.

**Keep the blast radius small.** It is a pilot and Google say so plainly:
breaking changes expected. One module does the parsing, our own tables and our
own API shapes are what the dashboard sees, and a schema change upstream becomes
a stale widget rather than a broken site. The widget needs a real empty state —
"no gauge near here" is a sentence we may have to show permanently.

---

## 5. Licensing

Their data is **CC BY 4.0**, which is the same licence we put on our readings on
2026-11-02 — so republishing is squarely permitted, and no clause fights ours.

What that requires of us:

- Attribution on anything showing it: Google Flood Hub, plus each gauge's own
  `source` (CWC, GRDC) since that is the agency whose instrument it is.
- A row in `DATA-LICENSE.md` under "what this covers and what it doesn't". Note
  that this is **unlike** `/forecast`: Open-Meteo output is excluded from our
  `Link: rel="license"` header because it is not ours to license, whereas flood
  data is CC BY 4.0 and *can* carry it — though the attribution it carries is
  Google's, not ours, so the cleanest answer is a separate header or a `source`
  field in the response rather than silently folding it into ours.
- A line on the `/api` page, since anyone building on our endpoints inherits the
  obligation.

---

## 6. What I would actually do

1. **§0.** Three calls, ten minutes. Everything else is conditional on them.
2. **Idea 1**, as the thinnest possible version: one gauge, severity and trend,
   on the station page. Enough to find out whether the data is any good here.
3. **Idea 5** in the background from day one — store every forecast from the
   start, because skill needs history and history cannot be backfilled past
   2023-10-01, and only to the extent `queryGaugeForecasts` will still serve it.
4. **Idea 2** once there are stored pairs to fit a lag against. This is the one
   worth the effort.
5. **Ideas 3 and 4** when a monsoon has shown whether flash-flood coverage
   reaches this valley at all.

And the thing not to do: put a flood warning on the homepage of a village in a
state where people have died in cloudbursts, on the strength of a 20 km grid
cell and a pilot API, without saying plainly where the number came from and how
coarse it is.
