# Map roadmap — from three dots to an instrument

Written + phases 1–2 implemented 2026-07-13. The map's job: answer "what is the
weather *doing across the mesh*" at a glance, and double as a maintenance view.
Implementation: `dashboard/js/map.js` (shared by the homepage and the board
`map` widget — one codebase, `compact` flag for widgets).

Station locations come from `stations.lat/lon/elevation_m`, set in the admin
console's station form (or the `POST /api/v1/stations` upsert). No coordinates
→ not on the map.

## Phase 1 — markers that say something ✅ (2026-07-13)

- **Data chips** replace dots: each station renders its current value in a
  colored pill — color scale per metric, value printed on the chip, wind
  direction as a rotated arrow riding along. Stale stations grey out;
  simulated stations get a dashed border.
- **Metric modes** (map control): °C · wind · AQI · rain · battery. AQI uses
  the Indian CPCB bands and official colors; battery is the maintenance view
  (LiFePO4 thresholds: green ≥3.15 V, amber ≥2.95 V, red below).
- **Legend** (bottom-left) follows the active mode — gradient ramps for
  continuous scales, labeled swatches for banded ones.
- **Richer popups**: temp/RH, wind avg+gust+direction, pressure, last-report
  rain, AQI, battery, RSSI, elevation, last-seen, station link.
- **UX**: wheel-zoom armed on click and disarmed on mouse-leave (no page-scroll
  hijack); fit-stations button; fullscreen toggle; theme-following tiles kept.

## Phase 2 — context layers ✅ (2026-07-13)

- **Terrain basemap** (OpenTopoMap) in the layer switcher — in the Himalaya,
  contours *are* context for wind and temperature readings.
- **Live rain radar** overlay (☂ button): RainViewer public composite tiles,
  latest frame, self-refreshing every 10 min while enabled. Fail-silent — if
  the API is unreachable the button apologizes in its tooltip and the map
  carries on. (Coverage over the subcontinent is partial; treat as advisory.)

## Phase 3 — history and events (future)

- **Time scrubber**: drag through the last 24 h; chips animate through
  `/stations/{slug}/series` data. The single most useful future item —
  "watch the front come through."
- **Lightning on the map**: AS3935 gives distance-only (no bearing), so render
  recent strikes as **range rings** around the reporting station, fading with
  age. Needs a small `/lightning/recent` API endpoint (events exist in the DB).
- **Camera thumbnails**: stations with a skycam get their latest frame in the
  popup, linking to the timelapse.
- **Gust vectors**: arrow length/width scaled by gust strength in wind mode.

## Phase 4 — density features (when the mesh earns them)

- **Interpolated surfaces** (IDW/contours for temp, pressure): meaningless at
  3 stations, defensible at ~10+, lovely at 20. Gate on station count.
- **Marker clustering** past ~20 stations.
- **Permalink state** (`#mode=aqi&radar=1&z=…`) for sharing a specific view;
  embed mode for the marketing site.

## Notes for implementers

- Everything derives from the `/stations` payload (latest reading per station)
  — phases 1–2 added zero API surface. Phase 3 items are the first to need
  new endpoints.
- Chip colors are data-driven (not theme vars) so they read identically in
  light/dark; the *chrome* (legend, controls) uses the dashboard's CSS vars.
- RainViewer and OpenTopoMap are third-party free tiers — degrade gracefully,
  never let their outage break the page.
