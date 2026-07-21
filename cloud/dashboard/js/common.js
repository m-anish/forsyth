/* forsyth live — shared helpers */
'use strict';

const API = '/api/v1';

/* PWA: install the service worker (network-first for anything live; see sw.js) */
if ('serviceWorker' in navigator) {
  addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}

async function getJSON(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
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
  return {
    stroke: cssVar('--ch-axis'),
    grid: { stroke: cssVar('--ch-grid') },
    ticks: { stroke: cssVar('--ch-grid') },
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
    series: [{}, ...series],
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
function satelliteLayer() {
  const esri = (svc, o = {}) => L.tileLayer(
    `https://server.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`,
    { maxZoom: 20, ...o });
  /* Hybrid, not bare imagery: roads and place names ride on top as transparent
     reference tiles, so you can tell WHERE you are while still seeing the roof
     or the ridge. Labels have data a zoom deeper than the imagery does. */
  return L.layerGroup([
    esri('World_Imagery', { maxNativeZoom: 18,
      attribution: 'Imagery © <a href="https://www.esri.com">Esri</a>, Maxar, Earthstar Geographics' }),
    esri('Reference/World_Transportation', { maxNativeZoom: 19 }),
    esri('Reference/World_Boundaries_and_Places', { maxNativeZoom: 19 }),
  ]);
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
  k.textContent = `${el.dataset.kBase} · ${agoLabel(el.dataset.genAt)}`
    + (ageMin > 15 ? ' — may be stale' : '');
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
    const d = await getJSON('/summary' + (qs.size ? `?${qs}` : ''));
    if (d.summary) {
      el.querySelector('p').textContent = d.summary;
      el.dataset.kBase =
        'Weather · ' + (d.generated_by === 'llm' ? 'as told by forsyth' : 'noted by forsyth');
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
  if (opts.reuse && el._fcRun === d.run_at && el.querySelector('.fc-strip')) {
    return el._fcPlot || null;   // strip-only widgets have no plot to return
  }
  /* rebuilding: tear the old plot down properly, or its resize observer leaks */
  if (el._fcPlot) { el._fcPlot.destroy(); el._fcPlot = null; }
  el._fcRun = d.run_at;

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
