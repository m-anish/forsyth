/* forsyth live — shared helpers */
'use strict';

const API = '/api/v1';

/* App version — shown in the footer (esp. useful for the PWA, where a stale
   cached build is otherwise invisible). Bump alongside the asset ?v= query. */
const APP_VERSION = '0.63';
addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.app-ver').forEach(el => { el.textContent = 'v' + APP_VERSION; });
});

/* PWA: install the service worker (network-first for anything live; see sw.js) */
if ('serviceWorker' in navigator) {
  addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}

async function getJSON(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

/* the signed-in flavour: sends the session cookie and surfaces the API's
   `detail` on failure. Lives here (not board.js) because js/auth.js wires the
   sign-in chrome on every page. */
async function apiJSON(path, opts = {}) {
  const r = await fetch(API + path, {
    credentials: 'same-origin',
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    ...opts,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
}

/* Refresh when the reader comes back to the page.

   setInterval is not a promise the browser keeps: background tabs get their
   timers throttled to a crawl, phones suspend them outright, and iOS restores a
   page from bfcache with its DOM exactly as it was frozen. So a tab returned to
   after an hour shows hour-old readings until the next tick happens to fire —
   which is why the only reliable fix used to be pressing reload.

   `minHiddenMs` keeps flicking between tabs from re-fetching for no reason;
   anything longer than a few seconds away is worth a refresh. */
function onVisible(fn, minHiddenMs = 5000) {
  let hiddenAt = null;
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') { hiddenAt = Date.now(); return; }
    if (hiddenAt === null || Date.now() - hiddenAt >= minHiddenMs) fn();
    hiddenAt = null;
  });
  /* bfcache restore (Safari back/forward): the timers were frozen with it */
  window.addEventListener('pageshow', (e) => { if (e.persisted) fn(); });
}

function fmt(v, digits = 1, unit = '') {
  if (v === null || v === undefined) return '—';
  return Number(v).toFixed(digits) + unit;
}

function agoLabel(iso) {
  if (!iso) return 'never heard from';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function isStale(iso) {
  return !iso || (Date.now() - new Date(iso).getTime()) > 30 * 60 * 1000;
}

const DIRS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
function dirName(deg) {
  if (deg === null || deg === undefined) return '—';
  return DIRS[Math.floor(((deg + 11.25) % 360) / 22.5)];
}

/* Indian CPCB AQI sub-index from PM2.5 + PM10 (worst of the two wins) */
function subIndex(c, bps) {
  if (c === null || c === undefined) return null;
  for (const [clo, chi, ilo, ihi] of bps) {
    if (c <= chi) return Math.round(ilo + (ihi - ilo) * (c - clo) / (chi - clo));
  }
  return 500;
}
const PM25_BP = [[0,30,0,50],[30,60,51,100],[60,90,101,200],[90,120,201,300],[120,250,301,400],[250,500,401,500]];
const PM10_BP = [[0,50,0,50],[50,100,51,100],[100,250,101,200],[250,350,201,300],[350,430,301,400],[430,600,401,500]];
function aqi(pm25, pm10) {
  const a = subIndex(pm25, PM25_BP), b = subIndex(pm10, PM10_BP);
  if (a === null && b === null) return null;
  return Math.max(a ?? 0, b ?? 0);
}
function aqiLabel(v) {
  if (v === null) return '—';
  if (v <= 50) return 'good';
  if (v <= 100) return 'satisfactory';
  if (v <= 200) return 'moderate';
  if (v <= 300) return 'poor';
  if (v <= 400) return 'very poor';
  return 'severe';
}

/* a one-line, dry description of conditions */
function describe(r) {
  if (!r || r.temp_c === null) return 'no opinion yet';
  const bits = [];
  if (r.rain_mm > 0.5) bits.push('raining');
  else if (r.rh > 88) bits.push('air like a wet towel');
  else if (r.rh < 35) bits.push('dry');
  if (r.wind_gust_ms > 10) bits.push('gusty');
  else if (r.wind_avg_ms > 4) bits.push('breezy');
  else bits.push('calm');
  const a = aqi(r.pm25, r.pm10);
  if (a !== null && a > 200) bits.push('air worth avoiding');
  return bits.join(', ');
}

/* ---- human-facing units (docs/v2-design.md §7, §6.2) --------------------
   The instrument speaks m/s, pascals and station pressure. People do not.
   One place to convert, so a widget can never disagree with another.        */

/* Wind direction is where the wind comes FROM — the universal met convention
   and the one the vane reports. The arrow, though, flies WITH the wind, so it
   points downwind (bearing + 180); that is what every consumer weather app
   draws, and an arrow pointing into the wind reads as wrong to everyone who
   is not a meteorologist. The words always say "from", so the two together
   cannot be misread. */
function windArrow(deg, size = 11) {
  if (deg === null || deg === undefined) return '';
  const r = (Number(deg) + 180) % 360;
  return `<svg class="wind-arrow" width="${size}" height="${size}" viewBox="0 0 24 24"
      style="transform:rotate(${r}deg)" aria-hidden="true"><path d="M12 3 L12 21 M12 3 L6 10 M12 3 L18 10"
      fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function windKmh(ms) {
  if (ms === null || ms === undefined) return null;
  return Number(ms) * 3.6;
}

/* Beaufort, in words people use rather than numbers they look up. */
function windWord(ms) {
  const k = windKmh(ms);
  if (k === null) return '—';
  if (k < 1)  return 'calm';
  if (k < 6)  return 'almost still';
  if (k < 12) return 'light breeze';
  if (k < 20) return 'breezy';
  if (k < 29) return 'windy';
  if (k < 39) return 'strong wind';
  if (k < 50) return 'very strong';
  return 'gale';
}

/* "↙ 8 km/h from NW" — arrow, number, and the direction spelled out. */
function windText(r) {
  const k = windKmh(r && r.wind_avg_ms);
  if (k === null) return '—';
  if (k < 1) return 'calm';
  return `${windArrow(r.wind_dir_deg)} ${Math.round(k)} km/h from ${dirName(r.wind_dir_deg)}`;
}

function gustText(r) {
  const k = windKmh(r && r.wind_gust_ms);
  if (k === null) return '—';
  return `${Math.round(k)} km/h`;
}

/* Station pressure at 1676 m reads ~838 hPa, which looks broken to anyone who
   knows sea level is ~1013. Reduce to sea level (the barometric formula every
   met service uses) and keep the station figure as the secondary number.     */
function pressureSeaLevelHpa(pa, elevation_m, temp_c) {
  if (pa === null || pa === undefined) return null;
  const hPa = Number(pa) / 100;
  if (elevation_m === null || elevation_m === undefined) return hPa;
  const t = (temp_c === null || temp_c === undefined) ? 15 : Number(temp_c);
  const h = Number(elevation_m);
  return hPa * Math.pow(1 - (0.0065 * h) / (t + 0.0065 * h + 273.15), -5.257);
}

/* Apparent temperature (Australian BoM): works in both directions — humidity
   makes warmth worse, wind makes cool worse — unlike heat-index or wind-chill
   alone, each of which is undefined over half the range we see here.         */
function feelsLike(temp_c, rh, wind_ms) {
  if (temp_c === null || temp_c === undefined) return null;
  const t = Number(temp_c);
  const h = (rh === null || rh === undefined) ? 50 : Number(rh);
  const v = (wind_ms === null || wind_ms === undefined) ? 0 : Number(wind_ms);
  const e = (h / 100) * 6.105 * Math.exp((17.27 * t) / (237.7 + t));
  return t + 0.33 * e - 0.70 * v - 4.0;
}

/* CPCB categories are more permissive than the US EPA's, so the number never
   travels alone: the scale is named wherever it appears, and PM2.5 is shown
   against the WHO 24-hour guideline (15 µg/m³, 2021). See §6.2.              */
const AQI_SCALE = 'CPCB';
function aqiGuidance(v) {
  if (v === null || v === undefined) return '';
  if (v <= 50)  return 'Air is clean. Go outside.';
  if (v <= 100) return 'Fine for most. Sensitive groups, take it easy.';
  if (v <= 200) return 'Sensitive groups: keep outdoor spells short.';
  if (v <= 300) return 'Everyone should ease off outdoor exertion.';
  if (v <= 400) return 'Avoid outdoor exertion.';
  return 'Stay indoors if you can.';
}
function whoPm25Multiple(pm25) {
  if (pm25 === null || pm25 === undefined) return null;
  return Number(pm25) / 15;
}

/* ---- what each metric IS, and therefore how it must be drawn -------------
   docs/v2-design.md §8. The question is not "does a line look nice" but what
   kind of quantity this is: an instantaneous reading (line) or an accumulation
   over the interval since the last report (bars). Rain is the latter — the
   schema says "accumulation since previous report" — so a line through it
   draws rainfall rates that never existed.                                  */
const METRIC_META = {
  temp_c:       { label: 'Temperature', unit: '°C',    kind: 'line' },
  rh:           { label: 'Humidity',    unit: '%',     kind: 'line' },
  pressure_pa:  { label: 'Pressure',    unit: 'hPa',   kind: 'line', conv: v => v / 100 },
  wind_avg_ms:  { label: 'Wind',        unit: 'km/h',  kind: 'line', conv: v => v * 3.6 },
  wind_gust_ms: { label: 'Gust',        unit: 'km/h',  kind: 'line', conv: v => v * 3.6 },
  wind_dir_deg: { label: 'Direction',   unit: '°',     kind: 'dir'  },
  rain_mm:      { label: 'Rain',        unit: 'mm',    kind: 'bars' },
  pm25:         { label: 'PM2.5',       unit: 'µg/m³', kind: 'line', sparse: true },
  pm10:         { label: 'PM10',        unit: 'µg/m³', kind: 'line', sparse: true },
  batt_v:       { label: 'Battery',     unit: 'V',     kind: 'line' },
  rssi_dbm:     { label: 'Signal',      unit: 'dBm',   kind: 'line' },
};
function metricMeta(m) {
  return METRIC_META[m] || { label: String(m).replace(/_/g, ' '), unit: '', kind: 'line' };
}
/* "Wind km/h" — never the raw column name. The generic chart widget used to
   label its series `wind avg ms` straight out of the database. */
function metricLabel(m) {
  const d = metricMeta(m);
  return d.unit ? `${d.label} ${d.unit}` : d.label;
}

/* A reporting gap must read as a gap. The leaf's battery taper stretches its
   cadence from 5 to 40 minutes and hibernate stops it altogether, so a line
   drawn straight across a four-hour hole asserts data nobody collected
   (§8 rule 6). Two different things look alike in the raw series and must not:
     - nulls BETWEEN samples of a sparse metric (PM rides every Nth report) —
       "not measured this cycle", so the line should simply join its real
       samples;
     - a genuine outage — which must break the line.
   So: drop the sparse nulls, then insert one explicit null wherever the time
   between real samples exceeds maxGapS. */
/* The leaf's cadence is not a constant — the taper moves it between 5 and 40
   minutes — so the "too long" threshold is derived from the data rather than
   hard-coded: three times the median spacing, floored so a dense series does
   not break on one slow report. */
function medianGapS(ts) {
  if (!ts || ts.length < 3) return Infinity;
  const d = [];
  for (let i = 1; i < ts.length; i++) d.push(ts[i] - ts[i - 1]);
  d.sort((a, b) => a - b);
  return d[Math.floor(d.length / 2)] || Infinity;
}
function gapThresholdS(ts) {
  const m = medianGapS(ts);
  return m === Infinity ? Infinity : Math.max(900, m * 3);
}

function breakGaps(ts, arrays, maxGapS, { dropNulls = false } = {}) {
  const keep = [];
  for (let i = 0; i < ts.length; i++) {
    if (dropNulls && arrays.every(a => a[i] === null || a[i] === undefined)) continue;
    keep.push(i);
  }
  /* Measure the threshold on the samples that will actually be drawn, not on
     the raw timestamps. PM rides every 6th report, so its real spacing is
     ~30 min while the series ticks every 5 — deriving the threshold from the
     raw ticks broke the line at EVERY PM sample and left bare dots. */
  if (maxGapS === undefined || maxGapS === null) {
    maxGapS = gapThresholdS(keep.map(i => ts[i]));
  }
  const outTs = [], outs = arrays.map(() => []);
  for (let j = 0; j < keep.length; j++) {
    const i = keep[j];
    outTs.push(ts[i]); arrays.forEach((a, k) => outs[k].push(a[i]));
    const nx = keep[j + 1];
    if (nx !== undefined && (ts[nx] - ts[i]) > maxGapS) {
      outTs.push(ts[i] + Math.floor(maxGapS / 2));
      outs.forEach(a => a.push(null));
    }
  }
  return [outTs, ...outs];
}

/* Below this the anemometer is not measuring, it is quantising. One reed
   closure in a 10 s gate is 0.067 m/s, and cups this size barely turn at all
   until roughly half a metre per second — SparkFun publishes a calibration
   point (1.492 mph = one closure per second) but no starting threshold. So
   anything under this reads as calm rather than as a number implying
   precision the instrument does not have. Matches the API's ROSE_CALM_MS. */
const WIND_CALM_MS = 0.5;

/* Wind direction as arrows along the top of the wind chart, never as a line.
   Direction is circular: 350° → 10° is a 20° shift that a linear axis renders
   as a full-height vertical crash (§8 rule 4). Drawn in a uPlot `draw` hook so
   they stay aligned through zoom and resize for free, pointing downwind to
   match windArrow() in the stat cells.

   Arrow LENGTH carries speed, so one glance reads direction and strength
   together — and nothing is drawn below WIND_CALM_MS, because an arrow
   pointing confidently nowhere is worse than no arrow: a still vane keeps
   whatever bearing it last held. */
function windDirArrows(ts, dirDeg, speedMs, opts = {}) {
  const everyPx = opts.every || 52;
  const calm = opts.calmMs !== undefined ? opts.calmMs : WIND_CALM_MS;
  const spd = speedMs || [];
  let vmax = 0;
  for (const v of spd) if (v !== null && v !== undefined && v > vmax) vmax = v;
  const MIN = 3.5, MAX = 9.5;
  return { hooks: { draw: u => {
    if (vmax < calm) return;            /* nothing above the floor to draw */
    const ctx = u.ctx, bb = u.bbox, dpr = window.devicePixelRatio || 1;
    const y = bb.top + 11 * dpr;
    ctx.save();
    ctx.strokeStyle = opts.color || cssVar('--text-dim') || '#888';
    ctx.lineWidth = 1.4 * dpr;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    let lastX = -Infinity;
    for (let i = 0; i < ts.length; i++) {
      const d = dirDeg[i], v = spd[i];
      if (d === null || d === undefined) continue;
      if (v === null || v === undefined || v < calm) continue;
      const x = u.valToPos(ts[i], 'x', true);
      if (x < bb.left || x > bb.left + bb.width) continue;
      if (x - lastX < everyPx * dpr) continue;
      lastX = x;
      const frac = vmax > calm ? (v - calm) / (vmax - calm) : 1;
      const len = (MIN + (MAX - MIN) * frac) * dpr;
      const a = ((Number(d) + 180) % 360) * Math.PI / 180;   /* flies downwind */
      const dx = Math.sin(a) * len, dy = -Math.cos(a) * len;
      const hx = x + dx, hy = y + dy;
      ctx.beginPath();
      ctx.moveTo(x - dx, y - dy); ctx.lineTo(hx, hy);
      for (const s of [0.75, -0.75]) {
        const b = a + Math.PI * s;
        ctx.moveTo(hx, hy);
        ctx.lineTo(hx + Math.sin(b) * len * 0.62, hy - Math.cos(b) * len * 0.62);
      }
      ctx.stroke();
    }
    ctx.restore();
  } } };
}

/* A labelled reference line. A concentration means little without the number
   it is meant to stay under, so the chart carries that number itself. */
function hLine(value, label, opts = {}) {
  return { hooks: { draw: u => {
    const bb = u.bbox, dpr = window.devicePixelRatio || 1;
    const y = u.valToPos(value, 'y', true);
    if (!(y >= bb.top && y <= bb.top + bb.height)) return;
    const ctx = u.ctx, col = opts.color || cssVar('--text-dim') || '#888';
    ctx.save();
    ctx.strokeStyle = col; ctx.lineWidth = dpr;
    ctx.setLineDash([4 * dpr, 4 * dpr]);
    ctx.beginPath(); ctx.moveTo(bb.left, y); ctx.lineTo(bb.left + bb.width, y); ctx.stroke();
    if (label) {
      ctx.setLineDash([]);
      ctx.fillStyle = col;
      ctx.font = `${9.5 * dpr}px ${getComputedStyle(document.body).fontFamily}`;
      ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
      ctx.fillText(label, bb.left + bb.width - 4 * dpr, y - 2 * dpr);
    }
    ctx.restore();
  } } };
}

/* dew point (Magnus formula) and estimated cloud base — the lifting
   condensation level: ~125 m of climb per °C of temp/dew-point spread.
   An estimate for cumulus bases, not gospel; RH near 100 % → base ~0 (fog). */
function dewPoint(tempC, rh) {
  if (tempC === null || tempC === undefined || !rh || rh <= 0) return null;
  const a = 17.62, b = 243.12;
  const g = Math.log(Math.min(rh, 100) / 100) + (a * tempC) / (b + tempC);
  return (b * g) / (a - g);
}

function cloudBaseM(tempC, rh) {
  const td = dewPoint(tempC, rh);
  if (td === null) return null;
  return Math.max(0, Math.round(125 * (tempC - td)));
}

/* theme-aware chart plumbing: colors come from CSS custom properties so the
   charts follow light/dark mode (station.js redraws on 'themechange') */
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function uplotAxis(extra = {}) {
  /* Colours are functions, not captured strings: uPlot re-reads them on every
     draw, so a chart that outlives a light/dark switch recolours on its next
     redraw instead of keeping the old theme's near-black grid on a pale page. */
  return {
    stroke: () => cssVar('--ch-axis'),
    grid: { stroke: () => cssVar('--ch-grid') },
    ticks: { stroke: () => cssVar('--ch-grid') },
    font: '11px JetBrains Mono, monospace',
    ...extra,
  };
}

function uplotBase() {
  return {
    width: 600, height: 200,
    /* hover shows a cursor line + live values in the legend; drag
       horizontally to zoom in; double-click (or double-tap) resets */
    cursor: { drag: { x: true, y: false, setScale: true } },
    legend: { live: true },
    axes: [uplotAxis(), uplotAxis({ size: 46 })],
  };
}

function makeChart(el, series, data, opts = {}) {
  const base = uplotBase();
  const o = {
    ...base,
    width: el.clientWidth || 600,
    height: opts.height || 200,
    /* line-only by default (uPlot otherwise auto-shows point markers on sparse
       series, which looked inconsistent next to the dense line charts). A caller
       can still opt a series back in with points:{show:true}. */
    series: [{}, ...series.map(s => ({ points: { show: false }, ...s }))],
    ...opts.uplot,
  };
  const u = new uPlot(o, data, el);
  /* helper series (band edges etc.) stay out of the legend */
  const rows = u.root.querySelectorAll('.u-legend .u-series');
  series.forEach((s, i) => {
    if (s.noLegend && rows[i + 1]) rows[i + 1].style.display = 'none';
  });
  if (el._ro) el._ro.disconnect();   // re-renders must not stack observers
  el._ro = new ResizeObserver(() => u.setSize({ width: el.clientWidth, height: o.height }));
  el._ro.observe(el);
  /* callers that only learn the right height after layout (see renderForecast's
     `fit`) correct it here — o.height is updated too, so the resize observer
     honors the correction instead of snapping back to the original guess */
  u.resizeHeight = (h) => { o.height = h; u.setSize({ width: el.clientWidth, height: h }); };
  return u;
}

/* Esri World Imagery — keyless, and the only basemap that shows the actual
   roof, orchard or ridge a station sits on. Native detail runs out around z18
   over the Himalaya (beyond that Esri serves a "no data" placeholder), so we
   cap maxNativeZoom and let Leaflet upscale instead. Shared by the mesh map
   and the admin siting picker so the URL and attribution live in one place. */
/* front-end config from the server (satellite key, feature flags). Fetched
   once, cached; every page that builds a map already awaits data first, so by
   the time satelliteLayer() runs this has resolved. */
let _cfg = null;
const _cfgReady = (async () => { try { _cfg = await getJSON('/config'); } catch { _cfg = {}; } })();

function satelliteLayer() {
  /* Hybrid, not bare imagery: you should be able to tell WHERE you are while
     still seeing the roof or the ridge.

     Preferred: a keyed provider (SATELLITE_TILE_URL) that bakes imagery, roads
     AND labels into one OSM-derived tileset — proper road geometry on the
     photo, and the same OpenStreetMap lineage as the streets/terrain views so
     switching layers doesn't switch cartographies.

     Fallback when no key is configured: keyless Esri imagery with OSM labels
     from CARTO. Labels harmonize with streets, but there's no road geometry —
     you read the roads off the photo itself. Deliberately NOT Esri's own
     reference tiles: their commercial road data disagrees with OSM on
     geometry, naming and which tracks exist, which is what looked wrong. */
  const sat = _cfg && _cfg.satellite;
  if (sat && sat.url) {
    return L.tileLayer(sat.url,
      { maxZoom: sat.maxZoom || 20, attribution: sat.attribution });
  }
  return L.layerGroup([
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { maxNativeZoom: 18, maxZoom: 20,
        attribution: 'Imagery © <a href="https://www.esri.com">Esri</a>, Maxar, Earthstar Geographics' }),
    /* Labels at double size: ask for the @2x tile one zoom level back and draw
       it at 512 px (tileSize 512 + zoomOffset -1). CARTO's label tiles are cut
       for 256 px, so at native size the place names came out too small to read
       over imagery — this trades a little label density for legibility, and the
       @2x asset keeps the text crisp rather than upscaled-blurry. ({r} without
       detectRetina resolved to nothing, so we were serving plain 1x tiles.) */
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png',
      { subdomains: 'abcd', tileSize: 512, zoomOffset: -1, maxNativeZoom: 18, maxZoom: 20,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/attributions">CARTO</a>' }),
  ]);
}

/* The default ("streets") basemap, shared by the mesh map and the admin siting
   picker so URL and credit live in one place — same as satelliteLayer() above.
   CARTO's keyless basemaps began serving "API KEY REQUIRED" watermark tiles
   (observed 2026-10-31), so the provider is configurable exactly like the
   satellite layer: BASEMAP_TILE_URL, plus an optional _DARK for the dark
   theme. Keyless CARTO stays as the last-resort fallback — watermarked, but a
   watermarked map still beats a blank one. Returns a bare URL string so
   callers can setUrl() it on themechange without rebuilding the layer. */
function basemapUrl(dark) {
  const bm = _cfg && _cfg.basemap;
  if (bm && bm.url) return (dark && bm.urlDark) ? bm.urlDark : bm.url;
  return `https://{s}.basemaps.cartocdn.com/${dark ? 'dark_all' : 'light_all'}/{z}/{x}/{y}{r}.png`;
}

/* Leaflet options belonging to basemapUrl(). Kept next to it deliberately:
   attribution and maxZoom are provider-specific, and taking the URL from one
   provider while keeping another's credit is how a map ends up misattributed.
   {s} subdomains are CARTO-only, so they are set only on the fallback path. */
function basemapOptions() {
  const bm = _cfg && _cfg.basemap;
  if (bm && bm.url) return { attribution: bm.attribution, maxZoom: bm.maxZoom || 20 };
  return { subdomains: 'abcd', maxZoom: 19,
           attribution: '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/attributions">CARTO</a>' };
}

/* viewer's timezone, as their locale abbreviates it ("IST", "CEST", "GMT+2").
   Every timestamp on the site is already rendered in the viewer's local time
   (toLocale* APIs) — this label just says so out loud. */
function tzLabel() {
  try {
    return new Intl.DateTimeFormat([], { timeZoneName: 'short' })
      .formatToParts(new Date()).find(p => p.type === 'timeZoneName')?.value || '';
  } catch { return ''; }
}

/* banner language preference (LLM summaries only; the rule-based fallback
   speaks English). Stored per browser. */
const LANG_KEY = 'forsyth-lang';
function bannerLang() { return localStorage.getItem(LANG_KEY) || 'en'; }

/* weather banner (shared by both pages) — present events and forecast ones.
   The kicker carries a freshness whisper ("just now" … "3 min ago") that
   turns into a real warning past 15 min — which only happens when the
   service worker is serving a cached summary to an offline device. */
function bannerFreshness(el) {
  const k = el.querySelector('.k');
  if (!k || !el.dataset.genAt) return;
  const ageMin = (Date.now() - new Date(el.dataset.genAt).getTime()) / 60000;
  /* just the freshness — the banner's voice speaks for itself */
  k.textContent = agoLabel(el.dataset.genAt) + (ageMin > 15 ? ' — may be stale' : '');
  k.classList.toggle('stale', ageMin > 15);
  el.classList.toggle('dim', ageMin > 60);
}

async function refreshBanner(slug) {
  const el = document.getElementById('wx-banner');
  if (!el) return;
  /* language toggle, built once — EN ⇄ हिं */
  if (!el.querySelector('.lang')) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'lang';
    b.title = 'banner language';
    b.textContent = bannerLang() === 'hi' ? 'हिं' : 'EN';
    b.onclick = () => {
      localStorage.setItem(LANG_KEY, bannerLang() === 'hi' ? 'en' : 'hi');
      b.textContent = bannerLang() === 'hi' ? 'हिं' : 'EN';
      refreshBanner(slug);
    };
    el.appendChild(b);
  }
  try {
    const qs = new URLSearchParams();
    if (slug) qs.set('slug', slug);
    if (bannerLang() !== 'en') qs.set('lang', bannerLang());
    /* toString(), not .size: URLSearchParams.size only arrived in Safari 17,
       and `undefined` is falsy — so every WebKit browser older than that (all
       of them on an older iPhone, Brave included) silently dropped the query
       and read the mesh-wide summary onto a station's page. */
    const query = qs.toString();
    const d = await getJSON('/summary' + (query ? `?${query}` : ''));
    if (d.summary) {
      el.querySelector('p').textContent = d.summary;
      el.dataset.genAt = d.generated_at || '';
      bannerFreshness(el);
      el.classList.add('on');
      /* tick the label between fetches so it never freezes */
      if (!el._freshTimer) el._freshTimer = setInterval(() => bannerFreshness(el), 30_000);
    } else {
      el.classList.remove('on');
    }
  } catch { el.classList.remove('on'); }
}

/* ---------- forecast (shared: station page panel + board widget) ---------- */

function wxGlyph(rainMm, prob, cloud, tempC) {
  if ((rainMm ?? 0) > 0.3 || (prob ?? 0) > 60)
    return (tempC !== null && tempC !== undefined && tempC <= 1) ? '🌨' : '🌧';
  if ((cloud ?? 0) > 70) return '☁';
  if ((cloud ?? 0) > 30) return '⛅';
  return '☀';
}

/* Renders the 6-hour strip + temp/precip chart into el (which is emptied).
   Returns the uPlot instance, or null (no chart / no forecast yet). */
async function renderForecast(el, slug, opts = {}) {
  const hours = opts.hours || 48;
  let d;
  try {
    d = await getJSON(`/stations/${slug}/forecast?hours=${hours}`);
  } catch {
    el.innerHTML = '<p class="wg-empty">No forecast yet. The worker asks the models every three hours.</p>';
    return null;
  }
  /* Same model run as last time, same window, DOM still intact → nothing to
     redraw. Forecasts change every 3 h; the refresh loop runs every minute. */
  const theme = document.documentElement.dataset.theme;
  if (opts.reuse && el._fcRun === d.run_at && el._fcTheme === theme
      && el.querySelector('.fc-strip')) {
    return el._fcPlot || null;   // strip-only widgets have no plot to return
  }
  /* rebuilding: tear the old plot down properly, or its resize observer leaks */
  if (el._fcPlot) { el._fcPlot.destroy(); el._fcPlot = null; }
  el._fcRun = d.run_at;
  el._fcTheme = theme;   // a theme switch forces a rebuild, recolouring series too

  const F = d.series;

  /* strip: the segment widens with the window, so a week reads as seven daily
     cards rather than twenty-eight six-hourly slivers */
  const segH = hours <= 48 ? 6 : hours <= 96 ? 12 : 24;
  const daily = segH >= 24;
  const segs = [];
  for (let i = 0; i < d.ts.length; i += segH) {
    const idx = [];
    for (let k = i; k < Math.min(i + segH, d.ts.length); k++) idx.push(k);
    const vals = a => idx.map(k => a[k]).filter(v => v !== null && v !== undefined);
    const avg = a => { const v = vals(a); return v.length ? v.reduce((x, y) => x + y, 0) / v.length : null; };
    const max = a => { const v = vals(a); return v.length ? Math.max(...v) : null; };
    const min = a => { const v = vals(a); return v.length ? Math.min(...v) : null; };
    const sum = a => vals(a).reduce((x, y) => x + y, 0);
    const rain = sum(F.precip_mm), prob = max(F.precip_prob);
    const t0 = new Date(d.ts[i] * 1000);
    segs.push({
      /* day and time on separate lines — side by side they collide on
         phones; explicit "21:00" because a bare "21" reads as a date */
      day: t0.toLocaleString([], { weekday: 'short' }),
      time: daily ? t0.toLocaleDateString([], { day: 'numeric', month: 'short' })
                  : t0.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }),
      /* daily cards headline the high and low, the way forecasts are read */
      temp: daily ? `${fmt(max(F.temp_c), 0)}°/${fmt(min(F.temp_c), 0)}°`
                  : `${fmt(avg(F.temp_c), 0)}°`,
      rain, prob,
      glyph: wxGlyph(rain, prob, avg(F.cloud_cover_pct), avg(F.temp_c)),
    });
  }
  el.innerHTML = `
    <div class="fc-strip${daily ? ' daily' : ''}">${segs.map(s => `
      <div class="fc-seg">
        <span class="t">${s.day}</span>
        <span class="t2">${s.time}</span>
        <span class="g">${s.glyph}</span>
        <span class="v">${s.temp}</span>
        <span class="p">${s.prob !== null ? Math.round(s.prob) + '%' :
                          s.rain > 0.2 ? s.rain.toFixed(1) + ' mm' : '·'}</span>
      </div>`).join('')}</div>
    <div class="fc-chart"></div>
    <div class="fc-foot wg-sub">model ${d.model} · run ${agoLabel(d.run_at)} · times ${tzLabel()}<span class="fc-skill"></span></div>`;

  /* signal "more →" when the strip overflows; the fade lifts at the end */
  const strip = el.querySelector('.fc-strip');
  const stripEdges = () => {
    strip.classList.toggle('scrollable', strip.scrollWidth > strip.clientWidth + 4);
    strip.classList.toggle('at-end',
      strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 4);
  };
  stripEdges();
  strip.addEventListener('scroll', stripEdges, { passive: true });

  const chartEl = el.querySelector('.fc-chart');
  if (opts.chart === false) { chartEl.remove(); return null; }

  /* fit: size the chart to whatever space is actually left after the strip and
     the footer, uPlot's own legend included — guessing at it (and forgetting
     the legend) is what made tall widgets overflow into a scrollbar */
  let chartH = opts.height || 200;
  let showLegend = true;
  if (opts.fit) {
    const stripH = el.querySelector('.fc-strip').offsetHeight;
    const footH = el.querySelector('.fc-foot').offsetHeight;
    const avail = el.clientHeight - stripH - footH - 14;   // 14 = the two margins
    const LEGEND_H = 26;
    /* In a short widget the strip, legend and footer together leave the chart
       nothing — so the legend goes rather than the chart being crushed. Hover
       still reads values off the cursor; a squashed plot reads nothing. */
    showLegend = avail - LEGEND_H >= 120;
    chartH = Math.max(90, avail - (showLegend ? LEGEND_H : 0));
  }

  /* temp line (with ensemble ±σ band when the GEFS rows exist) + rain bars */
  const hasSpread = F.temp_spread_c.some(v => v !== null);
  const series = [
    { label: '°C', stroke: cssVar('--ch-temp'), width: 1.5 },
    /* band edges are scaffolding for the shaded area — no line, and crucially
       no POINTS, which otherwise speckle the chart above and below the line */
    ...(hasSpread ? [{ label: '+σ', stroke: 'transparent', width: 0, noLegend: true,
                       points: { show: false } },
                     { label: '−σ', stroke: 'transparent', width: 0, noLegend: true,
                       points: { show: false } }] : []),
    { label: 'mm', stroke: cssVar('--ch-rain'), fill: cssVar('--ch-rain-fill'), scale: 'mm',
      points: { show: false },
      paths: uPlot.paths.bars ? uPlot.paths.bars({ size: [0.6, 100] }) : undefined },
  ];
  const data = [
    d.ts, F.temp_c,
    ...(hasSpread ? [
      F.temp_c.map((v, i) => v === null || F.temp_spread_c[i] === null ? null : v + F.temp_spread_c[i]),
      F.temp_c.map((v, i) => v === null || F.temp_spread_c[i] === null ? null : v - F.temp_spread_c[i]),
    ] : []),
    F.precip_mm,
  ];
  const u = makeChart(chartEl, series, data, {
    height: chartH,
    uplot: {
      legend: { show: showLegend, live: true },
      scales: { mm: { range: (u, mn, mx) => [0, Math.max(1, mx)] } },
      axes: [uplotAxis(), uplotAxis({ size: 46 }),
             uplotAxis({ size: 40, scale: 'mm', side: 1, grid: { show: false } })],
      ...(hasSpread ? { bands: [{ series: [2, 3],
        fill: cssVar('--ch-temp-band') || 'rgba(214, 129, 62, 0.14)' }] } : {}),
    },
  });

  /* The legend's real height is only knowable once uPlot has drawn it, so
     rather than guess again, measure what actually overflowed and give that
     much back. Run it again when the web fonts land: the strip and footer are
     measured in fallback metrics first, and Fraunces/JetBrains Mono arriving
     grows them by ~10px — which is exactly the scrollbar we were chasing. */
  if (opts.fit) {
    let curH = chartH;
    const refit = () => {
      const over = el.scrollHeight - el.clientHeight;
      if (over > 0) { curH = Math.max(90, curH - over); u.resizeHeight(curH); }
    };
    refit();
    document.fonts?.ready?.then(refit);
  }
  el._fcPlot = u;
  return u;
}

/* one dry line about how the models have actually done here — appended to
   the .fc-skill span; silent until enough forecast-vs-observed pairs exist */
async function renderSkillLine(el, slug) {
  try {
    const d = await getJSON(`/stations/${slug}/skill?days=30`);
    if (!d.n_pairs || !d.leads.length) return;
    const lead = d.leads.find(l => l.lead_h >= 18) || d.leads[d.leads.length - 1];
    const bits = [];
    if (lead.temp_mae_c !== null)
      bits.push(`temperature within ±${Math.round(lead.temp_mae_c * 10) / 10} °C about a day out`);
    if (lead.precip_pod !== null) bits.push(`${Math.round(lead.precip_pod * 100)}% of rainy hours called in advance`);
    if (bits.length) el.textContent = ` · past 30 days here: ${bits.join(', ')}`;
  } catch { /* skill is a luxury; silence is fine */ }
}
