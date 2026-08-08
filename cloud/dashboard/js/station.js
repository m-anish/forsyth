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

  document.getElementById('head-kicker').innerHTML =
    `Station · ${slug}` + (st.is_simulated ? ' &nbsp;<span class="badge sim">rehearsal data</span>' : '');
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
    <div><span class="k">Wind</span><span class="v">${fmt(st.wind_avg_ms, 1)} m/s ${dirName(st.wind_dir_deg)}</span></div>
    <div><span class="k">Gust</span><span class="v">${fmt(st.wind_gust_ms, 1)} m/s</span></div>
    <div><span class="k">Rain (last report)</span><span class="v">${fmt(st.rain_mm, 1)} mm</span></div>
    <div><span class="k">Dew point</span><span class="v">${fmt(dewPoint(st.temp_c, st.rh), 1)} °C</span></div>
    <div><span class="k">Cloud base (est.)</span><span class="v">${cbLabel}</span></div>`;

  document.getElementById('pres-now').textContent = st.pressure_pa ? (st.pressure_pa / 100).toFixed(1) : '—';

  /* air quality + wind rose are shared board widgets now (renderWidgets) */

  document.getElementById('hk-batt').textContent = fmt(st.batt_v, 2, ' V');
  document.getElementById('hk-solar').textContent = st.solar_state ?? '—';
  document.getElementById('hk-rssi').textContent = fmt(st.rssi_dbm, 0, ' dBm');
  document.getElementById('hk-seen').textContent = agoLabel(st.last_seen);
}

/* ---------- pressure trend ---------- */

async function refreshPressureTrend() {
  const d = await getJSON(`/stations/${slug}/series?metrics=pressure_pa&hours=3`);
  const vals = d.series.pressure_pa.filter(v => v !== null);
  const el = document.getElementById('pres-trend');
  const verdict = document.getElementById('pres-verdict');
  if (vals.length < 2) { el.textContent = 'not enough data'; return; }
  const delta = (vals[vals.length - 1] - vals[0]) / 100; // hPa
  const arrow = delta > 0.6 ? '↑' : delta < -0.6 ? '↓' : '→';
  el.textContent = `${arrow} ${delta >= 0 ? '+' : ''}${delta.toFixed(1)} hPa over 3 h`;
  el.className = 'trend ' + (delta > 0.6 ? 'up' : delta < -0.6 ? 'down' : 'flat');
  verdict.textContent =
    delta < -2.5 ? 'Falling fast. Forsyth is paying attention.' :
    delta < -0.6 ? 'Sliding. Keep the washing within reach.' :
    delta > 0.6 ? 'Rising. The sky is composing itself.' : 'Steady. No drama expected.';
}

/* ---------- charts ---------- */

function ts2data(d, keys) {
  return [d.ts, ...keys.map(k => d.series[k])];
}

async function drawCharts() {
  const h = S.hours;
  const [tempD, windD, presD, rainD, pmD, battD] = await Promise.all([
    getJSON(`/stations/${slug}/series?metrics=temp_c,rh&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=wind_avg_ms,wind_gust_ms&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=pressure_pa&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=rain_mm&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=pm25,pm10&hours=${h}`),
    getJSON(`/stations/${slug}/series?metrics=batt_v&hours=${h}`),
  ]);

  for (const u of Object.values(S.charts)) u.destroy();
  const COL = COLs();

  S.charts.temp = makeChart(document.getElementById('chart-temp'), [
    { label: '°C', stroke: COL.temp, width: 1.5 },
    { label: '%RH', stroke: COL.rh, width: 1, scale: 'rh' },
  ], ts2data(tempD, ['temp_c', 'rh']), {
    height: 230,
    uplot: { scales: { rh: { range: [0, 100] } },
             axes: [uplotAxis(), uplotAxis({ size: 46 }),
                    uplotAxis({ size: 46, scale: 'rh', side: 1, grid: { show: false } })] },
  });

  S.charts.wind = makeChart(document.getElementById('chart-wind'), [
    { label: 'avg m/s', stroke: COL.wind, width: 1.5 },
    { label: 'gust m/s', stroke: COL.gust, width: 1, dash: [4, 4] },
  ], ts2data(windD, ['wind_avg_ms', 'wind_gust_ms']));

  S.charts.pres = makeChart(document.getElementById('chart-pres'), [
    { label: 'hPa', stroke: COL.pres, width: 1.5 },
  ], [presD.ts, presD.series.pressure_pa.map(v => v === null ? null : v / 100)]);

  S.charts.rain = makeChart(document.getElementById('chart-rain'), [
    { label: 'mm', stroke: COL.rain, fill: COL.rainFill,
      paths: uPlot.paths.bars ? uPlot.paths.bars({ size: [0.8, 100] }) : undefined },
  ], ts2data(rainD, ['rain_mm']));

  /* PM is sparse (rides only every Nth reading), so spanGaps connects across
     the null gaps into a continuous line — no point markers (line-only, like
     the other charts; makeChart defaults points off). */
  S.charts.pm = makeChart(document.getElementById('chart-pm'), [
    { label: 'PM2.5', stroke: COL.pm25, width: 1.5, spanGaps: true },
    { label: 'PM10', stroke: COL.pm10, width: 1, spanGaps: true },
  ], ts2data(pmD, ['pm25', 'pm10']));

  S.charts.batt = makeChart(document.getElementById('chart-batt'), [
    { label: 'V', stroke: COL.batt, width: 1.5 },
  ], ts2data(battD, ['batt_v']), { height: 120 });
}

/* ---------- forecast panel ---------- */

async function refreshForecast() {
  const el = document.getElementById('forecast-box');
  if (!el) return;
  if (el._uplot) { el._uplot.destroy(); el._uplot = null; }
  el._uplot = await renderForecast(el, slug, { height: 240 });
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
    document.getElementById('cam-img').src = f.url + '?t=' + Date.now();
    document.getElementById('cam-capt').textContent =
      'captured ' + agoLabel(f.ts) + ' · one frame every few minutes';
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
setInterval(() => { refreshNow(); refreshPressureTrend(); renderWidgets(); refreshBanner(slug); }, 60_000);
setInterval(() => { drawCharts(); refreshCamera(); refreshForecast(); }, 5 * 60_000);

/* ...and neither timer runs while the tab is in the background, so refresh
   everything on the way back in rather than showing frozen readings until the
   next tick (js/common.js) */
onVisible(() => {
  refreshNow(); refreshPressureTrend(); renderWidgets(); refreshBanner(slug);
  drawCharts(); refreshCamera(); refreshForecast();
});
