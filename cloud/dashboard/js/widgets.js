/* forsyth board — widget registry.
   Each renderer: async render(bodyEl, config) — idempotent, re-called on refresh.
   Chart/map instances are stashed on the element and destroyed before re-render. */
'use strict';

const Widgets = (() => {

  let stationsCache = null;
  async function stations() {
    if (!stationsCache) stationsCache = (await getJSON('/stations')).stations;
    return stationsCache;
  }
  function invalidate() { stationsCache = null; }

  async function pick(config) {
    const list = await stations();
    if (!list.length) return null;
    return list.find(s => s.slug === (config.station || '')) || list[0];
  }

  function destroyInstance(el) {
    if (el._uplot) { el._uplot.destroy(); el._uplot = null; }
    if (el._maph) { el._maph.destroy(); el._maph = null; el._map = null; }
    else if (el._map) { el._map.remove(); el._map = null; }
  }

  /* ---------- renderers ---------- */

  async function now(el, config) {
    const s = await pick(config);
    if (!s) { el.innerHTML = '<p class="wg-empty">no stations yet</p>'; return; }
    const a = aqi(s.pm25, s.pm10);
    el.innerHTML = `
      <div class="wg-big">${fmt(s.temp_c,1)}<span class="u">°C</span></div>
      <div class="wg-sub">${s.name} · ${describe(s)} · ${agoLabel(s.last_seen)}</div>
      <div class="kv">
        <div><span class="k">Humidity</span><span class="v">${fmt(s.rh,0,'%')}</span></div>
        <div><span class="k">Wind</span><span class="v">${fmt(s.wind_avg_ms,1)} m/s ${dirName(s.wind_dir_deg)}</span></div>
        <div><span class="k">Pressure</span><span class="v">${s.pressure_pa ? (s.pressure_pa/100).toFixed(1) : '—'} hPa</span></div>
        <div><span class="k">AQI</span><span class="v">${a ?? '—'} ${aqiLabel(a)}</span></div>
        <div><span class="k">Battery</span><span class="v">${fmt(s.batt_v,2)} V</span></div>
        <div><span class="k">Solar</span><span class="v">${s.solar_state ?? '—'}</span></div>
      </div>`;
  }

  async function chart(el, config) {
    const s = await pick(config);
    if (!s) { el.innerHTML = '<p class="wg-empty">no stations yet</p>'; return; }
    const metrics = (config.metrics || 'temp_c').split(',').map(m => m.trim()).filter(Boolean);
    const hours = Number(config.hours || 24);
    const d = await getJSON(`/stations/${s.slug}/series?metrics=${metrics.join(',')}&hours=${hours}`);
    const data = [d.ts, ...metrics.map(m => d.series[m])];
    /* theme in the key: a light/dark switch rebuilds so the line colours (not
       just the live-read axis colours) come from the new palette */
    const key = `${s.slug}|${metrics.join(',')}|${hours}|${document.documentElement.dataset.theme}`;
    /* same chart, new numbers: feed the existing plot instead of rebuilding it.
       If the reader has dragged a zoom, leave their view alone this tick —
       resetting it every minute would make zooming useless. */
    if (el._uplot && el._chartKey === key) {
      const u = el._uplot, x = u.data[0];
      const zoomed = x.length > 1 &&
        (u.scales.x.min > x[0] || u.scales.x.max < x[x.length - 1]);
      if (!zoomed) u.setData(data);
      return;
    }
    destroyInstance(el);
    el.innerHTML = '';
    const palette = [cssVar('--ch-temp'), cssVar('--ch-rh'), cssVar('--ch-pres'),
                     cssVar('--ch-gust'), cssVar('--ch-batt'), cssVar('--ch-pm10')];
    const series = metrics.map((m, i) => ({ label: m.replace(/_/g, ' '), stroke: palette[i % palette.length], width: 1.5 }));
    el._uplot = makeChart(el, series, data,
                          { height: Math.max(120, el.clientHeight - 40) });
    el._chartKey = key;
  }

  async function windrose(el, config) {
    const s = await pick(config);
    if (!s) { el.innerHTML = '<p class="wg-empty">no stations yet</p>'; return; }
    const { bins, total } = await getJSON(`/stations/${s.slug}/windrose?hours=${config.hours || 24}`);
    const size = Math.max(140, Math.min(el.clientWidth, el.clientHeight) - 10);
    const cx = 110, cy = 110, rMax = 88;
    const maxN = Math.max(1, ...bins.map(b => b.n));
    let out = '';
    for (const rr of [0.33, 0.66, 1.0]) out += `<circle class="ring" cx="${cx}" cy="${cy}" r="${rMax*rr}"/>`;
    bins.forEach((b, i) => {
      if (!b.n) return;
      const r = rMax * (b.n / maxN);
      const a0 = ((i*22.5 - 90 - 10) * Math.PI) / 180, a1 = ((i*22.5 - 90 + 10) * Math.PI) / 180;
      out += `<path class="spoke" d="M${cx},${cy} L${cx + r*Math.cos(a0)},${cy + r*Math.sin(a0)}
              A${r},${r} 0 0 1 ${cx + r*Math.cos(a1)},${cy + r*Math.sin(a1)} Z"/>`;
    });
    for (const [t, i] of [['N',0],['E',4],['S',8],['W',12]]) {
      const a = ((i*22.5 - 90) * Math.PI) / 180;
      out += `<text x="${cx + (rMax+12)*Math.cos(a)}" y="${cy + (rMax+12)*Math.sin(a)+3}" text-anchor="middle">${t}</text>`;
    }
    if (!total) out += `<text x="${cx}" y="${cy}" text-anchor="middle">no wind data</text>`;
    el.innerHTML = `<svg class="rose" viewBox="0 0 220 220" width="${size}" height="${size}">${out}</svg>
      <div class="wg-sub" style="text-align:center">${s.name} · ${config.hours || 24} h</div>`;
  }

  async function aqiW(el, config) {
    const s = await pick(config);
    if (!s) { el.innerHTML = '<p class="wg-empty">no stations yet</p>'; return; }
    const a = aqi(s.pm25, s.pm10);
    el.innerHTML = `
      <div class="wg-big">${a ?? '—'}</div>
      <div class="wg-sub">${s.name} · ${aqiLabel(a)}</div>
      <div class="aqi-band"><span class="pin" style="left:${a !== null ? Math.min(100, a/5) : 0}%"></span></div>
      <div class="kv">
        <div><span class="k">PM2.5</span><span class="v">${fmt(s.pm25,1)} µg/m³</span></div>
        <div><span class="k">PM10</span><span class="v">${fmt(s.pm10,1)} µg/m³</span></div>
      </div>`;
  }

  async function lightning(el, config) {
    const q = config.station ? `&slug=${config.station}` : '';
    const { events } = await getJSON(`/lightning?hours=${config.hours || 48}${q}`);
    if (!events.length) {
      el.innerHTML = '<p class="wg-empty">The sky has kept its opinions to itself.</p>';
      return;
    }
    el.innerHTML = '<ul class="feed">' + events.slice(0, 30).map(e => `
      <li><span class="t">${new Date(e.ts).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}</span>
          <span class="bolt">⚡</span><span>${fmt(e.distance_km,0)} km · ${e.slug}</span>
          <span class="d">×${e.count}</span></li>`).join('') + '</ul>';
  }

  async function camera(el, config) {
    const s = await pick(config);
    if (!s) { el.innerHTML = '<p class="wg-empty">no stations yet</p>'; return; }
    try {
      const f = await getJSON(`/stations/${s.slug}/frames/latest`);
      const { timelapses } = await getJSON(`/stations/${s.slug}/timelapses`);
      el.innerHTML = `
        <img src="${f.url}?t=${Date.now()}" alt="latest frame from ${s.name}"
             style="width:100%;border:1px solid var(--border-2)" />
        <div class="wg-sub">${s.name} · captured ${agoLabel(f.ts)}</div>
        <ul class="tl-list">${timelapses.slice(0,4).map(t =>
          `<li><a href="${t.url}" target="_blank" rel="noopener">${t.day} ▸</a></li>`).join('')}</ul>`;
    } catch {
      el.innerHTML = `<p class="wg-empty">${s.name} has no camera. The sky goes unrecorded.</p>`;
    }
  }

  async function map(el, config) {
    const list = (await stations()).filter(s => s.lat !== null && s.lon !== null);
    if (!list.length) { el.innerHTML = '<p class="wg-empty">no sited stations</p>'; return; }
    const mode = config.mode || 'temp';
    /* Update in place. Rebuilding on every refresh threw away the reader's pan
       and zoom once a minute and re-downloaded every tile — the map handle
       exists precisely so new readings can flow into the live instance. */
    if (el._maph && el._mapMode === mode && el.querySelector('.wg-map')) {
      el._maph.update(list);
      return;
    }
    destroyInstance(el);
    el.innerHTML = '<div class="wg-map" style="position:absolute;inset:0"></div>';
    /* shared implementation (js/map.js) — compact: no legend/fullscreen */
    const h = forsythMap(el.firstChild, list, { compact: true, mode });
    el._map = h ? h.map : null;
    el._maph = h;
    el._mapMode = mode;
  }

  async function forecast(el, config) {
    const s = await pick(config);
    if (!s) { el.innerHTML = '<p class="wg-empty">no stations yet</p>'; return; }
    const hours = Number(config.hours || 48);
    /* shared renderer (js/common.js) — strip only when the widget is short.
       `reuse` lets it bail out when the model run hasn't changed: forecasts
       refresh every 3 h, so rebuilding this every minute was pure churn. */
    el._uplot = await renderForecast(el, s.slug, {
      hours,
      chart: el.clientHeight > 190,
      fit: true,   /* measure the leftover space instead of guessing at it */
      reuse: el._fcSig === `${s.slug}|${hours}`,
    });
    el._fcSig = `${s.slug}|${hours}`;
  }

  async function reports(el, config) {
    const d = await getJSON(`/reports?hours=${config.hours || 24}`);
    if (d.enabled === false) {
      el.innerHTML = '<p class="wg-empty">Reports are switched off on this mesh.</p>';
      return;
    }
    const btn = (typeof Report !== 'undefined')
      ? '<button class="tool-btn rp-open" type="button">💬 report the sky</button>' : '';
    if (!d.reports.length) {
      el.innerHTML = `<p class="wg-empty">No one has reported the sky lately.</p>${btn}`;
    } else {
      el.innerHTML = '<ul class="feed">' + d.reports.slice(0, 30).map(r => `
        <li><span class="t">${new Date(r.ts).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}</span>
            <span class="bolt">${Report?.GLYPH?.[r.kind] || '💬'}</span>
            <span>${r.kind.replace(/_/g, ' ')}${r.intensity ? [' · light',' · moderate',' · heavy'][r.intensity-1] : ''}
                  ${r.qc_flag === 'corroborated' ? ' ✓' : ''}</span>
            <span class="d">${r.reporter || 'anon'}${r.trusted ? ' ★' : ''}</span></li>`).join('') + `</ul>${btn}`;
    }
    const b = el.querySelector('.rp-open');
    if (b) b.onclick = () => Report.open();
  }

  async function summary(el, config) {
    const q = config.station ? `?slug=${config.station}` : '';
    const d = await getJSON(`/summary${q}`);
    el.innerHTML = d.summary
      ? `<div class="wg-banner">${d.summary}</div>`
      : '<p class="wg-empty">Nothing is happening. Forsyth approves.</p>';
  }

  async function health(el) {
    const d = await getJSON('/health');
    el.innerHTML = `<table class="wg-table">
      <tr><th>station</th><th>last heard</th><th>battery</th><th>rssi</th></tr>
      ${d.stations.map(s => `
        <tr><td>${s.slug} ${s.stale ? '⚠' : ''}</td>
            <td class="mono">${agoLabel(s.last_seen)}</td>
            <td class="mono">${fmt(s.batt_v,2)} V</td>
            <td class="mono">${fmt(s.rssi_dbm,0)} dBm</td></tr>`).join('')}
    </table>`;
  }

  /* ranges: one-tap presets rendered as chips in the widget header
     (board.js); defaultHours = what the renderer assumes when unset */
  const REGISTRY = {
    now:       { label: 'Current conditions', render: now,       w: 3, h: 4, fields: ['station'] },
    chart:     { label: 'Chart',              render: chart,     w: 6, h: 3, fields: ['station','metrics','hours','title'],
                 ranges: [[24,'24h'],[168,'7d'],[720,'30d']], defaultHours: 24 },
    windrose:  { label: 'Wind rose',          render: windrose,  w: 3, h: 4, fields: ['station','hours'],
                 ranges: [[24,'24h'],[168,'7d'],[720,'30d']], defaultHours: 24 },
    aqi:       { label: 'Air quality',        render: aqiW,      w: 3, h: 3, fields: ['station'] },
    lightning: { label: 'Lightning feed',     render: lightning, w: 4, h: 3, fields: ['stationOrAll','hours'],
                 ranges: [[24,'24h'],[48,'48h'],[168,'7d']], defaultHours: 48 },
    camera:    { label: 'Camera',             render: camera,    w: 3, h: 4, fields: ['station'] },
    map:       { label: 'Map',                render: map,       w: 6, h: 4, fields: [] },
    forecast:  { label: 'Forecast',           render: forecast,  w: 6, h: 4, fields: ['station','hours'],
                 ranges: [[24,'24h'],[48,'48h'],[96,'4d'],[168,'7d']], defaultHours: 48 },
    reports:   { label: 'Human reports',      render: reports,   w: 4, h: 3, fields: ['hours'],
                 ranges: [[24,'24h'],[72,'3d'],[168,'7d']], defaultHours: 24 },
    summary:   { label: 'Weather',            render: summary,   w: 12, h: 2, fields: ['stationOrAll'] },
    health:    { label: 'Mesh health',        render: health,    w: 4, h: 2, fields: [] },
  };

  return { REGISTRY, stations, invalidate, destroyInstance };
})();
