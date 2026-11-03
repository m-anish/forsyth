# The site should feel like the sky it is reporting on

Written 2026-11-02 as a plan. **Phase 1 shipped 2026-11-03**; phases 2–5 are
still a plan. The fall-back if it goes wrong is the `v1` tag
(`git checkout v1`). What phase 1 changed against the plan is in §8.

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
3. **The scene, static.** Hero only, no motion, all six states.
4. **The motion.** Three elements at most, reduced-motion honoured, paused when
   hidden.
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

### For phase 2

- `Theme.step()` already returns `day|golden|dusk|night` or `null`, and
  `Theme.place(lat, lon)` is the one way coordinates get in. `Sky` can wrap
  these rather than restate them.
- `themechange` now fires only on a real change, so a `skychange` event can
  follow the same discipline. The five-minute re-check depends on it.
- The hero still caches its icon per model hour, so it does **not** follow a
  step change mid-session. Harmless now; phase 3 must fix it, or a scene will
  disagree with the glyph above it.
