# Dashboard v2 — design review and plan

Written 2026-10-31, against the live site with one reporting station (OHHDL
Library) and one registered but silent (Bir Tibetan Colony).

**The target user changed.** v1 was built as an instrument console for the
person who owns the hardware. v2 is a public weather site for people who want
to know whether to carry a jacket. Almost every problem below follows from that
one change, and so does the good news: most of the parts already exist and are
pointed the wrong way.

---

## 1. The one-sentence verdict

**The homepage never shows the weather.** Everything else is detail.

Open the site today and you get, in order: a logo, "Sign in to customize", a
map whose tiles half-load, a dropdown reading "— pick a location —", and three
widgets explaining that nothing has happened. The temperature exists — the
station is reporting fine — but a visitor has to find a dropdown and choose
something before the site will tell them anything.

A weather site has one job in its first screenful: say the weather.

---

## 2. What v1 gets right — keep all of this

These are real strengths. They are not the problem, and v2 should preserve them
deliberately rather than lose them in a rewrite.

1. **The station page's information architecture is genuinely good.** Forecast →
   right now → pressure → air quality → history → housekeeping → export is a
   sensible descent from "what do I need" to "what am I curious about". Most of
   v2's homepage can be assembled from pieces already proven here.

2. **Plain-language interpretation.** "Steady. No drama expected." does
   something almost no weather site does: it reads the instrument *for* you.
   This is the single most valuable asset in the product and v2 should do far
   more of it, not less.

3. **Honesty about forecast skill.** "past 30 days here: temperature within
   ±7.6 °C about a day out" is a remarkable thing to show. Keep it, and give it
   better words.

4. **Derived values that answer human questions** — dew point, cloud base,
   pressure trend over 3 h. These are the difference between a data dump and a
   weather site.

5. **The voice.** "The sky has kept its opinions to itself." The copy has a
   personality and it is a good one. v2 keeps the voice and changes only the
   vocabulary (§3.4).

6. **The widget/board system is well-built.** Twelve widget kinds, a persisted
   layout, public/private boards, an admin "publish to home" path. The
   machinery is sound — it is the *default layout* that is wrong, which makes
   the most important fix in this document nearly free.

7. **Theming** — 44 design tokens, light/dark/auto, and a `themechange` event
   the map layers already listen to. A real foundation.

8. **Data export.** CSV with ranges up to a year, and an all-stations file. The
   enthusiast minority is well served; just stop showing it to everyone first.

---

## 3. What v1 gets wrong

### 3.1 The homepage is built from the wrong widgets

This is the core finding, and it is a layout problem, not a code problem.

The `default` board is:

| widget | size | serves |
|---|---|---|
| `map` | 12 × 6 | exploration |
| `localpanel` | 8 × 11 | **requires a choice before it shows anything** |
| `reports` | 4 × 5 | empty |
| `lightning` | 4 × 3 | empty |
| `health` | 4 × 3 | **the operator, not the visitor** |

Meanwhile these widget kinds already exist and appear nowhere on the homepage:

> `now` · `forecast` · `aqi` · `chart` · `windrose` · `summary`

The widgets a normal person needs are already written. They are simply not on
the page. **Rebuilding the default layout is the highest-value change in this
document and needs almost no new widget code.**

### 3.2 Priority inversion, top to bottom

- **"Sign in to customize." is the first line of the page.** The first thing
  the site says to a stranger is an invitation to do admin. Customisation is a
  power-user feature; it does not belong above the weather.
- **`health` is on the public homepage.** "bir-colony ⚠ never heard from / — V
  / — dBm" reads to a visitor as *the site is broken*. It is operator
  telemetry and belongs on a `/status` page or behind sign-in.
- **The map is the hero.** A map is an *exploration* tool. With two stations
  40 km apart there is nothing to explore. The hero should be a number.

### 3.3 The visitor is asked to do work

"— pick a location —" is the empty state of the main panel. With one reporting
station, the site knows the answer and still asks the question. v2 must open
with a location already chosen: geolocation when granted, nearest station
otherwise, the only station when there is only one. "Pick a location" should
never be a first impression.

### 3.4 Jargon written for the person who built it

| v1 says | a visitor understands |
|---|---|
| MESH HEALTH | — (and it alarms them) |
| LoRa RSSI, −8 dBm | — |
| HOUSEKEEPING | — |
| `localpanel` | — |
| `?slug=leaf-01` | — |
| "STATION · LEAF-01" | — |
| 0.0 m/s NW | nothing; people think in km/h |
| 838.3 hPa | "that's wrong" (it is station pressure at 1676 m) |
| AQI 100 "satisfactory" | depends entirely on *which scale*, which is unlabelled |

Two of these are not just vocabulary but **correctness-as-perceived**:

- **Pressure.** 838 hPa is correct at 1676 m and will read as broken to anyone
  who knows sea-level pressure is ~1013. Show sea-level-adjusted (QNH) by
  default, station pressure as the secondary figure.
- **AQI.** 60 µg/m³ PM2.5 is AQI ~100 on India's CPCB scale ("Satisfactory")
  and ~153 ("Unhealthy") on the US EPA scale. Showing a bare number with a
  reassuring word and no scale is the one place this site could actively
  mislead someone about their health. Label the scale, always.

### 3.5 Mobile is where this audience actually is, and mobile is worst

At 375 px: logo, "Sign in to customize", then a map card whose controls (zoom,
five metric chips, five overlay toggles, layer picker) cover most of the
visible tiles, then "pick a location". **No weather appears above the fold at
all.** The floating "report the sky" button overlaps content.

### 3.6 Emptiness is the dominant visual

Three of five homepage widgets are empty, and with one station they will stay
empty for months — lightning needs a storm, reports need a community. The copy
is charming about it, but charm does not survive being 60 % of the page. v2
should hide widgets with nothing to say rather than render an apology.

### 3.7 Confirmed bugs found during this review

1. **The map does not size itself correctly.** *(confirmed, high impact)* On
   mobile the card is 309 × 434 px but Leaflet requests only 2 tiles covering
   256 px — **59 % of the card**, 178 px blank. On the dedicated `map.html` in
   light mode the page is ~90 % blank. Cause: Leaflet measures the container
   before the grid layout settles and never re-measures. Fix: `invalidateSize()`
   on a `ResizeObserver` over the map element, plus once after layout. This
   affects the hero element on every viewport and should be fixed before any
   design work.
2. **An unknown query param silently redirects to the homepage.**
   `station.html?s=leaf-01` (wrong param; correct is `slug`) lands on `/` with
   no message. Either 404 honestly or resolve it.
3. **Layout leaves large dead gaps** when the grid reflows at intermediate
   widths — a tall empty band between the map and the lower widgets.

---

## 4. v2 principles

1. **Answer first, explore second.** The first screenful states the weather at
   one place, in words and one big number. Maps, charts and history come after.
2. **Never ask before answering.** Location is inferred, then adjustable.
3. **Say what it means, not just what it measured.** Extend "Steady. No drama
   expected." to wind, rain, AQI and the forecast.
4. **One audience per surface.** Public pages carry no volts, no dBm, no slugs.
   Operator data moves to `/status` and the signed-in view.
5. **Nothing empty on the homepage.** A widget with no data hides itself.
6. **Mobile is the design target.** Desktop is the wide version of it, not the
   other way round.
7. **Be explicit about provenance.** Measured-here vs model-forecast, and when.
   v1 already does this well on the station page; it is a trust asset.

---

## 5. The plan

### Phase 0 — fix what is broken (prerequisite)

Design review cannot proceed on a map that renders at 59 %.

- Map `invalidateSize()` via `ResizeObserver`; verify at 375 / 768 / 1440 px.
- Honest handling of unknown station params.
- Audit the grid reflow dead-space at intermediate widths.

### Phase 1 — rebuild the default board *(highest value, least code)*

Replace the `default` layout with widgets that already exist:

| order | widget | why |
|---|---|---|
| 1 | `now` | the answer, full width, big |
| 2 | `forecast` | what's coming — the second question everyone asks |
| 3 | `aqi` | locally the most consequential number, scale labelled |
| 4 | `map` | explore, now that the question is answered |
| 5 | `reports` | community, only when non-empty |
| — | ~~`health`~~ | → `/status` |
| — | ~~`localpanel`~~ | superseded by 1–3 with location pre-resolved |

Done via the existing admin "publish layout → home" path. No widget code.

### Phase 2 — language and units pass

Jargon table in §3.4; wind in km/h with a Beaufort-ish word ("calm", "breezy");
sea-level pressure by default; AQI scale labelled and colour-coded; "Station
health" replacing "Housekeeping"; place names before station names
("Dharamshala · OHHDL Library").

### Phase 3 — the hero widget

`now` as it stands is a stat grid. v2 wants a genuine hero: condition icon,
large temperature, a sentence ("Clear and calm. 13° tonight."), feels-like,
and a provenance line ("measured here, 2 minutes ago"). This is the one piece
of real new design work.

### Phase 4 — information architecture

Slug-free URLs (`/dharamshala` over `station.html?slug=leaf-01`); a real nav
rather than three header buttons; `/status` for operator data; decide whether
board customisation is public at all.

### Phase 5 — completeness audit

Only after the above: every widget, every empty state, every loading state,
every error state, light and dark, 375/768/1440, keyboard and contrast.

---

## 6. Decisions

Answered 2026-10-31. Items 3 and 4 are assumptions drawn from the deployment,
not statements from the owner — correct them and the affected phases shift.

### 6.1 Board customisation stays, its chrome does not

`main.py` keeps the homepage *as* a board on purpose: "a single homepage
implementation, not a hand-built page drifting apart from the board it's meant
to mirror". That reasoning is sound and v2 keeps it — a bespoke homepage would
drift within two releases.

What goes is the **editing affordance**, not the mechanism. Signed-out visitors
get the `default` board rendered read-only, with no "Sign in to customize", no
drag handles, no grid chrome. Customisation appears only once signed in. This
fixes the priority inversion in §3.2 without a rewrite, and removes the public
path from a whole class of grid-reflow bugs (§3.7.3).

### 6.2 AQI: CPCB, labelled, with raw µg/m³ and a WHO reference

Use the **Indian CPCB scale**. The audience checks Indian apps and news; a
number that disagrees with every other source they see reads as a broken site,
not a stricter standard.

But CPCB is permissive, and §3.4 showed the gap is health-relevant — 60 µg/m³
PM2.5 is "Satisfactory" (CPCB ~100) and "Unhealthy" (US EPA ~153). So never
show the number bare:

> **AQI 100 · Satisfactory** (CPCB)
> PM2.5 60 µg/m³ — 4× the WHO 24-hour guideline of 15

That agrees with local sources, names its scale, and still tells the truth about
the air. The WHO line does the honest work without crying wolf.

### 6.3 Design for 2–5 stations *(assumption)*

One reporting, one silent, and Board A is still at bring-up. A handful within a
year is the realistic case for hand-built LoRa hardware.

Consequences: **the map is not a hero** (§3.2) and Phase 4's slug-free URLs and
nav are genuinely low priority. Keep the degradation graceful — past roughly ten
stations the map earns its place back and Phase 4 moves up.

### 6.4 Audience: Dharamshala/HP local, Tibetan-community-adjacent *(assumption)*

The two station names — "OHHDL Library" and "Bir Tibetan Colony" — read as the
Office of His Holiness the Dalai Lama and the Bir settlement. If that is right,
the audience is residents of Dharamshala/McLeodganj and Bir rather than a
general Indian or international one.

Consequences: °C, km/h, IST, CPCB; place names people actually use
(Dharamshala, McLeodganj, Bir, Palampur) ahead of station names; monsoon
framing matters more than it would elsewhere — rain, landslides and road
closures are the local weather questions. It also makes "report the sky"
(§2.5) a better fit than it looks on a site with one station: a small, dense,
place-attached community is exactly who files such reports.

Flag: if this is wrong, §6.4 is the only decision that changes materially —
language and place naming — and nothing in Phases 0–3 depends on it.

---

## 7. Widget-by-widget

Read against the current `widgets.js`. The pattern in nearly every case: the
widget reports the measurement correctly and stops one step short of the
*insight* — the arrow, the comparison, the consequence. That last step is what
separates a readout from a weather site, and it is usually a few lines of code.

**Cross-cutting defaults** (apply everywhere before touching individual cards):

| | today | v2 |
|---|---|---|
| wind speed | `0.0 m/s` | `0 km/h` + word (`calm`, `light`, `breezy`, `gusty`) |
| wind direction | `NW` | `NW` **plus a glyph rotated to the bearing** |
| pressure | station hPa (838) | sea-level, station as secondary |
| AQI | bare number | number + named scale + WHO multiple |
| missing data | `—` | `—` plus *why* (`no sensor` vs `no report yet`) |
| staleness | `agoLabel` only | visibly dim the card past ~3 report intervals |
| direction convention | — | state once: **wind is where it blows *from*** |

### 7.1 `now` — becomes the hero (§5 Phase 3)

Today: big temp, then a 6-cell grid of Humidity / Wind / Pressure / AQI /
**Battery** / **Solar**.

- **Drop Battery and Solar.** Two of six cells on the public hero are operator
  telemetry (§6.1). They go to `/status`.
- **Add feels-like.** The single most-wanted number after temperature. At 1676 m
  with low humidity it will often differ meaningfully from the dry-bulb reading.
- **Add today's high/low**, and a **trend arrow on the temperature itself**
  (↑ 1.2° in the last hour) — the page already has the series to compute it.
- **Wind cell gets the arrow**: `→ 8 km/h from NW`, glyph rotated by bearing.
- **Sunrise/sunset.** Cheap to compute from lat/lon, and it is one of the three
  things people actually open a weather site for.
- Condition icon + one-sentence summary, matching the station page's voice.

### 7.2 `chart` — labels currently leak field names

`series` labels come from `m.replace(/_/g,' ')`, so the legend literally reads
`temp c`, `wind avg ms`, `batt v`. Needs a field→label+unit map (`Temperature
°C`, `Wind km/h`). Then: a **"now" marker**, night shading behind the series,
and min/max annotations. Default range 24 h is right; the 1 H option is useless
with a 5-minute cadence (12 points) — drop it or make it 3 H.

### 7.3 `windrose` — the biggest single upgrade available

Currently petals are scaled by *frequency only*, normalised to `maxN`, with the
rings unlabelled. A reader cannot tell whether the outer ring means 10 % or 60 %
of the time, and the rose says nothing about **speed**.

- **Colour petals by speed band** (the conventional rose) with a small legend.
  This turns one variable into two at no extra screen cost.
- **Label the outer ring** (`28 % of the time`).
- **Calm percentage in the centre** — at this site it will often dominate, and
  omitting it overstates the wind.
- **State the prevailing direction in words** beneath: *"Mostly from the NW."*
  That sentence is what most readers actually wanted from the rose.

### 7.4 `aqi` — the health-relevant one (§6.2)

The band pin is `left: aqi/5 %`, which hard-codes a 0–500 scale without saying
so. Name the scale, colour the big number to match the band, and add **one line
of guidance** ("Fine for a walk." / "Sensitive groups: take it easy.") plus the
WHO multiple on PM2.5. Also show which pollutant is driving the index — with
PM10 74 and PM2.5 60 it is worth knowing which one set the number.

### 7.5 `lightning` — a list where a headline belongs

A feed of rows is the right *detail* view but the wrong *summary*. Lead with one
line — **"Nearest strike 8 km away, 12 minutes ago — moving away"** — derived
from the distance trend across recent events. The AS3935 gives no bearing, so
distance-over-time is the only honest trend, and it is the one people want.
Group bursts into storms rather than listing 30 rows.

### 7.6 `camera` — fine; make the timestamp load-bearing

Works. Surface capture time next to the image rather than below, and mark a
frame stale if it is older than the capture interval — a silently old sky photo
is worse than none.

### 7.7 `map` — fix sizing (§3.7.1), then thin the controls

In `compact: true` the card still carries zoom, five metric chips, five overlay
toggles and a layer picker. On a phone these cover most of the tiles. Compact
should keep the metric chips and the legend, and drop the rest to the full
`map.html`.

### 7.8 `forecast` — good; add the two callouts people look for

The strip plus optional chart is solid, and the skill line (§2.3) is excellent.
Add **night shading** and a **"next rain" callout** ("Dry through Tuesday" /
"Rain likely Sunday evening") — precipitation timing is the question the strip
is being scanned for.

### 7.9 `reports` — invert the empty state

"No one has reported the sky lately." apologises where it should invite:
*"Seen fog, hail or a blocked road? Be the first to say so."* The corroboration
✓ and trust ★ mechanics are genuinely well designed — surface them with a
legend, since neither glyph explains itself.

### 7.10 `summary` — promote it

This is the only widget whose whole job is *insight*, and it is absent from the
homepage. Whatever `/summary` produces belongs directly under the hero. Its
empty state ("Nothing is happening. Forsyth approves.") is the best line on the
site and is currently almost unreachable.

### 7.11 `health` — move wholesale to `/status`

Slugs, volts and dBm. Nothing here is for a visitor (§3.2).

### 7.12 `localpanel` — dissolve

Once location resolves automatically (§3.3), the wrapper's job shrinks to a
location *switcher* in the header. The `— pick a location —` default option
should not exist; `@here` should fall back to nearest, then to the only station.

---

## 8. Chart types — what each quantity actually is

The generic `chart` widget draws **every** metric as an unmarked line, labelled
with the raw database column. That is right for some metrics and wrong for
others — and the codebase already knew better in two places: `renderForecast`
draws forecast rain as **bars** under an ensemble **band**, and the station
page's rain chart was bars from the start. The patterns existed; they were just
not applied consistently.

*Corrected 2026-10-31: an earlier draft of this section said the station page
drew rain as a line. It did not — only the generic widget did.*

The question to ask of each metric is not "does a line look nice" but **what
kind of quantity is this** — and the answer dictates the encoding.

### 8.1 The rules

1. **Instantaneous quantities get lines.** Temperature, humidity, pressure,
   wind speed, PM — each sample is a reading of a thing that existed at that
   instant, and the value between samples genuinely varied continuously.
2. **Interval quantities get bars.** Rain is *accumulation since the previous
   report* (`schema.sql` says so). Lightning counts are per-bucket. These have
   no meaningful value "between" samples — a line through them draws a quantity
   that never existed.
3. **Never smooth a measurement.** Spline interpolation manufactures peaks and
   troughs that were never recorded — on a gust series it will invent a maximum
   higher than the highest gust. Straight segments, or steps for interval data.
   (uPlot's linear default is already correct; the rule is "don't 'improve' it".)
4. **Circular quantities never get a linear axis.** See 8.2.
5. **Zero-base only what lives near zero.** Rain and wind speed: yes. Pressure
   (838 ± 2 hPa), battery (3.2–3.4 V) and °C: absolutely not — a zero-based
   axis flattens the entire signal into a straight line.
6. **A gap must look like a gap.** This matters more here than on most sites:
   the battery taper (§ firmware) legitimately stretches reporting from 5 to 40
   minutes, and hibernate stops it entirely. A line drawn straight across a
   four-hour hole asserts data that was never collected. Break the series on
   gaps beyond ~2 expected intervals.
7. **Show sample density when cadence varies.** `makeChart` sets
   `points:{show:false}` globally. For PM — sampled every 6th report, and far
   less often under taper — the dots *are* information. Show points where
   samples are sparse.

### 8.2 Per-metric

| metric | today | should be | why |
|---|---|---|---|
| temperature | line | **line** ✓ | continuous; add day/night shading and a "now" marker |
| humidity | line | **line** ✓ | as above |
| pressure | line | **line, tightly auto-ranged** | the signal is ±2 hPa on an 838 base; the *trend* is the story, so annotate the 3 h delta |
| wind avg + gust | two lines | **band between avg and gust, line on avg** | the gap between sustained and gust *is* the information; two spiky lines read as noise |
| **wind direction** | line | **arrow glyphs along the time axis** | **a line here is actively wrong**: 350°→10° is a 20° shift that draws as a full-height vertical crash. Circular data cannot go on a linear axis |
| **rain** | bars on the station page, line in the widget | **bars everywhere** | interval quantity; a line interpolates rain that did not fall |
| PM2.5 / PM10 | line | **line + visible points, AQI bands behind** | sparse sampling; the category thresholds are the context that makes the number mean anything |
| battery | line | **line, tight range, taper thresholds as reference lines** | LiFePO4's plateau is flat; the thresholds are what make it readable |
| **lightning** | feed only | **bar histogram of strikes per bucket** + **scatter of distance vs time** | discrete events — a line between strikes implies continuity that does not exist |
| forecast temp | line | **line + ensemble spread band** ✓ | already right; keep |
| forecast precip | bars ✓ | **bars** ✓ | already right; probability as bar opacity or a second light series |

### 8.3 Two additions worth the pixels

- **A 24 h sparkline under the hero temperature.** One line, no axes, no
  legend. It answers "is this normal for today?" in a glance and costs almost
  nothing.
- **Day/night shading behind every time-series chart.** It converts a chart
  into something readable without consulting the axis, and the diurnal cycle is
  the dominant pattern in nearly all of these metrics.

---

## 9. A palette that follows the sun — what it would cost

Asked 2026-11-01, after the chart backgrounds started shading night as a
gradient rather than a rectangle: could the *whole site* drift between its day
and night palettes instead of flipping?

It can. The mechanism is already half-built — `sunAltitude(ms, lat, lon)` in
`js/common.js` returns the one number the whole thing needs, and `nightBands`
already turns that number into a 0…1 darkness with a smoothstep. The question
is what the rest of the page costs.

### 9.1 The continuous version

Rename the two palette blocks in `dash.css` to source sets (`--d-*`, `--n-*`),
then derive the ~35 live tokens from them:

```css
--bg: color-mix(in oklab, var(--d-bg) calc((1 - var(--k)) * 100%), var(--n-bg));
```

…and have a two-minute tick set `--k` on `<html>` from the sun's altitude at
the active station. Mechanical, about thirty-five lines of CSS and twenty of
JS.

Then the parts that are not CSS:

- **Charts.** uPlot reads its colours once, at build, and the code rebuilds on
  `themechange`. A palette that moves continuously either rebuilds charts on a
  timer — which costs a redraw and throws away the reader's zoom — or needs a
  recolour-without-rebuild path. Quantising chart strokes to a few steps is the
  cheap way out.
- **The map.** Raster tiles do not interpolate. Two tile sets cross-faded at a
  threshold, or snapped at the halfway point; nothing in between.
- **Contrast.** This is the real cost, and the reason not to hand-wave it. Both
  endpoint palettes pass AA today. **A blend of two passing palettes is not
  itself guaranteed to pass** — around the midpoint, text and background move
  toward each other, and `--text-mute` on `--bg-elev` was already the tightest
  pair in the set at 4.65:1. Every intermediate `k` has to be swept, which
  `tools/ui-audit.js` can do unattended in steps of 0.05.
- **Whose choice is it.** `auto` currently means "the OS setting". Adding a
  third meaning — "the sky where you are" — is a UX decision, not a technical
  one, and it must honour `prefers-reduced-motion`.

Honest estimate: half a day for the mechanism, half a day for charts and the
map, and **a day for the contrast sweep and fixing whatever midpoints fail** —
call it two days, with the risk concentrated in the last part.

### 9.2 The version worth doing first

Three or four fixed palettes — day, golden, dusk, night — cross-faded at the
boundaries with the transition `body` already carries. Each one is checked for
contrast **once**, by hand, the way the current two were. It reads as "the site
follows the sun" to anyone who is not holding a colour picker, and it is a few
hours rather than two days.

The cheapest 80% is already shipped: the chart and map backgrounds follow the
sun continuously while the page chrome holds still, which is where the diurnal
cue actually earns its keep.
