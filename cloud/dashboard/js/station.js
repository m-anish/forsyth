/* forsyth live — station page */
'use strict';

const slug = new URLSearchParams(location.search).get('slug');
if (!slug) location.href = '/';

const S = { hours: 24, charts: {} };
/* chart colors resolve from CSS vars each draw, so charts follow the theme */
function COLs() {
  return {
    temp: cssVar('--ch-temp'), rh: cssVar('--ch-rh'), pres: cssVar('--ch-pres'),
    wind: cssVar('--ch-wind'), gust: cssVar('--ch-gust'),
    rain: cssVar('--ch-rain'), rainFill: cssVar('--ch-rain-fill'),
    pm25: cssVar('--ch-pm25'), pm10: cssVar('--ch-pm10'), batt: cssVar('--ch-batt'),
    pm25Fill: cssVar('--ch-pm25-fill'), pm10Fill: cssVar('--ch-pm10-fill'),
  };
}

document.getElementById('crumb-slug').textContent = slug;
document.getElementById('csv-link').href = `/api/v1/export/${slug}.csv?hours=${24 * 7}`;

/* ---------- header + "right now" ---------- */

/* station-to-station navigation: prev/next arrows (wrap-around), a switcher,
   and ←/→ keys. The /stations list is already slug-ordered by the API.      */
function renderStnav(stations) {
  const nav = document.getElementById('stnav');
  if (!nav) return;
  const i = stations.findIndex(x => x.slug === slug);
  if (i < 0 || stations.length < 2) {
    nav.innerHTML = '<a class="sn-all" href="/">← all stations</a>';
    return;
  }
  const prev = stations[(i - 1 + stations.length) % stations.length];
  const next = stations[(i + 1) % stations.length];
  S.prevSlug = prev.slug; S.nextSlug = next.slug;
  nav.innerHTML = `
    <a class="sn-arrow" href="station.html?slug=${prev.slug}" title="${prev.name}">←</a>
    <select id="sn-sel" aria-label="switch station">
      ${stations.map(x => `<option value="${x.slug}" ${x.slug === slug ? 'selected' : ''}>${x.name}</option>`).join('')}
    </select>
    <a class="sn-arrow" href="station.html?slug=${next.slug}" title="${next.name}">→</a>
    <a class="sn-all" href="/">all stations</a>`;
  nav.querySelector('#sn-sel').addEventListener('change', e => {
    location.href = `station.html?slug=${e.target.value}`;
  });
}

document.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.target instanceof Element &&
      e.target.matches('input, select, textarea, [contenteditable]')) return;
  if (e.key === 'ArrowLeft' && S.prevSlug) location.href = `station.html?slug=${S.prevSlug}`;
  if (e.key === 'ArrowRight' && S.nextSlug) location.href = `station.html?slug=${S.nextSlug}`;
});

async function refreshNow() {
  const { stations } = await getJSON('/stations');
  const st = stations.find(x => x.slug === slug);
  renderStnav(stations);
  if (!st) { document.getElementById('head-name').textContent = 'Unknown station.'; return; }
  S.station = st;   /* the report dialog falls back to these coords */
  Theme.place(st.lat, st.lon);   /* 'sky' needs a place for the sun's altitude */

  /* "Station · leaf-01" told a visitor nothing: the slug is a database key.
     The name is already the headline below (docs/v2-design.md §3.4). */
  document.getElementById('head-kicker').innerHTML =
    'Weather station' + (st.is_simulated ? ' &nbsp;<span class="badge sim">rehearsal data</span>' : '');
  document.getElementById('crumb-slug').textContent = st.name;
  document.getElementById('head-name').textContent = st.name;
  document.getElementById('head-sub').textContent =
    (st.lat ? `${st.lat.toFixed(3)}°N ${st.lon.toFixed(3)}°E · ${Math.round(st.elevation_m)} m` : '') +
    (st.is_simulated ? ' · This station exists only in arithmetic, for now.' : '');
  document.getElementById('seen').textContent = agoLabel(st.last_seen);

  document.getElementById('now-temp').innerHTML = `${fmt(st.temp_c, 1)}<span class="u">°C</span>`;
  document.getElementById('now-desc').textContent = describe(st);
  const cb = cloudBaseM(st.temp_c, st.rh);
  const cbLabel = cb === null ? '—' : cb < 100 ? 'on the deck' : `~${cb} m up`;
  document.getElementById('now-kv').innerHTML = `
    <div><span class="k">Humidity</span><span class="v">${fmt(st.rh, 0, '%')}</span></div>
    <div><span class="k">Wind</span><span class="v">${windText(st)}</span></div>
    <div><span class="k">Gust</span><span class="v">${gustText(st)}</span></div>
    <div><span class="k">Rain (last report)</span><span class="v">${fmt(st.rain_mm, 1)} mm</span></div>
    <div><span class="k">Dew point</span><span class="v">${fmt(dewPoint(st.temp_c, st.rh), 1)} °C</span></div>
    <div><span class="k">Cloud base (est.)</span><span class="v">${cbLabel}</span></div>`;

  /* Sea-level, not station: 838 hPa at 1676 m is correct and reads as broken
     to anyone who knows sea level is ~1013 (§3.4). The station figure stays,
     on hover, because it is the one actually measured. */
  const slpEl = document.getElementById('pres-now');
  const slpV = pressureSeaLevelHpa(st.pressure_pa, st.elevation_m, st.temp_c);
  slpEl.textContent = slpV === null ? '—' : slpV.toFixed(1);
  slpEl.title = st.pressure_pa
    ? `${(st.pressure_pa / 100).toFixed(1)} hPa measured at the station, ${Math.round(st.elevation_m)} m up`
    : '';

  /* air quality + wind rose are shared board widgets now (renderWidgets) */

  document.getElementById('hk-batt').textContent = fmt(st.batt_v, 2, ' V');
  document.getElementById('hk-solar').textContent = solarWord(st.solar_state);
  const rw = rssiWord(st.rssi_dbm);
  document.getElementById('hk-rssi').textContent =
    fmt(st.rssi_dbm, 0, ' dBm') + (rw ? ` · ${rw}` : '');
  document.getElementById('hk-seen').textContent = agoLabel(st.last_seen);
}

/* ---------- pressure trend ---------- */

async function refreshPressureTrend() {
  const d = await getJSON(`/stations/${slug}/series?metrics=pressure_pa,temp_c&hours=3`);
  const el = document.getElementById('pres-trend');
  const verdict = document.getElementById('pres-verdict');

  /* temperature gets the same treatment, in the same window */
  const tt = trendOf('temp_c', d.ts, d.series.temp_c || [], 3);
  document.getElementById('now-trend').innerHTML = trendHtml(tt);

  const pt = trendOf('pressure_pa', d.ts, d.series.pressure_pa || [], 3);
  if (!pt) {
    /* Below the barometer's noise floor is not "no data" — it is the most
       common state a barometer is in, and the verdict line already says so. */
    const vals = (d.series.pressure_pa || []).filter(v => v !== null);
    el.innerHTML = vals.length < 2 ? '<span class="tr-win">not enough data yet</span>'
                                   : '<span class="tr-win">steady over 3 h</span>';
    verdict.textContent = vals.length < 2 ? '' : 'Steady. No drama expected.';
    return;
  }
  el.innerHTML = trendHtml(pt);
  const delta = pt.delta;
  verdict.textContent =
    delta < -2.5 ? 'Falling fast. Forsyth is paying attention.' :
    delta < -0.6 ? 'Sliding. Keep the washing within reach.' :
    delta > 0.6 ? 'Rising. The sky is composing itself.' : 'Steady. No drama expected.';
}

/* ---------- charts ---------- */

function ts2data(d, keys) {
  return [d.ts, ...keys.map(k => d.series[k])];
}

/* ts2data, but a reporting outage breaks the line rather than being drawn
   across. The taper moves the leaf between 5- and 40-minute reporting, so the
   threshold is derived from the data (docs/v2-design.md §8 rule 6). */
/* Night shaded behind every history chart. The diurnal cycle is the dominant
   pattern in nearly all of these metrics, so marking it lets the shape be read
   without consulting the time axis (docs/v2-design.md §8.3). Needs the
   station's coordinates; without them the charts simply go unshaded. */
function nightPlugins(...extra) {
  const st = S.station, out = [];
  if (st && st.lat !== null && st.lat !== undefined) {
    const nb = nightBands(st.lat, st.lon);
    if (nb) out.push(nb);
  }
  return out.concat(extra.filter(Boolean));
}

function gapped(d, keys, opts) {
  return breakGaps(d.ts, keys.map(k => d.series[k] || []), undefined, opts);
}

async function drawCharts() {
  const h = S.hours;
  const [tempD, windD, presD, rainD, pmD, battD] = await Promise.all([
    getJSON(`/stations/${slug}/series?metrics=temp_c,rh&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=wind_avg_ms,wind_gust_ms,wind_dir_deg&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=pressure_pa,temp_c&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=rain_mm&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=pm25,pm10&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=batt_v&hours=${h}`),
  ]);

  for (const u of Object.values(S.charts)) u.destroy();
  const COL = COLs();

  S.charts.temp = makeChart(document.getElementById('chart-temp'), [
    { label: 'Temperature °C', stroke: COL.temp, width: 1.5 },
    { label: 'Humidity %', stroke: COL.rh, width: 1, scale: 'rh' },
  ], gapped(tempD, ['temp_c', 'rh']), {
    height: 230,
    uplot: { plugins: nightPlugins(),
             scales: { rh: { range: [0, 100] } },
             axes: [uplotAxis(), uplotAxis({ size: 46 }),
                    uplotAxis({ size: 46, scale: 'rh', side: 1, grid: { show: false } })] },
  });

  /* km/h, not m/s — nobody thinks in m/s (§7 units table). */
  const windKmh = ['wind_avg_ms', 'wind_gust_ms'].map(k =>
    (windD.series[k] || []).map(v => (v === null || v === undefined) ? null : v * 3.6));
  S.charts.wind = makeChart(document.getElementById('chart-wind'), [
    { label: 'Wind km/h', stroke: COL.wind, width: 1.5 },
    { label: 'Gust km/h', stroke: COL.gust, width: 1 },
  ], breakGaps(windD.ts, windKmh, gapThresholdS(windD.ts)), {
    uplot: {
      /* The gap between sustained and gust IS the information. Filling it
         says "this is the range the wind moved in"; two spiky lines just read
         as noise (§8). Direction rides on top as arrows — a circular quantity
         cannot go on a linear axis without 350°→10° looking like a crash. */
      bands: [{ series: [2, 1], fill: cssVar('--ch-gust-fill') }],
      plugins: nightPlugins(windDirArrows(windD.ts, windD.series.wind_dir_deg || [],
                                          windD.series.wind_gust_ms || [])),
    },
  });

  /* Sea level, matching the panel above. The two disagreed by 177 hPa while
     both were labelled "Pressure": the panel had been reduced to sea level and
     the chart was still plotting what the sensor reads at 1676 m. Reduction
     needs the temperature at each sample, which is why temp_c rides along in
     the fetch.

     The axis gutter grows with it. At 46px a six-figure label ("838.75", and
     now "1015.75") ran off the left edge and rendered as "38.75" — the leading
     digit silently cut, which is the worst way for a number to be wrong. */
  const presHpa = presD.series.pressure_pa.map((v, i) => v === null ? null
    : pressureSeaLevelHpa(v, S.station && S.station.elevation_m,
                          (presD.series.temp_c || [])[i]));
  S.charts.pres = makeChart(document.getElementById('chart-pres'), [
    { label: 'Pressure hPa', stroke: COL.pres, width: 1.5 },
  ], breakGaps(presD.ts, [presHpa], gapThresholdS(presD.ts)),
     { uplot: { plugins: nightPlugins(),
                axes: [uplotAxis(), uplotAxis({ size: 62 })] } });

  /* Already bars, and right to be: rain is accumulation since the previous
     report, so there is no meaningful value between samples (§8 rule 2). */
  S.charts.rain = makeChart(document.getElementById('chart-rain'), [
    { label: 'Rain mm', stroke: COL.rain, fill: COL.rainFill,
      paths: uPlot.paths.bars ? uPlot.paths.bars({ size: [0.8, 100] }) : undefined },
  ], gapped(rainD, ['rain_mm']), {
    /* With no rain in the window uPlot's auto-range fell back to 0–100 mm:
       a catastrophic flood, drawn as a flat line at zero. Rain is zero-based
       (§8 rule 5) and gets a floor on the top so a dry spell reads as a quiet
       chart rather than a suspiciously calm deluge. One bucket tip is
       0.2794 mm, so a 2 mm ceiling still shows a single tip clearly. */
    uplot: { plugins: nightPlugins(),
             scales: { y: { range: (u, _min, max) => [0, Math.max(2, (max || 0) * 1.25)] } } },
  });

  /* PM rides only every Nth reading. spanGaps used to connect across every
     null, which also papered over genuine outages — the line looked identical
     whether the sensor skipped a cycle or the station was down for four hours.
     Dropping the between-sample nulls and then breaking on real gaps separates
     the two, and the points show how sparse the sampling actually is (§8). */
  /* PM2.5 is a SUBSET of PM10 — "particles under 10 µm" includes "under
     2.5 µm" — so PM10 >= PM2.5 always, and two independent lines hide that.
     Drawn as nested areas instead: PM2.5 filled from zero, PM10 as the upper
     bound, and the band between them IS the coarse fraction (2.5–10 µm), which
     is the dust/pollen part and behaves quite differently from the fine
     fraction. The reading is every 6th report (~30 min), so points mark the
     real samples rather than implying a continuous trace. */
  S.charts.pm = makeChart(document.getElementById('chart-pm'), [
    { label: 'PM10 µg/m³', stroke: COL.pm10, width: 1.3, points: { show: true, size: 3.5 } },
    { label: 'PM2.5 µg/m³', stroke: COL.pm25, width: 1.6, fill: COL.pm25Fill,
      points: { show: true, size: 3.5 } },
  ], gapped(pmD, ['pm10', 'pm25'], { dropNulls: true }), {
    uplot: {
      bands: [{ series: [1, 2], fill: COL.pm10Fill }],
      /* a concentration means little without the number it should stay under */
      plugins: nightPlugins(hLine(15, 'WHO 24 h guideline')),
    },
  });

  S.charts.batt = makeChart(document.getElementById('chart-batt'), [
    { label: 'Battery V', stroke: COL.batt, width: 1.5 },
  ], gapped(battD, ['batt_v']),
     { height: 120, uplot: { plugins: nightPlugins() } });
}

/* ---------- forecast panel ---------- */

async function refreshForecast() {
  const el = document.getElementById('forecast-box');
  if (!el) return;
  if (el._uplot) { el._uplot.destroy(); el._uplot = null; }
  el._uplot = await renderForecast(el, slug, { height: 240,
    /* boot() awaits refreshNow() first, so the coordinates are in by here */
    lat: S.station && S.station.lat, lon: S.station && S.station.lon });
  const sk = el.querySelector('.fc-skill');
  if (sk) renderSkillLine(sk, slug);
}

/* charts follow the theme */
window.addEventListener('themechange', () => {
  if (Object.keys(S.charts).length) drawCharts();
  refreshForecast();
});

/* ---------- data download ---------- */

function dlTarget() {
  return document.getElementById('dl-all').checked ? 'all' : slug;
}
document.querySelectorAll('[data-dl-hours]').forEach(b => b.onclick = () => {
  location.href = `${API}/export/${dlTarget()}.csv?hours=${b.dataset.dlHours}`;
});
document.getElementById('dl-custom-btn').onclick = () => {
  const s = document.getElementById('dl-start').value;
  const e = document.getElementById('dl-end').value;
  if (!s) { alert('Pick a start date.'); return; }
  let url = `${API}/export/${dlTarget()}.csv?start=${s}T00:00:00Z`;
  if (e) url += `&end=${e}T23:59:59Z`;
  location.href = url;
};

/* range picker */
const rangeEl = document.querySelector('.range');
for (const [label, hours] of [['1 h', 1], ['6 h', 6], ['12 h', 12],
                              ['1 d', 24], ['2 d', 48], ['7 d', 168], ['30 d', 720]]) {
  const b = document.createElement('button');
  b.textContent = label;
  if (hours === S.hours) b.classList.add('on');
  b.onclick = () => {
    S.hours = hours;
    rangeEl.querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    drawCharts();
  };
  rangeEl.appendChild(b);
}

/* ---------- shared board widgets (reused from the common pool, js/widgets.js)
   so the station page and the boards render the same components, same styling.
   Air quality, the wind rose, and the lightning feed are scoped to this
   station via config.station. ---------- */

function renderWidgets() {
  const cfg = {
    aqi:       { station: slug },
    /* label:false — the panel title already says which station, and 24 h */
    windrose:  { station: slug, hours: 24, label: false },
    lightning: { station: slug, hours: 48 },
  };
  document.querySelectorAll('[data-widget]').forEach(el => {
    const w = Widgets.REGISTRY[el.dataset.widget];
    if (w) w.render(el, cfg[el.dataset.widget] || { station: slug });
  });
}

/* ---------- camera ---------- */

async function refreshCamera() {
  try {
    const f = await getJSON(`/stations/${slug}/frames/latest`);
    const panel = document.getElementById('cam-panel');
    panel.hidden = false;
    const img = document.getElementById('cam-img');
    img.src = f.url + '?t=' + Date.now();
    img.alt = `The view from ${(S.station && S.station.name) || slug}, `
            + `photographed ${agoLabel(f.ts)}`;
    document.getElementById('cam-link').href = f.url;
    /* A photograph carries no hint of its own age, so the time it was taken
       is part of the picture's meaning, not a footnote. Past half an hour the
       camera has missed several frames and the view may be nothing like it. */
    const ageMin = (Date.now() - new Date(f.ts).getTime()) / 60000;
    const capt = document.getElementById('cam-capt');
    capt.textContent = 'captured ' + agoLabel(f.ts)
      + (ageMin > 30 ? ' — the camera has gone quiet' : '');
    capt.classList.toggle('stale', ageMin > 30);
    const { timelapses } = await getJSON(`/stations/${slug}/timelapses`);
    const list = document.getElementById('tl-list');
    list.innerHTML = timelapses.slice(0, 7).map(t =>
      `<li><a href="#" data-url="${t.url}">${t.day} ▸</a></li>`).join('');
    list.querySelectorAll('a').forEach(a => a.onclick = ev => {
      ev.preventDefault();
      const v = document.getElementById('tl-video');
      v.src = a.dataset.url; v.hidden = false; v.play();
    });
  } catch { /* no camera on this station — panel stays hidden */ }
}

/* ---------- boot + polling ---------- */

async function boot() {
  await refreshNow();
  await Promise.all([drawCharts(), renderWidgets(), refreshPressureTrend(),
                     refreshCamera(), refreshBanner(slug), refreshForecast()]);
}
boot();
/* same navbar chrome as the board page: sign in / sign out, admin link */
ForsythAuth.boot();
Report.mount({ fallback: () => S.station && S.station.lat != null
  ? { lat: S.station.lat, lon: S.station.lon, name: S.station.name } : null });
/* Two cadences: the light reads follow the minute, the charts follow the data.
   Charts are deliberately NOT on the 60 s tick — drawCharts() tears every plot
   down and rebuilds it, which would throw away the reader's zoom once a minute
   (the board's chart widget avoids this by feeding the existing plot; this page
   does not, yet). The cost is that a fresh reading can reach the panels up to
   ~4 min before it reaches the graphs. */
/* Every refresh is a network call, and on the connections this site is read
   over it will sometimes fail. Three things used to go wrong when it did, all
   silently: the rejection went unhandled (so everything after the await in
   that function never ran, leaving the page half-updated); nothing recorded
   that the numbers had stopped moving; and the "last heard" label froze at
   whatever it said when the last good fetch landed — so during an outage the
   page claimed the reading was two minutes old indefinitely.

   allSettled keeps one failing endpoint from taking the others down with it,
   and the page is only called stale when the WHOLE tick failed, which is an
   outage rather than one endpoint hiccuping. */
function markStale(on) { document.body.classList.toggle('is-stale', !!on); }

async function tick(fns, label) {
  const out = await Promise.allSettled(fns.map(f => f()));
  const failed = out.filter(r => r.status === 'rejected');
  for (const f of failed) console.warn(`[forsyth] ${label} failed:`, f.reason);
  if (failed.length) markStale(failed.length === out.length);
  else markStale(false);
}

const minuteWork = () => tick(
  [refreshNow, refreshPressureTrend, renderWidgets, () => refreshBanner(slug)], 'minute refresh');
const slowWork = () => tick(
  [drawCharts, refreshCamera, refreshForecast], 'five-minute refresh');

setInterval(minuteWork, 60_000);
setInterval(slowWork, 5 * 60_000);

/* ...and neither timer runs while the tab is in the background, so refresh
   everything on the way back in rather than showing frozen readings until the
   next tick (js/common.js) */
onVisible(() => { minuteWork(); slowWork(); });
