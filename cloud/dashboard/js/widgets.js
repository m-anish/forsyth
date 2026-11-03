/* forsyth board — widget registry.
   Each renderer: async render(bodyEl, config) — idempotent, re-called on refresh.
   Chart/map instances are stashed on the element and destroyed before re-render. */
'use strict';

const Widgets = (() => {

  let stationsCache = null;
  async function stations() {
    if (!stationsCache) {
      stationsCache = (await getJSON('/stations')).stations;
      /* The board has no single station, but the 'sky' palette needs one place
         to put the sun in. The reader's chosen location if they have one, else
         the first station with coordinates — in one valley the difference is
         under a minute of sunset either way. */
      const here = window.ForsythLoc && ForsythLoc.active();
      const s = stationsCache.find(x => x.slug === here && x.lat != null)
             || stationsCache.find(x => x.lat != null);
      if (s) Theme.place(s.lat, s.lon);
    }
    return stationsCache;
  }
  function invalidate() { stationsCache = null; }

  /* Resolve the station a widget should show. config.station may be a slug, ''
     (first station), or the '@here' sentinel — which follows the reader's active
     location (js/location.js). When '@here' has no location yet, render a
     "pick a location" placeholder into `el` and return null; the caller just
     `return`s. Also returns null (with a message) when there are no stations. */
  async function pick(config, el) {
    const list = await stations();
    if (!list.length) { if (el) el.innerHTML = '<p class="wg-empty">no stations yet</p>'; return null; }
    let slug = config.station || '';
    if (slug === '@here') {
      slug = (window.ForsythLoc && ForsythLoc.active()) || '';
      if (!slug) {
        if (el) el.innerHTML =
          `<div class="wg-pickloc"><p class="wg-empty">Pick a location to see this.</p>
           <button class="tool-btn wg-pickloc-btn" type="button">choose a location</button></div>`;
        return null;
      }
    }
    return list.find(s => s.slug === slug) || list[0];
  }

  function destroyInstance(el) {
    if (el._uplot) { el._uplot.destroy(); el._uplot = null; }
    if (el._maph) { el._maph.destroy(); el._maph = null; el._map = null; }
    else if (el._map) { el._map.remove(); el._map = null; }
  }

  /* ---------- renderers ---------- */

  /* The hero (docs/v2-design.md §5 Phase 3). v1 was a stat grid: a number and
     six cells, two of which were battery and solar. A weather site's first
     screenful should say what it is like out there in words a person would
     use, and show the shape of the day — so: glyph, temperature, a sentence,
     the last 24 h as a sparkline, and where the number came from. */
  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  async function now(el, config) {
    const s = await pick(config, el);
    if (!s) return;
    const a = aqi(s.pm25, s.pm10);
    const slp = pressureSeaLevelHpa(s.pressure_pa, s.elevation_m, s.temp_c);
    const fl = feelsLike(s.temp_c, s.rh, s.wind_avg_ms);
    const showFeels = fl !== null && s.temp_c !== null && Math.abs(fl - s.temp_c) >= 1;

    /* The day's shape, measured — not forecast. One fetch, reused across the
       minute-by-minute refresh via a signature on the element. */
    let spark = '', hiLo = '', trend = '';
    try {
      const sig = `${s.slug}|${Math.floor(Date.now() / 300000)}`;
      if (el._histSig !== sig || !el._hist) {
        el._hist = await getJSON(`/stations/${s.slug}/series?metrics=temp_c&hours=24`);
        el._histSig = sig;
      }
      const h = el._hist, vals = (h.series && h.series.temp_c) || [];
      const real = vals.filter(v => v !== null && v !== undefined);
      if (real.length >= 2) {
        spark = sparkline(vals, { width: 240, height: 30 });
        hiLo = `High ${Math.round(Math.max(...real))}° · Low ${Math.round(Math.min(...real))}°`;
        /* 3 h, the same window the pressure panel uses and the one met
           services quote — long enough to survive the taper's slow cadence. */
        trend = trendHtml(trendFromSeries('temp_c', h.ts, vals, 3));
      }
    } catch { /* no history yet — the hero still works without it */ }

    /* The glyph needs cloud cover, which only the model has; the station
       cannot see the sky. Cached per model hour — it changes every 3 h and
       this widget refreshes every minute. */
    let glyph = '';
    try {
      const fsig = `${s.slug}|${new Date().getUTCHours()}`;
      if (el._fcSig2 !== fsig || !el._sky) {
        const f = await getJSON(`/stations/${s.slug}/forecast?hours=6`);
        const F = f.series || {};
        el._sky = wxKind((F.precip_mm || [])[0], (F.precip_prob || [])[0],
                         (F.cloud_cover_pct || [])[0], (F.temp_c || [])[0]);
        el._fcSig2 = fsig;
      }
      /* The sky state is cached per model hour; whether there is a sun in it
         or a moon is settled on every render, so the icon turns over near
         enough to sunset instead of at the top of the following hour. */
      glyph = el._sky ? wxIcon(el._sky, isNight(Date.now() / 1000, s.lat, s.lon)) : '';
    } catch { /* no forecast: no glyph, rather than a guessed one */ }
    /* rain measured here always beats the model's opinion of the sky */
    if ((s.rain_mm ?? 0) > 0.3) glyph = wxIcon('rain');

    const says = [cap(describe(s)) + '.'];
    if (showFeels) says.push(`Feels like ${Math.round(fl)}°.`);

    /* Wind and gust were two blocks saying one thing. Together they read as a
       single fact — "calm, gusting 4 km/h" — and four stats fit two rows on a
       phone where five needed three, which is what pushed the hero past its
       card. */
    const windCell = (() => {
      const k = windKmh(s.wind_avg_ms), g = windKmh(s.wind_gust_ms);
      if (k === null) return '—';
      const base = k < 1 ? 'calm'
        : `${windArrow(s.wind_dir_deg)} ${Math.round(k)} km/h ${dirName(s.wind_dir_deg)}`;
      /* A gust is only worth naming once it clears the same floor everything
         else uses (WIND_CALM_MS). "calm · gusting 1" was one reed closure in a
         10 s gate reported as weather, and it read as broken because it is. */
      const gustWorthSaying = g !== null && (s.wind_gust_ms >= WIND_CALM_MS) &&
                              Math.round(g) > Math.round(k);
      return gustWorthSaying
        ? `${base}<span class="hero-sub2"> · gusting ${Math.round(g)} km/h</span>` : base;
    })();

    el.innerHTML = `
      <div class="hero">
      <div class="hero-top">
        ${glyph ? `<span class="hero-glyph">${glyph}</span>` : ''}
        <span class="hero-temp">${fmt(s.temp_c, 1)}<span class="u">°C</span></span>
        ${trend}
      </div>
      <p class="hero-say">${says.join(' ')}</p>
      ${spark}
      <div class="hero-meta">${hiLo ? hiLo + ' · ' : ''}measured at ${s.name}, ${agoLabel(s.last_seen)}</div>
      <div class="hero-stats">
        <div><span class="k">Humidity</span><span class="v">${fmt(s.rh, 0, '%')}</span></div>
        <div><span class="k">Wind</span><span class="v">${windCell}</span></div>
        <div><span class="k">Pressure</span><span class="v">${fmt(slp, 0, ' hPa')}</span></div>
        <div><span class="k">Air (${AQI_SCALE})</span><span class="v">${a ?? '—'} ${aqiLabel(a)}</span></div>
      </div>
      </div>`;
  }

  async function chart(el, config) {
    const s = await pick(config, el);
    if (!s) return;
    const metrics = (config.metrics || 'temp_c').split(',').map(m => m.trim()).filter(Boolean);
    const hours = Number(config.hours || 24);
    const d = await getJSON(`/stations/${s.slug}/series?metrics=${metrics.join(',')}&hours=${hours}`);
    /* Convert to the unit the label promises, then let a reporting gap read as
       a gap. A series that is sparse by design (PM) has its between-sample
       nulls dropped first, so only real outages break it (docs/v2-design.md §8). */
    const cols = metrics.map(m => {
      const meta = metricMeta(m), arr = d.series[m] || [];
      return meta.conv ? arr.map(v => (v === null || v === undefined) ? null : meta.conv(v)) : arr;
    });
    const data = breakGaps(d.ts, cols, undefined,
                           { dropNulls: metrics.every(m => metricMeta(m).sparse) });
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
    /* Labels used to come straight from the database — the legend read
       `wind avg ms`. And every metric was a line, including rain, which is an
       accumulation per interval and so belongs in bars (§8). */
    const series = metrics.map((m, i) => {
      const meta = metricMeta(m), col = palette[i % palette.length];
      const sr = { label: metricLabel(m), stroke: col, width: 1.5 };
      if (meta.kind === 'bars' && uPlot.paths.bars) {
        sr.paths = uPlot.paths.bars({ size: [0.8, 100] });
        sr.fill = col;
      }
      if (meta.sparse) sr.points = { show: true, size: 3 };
      return sr;
    });
    /* The nights, shaded, the same as on the station page: a board chart was
       the one place a reader had to consult the time axis to tell which dip
       was the night and which was the weather. */
    const nights = nightBands(s.lat, s.lon);
    el._uplot = makeChart(el, series, data,
                          { height: Math.max(120, el.clientHeight - 40),
                            uplot: nights ? { plugins: [nights] } : {} });
    el._chartKey = key;
  }

  /* A rose scaled by frequency alone cannot answer the question it is usually
     asked — does this direction bring a breeze or a gale? Petals are stacked
     by speed band, the outer ring states what share of the time it represents,
     and calm sits in the hole at the centre because a still vane has no
     direction to contribute. docs/v2-design.md §7.3. */
  const ROSE_BANDS = ['rose-b1', 'rose-b2', 'rose-b3', 'rose-b4'];

  async function windrose(el, config) {
    const s = await pick(config, el);
    if (!s) return;
    const hours = config.hours || 24;
    const d = await getJSON(`/stations/${s.slug}/windrose?hours=${hours}`);
    const bins = d.bins || [];
    const total = d.total || 0;
    const nb = (d.band_edges_ms || [2, 4, 8]).length + 1;

    /* 240-unit viewBox: cardinal labels scale with the SVG, so they need to be
       a decent fraction of it to stay readable in a small card. */
    const cx = 120, cy = 120, rMax = 92, r0 = 20, rLab = rMax + 15;
    const maxN = Math.max(1, ...bins.map(b => b.n || 0));
    const rAt = frac => r0 + (rMax - r0) * frac;
    const pt = (r, a) => `${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`;

    let out = '';
    for (const rr of [0.34, 0.67, 1.0]) {
      out += `<circle class="ring" cx="${cx}" cy="${cy}" r="${rAt(rr).toFixed(2)}"/>`;
    }

    bins.forEach((b, i) => {
      if (!b.n) return;
      const bands = b.bands || [b.n];
      const a0 = ((i * 22.5 - 90 - 9.5) * Math.PI) / 180;
      const a1 = ((i * 22.5 - 90 + 9.5) * Math.PI) / 180;
      let cum = 0;
      for (let k = 0; k < nb; k++) {
        const n = bands[k] || 0;
        if (!n) { continue; }
        const rIn = rAt(cum / maxN);
        cum += n;
        const rOut = rAt(cum / maxN);
        /* annular wedge: out along a0, arc to a1, back in, arc home */
        out += `<path class="spoke ${ROSE_BANDS[Math.min(k, ROSE_BANDS.length - 1)]}" d="`
             + `M${pt(rIn, a0)} L${pt(rOut, a0)}`
             + ` A${rOut.toFixed(2)},${rOut.toFixed(2)} 0 0 1 ${pt(rOut, a1)}`
             + ` L${pt(rIn, a1)}`
             + ` A${rIn.toFixed(2)},${rIn.toFixed(2)} 0 0 0 ${pt(rIn, a0)} Z"/>`;
      }
    });

    /* What the outer ring is worth, so the petals mean something absolute.
       Without this a reader cannot tell 10 % of the time from 60 %. */
    if (total) {
      const pct = Math.round((maxN / total) * 100);
      out += `<text class="rose-ring" x="${cx + 3}" y="${cy - rMax + 1}">${pct}%</text>`;
    }

    for (const [txt, i] of [['N', 0], ['E', 4], ['S', 8], ['W', 12]]) {
      const a = ((i * 22.5 - 90) * Math.PI) / 180;
      out += `<text class="rose-card" x="${(cx + rLab * Math.cos(a)).toFixed(1)}"`
           + ` y="${(cy + rLab * Math.sin(a) + 5).toFixed(1)}" text-anchor="middle">${txt}</text>`;
    }

    /* calm lives in the hole: it has no direction to be drawn in */
    out += `<circle class="rose-hole" cx="${cx}" cy="${cy}" r="${r0 - 1}"/>`;
    if (d.calm_pct !== undefined && d.samples) {
      out += `<text class="rose-calm" x="${cx}" y="${cy - 1}" text-anchor="middle">${Math.round(d.calm_pct)}%</text>`
           + `<text class="rose-calmlab" x="${cx}" y="${cy + 9}" text-anchor="middle">calm</text>`;
    }
    if (!total && !(d.samples || 0)) {
      out += `<text class="rose-empty" x="${cx}" y="${cy + 34}" text-anchor="middle">no wind data yet</text>`;
    }

    /* the sentence most readers actually wanted from the rose */
    let lead = '';
    if (total) {
      let bi = 0;
      bins.forEach((b, i) => { if ((b.n || 0) > (bins[bi].n || 0)) bi = i; });
      const pct = Math.round((bins[bi].n / total) * 100);
      lead = `<p class="rose-lead">Mostly from the <b>${dirName(bi * 22.5)}</b>`
           + `<span class="rose-dim"> · ${pct}% of the time it blows</span></p>`;
    } else if (d.samples) {
      lead = `<p class="rose-lead">Still air — no wind to speak of in the last ${hours} h.</p>`;
    }

    /* Gusts cannot ride the petals: the radial axis is frequency, and
       overloading it with a second meaning would make both unreadable. So the
       strongest gust and where it came from are simply stated. */
    let gustLine = '';
    let gi = -1;
    bins.forEach((b, i) => { if ((b.gust || 0) > (gi < 0 ? 0 : (bins[gi].gust || 0))) gi = i; });
    if (gi >= 0 && (bins[gi].gust || 0) > 0) {
      gustLine = `<p class="rose-gust">Strongest gust <b>${Math.round(bins[gi].gust * 3.6)} km/h</b>`
               + `<span class="rose-dim"> from the ${dirName(gi * 22.5)}</span></p>`;
    }

    const edges = (d.band_edges_ms || [2, 4, 8]).map(v => Math.round(v * 3.6));
    const legend = total ? `<div class="rose-legend">` + ROSE_BANDS.slice(0, nb).map((c, k) => {
      const txt = k === 0 ? `<${edges[0]}`
                : k === nb - 1 ? `${edges[nb - 2]}+`
                : `${edges[k - 1]}–${edges[k]}`;
      return `<span class="rose-key"><i class="${c}"></i>${txt}</span>`;
    }).join('') + `<span class="rose-key rose-dim">km/h</span></div>` : '';

    /* no width/height: the SVG scales to its container via the viewBox (CSS
       keeps it square), so the rose fills whatever card it is dropped into. */
    el.innerHTML = `<svg class="rose" viewBox="0 0 240 240" preserveAspectRatio="xMidYMid meet">${out}</svg>`
      + lead + gustLine + legend
      + (config.label === false ? ''
         : `<div class="wg-sub" style="text-align:center">${s.name} · ${hours} h</div>`);
  }

  async function aqiW(el, config) {
    const s = await pick(config, el);
    if (!s) return;
    const a = aqi(s.pm25, s.pm10);
    const who = whoPm25Multiple(s.pm25);
    /* Worth more than most trends here: "getting worse" is the cue to shut a
       window, and the index moves slowly enough that a 3 h fit is meaningful.
       Rising reads red, falling green — the polarity lives in TREND_SPECS,
       because a naive up-is-good would call worsening air an improvement. */
    let aqTrend = '';
    try {
      const sig = `${s.slug}|${Math.floor(Date.now() / 300000)}`;
      if (el._aqSig !== sig || !el._aqHist) {
        el._aqHist = await getJSON(`/stations/${s.slug}/series?metrics=pm25,pm10&hours=3`);
        el._aqSig = sig;
      }
      const H = el._aqHist, p25 = (H.series && H.series.pm25) || [],
            p10 = (H.series && H.series.pm10) || [];
      const idx = p25.map((v, i) =>
        (v === null || v === undefined) && (p10[i] === null || p10[i] === undefined)
          ? null : aqi(v, p10[i]));
      aqTrend = trendHtml(trendOf('aqi', H.ts, idx, 3));
    } catch { /* no history: no trend, which is the honest default */ }
    /* The scale is named every time. CPCB reads ~50 points kinder than the US
       EPA at these concentrations, so a bare number with a reassuring word is
       the one thing on this site that could mislead someone about their health
       (docs/v2-design.md §6.2). The WHO multiple is the honest anchor. */
    el.innerHTML = `
      <div class="wg-big">${a ?? '—'}</div>
      <div class="wg-sub">${s.name} · ${aqiLabel(a)} · ${AQI_SCALE} scale</div>
      ${aqTrend ? `<div class="aqi-trend">${aqTrend}</div>` : ''}
      <div class="aqi-band"><span class="pin" style="left:${a !== null ? Math.min(100, a/5) : 0}%"></span></div>
      ${a !== null ? `<p class="aqi-advice">${aqiGuidance(a)}</p>` : ''}
      <div class="kv">
        <div><span class="k">PM2.5</span><span class="v">${fmt(s.pm25,1)} µg/m³</span></div>
        <div><span class="k">PM10</span><span class="v">${fmt(s.pm10,1)} µg/m³</span></div>
      </div>
      ${who !== null ? `<p class="aqi-who">PM2.5 is <b>${who.toFixed(1)}×</b> the WHO
         24-hour guideline of 15 µg/m³</p>` : ''}`;
  }

  async function lightning(el, config) {
    const scoped = !!config.station;   // one station → the slug is redundant on every row
    const q = scoped ? `&slug=${config.station}` : '';
    const { events } = await getJSON(`/lightning?hours=${config.hours || 48}${q}`);
    if (!events.length) {
      el.innerHTML = '<p class="wg-empty">The sky has kept its opinions to itself.</p>';
      return;
    }
    el.innerHTML = '<ul class="feed">' + events.slice(0, 30).map(e => `
      <li><span class="t">${new Date(e.ts).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}</span>
          <span class="bolt">⚡</span><span>${fmt(e.distance_km,0)} km out${scoped ? '' : ' · ' + e.slug}</span>
          <span class="d">×${e.count}</span></li>`).join('') + '</ul>';
  }

  async function camera(el, config) {
    const s = await pick(config, el);
    if (!s) return;
    try {
      const f = await getJSON(`/stations/${s.slug}/frames/latest`);
      const { timelapses } = await getJSON(`/stations/${s.slug}/timelapses`);
      const ageMin = (Date.now() - new Date(f.ts).getTime()) / 60000;
      el.innerHTML = `
        <a class="cam-shot" href="${f.url}" target="_blank" rel="noopener">
          <img src="${f.url}?t=${Date.now()}"
               alt="The view from ${s.name}, photographed ${agoLabel(f.ts)}" />
        </a>
        <div class="wg-sub${ageMin > 30 ? ' stale' : ''}">${s.name} · captured ${agoLabel(f.ts)}${
          ageMin > 30 ? ' — the camera has gone quiet' : ''}</div>
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
    const s = await pick(config, el);
    if (!s) return;
    const hours = Number(config.hours || 48);
    /* shared renderer (js/common.js) — strip only when the widget is short.
       `reuse` lets it bail out when the model run hasn't changed: forecasts
       refresh every 3 h, so rebuilding this every minute was pure churn. */
    /* The grid settles AFTER the first render, so a card measured while it was
       still 80px tall decided "too short for a chart" — and because the reuse
       signature did not include that decision, the guard then locked the
       chartless version in for good. Same failure as the map's: a measurement
       taken before layout finished, trusted forever. The decision is part of
       the signature now, and a ResizeObserver re-renders once the card
       actually reaches its height. */
    const wantChart = el.clientHeight > 190;
    el._uplot = await renderForecast(el, s.slug, {
      hours,
      chart: wantChart,
      fit: true,   /* measure the leftover space instead of guessing at it */
      lat: s.lat, lon: s.lon,   /* moons on the night cards, nights on the chart */
      reuse: el._fcSig === `${s.slug}|${hours}|${wantChart}`,
    });
    el._fcSig = `${s.slug}|${hours}|${wantChart}`;
    if (!el._fcRo) {
      el._fcRo = new ResizeObserver(() => {
        if (el.clientHeight > 190 && !el._uplot) forecast(el, config);
      });
      el._fcRo.observe(el);
    }
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
      const alertName = ['', 'yellow', 'orange', 'red'];
      el.innerHTML = '<ul class="feed">' + d.reports.slice(0, 30).map(r => {
        const obs = r.observations || [{ kind: r.kind, intensity: r.intensity, qc_flag: r.qc_flag }];
        const glyph = Report?.GLYPH?.[obs[0].kind] || '💬';
        const text = obs.map(o => o.kind.replace(/_/g, ' ')
          + (o.intensity ? [' · light', ' · mod', ' · heavy'][o.intensity - 1] : '')).join(', ');
        const agrees = obs.some(o => o.qc_flag === 'corroborated');
        const alert = r.alert_level
          ? `<span class="rp-lvl rp-lvl-${r.alert_level}">${alertName[r.alert_level]}</span> ` : '';
        return `<li><span class="t">${new Date(r.ts).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}</span>
            <span class="bolt">${glyph}</span>
            <span>${alert}${text}${agrees ? ' ✓' : ''}</span>
            <span class="d">${r.reporter || 'anon'}${r.trusted ? ' ★' : ''}</span></li>`;
      }).join('') + `</ul>${btn}`;
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

  /* ---- location panel: one card enclosing the location-bound widgets, with
     the location selector in its own title. The nav applies only to this
     group; the rest of the homepage (map, reports, lightning, health) is
     mesh-wide. Follows ForsythLoc (js/location.js). ---- */
  function locNavHTML() {
    if (!window.ForsythLoc) return '';
    const list = ForsythLoc.stations();
    const active = ForsythLoc.active();
    const cur = list.find(s => s.slug === active);
    return `<span class="lp-lead">Conditions &amp; forecast for</span>
      <select class="lp-select" aria-label="choose a location">
        ${cur ? '' : '<option value="" selected>— pick a location —</option>'}
        ${list.map(s => `<option value="${s.slug}"${s.slug === active ? ' selected' : ''}>${s.name}</option>`).join('')}
      </select>
      ${cur ? `<a class="lp-link" href="station.html?slug=${cur.slug}">${cur.name} →</a>` : ''}
      <button class="lp-here" type="button" title="use my location">📍</button>`;
  }
  function wireLocNav(el) {
    const sel = el.querySelector('.lp-select');
    if (sel) sel.onchange = (e) => { if (e.target.value) ForsythLoc.set(e.target.value); };
    const here = el.querySelector('.lp-here');
    if (here) here.onclick = async (e) => {
      e.currentTarget.disabled = true;
      if (!(await ForsythLoc.useMyLocation())) e.currentTarget.disabled = false;
    };
  }

  /* each sub-widget gets its own titled card, so the panel reads as four
     separated things under one location header rather than one long column */
  const LP_CELLS = [
    ['forecast', 'The next 48 hours'],
    ['now',      'Right now'],
    ['wind',     'Wind rose'],
    ['chart',    'Temperature &amp; humidity'],
  ];

  async function localpanel(el, config) {
    if (!window.ForsythLoc) { el.innerHTML = '<p class="wg-empty">—</p>'; return; }
    const active = ForsythLoc.active();
    const stateKey = active || '__none__';
    if (el._lpState !== stateKey) {        // rebuild the shell only when the state category flips
      el._lpState = stateKey;
      el.innerHTML = active
        ? `<div class="lp-head">${locNavHTML()}</div>
           <div class="lp-grid">
             ${LP_CELLS.map(([k, title]) => `
               <section class="lp-cell lp-c-${k}">
                 <h4>${title}</h4>
                 <div class="lp-body"></div>
               </section>`).join('')}
           </div>`
        : `<div class="lp-head">${locNavHTML()}</div>
           <div class="lp-empty"><p class="wg-empty">Pick a location above to see local conditions &amp; forecast.</p></div>`;
      wireLocNav(el);
    }
    if (!active) return;
    const cfg = { station: active };
    const body = k => el.querySelector(`.lp-c-${k} .lp-body`);
    /* the card titles already name the window and the header names the station,
       so the sub-widgets render without their own captions */
    await Promise.allSettled([
      forecast(body('forecast'), { ...cfg, hours: 48 }),
      now(body('now'), cfg),
      windrose(body('wind'), { ...cfg, hours: 24, label: false }),
      chart(body('chart'), { ...cfg, metrics: 'temp_c,rh', hours: 24 }),
    ]);
  }

  /* ranges: one-tap presets rendered as chips in the widget header
     (board.js); defaultHours = what the renderer assumes when unset */
  /* The river below, from Google's flood model (docs/flood-roadmap.md).

     Two states on purpose. Eleven months a year the answer is "the stream is
     at a ninth of its warning level", which deserves one line and not a card.
     But it does NOT deserve nothing: a warning you have never seen while calm
     is one nobody trusts the first time it appears, and an empty space cannot
     be told apart from a broken feed. So: quiet, then loud.

     Everything here says "modelled". There is no gauge in this valley — these
     are virtual HydroBASINS reaches and Google decline to quality-verify them,
     so presenting a number as though an instrument produced it would be the
     most harmful thing this widget could do. */
  function riverBar(r) {
    /* Scale the bar to the reach's own thresholds, never to a shared axis:
       warning levels here run from 17.7 to 1781 m3/s. */
    const top = r.extreme_level || (r.danger_level ? r.danger_level * 1.35 : null);
    if (!top || !r.warning_level) return '';
    const at = v => Math.max(0, Math.min(100, (v / top) * 100));
    const now = r.value !== null ? at(r.value) : null;
    const peak = r.peak !== null ? at(r.peak) : null;
    return `
      <div class="rv-bar" role="img" aria-label="${fmt(r.value, 1)} of a warning level of ${fmt(r.warning_level, 0)}">
        <span class="rv-zone warn" style="left:${at(r.warning_level)}%"></span>
        <span class="rv-zone danger" style="left:${at(r.danger_level)}%"></span>
        ${peak !== null ? `<span class="rv-peak" style="left:${peak}%"></span>` : ''}
        ${now !== null ? `<span class="rv-now" style="left:${now}%"></span>` : ''}
      </div>
      <div class="rv-scale"><span>warning ${fmt(r.warning_level, 0)}</span>
        <span>danger ${fmt(r.danger_level, 0)}</span>
        <span>of ${fmt(top, 0)} ${r.unit === 'METERS' ? 'm' : 'm³/s'}</span></div>`;
  }

  async function river(el, config) {
    const s = await pick(config, el);
    if (!s) return;
    let d;
    try {
      d = await getJSON(`/stations/${s.slug}/river?limit=3`);
    } catch {
      el.innerHTML = '<p class="wg-empty">No river model for this station.</p>';
      return;
    }
    const rs = d.reaches || [];
    if (!rs.length) {
      /* Said plainly rather than hidden: "no modelled reach near here" is a
         fact about coverage, and a reader who sees nothing cannot learn it. */
      el.innerHTML = '<p class="wg-empty">No modelled river reach within '
                   + 'range of this station.</p>';
      el.dataset.quiet = '1';
      return;
    }
    const r = rs[0];
    const pct = r.of_warning !== null ? Math.round(r.of_warning * 100) : null;
    const unit = r.unit === 'METERS' ? 'm' : 'm³/s';
    const where = `${r.km} km away`;

    if (!d.notable) {
      /* The quiet line. Still names the number and the threshold, so the
         reader has seen the units before the day they matter. */
      el.dataset.quiet = '1';
      el.innerHTML = `
        <div class="rv-quiet">
          <span class="rv-dot ok" aria-hidden="true"></span>
          <span class="rv-q-text">The river ${where} is running normally${
            r.value !== null && r.warning_level
              ? ` — ${fmt(r.value, 1)} of ${fmt(r.warning_level, 0)} ${unit}` : ''}.</span>
          <span class="rv-src">modelled · Google Flood Hub</span>
        </div>`;
      return;
    }

    delete el.dataset.quiet;
    const sev = (r.severity || '').toLowerCase().replace('_', '-');
    const trend = r.trend === 'RISE' ? 'rising' : r.trend === 'FALL' ? 'falling' : 'steady';
    el.innerHTML = `
      <div class="rv-loud ${sev}">
        <div class="rv-head">
          <span class="rv-dot ${sev}" aria-hidden="true"></span>
          <span class="rv-sev">${(r.severity || 'above normal').replace(/_/g, ' ').toLowerCase()}</span>
          <span class="rv-trend">${trend}</span>
        </div>
        <div class="wg-big">${fmt(r.value, 1)}<span class="u"> ${unit}</span></div>
        <div class="wg-sub">${pct !== null ? `${pct}% of this reach's warning level` : ''}
          · ${where}${r.river ? ' · ' + r.river : ''}</div>
        ${riverBar(r)}
        ${r.peak !== null && r.of_warning_peak !== null ? `<p class="rv-peakline">Forecast to
          peak near ${fmt(r.peak, 1)} ${unit}
          (${Math.round(r.of_warning_peak * 100)}% of warning) in the next few days.</p>` : ''}
        <p class="rv-caveat">Modelled, not measured. There is no river gauge in
          this valley — this is Google's estimate for a catchment ${where}, and
          it is not quality-verified. Treat it as a hint to look at the water,
          not as a reading.</p>
        <div class="rv-src">Google Flood Hub · CC BY 4.0</div>
      </div>`;
  }

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
    /* sizeToContent, because the whole design is that it is one line on a calm
       day and a card on a bad one — a fixed height would give back the space
       the quiet state exists to save. */
    river:     { label: 'River level',        render: river,     w: 4, h: 2, fields: ['station'],
                 sizeToContent: true },
    /* sizeToContent: the sub-cards are content-sized, and the total differs a
       lot between one column and two — a fixed gs-h clipped one or padded the
       other, so the panel grows to whatever it needs (board.js) */
    localpanel:{ label: 'Local conditions',   render: localpanel, w: 8, h: 11, fields: [],
                 sizeToContent: true },
  };

  return { REGISTRY, stations, invalidate, destroyInstance };
})();
