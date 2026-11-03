# The site should feel like the sky it is reporting on

Written 2026-11-02 as a plan. **Phases 1–4 are built**; 1–3 are deployed, 4 is
not. Phase 5 is still a plan. Fall back with `git checkout v2` (the palette
work, before any scene) or `git checkout v1` (before any of it). What the built
phases changed against the plan is in §8–§11.

Asked for: the three-or-four fixed palettes from [v2-design.md](v2-design.md)
§9.2, extended so that **weather** and not only time of day shapes the page —
rainy night meaning something different from clear night — plus a few drawn
elements that give the page a feel, in the spirit of Google's weather widget
but restrained. Hard constraint: it must stay fast and snappy, and must not
feel overdone.

---

## 1. The decomposition this hangs on

The obvious reading of the request is "palettes for every combination of time
and weather", which is 4 times of day × 5 weather states = 20 palettes, 20
contrast sweeps, and an unmaintainable mess. Do not do that.

Split the two signals into two **different visual channels**:

| signal | channel | why |
|---|---|---|
| time of day | the **palette** — background, text, chrome | slow, global, sets the mood; it is what "the page feels like evening" means |
| weather | a contained **scene layer** | an event, not a mood; additive, and can be wrong without poisoning legibility |

They compose rather than multiply: *clear night* is the night palette plus the
moon scene; *rainy night* is the night palette plus the rain scene. Four
palettes plus five scenes is nine things to build, not twenty.

It also separates the risk. The palette is the invasive half — it touches every
pixel and every contrast ratio. The scene is contained and can be judged purely
on taste. They should therefore ship separately, and in that order.

## 2. Both inputs already exist

Nothing new has to be computed:

- `sunAltitude(ms, lat, lon)` in `js/common.js` already returns the sun's
  altitude in degrees. It drives the graded night shading on every chart.
- `wxKind(rainMm, prob, cloud, tempC)` already reduces the forecast to
  `clear | partly | cloud | rain | snow`. It drives the hero's icon.
- The hero already fetches `/stations/{slug}/forecast?hours=6` and caches the
  result per model hour, so **the weather state is in hand with no new
  request** — see §6 for the small refactor that stops it being fetched twice.

## 3. The palettes

Anchored to sun altitude, so dawn and dusk are the same two steps in reverse
and nothing is an arbitrary clock time:

| step | sun altitude | what it is |
|---|---|---|
| **day** | above +6° | today's light palette, unchanged |
| **golden** | +6° to −0.833° | low warm light; warmer paper, longer shadows in the greys |
| **dusk** | −0.833° to −12° | the blue hour; cool, desaturated, the one genuinely new mood |
| **night** | below −12° | today's dark palette, unchanged |

**Only two new palettes.** Day and night are the existing light and dark, which
are already checked against WCAG AA. That is a far smaller job than §9.1
assumed, and worth saying plainly.

Dawn and dusk share their palettes to begin with. Splitting them later (dawn
pinker, dusk oranger) is a refinement, not part of this.

### The flash, which is the real technical problem

`js/theme.js` sets `data-theme` **synchronously before first paint**, from
localStorage plus `matchMedia`, precisely to avoid a flash of the wrong theme.
A sky palette cannot do that: it needs the station's coordinates, which come
from the API, which is asynchronous. Left alone this paints night and then
jumps to golden a second later, on every single load — which would feel broken
and cheap in exactly the way we are trying to avoid.

Fix: cache the last resolved step **and** the coordinates in localStorage, and
paint from the cache before first paint, then correct once the data lands.
Coordinates barely change, and a cached step is at worst one boundary stale for
a second. Only a first-ever visit can flash, and it can fall back to `auto`.

### Whose choice the palette is

This is the part most likely to annoy people, and it is not a technical
question. `auto` currently means "whatever the OS says", and a lot of people
set dark permanently and mean it. Overriding that with "but it is noon in Bir"
is hijacking a stated preference.

So: **`sky` becomes a fourth mode, not a redefinition of `auto`.** The button
cycles `auto → light → dark → sky`, the default stays `auto`, and nobody who
has not asked for this gets it. Whether `sky` should later become the default
is a separate decision, taken after we have looked at it for a while — not
baked in now.

`prefers-contrast: more` pins the palette to the plain light/dark pair, which
are the two with the most headroom.

`prefers-reduced-motion` deliberately does **not**, which is a change of mind
from the first draft. The palette turns four times a day behind a 250 ms
crossfade. That is not motion in the sense that setting is about, and honouring
it there would deny the whole feature to anyone who merely dislikes animation.
It still governs the scene layer in §4, where it belongs.

## 4. The scene layer

### Where it goes, which is most of the design

**Inside the hero card, not behind the page.** Containing it is the single
biggest safeguard against "overdone": a backdrop behind the whole page competes
with every chart, every table and every number on the site, and there is no
amount of subtlety that fixes that. The hero is the one element whose entire
job is "what the sky is doing right now", it sits at the top, and a scene
confined to it can never interfere with a chart.

A band across the upper part of the hero, roughly 120–160 px, masked so it
fades out before it reaches any text.

> **This is the part that was wrong.** "Behind the text, masked" caps the
> scene at whatever the smallest thing over it can survive, which measured out
> at an alpha of 0.04 on the dark palette — invisible. The scene was given a
> band of its own instead, with the hero pushed below it. §10 has the numbers.

### What it is made of

The same drawn vocabulary as the icon set, at wallpaper scale and much lower
contrast — a sun disc with eight rays, a crescent cut from two discs, clouds as
three circles over a rounded rect, rain as slanted round-capped strokes, snow
as dots. Reusing that vocabulary is the strongest argument for this working at
all: the page already has a visual language for weather, and the scene is that
language enlarged rather than a second, competing one.

| state | the scene |
|---|---|
| clear day | a low warm radial where the sun actually is — azimuth sets the horizontal position. **No disc**: a sun disc at wallpaper scale reads as a logo |
| clear night | a crescent, small and high, plus a scatter of static dots at varied opacity. The real moon phase is computable and would be a nice later touch |
| partly | the radial, plus two or three soft cloud forms drifting very slowly |
| overcast | cloud forms only, lower contrast, no radial |
| rain | cloud forms plus a sparse set of slanted strokes, the group translated by exactly its own tile height on a ~2 s linear loop so it reads as continuous |
| snow | the same, slower, as dots |

Colours come from the palette tokens that already exist (`--wx-sun`,
`--wx-moon`, `--wx-cloud`), so the scene changes with the time of day for free.
That is the point of the decomposition: *rainy night* needs no rule of its own.

### The rules that keep it cheap

- Inline SVG, one kind in the DOM at a time. Estimate under 3 kB on the wire
  for the whole set, no images, no library, nothing added to the critical path.
- `transform` and `opacity` only — never `top`, `left` or `width`. Compositor
  work, no layout, no paint.
- **At most three moving elements**, and nothing faster than a ~2 s loop.
- Paused when the tab is hidden, using the `onVisible` machinery that exists.
- `@media (prefers-reduced-motion: reduce)` → the scene renders static. It must
  look finished without motion, not broken.
- If the forecast is missing or stale, **no scene at all** rather than a guessed
  one. The same discipline the hero icon already follows: better to show
  nothing than the wrong sky.

## 5. What I am less sure about

The palette half I am confident in: two new palettes, a mode nobody is opted
into by default, and a contrast sweep that `tools/ui-audit.js` can run
unattended across all four steps.

The scene half carries real risk, and it is not technical — it is taste. Drawn
weather on a page of instrument readings can very easily look cheap, and no
amount of planning settles that in advance. Which is why it ships behind the
palette work, on one page, where it can be looked at and thrown away.

## 6. Phases, each shippable and each revertable

0. **`v1` tagged.** Done.
1. **Two palettes and the `sky` mode.** Opt-in, no scene. Includes the
   localStorage pre-paint cache, and the contrast sweep across all four steps.
   Smallest change that proves the hard part. **Done** — `4cd8d58`, with the
   pre-existing AA fixes it turned up in `e7bab84`.
2. **A `Sky` module.** Owns sun step and weather state, fetches the forecast
   once, exposes `Sky.state()` and emits `skychange`; the hero consumes it
   instead of fetching its own copy. Net effect is **one fewer request**, and
   no visual change at all — which makes it a safe, boring commit.
   **Done** — `a203e4f`. The saving was larger than this line assumed; §9.
3. **The scene, static.** Hero only, no motion, all six states.
   **Done** — `6db1b04`, but not as described here; §10.
4. **The motion.** Three elements at most, reduced-motion honoured, paused when
   hidden. **Done** — `bc254d6`; §11.
5. **Decide whether `sky` becomes the default.** Only after living with it.

Stop after any phase and the site is coherent. Phase 1 reverts cleanly on its
own; so does each one after it.

## 7. Things to carry in, from what is already known

- **The asset version must be bumped by hand** on every phase that touches CSS
  or JS — all five HTML files plus `sw.js`. A deploy that looks successful and
  changes nothing is the standing trap here.
- **Charts read their colours once, at build**, and rebuild on `themechange`.
  Four palette steps mean four rebuilds a day, which is nothing. This is also
  the second reason to prefer fixed steps over the continuous blend §9.1 priced
  at two days: a continuously moving palette would mean either rebuilding
  charts on a timer or letting their colours drift out of step.
- **Map tiles have only two variants**, light and dark, so the map snaps at the
  day/dusk boundary rather than following all four steps. Acceptable; say so
  rather than pretending otherwise.
- **Contrast is the thing that fails.** `--text-mute` on `--bg-elev` is already
  the tightest pair in the set at 4.65:1. The golden and dusk palettes must be
  swept before they ship, not after.

## 8. What phase 1 actually cost, and what it corrected

Shipped as `4cd8d58`, preceded by `e7bab84`. Four things the plan had wrong or
had not thought of, recorded because the later phases rest on them.

**The step cache was unnecessary.** §3 said to cache the last resolved step
*and* the coordinates. Only the coordinates are cached. `sunAltitude` is pure
arithmetic, so a cached place yields the exact current step at parse time for
free, and a cached step would have been a second thing to keep honest.

**`data-sky`, not a redefinition of `data-theme`.** The plan did not say how
the four steps would be expressed. They are an overlay: `data-theme` still
carries light-or-dark, and `[data-sky="golden"]` / `[data-sky="dusk"]` restate
only what they change. Nothing else in the codebase had to learn about them —
`color-scheme`, every `[data-theme="light"]` rule, the chart rebuild and the
map tiles all kept working untouched. Phase 3's scene can read `data-sky` from
CSS alone.

**The overlay is safe because of luminance, and that is now checked.** Each of
golden's three backgrounds is at least as light as light's; each of dusk's at
least as dark as dark's. So any foreground either palette inherits can only
land at a better ratio than the one it already passed. The first cut held this
for `--bg-elev` only, shipped a `--bg-card` a shade too dark, and dropped
`.tool-btn` text to 4.50:1 — found by the page audit, not the token table.
`tools/palette-contrast.js` now checks the invariant rather than a comment
asserting it, and exits non-zero on a break.

**§1's claim that day and night were "already checked against WCAG AA" was
false.** The sweep written to vet the *new* palettes found three failures in
the existing light palette (`--good` 4.03, `--warn` 3.68, `--wx-sun` 2.93),
plus `--accent-2` at 4.21 under the `<sup class="beta">` tag and a hard-coded
white on `--accent` at 2.67 in dark. All five were live before any of this
work. Two tools came out of it, and both earn their keep:

- `tools/palette-contrast.js` sweeps all six palettes from the CSS with no
  browser, checks every foreground against all three painted backgrounds, and
  refuses to silently skip a token it has no threshold for.
- `tools/ui-audit.js` gained `sup, sub, small, code, strong, em, b, i, time,
  dt, dd, figcaption, legend`. The beta tag had been failing in plain sight
  because `<sup>` was not on its list.

They answer different questions and neither replaces the other: the token sweep
checks the table, the page audit checks the pixels. Golden's `--bg-card` was
caught only by the page audit; the beta tag only by the token sweep.

### For phase 2 — all three carried out, see §9

## 9. What phase 2 found, and what phase 3 inherits

Shipped as `a203e4f`. No visual change, by design.

**The shape.** `js/sky.js` loads in `<head>` before `js/theme.js` and holds
both signals plus the solar maths. `theme.js` lost the place cache, the step
thresholds, the timer and `sunAltitude`, and is now a file about choosing a
theme, which is what its name says. The division is: **Sky says what the sky is
doing; Theme decides whether the reader asked for that to be painted.**

```
Sky.place(lat, lon, slug)   remember where, and whose weather is "the" weather
Sky.step()                  day | golden | dusk | night | null (no place yet)
Sky.base(step)              light | dark, for the charts and the map tiles
Sky.forecast(slug, hours)   the shared, deduped, per-run cache
Sky.state(slug?)            { step, base, kind } — either half may be null
'skychange' on window       fires only on a real turn of step or weather
```

**The saving was bigger than §6 priced it.** The plan said one fewer request,
from the hero dropping its own `hours=6` call. That works because the API
answers every window from `now - 1 h`, so a 48 h response is a strict superset
of a 6 h one — same first sample, same run.

The larger half was not foreseen: `renderForecast` fetched **before** its own
reuse check, so a board refetched the whole forecast every sixty seconds in
order to discover it had not changed, and the station page refetched on every
`themechange`. Sky caches per model run, and a run lasts three hours. Measured:
one request on the board, still one after a full refresh tick; and on the
station page, four step changes and four chart rebuilds with no refetch at all.

**A bug found in passing.** `Widgets.stations()` cached the *result* rather
than the promise, so five widgets rendering in parallel opened five identical
requests for the same list. Fixed with the same in-flight dedupe Sky uses.
`location.js`, `report.js` and `station.js` still each fetch `/stations` for
themselves; a shared cache for those is a separate job and is **not** done.

### For phase 3

- The scene can read the step from CSS alone (`[data-sky]` on `<html>`) and the
  weather from `Sky.state()` or the `skychange` event. It does not need a
  request of its own.
- **`skychange` fires on a real turn only**, so a listener that rebuilds is
  woken about four times a day plus whenever the weather state changes, not on
  a timer. Keep that discipline when adding the scene.
- The hero no longer caches its own sky state, so it follows a step change as
  soon as it re-renders — but it still only re-renders on the board's
  sixty-second tick. A scene that moves faster than that will briefly disagree
  with the glyph above it; have the hero listen to `skychange` too.
- `Sky.state()` with no argument answers for the primary station, which is
  whichever one called `Sky.place()` with a slug. That is the right station for
  a scene that is about "here".

## 10. Phase 3, and the assumption it broke

Built as `6db1b04`. Not deployed at the time of writing.

### Behind the text was the wrong place, and the measurement said so

§4 said to put the scene behind the hero's content and mask it. Built that
way, the scene's strength is capped by the least forgiving thing drawn over
it. The guess was that dark would tolerate more, since its `--text` sits at
14.7:1. That is true of `--text` and of nothing else: `--text-mute` is 4.84:1
on the dark card, so **any** lightening breaks it. Solving for the ceiling:

| palette | max `--sky-a` behind text | first token to break |
|---|---|---|
| light | 0.155 | `--text-mute` over `--wx-moon` |
| golden | 0.185 | `--good` over `--wx-moon` |
| dusk | 0.085 | `--text-mute` over `--wx-sun` |
| **dark** | **0.040** | `--text-mute` over `--wx-sun` |

0.04 is invisible. And it is not a tuning problem: a tint always moves the
background toward mid-grey, which is where mid-tone text lives, so there is no
palette where this is cheap and no alpha that is both safe and visible. A
picture dimmed until it cannot hurt the text is not a picture.

**So the scene got the space instead.** `.hero-sky` is absolutely positioned
(an absolute child resolves against the padding box, so it reaches the card's
inner edges without restating `.wg-body`'s padding) and `.hero-sky + .hero`
takes a `padding-top` of the same height. The adjacent-sibling selector is the
point: no scene element, no padding, so a station with no forecast gets its old
layout back with nothing to configure. No text is read against the scene, the
ceiling disappears, and the alpha became a question of taste.

### Three defects the pixel audit found that arithmetic had not

The first audit composited the real SVG under the real mask over the real card
and read the pixels under every glyph. It paid for itself immediately:

- **stars with no alpha ceiling** — `.wx-scene .st` set `fill` and nothing
  else, so they drew at their own 0.35–0.85 opacity. Near-opaque light dots on
  a dark card: **1.06:1** under the trend chip.
- **the moon at the sun's azimuth**, which put it on that same chip at 3.3:1.
  It is fixed in the corner now. Nothing here computes a lunar ephemeris, and
  an illustration placed precisely wrong is worse than one that makes no claim.
- **a viewBox that did not match the band.** 400x80 sliced into a 54px band
  crops 40% of the height; the clouds lost their bumps and read as grey pills.
  The viewBox is 400x60 now, sized so a hero card's real aspect range
  (about 5.7:1 to 7.6:1) lands either side of it, and the drawing keeps inside
  y 4..52.

A fourth, from reading rather than measuring: `wxSceneCloud` took a raw
translate, but the cloud's ink begins at y=6.7 inside its 24-box, so
`translate(40 18)` put its top at y=50. It takes the visible corner now, so
the number in the call is the number on the screen.

### What checks what

- `tools/palette-contrast.js` — the token table, no browser. It briefly carried
  a table of audited alphas; that is gone, because there is no composite left
  to audit.
- `tools/scene-audit.js` — asserts the stronger property: **no text box
  intersects the band**, at every palette step and sky state. It cannot go
  stale when someone moves a cloud.

`prefers-contrast: more` hides the scene and collapses the band. That reader
asked for less decoration, whatever the ratios say.

### Two bugs found on the way, neither about the sky

- **The dev proxy spoke HTTP/1.0.** Every local check was taking minutes, with
  the browser reporting 25,000 ms API calls, while the same proxy answered
  fifteen parallel calls in 0.54 s from a shell. 1.0 closes the connection
  after each response. With keep-alive the slowest call on a board load went
  from 25,000 ms to 431 ms.
- **The service worker was registering on localhost**, serving an edit-old
  `common.js` from cache while the proxy answered `no-store`. Three debugging
  detours in one afternoon before the cause was obvious. It no longer registers
  there, and tears down anything an earlier session left.

### For phase 4

- The groups are the units to move: `.cl .mn .st .rn .sn`. `wxSceneRain` draws
  one tile-height row, so translating the group by that row and looping reads
  as continuous.
- `transform` and `opacity` only, at most three moving elements, nothing faster
  than about 2 s, paused when hidden, and static under
  `prefers-reduced-motion` — unchanged from §4 and still right.
- The hero re-renders on `skychange` already (coalesced with `themechange` in
  board.js), so a moving scene will not disagree with the glyph above it.

## 11. Phase 4, and the two things that only showed up in motion

Built as `bc254d6`. Rain falls, snow falls slower, clouds drift; a clear sky
does not move, because that is what a clear sky does.

**Tiling, not translating.** §4 said to translate the rain group "by exactly
its own tile height on a ~2 s linear loop so it reads as continuous". A single
row translated by its own height does **not** loop: halfway through, the row
has left the top of the band and nothing has arrived behind it, so the rain
thins and then snaps. The falling groups are drawn as rows exactly `WX_TILE`
apart covering one row above the band and one past the bottom, and then the
translate returns the figure to itself. `WX_TILE` in `js/common.js` and the
`20px` in the keyframe are one number living in two files.

**A CSS transform replaces an SVG transform attribute** rather than composing
with it, so animating `.cl` directly would have discarded the translate and
scale that place each cloud. Hence `.cl-d`, a wrapper that the drift owns and
nothing else touches. Three periods — 48s, 71s, 97s, none a multiple of
another — so the overcast sky's three clouds never start moving as one object.

Budget held: `transform` and `opacity` only, at most three moving groups in any
state, nothing faster than a 2.2s loop, paused on `data-hidden` (set by
`js/sky.js`), gone under `prefers-reduced-motion`.

**Verified by driving the animation, not waiting on it.** The pane runs hidden
pages as background pages, so animations are paused exactly when a test would
want to watch them. Setting `animation.currentTime` and reading the computed
transform sidesteps that entirely: rain is linear 0 → 19.98 over 2.2s, landing
on the tile height. Worth reaching for before any test that sleeps.

`tools/scene-audit.js` used `requestAnimationFrame` in its sweep, which never
fires in a hidden pane — the same trap `ui-audit.js` carries a comment about
avoiding, walked into one file later and one day after. `setTimeout` now.

### What came after, on request

Sun **rays** in the clear and partly scenes, leaning by the sun's real azimuth,
and the hero's temperature casting a **shadow** the other way — both from
`Sky.shadow()`, so the two halves of the lighting cannot disagree. Length is
`1/tan(altitude)`, clamped, so shadows stretch as the sun drops. Only `clear`
and `partly` are lit: under an overcast sky nothing casts a shadow, which is
also what finally made `cloud` read as a different sky rather than a sunny one
with the sun removed (four overlapping forms, and `.wx-cloud` asking the same
token for more weight).

Three sign-and-counting errors, all silent, all caught by checking rather than
by looking — worth keeping as a list because each one *looked* right:

- the shadow fell east when the sun was in the east. The east-west component of
  a bearing is east-positive, but `sunX` puts east at the LEFT of the card, so
  the sign flips back.
- the beams leaned **towards** the sun. SVG's positive rotation is clockwise,
  and a downward fan rotated clockwise swings left. For one revision the beams
  and the shadow disagreed about the light on the same card.
- `:nth-of-type(-n+2)`, meant to pick the first two clouds, counts every `<g>`
  **sibling** — so the beams group and the moon were counted as clouds and a
  partly-cloudy night had nothing moving at all. Clouds now name their drift
  track instead of being chosen by position.

And the viewBox lesson, for the third time: a hero card is 60px tall and up to
the full width of the board, so `slice` crops the **vertical** axis, and at
10:1 only the middle two thirds survives. Ink lives in y 10..50.

### Phase 5, which is all that is left

Whether `sky` becomes the default theme mode. Deliberately not decided here:
it is a judgement to make after living with it, not a line of code to write.
