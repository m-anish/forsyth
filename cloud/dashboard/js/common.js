/* forsyth live — shared helpers */
'use strict';

const API = '/api/v1';

/* App version — shown in the footer (esp. useful for the PWA, where a stale
   cached build is otherwise invisible). Bump alongside the asset ?v= query. */
const APP_VERSION = '0.63';
addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.app-ver').forEach(el => { el.textContent = 'v' + APP_VERSION; });
});

/* PWA: install the service worker (network-first for anything live; see sw.js).

   Never on localhost. The worker's stale-while-revalidate is safe in
   production because ?v=N makes a new asset a new URL, but in development the
   version does not move between edits — so it kept serving an edit-old copy
   of this very file from cache while tools/dev-proxy.py was answering every
   request with `cache-control: no-store`, and the page looked unchanged for
   reasons that had nothing to do with the change. It cost three debugging
   detours in one afternoon before the cause was obvious.

   A worker already registered from an earlier session is torn down too, or
   the first load after this lands would still be served by it. */
const SW_LOCAL = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)
              || location.hostname.endsWith('.localhost');
if ('serviceWorker' in navigator) {
  if (SW_LOCAL) {
    navigator.serviceWorker.getRegistrations()
      .then(rs => rs.forEach(r => r.unregister()))
      .then(() => caches.keys().then(ks => ks.forEach(k => caches.delete(k))))
      .catch(() => {});
  } else {
    addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
  }
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

/* The charge policy's own vocabulary, in words. "charging-allowed" is the
   policy state — the MCU is not inhibiting charge — not a claim that current
   is flowing, so "ready to charge" is the honest rendering. */
function solarWord(state) {
  switch (state) {
    case 'charging':         return 'charging';
    case 'charging-allowed': return 'ready to charge';
    case 'float':            return 'topped up';
    case 'discharging':      return 'running on battery';
    default:                 return state || '—';
  }
}

/* dBm means nothing to most people; the word beside it does. */
function rssiWord(dbm) {
  if (dbm === null || dbm === undefined) return '';
  if (dbm >= -70)  return 'strong';
  if (dbm >= -85)  return 'good';
  if (dbm >= -100) return 'weak';
  return 'marginal';
}
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

/* ---- trends -------------------------------------------------------------
   A trend is a RATE, not a difference, so the arrow is drawn at an angle:
   rise over run, where the run is time. A vertical arrow says only "up"; a
   diagonal one says how fast, and reads as movement through the window it
   names. The tilt is mapped from the metric's own "full tilt" rate and clamped
   to ±45°, so a gentle drift and a collapse do not look alike.

   Deliberately NOT a zigzag tracing the samples. At glyph size you cannot
   resolve more than two or three segments, so the shape would be noise rather
   than information, and it would flicker between refreshes as the window
   slides. Shape is the sparkline's job, and the chart's; a glyph's job is
   direction and pace.

   The slope is a least-squares fit across the window, not last-minus-first:
   hanging a trend on two samples means one noisy endpoint can reverse it.

   `polarity` decides colour, and it is per metric rather than per direction —
   rising air pollution is not "up, therefore good". Temperature has no
   polarity at all: warmer is neither better nor worse.                      */
const TREND_SPECS = {
  temp_c:      { unit: '°C',  dp: 1, noise: 0.3,  full: 2.0,  polarity: 'neutral' },
  pressure_pa: { unit: 'hPa', dp: 1, noise: 0.6,  full: 2.0,  polarity: 'neutral',
                 conv: v => v / 100 },
  aqi:         { unit: '',    dp: 0, noise: 5,    full: 30,   polarity: 'up-bad' },
  batt_v:      { unit: 'V',   dp: 2, noise: 0.02, full: 0.10, polarity: 'neutral' },
};

/* Returns null — meaning "say nothing" — whenever the trend would not be
   honest: too few samples, a window barely covered, or a change inside the
   instrument's noise. A trend is worth showing when it is true, not when
   there happens to be room for it. */
function trendOf(metric, ts, vals, hours) {
  const spec = TREND_SPECS[metric];
  if (!spec || !ts || !vals) return null;
  const conv = spec.conv || (v => v);
  const xs = [], ys = [];
  for (let i = 0; i < ts.length; i++) {
    const v = vals[i];
    if (v === null || v === undefined) continue;
    xs.push(ts[i]); ys.push(conv(v));
  }
  if (xs.length < 4) return null;
  if (xs[xs.length - 1] - xs[0] < hours * 3600 * 0.5) return null;
  const n = xs.length;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0, den = 0;
  for (let i = 0; i < n; i++) { const dx = xs[i] - mx; num += dx * (ys[i] - my); den += dx * dx; }
  if (!den) return null;
  const delta = (num / den) * hours * 3600;
  if (!isFinite(delta) || Math.abs(delta) < spec.noise) return null;
  const frac = Math.max(-1, Math.min(1, delta / spec.full));
  const rising = delta > 0;
  const tone = spec.polarity === 'up-bad'  ? (rising ? 'bad' : 'good')
             : spec.polarity === 'up-good' ? (rising ? 'good' : 'bad')
             : 'neutral';
  return { delta, angle: frac * 45, rising, tone, spec, hours };
}

/* The arrow points forward through time and tilts with the rate. Rotation is
   negated because SVG's y grows downward, so "up" is a negative angle. */
function trendArrow(t, size = 14) {
  return `<svg class="tr-arrow" width="${size}" height="${size}" viewBox="0 0 24 24"`
       + ` style="transform:rotate(${(-t.angle).toFixed(1)}deg)" aria-hidden="true">`
       + `<path d="M3 12 H19 M19 12 L13.5 7 M19 12 L13.5 17" fill="none"`
       + ` stroke="currentColor" stroke-width="2.4" stroke-linecap="round"`
       + ` stroke-linejoin="round"/></svg>`;
}

function trendHtml(t) {
  if (!t) return '';
  const s = t.spec;
  const sign = t.delta >= 0 ? '+' : '\u2212';
  const unit = s.unit ? `\u2009${s.unit}` : '';
  return `<span class="trend-chip tone-${t.tone}">${trendArrow(t)}`
       + `<span class="tr-val">${sign}${Math.abs(t.delta).toFixed(s.dp)}${unit}</span>`
       + `<span class="tr-win">over ${t.hours} h</span></span>`;
}

/* Convenience: slice a longer series down to the trailing `hours` and fit. */
function trendFromSeries(metric, ts, vals, hours) {
  if (!ts || !ts.length) return null;
  const cut = ts[ts.length - 1] - hours * 3600;
  const xs = [], ys = [];
  for (let i = 0; i < ts.length; i++) if (ts[i] >= cut) { xs.push(ts[i]); ys.push(vals[i]); }
  return trendOf(metric, xs, ys, hours);
}

/* Sunrise and sunset for a date and place (the standard NOAA/SunCalc
   approximation — good to about a minute at these latitudes). Returns epoch
   seconds, or null where the sun never crosses the horizon. -0.833° is the
   horizon with refraction and the sun's own radius allowed for. */
function sunTimes(dateMs, lat, lon) {
  const rad = Math.PI / 180, J1970 = 2440588, J2000 = 2451545;
  const d = dateMs / 86400000 - 0.5 + J1970 - J2000;
  const n = Math.round(d - 0.0009 - (-lon / 360));
  const Jnoon = J2000 + 0.0009 + (-lon / 360) + n;
  const M = rad * (357.5291 + 0.98560028 * (Jnoon - J2000));
  const C = rad * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M));
  const L = M + C + rad * 102.9372 + Math.PI;
  const Jtransit = Jnoon + 0.0053 * Math.sin(M) - 0.0069 * Math.sin(2 * L);
  const dec = Math.asin(Math.sin(L) * Math.sin(rad * 23.4397));
  const cosW = (Math.sin(rad * -0.833) - Math.sin(rad * lat) * Math.sin(dec)) /
               (Math.cos(rad * lat) * Math.cos(dec));
  if (cosW > 1 || cosW < -1) return null;
  const w = Math.acos(cosW) / (2 * Math.PI);
  const toEpoch = j => (j + 0.5 - J1970) * 86400;
  return { sunrise: toEpoch(Jtransit - w), sunset: toEpoch(Jtransit + w) };
}

/* sunAltitude() — how high the sun is, in degrees — is the same series as
   sunTimes above stopped a step earlier: where that solves for the time of a
   crossing, this asks where the sun is right now. It MOVED to js/theme.js,
   which the sky palette needs before first paint and which therefore loads in
   <head> while this file loads at the end of <body>. Every page that loads
   common.js loads theme.js first, so calling it from here is safe. */

/* Night shaded behind the series. The diurnal cycle is the dominant pattern in
   nearly every metric here, so marking it turns a chart into something you can
   read without consulting the time axis (docs/v2-design.md §8.3). Drawn on the
   `drawClear` hook, which fires after the canvas is cleared but before the
   series, so it sits behind the data rather than over it.

   Not a rectangle. A hard edge at sunset drew a vertical line through the
   data, and a line through a chart reads as something that HAPPENED — which is
   the one thing dusk is not. So the shading follows the sun's altitude
   instead: clear while it is 8° up, full once it is 12° down, smoothstepped
   between, which puts the half-dark point within a few minutes of sunset and
   spreads the turn over the hour and a half it actually takes at this
   latitude. Sampling altitude rather than solving for crossings also means
   there are no cases: a polar summer simply never reaches the dark end, and
   the far north's three-hour dusk draws itself at three hours wide.

   One gradient across the plot, sixty-odd stops, rebuilt per draw. Measured at
   well under a millisecond — the trigonometry is twelve operations a sample. */
function nightBands(lat, lon) {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return null;
  const ease = t => t * t * (3 - 2 * t);
  const DAY = 8, DARK = -12;            // sun altitude, degrees: clear → full
  return { hooks: { drawClear: u => {
    const bb = u.bbox, ctx = u.ctx;
    const t0 = u.scales.x.min, t1 = u.scales.x.max;
    if (t0 === undefined || t1 === undefined || t0 === null || t1 === null) return;
    if (!(t1 > t0) || !(bb.width > 0)) return;
    const col = cssVar('--night-band') || 'rgba(0,0,0,0.10)';
    if (fadeColor(col, 1) === null) return;   // unparseable token: draw nothing
    /* one stop every ~6 device pixels: finer than the eye resolves on a
       gradient, coarse enough that a wide chart stays under a hundred */
    const n = Math.max(24, Math.min(180, Math.round(bb.width / 6)));
    const g = ctx.createLinearGradient(bb.left, 0, bb.left + bb.width, 0);
    let dark = false;
    for (let i = 0; i <= n; i++) {
      const k = i / n;
      const alt = sunAltitude((t0 + (t1 - t0) * k) * 1000, lat, lon);
      const a = 1 - ease(Math.max(0, Math.min(1, (alt - DARK) / (DAY - DARK))));
      if (a > 0.01) dark = true;
      g.addColorStop(k, fadeColor(col, a));
    }
    if (!dark) return;                  // the whole window is daylight
    ctx.save();
    ctx.fillStyle = g;
    ctx.fillRect(bb.left, bb.top, bb.width, bb.height);
    ctx.restore();
  } } };
}

/* Scale a colour's alpha. Canvas gradients take colour strings and nothing
   else, so a stop built from a theme token has to be mixed by hand. Returns
   null for anything that isn't rgb()/rgba(), which is the caller's cue to fall
   back to a flat fill rather than draw nothing. */
function fadeColor(css, k) {
  const m = /^\s*rgba?\(([^)]+)\)\s*$/.exec(css || '');
  if (!m) return null;
  const p = m[1].split(',').map(v => parseFloat(v));
  if (p.length < 3 || p.slice(0, 3).some(v => !isFinite(v))) return null;
  const a = (p.length > 3 && isFinite(p[3]) ? p[3] : 1) * k;
  return `rgba(${p[0]},${p[1]},${p[2]},${a.toFixed(3)})`;
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
    return L.tileLayer(sat.url, { maxZoom: sat.maxZoom || 20,
      attribution: sat.attribution, ...retinaTileOpts(sat.url) });
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
/* Place names were unreadably small on every layer. The fix is the same one
   the fallback label layer already used: ask for the @2x tile ONE ZOOM LEVEL
   BACK and draw it at 512 CSS px. The tile then covers the same ground as two
   normal tiles, so every label, road and symbol on it renders at double size
   — and because the source has four times the pixels, it stays crisp rather
   than being upscaled. Keyed off the URL so the server config stays
   provider-agnostic: put @2x in the template and the client does the rest. */
function retinaTileOpts(url) {
  return /@2x/.test(url || '') ? { tileSize: 512, zoomOffset: -1 } : {};
}

/* Terrain, configurable like the others. The keyless OpenTopoMap fallback has
   no retina tile, so its labels stay small — that is the cost of having no
   key, not a preference. */
function terrainLayer() {
  const tr = _cfg && _cfg.terrain;
  if (tr && tr.url) {
    return L.tileLayer(tr.url, { maxZoom: tr.maxZoom || 18,
      attribution: tr.attribution, ...retinaTileOpts(tr.url) });
  }
  return L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    { attribution: '© OSM © <a href="https://opentopomap.org">OpenTopoMap</a>',
      maxZoom: 17 });
}

function basemapOptions() {
  const bm = _cfg && _cfg.basemap;
  if (bm && bm.url) return { attribution: bm.attribution, maxZoom: bm.maxZoom || 20,
                             ...retinaTileOpts(bm.url) };
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

/* A sparkline: the shape of the last day, no axes, no legend, no labels. It
   answers "is this normal for today?" in a glance and costs almost nothing
   (docs/v2-design.md §8.3). Nulls break the path rather than being bridged,
   for the same reason the full charts break on an outage. */
function sparkline(vals, opts = {}) {
  const real = vals.filter(v => v !== null && v !== undefined);
  if (real.length < 2) return '';
  const w = opts.width || 240, h = opts.height || 30, pad = 1.5;
  let min = Math.min(...real), max = Math.max(...real);
  /* a flat day is still a line, not a divide-by-zero */
  if (max - min < 0.5) { const m = (max + min) / 2; min = m - 0.25; max = m + 0.25; }
  const n = vals.length;
  let d = '', pen = false;
  for (let i = 0; i < n; i++) {
    const v = vals[i];
    if (v === null || v === undefined) { pen = false; continue; }
    const x = (i / (n - 1)) * w;
    const y = pad + (h - 2 * pad) * (1 - (v - min) / (max - min));
    d += `${pen ? ' L' : ' M'}${x.toFixed(1)},${y.toFixed(1)}`;
    pen = true;
  }
  if (!d) return '';
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"`
       + ` aria-hidden="true"><path d="${d.trim()}"/></svg>`;
}

/* ---------- forecast (shared: station page panel + board widget) ---------- */

/* Is it dark at this place and instant? sunTimes() resolves to the solar day
   nearest the timestamp, which is what makes 23:00 answer against the sunrise
   still to come rather than the one already past. An unknown place returns
   null — the icons then keep their daytime form instead of guessing. */
function isNight(tsSec, lat, lon) {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return null;
  const s = sunTimes(tsSec * 1000, lat, lon);
  if (!s) return null;              // polar day or night: no crossing to read
  return tsSec < s.sunrise || tsSec > s.sunset;
}

/* The sky as one of five states. Cloud cover only the model has; the station
   cannot see the sky. */
function wxKind(rainMm, prob, cloud, tempC) {
  if ((rainMm ?? 0) > 0.3 || (prob ?? 0) > 60)
    return (tempC !== null && tempC !== undefined && tempC <= 1) ? 'snow' : 'rain';
  if ((cloud ?? 0) > 70) return 'cloud';
  if ((cloud ?? 0) > 30) return 'partly';
  return 'clear';
}

/* Drawn, not typed. Emoji has no moon behind a cloud — the one state a weather
   icon needs most between sunset and sunrise — and what it does have arrives
   as full-colour Apple/Noto art for some codepoints and flat text symbols for
   others, so a row of them was never one set to begin with. Seven shapes in
   the page's own two or three colours, and the theme owns every one of them. */
const WX_CLOUD = '<circle cx="8.6" cy="13.2" r="3.9"/><circle cx="12.6" cy="11.3" r="4.6"/>'
               + '<circle cx="16.4" cy="13.6" r="3.4"/>'
               + '<rect x="4.7" y="13.4" width="14.6" height="4.2" rx="2.1"/>';
/* a crescent: one disc with a slightly tighter one taken out of its right */
const WX_MOON = 'M16.5 4.2A8.4 8.4 0 1 0 16.5 19.8A8.2 8.2 0 0 1 16.5 4.2Z';

function wxSun(cx, cy, r, r1, r2) {
  let rays = '';
  for (let i = 0; i < 8; i++) {
    const t = i * Math.PI / 4, dx = Math.cos(t), dy = Math.sin(t);
    rays += `<line x1="${(cx + dx * r1).toFixed(2)}" y1="${(cy + dy * r1).toFixed(2)}"`
          + ` x2="${(cx + dx * r2).toFixed(2)}" y2="${(cy + dy * r2).toFixed(2)}"/>`;
  }
  return `<circle cx="${cx}" cy="${cy}" r="${r}"/><g class="ray">${rays}</g>`;
}

/* Said aloud, because the icon is the only place the sky state appears — the
   card already carries the temperature and the chance of rain, but nothing
   else on it says "cloudy". The emoji it replaces were announced by name. */
const WX_SAID = {
  clear: 'Clear', 'clear-night': 'Clear, night',
  partly: 'Partly cloudy', 'partly-night': 'Partly cloudy, night',
  cloud: 'Overcast', rain: 'Rain', snow: 'Snow',
};

function wxIcon(kind, night) {
  const k = night && (kind === 'clear' || kind === 'partly') ? kind + '-night' : kind;
  const cloud = (t) => `<g class="cloud" transform="${t}">${WX_CLOUD}</g>`;
  const moon = (t) => `<path class="moon" d="${WX_MOON}" transform="${t}"/>`;
  let body;
  switch (k) {
    case 'clear':
      body = `<g class="sun">${wxSun(12, 12, 3.9, 6.1, 8.6)}</g>`; break;
    case 'clear-night':
      body = moon('translate(1.7 0)'); break;
    /* sun or moon up and to the left, cloud across the lower right: the
       overlap is what makes it read as one sky rather than two symbols */
    case 'partly':
      body = `<g class="sun">${wxSun(8.4, 8, 2.9, 4.6, 6.5)}</g>`
           + cloud('translate(3.6 4.4) scale(0.82)'); break;
    case 'partly-night':
      body = moon('translate(0.9 0.2) scale(0.56)')
           + cloud('translate(3.6 4.4) scale(0.82)'); break;
    case 'cloud':
      body = cloud('translate(0 1.2)'); break;
    case 'rain':
      body = cloud('translate(0 -1.4) scale(0.95)')
           + '<g class="drop"><line x1="9.1" y1="16.4" x2="8.1" y2="20.4"/>'
           + '<line x1="12.5" y1="17" x2="11.5" y2="21"/>'
           + '<line x1="15.9" y1="16.4" x2="14.9" y2="20.4"/></g>'; break;
    /* dots rather than asterisks: a six-spoke flake at 17px is sub-pixel
       strokes, which the browser renders as a grey smudge */
    case 'snow':
      body = cloud('translate(0 -1.4) scale(0.95)')
           + '<g class="flake"><circle cx="8.8" cy="18.2" r="1.3"/>'
           + '<circle cx="12.2" cy="20.4" r="1.3"/>'
           + '<circle cx="15.6" cy="18.2" r="1.3"/></g>'; break;
    default: return '';
  }
  return '<svg class="wx-ico" viewBox="0 0 24 24" role="img"'
       + ` aria-label="${WX_SAID[k] || ''}">${body}</svg>`;
}

/* the model numbers straight to an icon, for the two callers that hold them */
function wxGlyph(rainMm, prob, cloud, tempC, night) {
  return wxIcon(wxKind(rainMm, prob, cloud, tempC), night);
}

/* ---------- the scene (docs/sky-design.md §4) ----------------------------

   The same vocabulary as wxIcon above, enlarged to wallpaper scale: a sun's
   glow where the sun actually is, a crescent, clouds as three circles over a
   rounded rect, rain as slanted strokes, snow as dots. Reusing that vocabulary
   is the strongest argument for the whole idea — the page already has a visual
   language for weather, and this is that language at a different size rather
   than a second one competing with it.

   It draws into a band of its own at the top of the hero card (css/dash.css,
   .hero-sky), never behind the hero's text. That is not a detail: a scene
   behind text has to be dimmed until it clears AA against the smallest thing
   over it, which on the dark palette meant an alpha of 0.04 — a picture dimmed
   out of existence. Given its own space it can simply be drawn.

   The viewBox is 400x60 and the band is `slice`d from it, so whichever axis
   is long gets cropped. A hero card is 60px tall and anywhere from about
   280px wide (three of twelve columns) to the full width of the board, so the
   long axis is nearly always horizontal and the crop is VERTICAL: at an
   aspect of 10:1 only the middle two thirds of the viewBox is on screen.

   So the ink keeps inside y 10..50 and nothing is composed at the edges. Two
   earlier versions got this wrong the same way — a 400x80 box in a 54px band,
   then this one laid out across the full 60 — and both times the clouds lost
   their bumps and rendered as grey pills that read as loading skeletons. The
   beams are the exception and are meant to be cut: light arrives from off the
   top of the card rather than starting inside it.

   One <svg> in the DOM at a time, no images, no library, nothing on the
   critical path, around 300-1,800 bytes of markup.

   Motion (phase 4) is CSS on the groups and lives in css/dash.css: rain and
   snow fall, clouds drift, and nothing else moves — a clear sky does not, for
   the good reason that it does not. transform and opacity only, three moving
   groups at the most, nothing faster than a 2.2 s loop, paused while the tab
   is hidden, and gone entirely under prefers-reduced-motion. */

/* gradients need document-unique ids: a board may hold two `now` widgets, and
   two <defs> sharing an id means the second one silently wins for both. */
let WX_SCENE_N = 0;

/* A cloud form at wallpaper scale, placed by the corner you can actually see.

   The icon's cloud does not start at its own origin: inside the 24-box its ink
   runs x 4.7..19.9 and y 6.7..17.6, so a bare translate(40 18) put the top of
   the shape at y=50 rather than 18. Taking the ink's left and top and solving
   for the transform means the number in the call is the number on the screen,
   which is the only way the composition above is checkable by reading it. */
const WX_CLOUD_INK = { x: 4.7, y: 6.7, w: 15.2, h: 10.9 };

/* `drift` is 1, 2 or 0 — which of the two drift tracks this cloud rides, or
   none. Named by the caller rather than worked out positionally: the obvious
   :nth-of-type(-n+2) counts every <g> SIBLING, so the beams group and the
   moon group were being counted as clouds and a partly-cloudy night ended up
   with nothing moving at all. A cloud that drifts should say so. */
function wxSceneCloud(left, top, k, o, drift = 0) {
  const tx = (left - WX_CLOUD_INK.x * k).toFixed(1);
  const ty = (top - WX_CLOUD_INK.y * k).toFixed(1);
  /* Two groups, not one. A CSS `transform` REPLACES an element's transform
     attribute rather than composing with it, so animating .cl directly would
     throw away the translate and scale that place it. The outer group is the
     only thing the drift animation touches. */
  return `<g class="cl-d${drift ? ' cl-d' + drift : ''}">`
       + `<g class="cl" transform="translate(${tx} ${ty}) scale(${k})"`
       + ` opacity="${o}">${WX_CLOUD}</g></g>`;
}

/* Deterministic scatter: the same card draws the same stars every render, so a
   refresh does not reshuffle the sky. A hash, not Math.random. */
function wxSceneStars(n) {
  let out = '';
  for (let i = 0; i < n; i++) {
    const h = Math.sin(i * 12.9898) * 43758.5453, f = h - Math.floor(h);
    const g = Math.sin(i * 78.233) * 12345.6789, f2 = g - Math.floor(g);
    out += `<circle cx="${(f * 384 + 8).toFixed(1)}" cy="${(f2 * 22 + 13).toFixed(1)}"`
         + ` r="${(1 + f2 * 1.2).toFixed(2)}" opacity="${(0.4 + f * 0.6).toFixed(2)}"/>`;
  }
  return `<g class="st">${out}</g>`;
}

/* Falling things are drawn as TILES, stacked, so the group can be translated
   by exactly one tile height and loop with nothing to see at the seam.

   Translating a single row by its own height does not work: at the halfway
   point the row has left the top of the band and nothing has arrived to take
   its place, so the rain visibly thins and then snaps. Rows a tile apart,
   covering one tile above the band and one below, leave no frame uncovered.
   WX_TILE is that height, and the animation in css/dash.css must translate by
   exactly it — they are two halves of one number. */
const WX_TILE = 20;

function wxSceneFall(kind, perRow, draw) {
  let out = '';
  /* -1 is the row waiting above the band; 3 carries it past the bottom */
  for (let row = -1; row <= 3; row++) {
    const base = row * WX_TILE;
    for (let i = 0; i < perRow; i++) {
      /* a third of a tile of jitter, so a row does not read as a ruled line */
      out += draw(18 + i * (376 / perRow) + (i % 2) * 9, base + (i % 3) * 6);
    }
  }
  return `<g class="${kind}">${out}</g>`;
}

/* Slanted strokes, spaced so they read as rain rather than as hatching. */
function wxSceneRain() {
  return wxSceneFall('rn', 7,
    (x, y) => `<line x1="${x.toFixed(0)}" y1="${y}" x2="${(x - 4).toFixed(0)}" y2="${y + 11}"/>`);
}

function wxSceneSnow() {
  return wxSceneFall('sn', 6, (x, y) => `<circle cx="${x.toFixed(0)}" cy="${y}" r="2"/>`);
}

/* Crepuscular rays, fanning from wherever the sun is. Narrow wedges rather
   than lines: a beam of light widens with distance, and a constant-width
   stroke reads as a scratch on the glass instead.

   Drawn from an apex at 0,0 so the group can be placed by a translate and
   then rocked about that apex by css (.bm, transform-origin 0 0). The apex
   sits a little ABOVE the band's top edge, which is why the wedges are never
   seen to converge — light arrives, it does not emanate from a point you can
   see on the card. */
function wxSceneBeams(n = 5) {
  const R = 110, rad = Math.PI / 180;
  let out = '';
  for (let i = 0; i < n; i++) {
    /* uneven spacing: evenly fanned beams read as a logo, not as weather */
    const t = (-46 + i * (92 / (n - 1)) + (i % 2 ? 5 : -3));
    const w = 2.1 + (i % 3) * 0.9;
    const p1 = [R * Math.sin((t - w) * rad), R * Math.cos((t - w) * rad)];
    const p2 = [R * Math.sin((t + w) * rad), R * Math.cos((t + w) * rad)];
    out += `<polygon points="0,0 ${p1[0].toFixed(1)},${p1[1].toFixed(1)}`
         + ` ${p2[0].toFixed(1)},${p2[1].toFixed(1)}"/>`;
  }
  return `<g class="bm">${out}</g>`;
}

/* The six states. `sunX` is 0..1 across the card and comes from the sun's real
   azimuth (Sky.sunX), so the light sits where the light is and drifts across
   the card over a day instead of sitting in a corner like a logo. */
function wxScene(kind, night, sunX) {
  const id = 'wxs' + (++WX_SCENE_N);
  const cx = Math.round(Math.min(0.9, Math.max(0.1, sunX ?? 0.5)) * 100);
  /* Beams lean AWAY from the sun's side: a sun on the left throws its light
     down and to the right. 34° at the extremes is about as far as the fan can
     lean before it starts leaving the band through the side.

     Negative for a sun on the left, because SVG's positive rotation is
     CLOCKWISE and a downward fan rotated clockwise swings to the left — the
     first version had it the other way and the beams leaned back towards the
     sun while the temperature's shadow fell correctly away from it, the two
     halves of the same lighting disagreeing on the same card. */
  const slant = (((sunX ?? 0.5) - 0.5) * 2 * 34).toFixed(1);
  /* A disc at this size reads as a logo, so a clear sky is light and no disc.
     The drawn sun stays in the hero's own glyph, small enough to be an icon. */
  const glow = `<defs><radialGradient id="${id}" cx="${cx}%" cy="8%" r="72%">`
             + `<stop offset="0" class="g0"/><stop offset="1" class="g1"/>`
             + `</radialGradient></defs>`
             + `<rect width="400" height="60" fill="url(#${id})"/>`
             /* The rays hang off the point the glow is centred on, and lean
                the way the light actually leans: straight down at noon, and
                further off vertical the lower the sun gets. `slant` is the
                same number the hero's shadow is built from, so the beams and
                the shadow under the temperature always agree about which
                side the light is on. */
             + `<g class="bm-o" transform="translate(${cx * 4} -16) rotate(${slant})">`
             + `${wxSceneBeams()}</g>`;
  /* A crescent, small and high. Fixed, and NOT at sunX: the moon is not where
     the sun is, nothing here computes a lunar ephemeris, and an illustration
     put in a precise wrong place is worse than one that does not claim. */
  const moon = `<g class="mn" transform="translate(308 7) scale(1.3)">`
             + `<path d="${WX_MOON}"/></g>`;

  let body;
  switch (kind) {
    case 'clear':
      body = night ? wxSceneStars(11) + moon : glow; break;
    case 'partly':
      body = (night ? wxSceneStars(7) + moon : glow)
           + wxSceneCloud(30, 14, 2.8, 0.95, 1) + wxSceneCloud(216, 11, 3.1, 0.7, 2); break;
    case 'cloud':
      /* No glow — an overcast sky is the one state with no light in it — and
         four forms that OVERLAP rather than three that sit apart. Overcast is
         read as coverage before it is read as colour: three tidy clouds with
         gaps between them is just a partly-cloudy sky that lost its sun. The
         extra weight on top of that comes from .wx-cloud in css/dash.css. */
      body = wxSceneCloud(-16, 13, 3.0, 0.95) + wxSceneCloud(92, 10, 3.4, 0.85, 1)
           + wxSceneCloud(206, 15, 2.8, 0.8) + wxSceneCloud(300, 11, 3.2, 0.7, 2);
      break;
    case 'rain':
      body = wxSceneCloud(22, 12, 2.8, 0.9, 1) + wxSceneCloud(232, 10, 3.0, 0.7, 2)
           + wxSceneRain(); break;
    case 'snow':
      body = wxSceneCloud(22, 12, 2.8, 0.9, 1) + wxSceneCloud(232, 10, 3.0, 0.7, 2)
           + wxSceneSnow(); break;
    default: return '';
  }
  /* aria-hidden: the hero's own glyph already says what the sky is doing, in
     words, to a screen reader. Saying it twice is noise. */
  /* the state rides on the element: css should be able to say "overcast is
     heavier" without js having to encode what heavier means */
  return `<svg class="wx-scene wx-${kind}${night ? ' wx-night' : ''}"`
       + ` viewBox="0 0 400 60" preserveAspectRatio="xMidYMid slice"`
       + ` aria-hidden="true" focusable="false">${body}</svg>`;
}

/* Renders the 6-hour strip + temp/precip chart into el (which is emptied).
   Returns the uPlot instance, or null (no chart / no forecast yet).

   opts.lat/opts.lon are the station's: without them the strip cannot know
   which of its cards are after dark, and the chart cannot shade the nights.
   Both degrade to their daytime selves rather than refusing to draw. */
async function renderForecast(el, slug, opts = {}) {
  const hours = opts.hours || 48;
  let d;
  try {
    /* through Sky, not straight to the API: it dedupes the requests a board's
       parallel widgets would otherwise each open, and the response it caches
       is the one the hero's glyph reads. */
    d = await Sky.forecast(slug, hours);
  } catch {
    el.innerHTML = '<p class="wg-empty">No forecast yet. The worker asks the models every three hours.</p>';
    return null;
  }
  /* Same model run as last time, same window, DOM still intact → nothing to
     redraw. Forecasts change every 3 h; the refresh loop runs every minute. */
  const theme = document.documentElement.dataset.theme;
  /* The run is not the only thing that goes stale. The window itself slides
     with the clock (the API answers from now − 1 h), and so does which card
     has a moon on it — a strip held since before sunset would still be showing
     suns at nine in the evening. An hour is the coarsest bucket that cannot
     get that wrong by more than an hour, and costs one rebuild. */
  const hourKey = Math.floor(Date.now() / 3600000);
  if (opts.reuse && el._fcRun === d.run_at && el._fcTheme === theme
      && el._fcHour === hourKey && el.querySelector('.fc-strip')) {
    return el._fcPlot || null;   // strip-only widgets have no plot to return
  }
  /* rebuilding: tear the old plot down properly, or its resize observer leaks */
  if (el._fcPlot) { el._fcPlot.destroy(); el._fcPlot = null; }
  el._fcRun = d.run_at;
  el._fcTheme = theme;   // a theme switch forces a rebuild, recolouring series too
  el._fcHour = hourKey;

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
    /* Sun or moon is decided by the time printed on the card, not by the
       middle of the six hours it covers. The midpoint is arguably the better
       average — but it put a moon on a card headed 15:30, and a reader checks
       an icon against the label beside it, not against a window they cannot
       see. A daily card spans both and gets neither: a 24 h summary with a
       moon on it would simply be wrong. */
    const night = daily ? false : isNight(d.ts[i], opts.lat, opts.lon);
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
      glyph: wxGlyph(rain, prob, avg(F.cloud_cover_pct), avg(F.temp_c), night),
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
  /* Runs on every scroll frame, so it does no DOM lookups and writes nothing
     that has not changed — a redundant class write still invalidates style,
     and on a masked element that means a repaint per frame. */
  let edgeMore = null, edgeEnd = null;
  const stripEdges = () => {
    const ch = el.querySelector('.fc-chart');
    const more = strip.scrollWidth > strip.clientWidth + 4;
    const end = strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 4;
    if (more !== edgeMore) {
      edgeMore = more;
      strip.classList.toggle('scrollable', more);
      if (ch) ch.classList.toggle('scrollable', more);
    }
    if (end !== edgeEnd) {
      edgeEnd = end;
      strip.classList.toggle('at-end', end);
      /* the chart is the same window, so it carries the same "more →" edge */
      if (ch) ch.classList.toggle('at-end', end);
    }
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
  /* Fix the vertical scale to the WHOLE forecast, not the visible slice.
     uPlot re-fits y to whatever is on screen, so scrolling the strip changed
     the shape of the curve underneath it: a calm stretch got stretched to fill
     the card and read as weather, and two parts of the forecast could not be
     compared because each was drawn to its own scale. A fixed range means the
     shape you see is the shape that exists.

     Not a performance fix — setScale measures 0.1 ms either way (the drag
     stutter was scroll-snap, not redraw cost). This is about the chart telling
     the truth while it moves.

     Series 1..n-1 are the temperature line and, when the ensemble is in, its
     ±σ band edges; the last series is precipitation on its own 'mm' scale. */
  const tVals = [];
  for (let si = 1; si < data.length - 1; si++)
    for (const v of data[si]) if (v !== null && v !== undefined) tVals.push(v);
  const pVals = (F.precip_mm || []).filter(v => v !== null && v !== undefined);
  const tMin = tVals.length ? Math.min(...tVals) : null;
  const tMax = tVals.length ? Math.max(...tVals) : null;
  /* a little headroom, and a floor so a dead-flat day is not a single line
     pinned to the frame */
  const tPad = tMin === null ? 0 : Math.max(0.5, (tMax - tMin) * 0.08);
  const pMax = Math.max(1, ...(pVals.length ? pVals : [0]));
  const nights = nightBands(opts.lat, opts.lon);

  const u = makeChart(chartEl, series, data, {
    height: chartH,
    uplot: {
      legend: { show: showLegend, live: true },
      /* Drag-zoom off: the chart and the strip are linked now, and dragging to
         zoom and dragging to scroll cannot both own the same gesture. Scrolling
         is what a forecast is read with. Hover still reads values. */
      cursor: { drag: { x: false, y: false, setScale: false } },
      scales: {
        mm: { range: [0, pMax] },
        ...(tMin !== null ? { y: { range: [tMin - tPad, tMax + tPad] } } : {}),
      },
      /* The rain axis shares no gridlines with the temperature axis, so its
         tick marks landed at heights nothing else sits at and read as a
         misprint along the right edge. Labels stay; the stray dashes go. */
      axes: [uplotAxis(), uplotAxis({ size: 46 }),
             uplotAxis({ size: 40, scale: 'mm', side: 1,
                         grid: { show: false }, ticks: { show: false } })],
      ...(hasSpread ? { bands: [{ series: [2, 3],
        fill: cssVar('--ch-temp-band') || 'rgba(214, 129, 62, 0.14)' }] } : {}),
      /* The nights, shaded, same as every chart on the station page. A
         forecast is read as "when", and the overnight dip in the temperature
         line means nothing until you can see which part of it is overnight. */
      ...(nights ? { plugins: [nights] } : {}),
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

  /* The strip and the chart are two views of the same window, so moving one
     moves the other. Without this the bubbles slide and the graph beneath them
     sits still, which reads as two unrelated things that happen to be stacked.
     The chart PANS rather than scrolls — its axes stay put and only the data
     moves, so the y-scale and the time labels remain readable.

     Throttled to one frame: setScale redraws, and redrawing on every scroll
     event stalls momentum scrolling on a phone. */
  if (u && strip) {
    const t0 = d.ts[0], t1 = d.ts[d.ts.length - 1], span = t1 - t0;
    const syncFromStrip = () => {
      const over = strip.scrollWidth - strip.clientWidth;
      if (over <= 4 || !span) { u.setScale('x', { min: t0, max: t1 }); return; }
      const frac = strip.clientWidth / strip.scrollWidth;
      const start = strip.scrollLeft / strip.scrollWidth;
      u.setScale('x', { min: t0 + span * start, max: t0 + span * (start + frac) });
    };
    let raf = 0;
    strip.addEventListener('scroll', () => {
      if (fromX !== null) return;   /* a drag already panned it, in frame */
      if (raf) return;
      raf = requestAnimationFrame(() => { raf = 0; syncFromStrip(); });
    }, { passive: true });
    syncFromStrip();

    /* The chart is grabbable too. Only the bubbles were, so the half of the
       widget most people would instinctively drag — the graph — did nothing.
       pan-y keeps vertical page scrolling with the page; horizontal belongs
       to us. */
    chartEl.style.touchAction = 'pan-y';
    chartEl.style.cursor = 'grab';
    let fromX = null, fromScroll = 0, wantScroll = 0, dragRaf = 0;
    chartEl.addEventListener('pointerdown', e => {
      fromX = e.clientX; fromScroll = strip.scrollLeft; wantScroll = fromScroll;
      chartEl.style.cursor = 'grabbing';
      /* Snap OFF for the duration. Measured, the redraw and the scroll write
         are 0.1 ms each — the cost was never the work. With scroll-snap live,
         every programmatic scrollLeft starts the browser settling toward a
         snap point, which we then overwrite on the next frame: the gesture
         and the snapping fight each other. The strip feels smooth because a
         real finger-scroll snaps WITH the browser, not against it. */
      strip.style.scrollSnapType = 'none';
      try { chartEl.setPointerCapture(e.pointerId); } catch {}
    });
    /* A pointermove can fire several times per frame, and each write of
       scrollLeft forces a synchronous layout, fires a scroll event and
       redraws the chart. Doing that three or four times for one painted frame
       is what made the drag feel like it was catching on something. Record
       the wanted position; apply it once, in the frame. */
    chartEl.addEventListener('pointermove', e => {
      if (fromX === null) return;
      wantScroll = fromScroll - (e.clientX - fromX);
      if (dragRaf) return;
      dragRaf = requestAnimationFrame(() => {
        dragRaf = 0;
        if (fromX === null) return;
        strip.scrollLeft = wantScroll;
        /* Pan in the SAME frame. Waiting for the strip's scroll event to
           schedule its own rAF put the chart a whole frame behind the finger,
           which reads as roughness even when nothing is dropped. */
        syncFromStrip();
      });
    }, { passive: true });
    const endDrag = e => {
      fromX = null; chartEl.style.cursor = 'grab';
      if (dragRaf) { cancelAnimationFrame(dragRaf); dragRaf = 0; }
      strip.style.scrollSnapType = '';     /* snap back on for finger-scrolls */
      try { chartEl.releasePointerCapture(e.pointerId); } catch {}
    };
    chartEl.addEventListener('pointerup', endDrag);
    chartEl.addEventListener('pointercancel', endDrag);
    /* a sideways trackpad swipe over the chart, too */
    chartEl.addEventListener('wheel', e => {
      if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
      e.preventDefault();
      strip.scrollLeft += e.deltaX;
    }, { passive: false });
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
