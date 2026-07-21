/* forsyth live — the map, upgraded from "three dots" to an instrument.
   Shared by index.html and the board 'map' widget: one implementation,
   `forsythMap(el, stations, opts)` → handle with .update(stations).

   Modes color every station chip by one metric; the legend follows; wind
   direction rides along as a rotated arrow. Overlays: live rain radar
   (RainViewer public tiles, fail-silent) and an OpenTopoMap terrain basemap
   (we are in the Himalaya; contours are context). Roadmap and phase status:
   cloud/docs/map-roadmap.md. */
'use strict';

const forsythMap = (() => {

  /* ---------- color scales ---------- */
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  function tempColor(t) {           // -5 °C blue → 40 °C red
    const h = 210 - clamp((t + 5) / 45, 0, 1) * 230;
    return `hsl(${(h + 360) % 360},72%,44%)`;
  }
  function windColor(v) {           // 0 calm teal → 15 m/s violet
    return `hsl(${190 + clamp(v / 15, 0, 1) * 100},60%,42%)`;
  }
  const AQI_BANDS = [               // Indian CPCB bands + official palette
    [50, '#00b050'], [100, '#92d050'], [200, '#f5d000'],
    [300, '#ff9900'], [400, '#ff2a00'], [500, '#c00000'],
  ];
  function aqiColor(v) {
    for (const [hi, c] of AQI_BANDS) if (v <= hi) return c;
    return '#c00000';
  }
  function rainColor(mm) {          // per-report accumulation, dry → deep blue
    if (!mm) return 'hsl(215,15%,55%)';
    return `hsl(215,80%,${70 - clamp(mm / 20, 0, 1) * 42}%)`;
  }
  function battColor(v) {           // LiFePO4-flavored maintenance view
    if (v == null) return 'hsl(215,15%,55%)';
    return v >= 3.15 ? '#2e9e5b' : v >= 2.95 ? '#e0a020' : '#d64541';
  }
  function textOn(bg) {             // black text on the yellow-ish bands
    return /f5d000|92d050/.test(bg) ? '#1c2430' : '#fff';
  }

  /* ---------- lightning ring tuning ----------
     The AS3935 "energy" byte is a 21-bit UNCALIBRATED number — physically
     meaningless in absolute terms, but within one storm it tracks relative
     strike strength. So we normalize each strike to the strongest one
     currently in view, never to a fixed threshold. Strong + recent strikes
     are bright, thick, opaque; weak or aging ones dim out fast and, past a
     floor, aren't drawn at all — which is also what thins the clutter. */
  const LTG = {
    windowMin: 45,     // strikes older than this vanish (was a flat 3 h)
    perStation: 5,     // draw only the strongest few rings per station
    minAlpha: 0.12,    // below this an aged/weak ring isn't worth the ink
    fadePow: 2.2,      // >1 = older strikes fade faster than linear
  };

  /* ---------- modes ---------- */
  const MODES = {
    temp: { label: '°C',   value: s => s.temp_c,      text: v => `${Number(v).toFixed(1)}°`,  color: tempColor,
            legend: { kind: 'ramp', stops: [-5, 5, 15, 25, 35], fmt: v => v + '°', color: tempColor } },
    wind: { label: 'wind', value: s => s.wind_avg_ms, text: v => `${Number(v).toFixed(1)}`,   color: windColor,
            legend: { kind: 'ramp', stops: [0, 4, 8, 12, 15], fmt: v => v + ' m/s', color: windColor } },
    aqi:  { label: 'AQI',  value: s => aqi(s.pm25, s.pm10), text: v => `${v}`,                color: aqiColor,
            legend: { kind: 'bands', bands: AQI_BANDS, labels: ['good', 'ok', 'mod', 'poor', 'v.poor', 'sev'] } },
    rain: { label: 'rain', value: s => s.rain_mm ?? 0, text: v => `${Number(v).toFixed(1)}`,  color: rainColor,
            legend: { kind: 'ramp', stops: [0, 2, 5, 10, 20], fmt: v => v + ' mm', color: rainColor } },
    batt: { label: 'batt', value: s => s.batt_v,      text: v => `${Number(v).toFixed(2)}`,   color: battColor,
            legend: { kind: 'bands', bands: [[0, '#d64541'], [0, '#e0a020'], [0, '#2e9e5b']],
                      labels: ['< 2.95 V', '< 3.15 V', 'healthy'] } },
  };

  /* ---------- chip markers ---------- */
  function chipIcon(s, mode, staleOverride) {
    const m = MODES[mode];
    const v = m.value(s);
    const stale = staleOverride !== undefined ? staleOverride : isStale(s.last_seen);
    const bg = stale || v == null ? 'hsl(215,12%,52%)' : m.color(v);
    /* in wind mode the arrow doubles as a gust vector: it grows with gust */
    const asz = mode === 'wind' && s.wind_gust_ms != null
      ? 11 + clamp(s.wind_gust_ms / 15, 0, 1) * 8 : 11;
    const arrow = (s.wind_dir_deg != null && !stale)
      ? `<span class="wc-a" style="font-size:${asz}px;transform:rotate(${(s.wind_dir_deg + 180) % 360}deg)">↑</span>` : '';
    const cls = 'wx-chip' + (stale ? ' stale' : '') + (s.is_simulated ? ' sim' : '');
    const txt = v == null ? '—' : m.text(v);
    const html = `<div class="${cls}" style="--bg:${bg};--fg:${textOn(bg)}">` +
                 `<span class="wc-v">${txt}</span>${arrow}</div>`;
    return L.divIcon({ className: 'wx-chip-wrap', html, iconSize: null, iconAnchor: [26, 14] });
  }

  function popupHtml(s) {
    const a = aqi(s.pm25, s.pm10);
    const row = (l, v) => v ? `<div class="r"><span>${l}</span><b>${v}</b></div>` : '';
    return `<div class="map-pop">
      <h4>${s.name} ${s.is_simulated ? '<span class="badge sim">rehearsal</span>' : ''}</h4>
      <div class="l">${describe(s)} · ${agoLabel(s.last_seen)}</div>
      ${row('temp', s.temp_c != null ? fmt(s.temp_c, 1) + ' °C · ' + fmt(s.rh, 0) + '% rh' : '')}
      ${row('wind', s.wind_avg_ms != null ? `${fmt(s.wind_avg_ms,1)} m/s ${dirName(s.wind_dir_deg)} (gust ${fmt(s.wind_gust_ms,1)})` : '')}
      ${row('pressure', s.pressure_pa ? (s.pressure_pa / 100).toFixed(1) + ' hPa' : '')}
      ${row('rain', s.rain_mm ? fmt(s.rain_mm, 1) + ' mm (last report)' : '')}
      ${row('aqi', a != null ? `${a} · ${aqiLabel(a)}` : '')}
      ${row('battery', s.batt_v != null ? fmt(s.batt_v, 2) + ' V' : '')}
      ${row('radio', s.rssi_dbm != null ? fmt(s.rssi_dbm, 0) + ' dBm' : '')}
      ${row('elevation', s.elevation_m != null ? fmt(s.elevation_m, 0) + ' m' : '')}
      <div class="pop-cam" data-slug="${s.slug}"></div>
      <a href="station.html?slug=${s.slug}">station page →</a>
    </div>`;
  }

  /* camera thumbnail, fetched lazily on popup open; 404 = station has no
     camera, the div quietly stays empty. Cached per slug for the session.   */
  const camCache = {};
  async function fillCam(popupEl) {
    const d = popupEl.querySelector('.pop-cam');
    if (!d || d.dataset.done) return;
    d.dataset.done = '1';
    const slug = d.dataset.slug;
    try {
      camCache[slug] ??= await getJSON(`/stations/${slug}/frames/latest`);
      d.innerHTML = `<img src="${camCache[slug].url}" alt="latest sky frame" loading="lazy" />`;
    } catch { /* no camera — nothing to show */ }
  }

  /* ---------- tile layers ---------- */
  function cartoUrl() {
    const kind = document.documentElement.dataset.theme === 'light' ? 'light_all' : 'dark_all';
    return `https://{s}.basemaps.cartocdn.com/${kind}/{z}/{x}/{y}{r}.png`;
  }

  /* RainViewer public radar — global composite; fail-silent (an ad-blocked or
     down API must never take the map with it). Frames age fast: re-resolve
     the newest frame every 10 min while the overlay is on. */
  async function radarUrl() {
    const r = await fetch('https://api.rainviewer.com/public/weather-maps.json');
    const d = await r.json();
    const frames = d?.radar?.past || [];
    if (!frames.length) throw new Error('no radar frames');
    return `${d.host}${frames[frames.length - 1].path}/256/{z}/{x}/{y}/2/1_1.png`;
  }

  /* ---------- legend + mode controls ---------- */
  function legendHtml(mode) {
    const lg = MODES[mode].legend;
    if (lg.kind === 'ramp') {
      const stops = lg.stops.map(v => lg.color(v)).join(',');
      return `<div class="lg-ramp" style="background:linear-gradient(90deg,${stops})"></div>
              <div class="lg-ticks">${lg.stops.map(v => `<span>${lg.fmt(v)}</span>`).join('')}</div>`;
    }
    return `<div class="lg-bands">` + lg.bands.map(([, c], i) =>
      `<span class="lg-band"><i style="background:${c}"></i>${lg.labels[i]}</span>`).join('') + `</div>`;
  }

  /* ---------- the factory ---------- */
  function create(el, stations, opts = {}) {
    const sited = () => (state.stations || []).filter(s => s.lat != null && s.lon != null);
    const state = { stations, mode: opts.mode || 'temp', markers: [], radar: null, radarTimer: null };
    if (!stations.filter(s => s.lat != null && s.lon != null).length) return null;

    const map = L.map(el, { scrollWheelZoom: false, attributionControl: !opts.compact, zoomControl: true });
    /* Leaflet's default prefix carries a flag; keep the credit, drop the rest.
       (The OSM/CARTO lines on the tile layers are license-required — untouched.) */
    if (map.attributionControl)
      map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
    /* wheel zoom armed by intent (click), disarmed when the pointer leaves —
       stops the page-scroll hijack without making zoom unreachable */
    map.on('click focus', () => map.scrollWheelZoom.enable());
    el.addEventListener('mouseleave', () => map.scrollWheelZoom.disable());

    const carto = L.tileLayer(cartoUrl(), {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: 'abcd', maxZoom: 19 });
    const topo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
      attribution: '© OSM © <a href="https://opentopomap.org">OpenTopoMap</a>', maxZoom: 17 });
    const sat = satelliteLayer();
    carto.addTo(map);
    window.addEventListener('themechange', () => carto.setUrl(cartoUrl()));
    /* streets stays the default — the station chips have to stay legible; the
       imagery is there when you want to see the actual terrain under them */
    L.control.layers({ 'streets': carto, 'terrain': topo, 'satellite': sat },
                     {}, { position: 'topright', collapsed: true }).addTo(map);

    const fit = () => map.fitBounds(sited().map(s => [s.lat, s.lon]), { padding: [40, 40], maxZoom: 13 });

    /* ---- lightning range rings ----
       The AS3935 reports distance without bearing, so a ring around the
       reporting station IS the honest picture. One draw function serves both
       moments: rings for the LTG.windowMin ending at `atMs`, faded toward it
       — "now" and "the browsed past" are the same question at different
       times. Intensity (energy) sets brightness/thickness and thins the field
       (see LTG note above). */
    state.rings = L.layerGroup();
    function drawRings(events, atMs) {
      state.rings.clearLayers();
      const by = {}; sited().forEach(s => { by[s.slug] = s; });

      /* window + join to station, carrying age and raw energy */
      const win = [];
      (events || []).forEach(ev => {
        const s = by[ev.slug];
        if (!s || ev.distance_km == null) return;
        const ageMin = (atMs - new Date(ev.ts).getTime()) / 60000;
        if (ageMin < 0 || ageMin > LTG.windowMin) return;
        win.push({ ev, s, ageMin, energy: ev.energy || 0 });
      });
      if (!win.length) return;

      /* intensity, relative to the strongest strike currently in view */
      const maxE = Math.max(1, ...win.map(w => w.energy));
      win.forEach(w => { w.intensity = w.energy ? clamp(w.energy / maxE, 0, 1) : 0.2; });

      /* thin the field: keep only the strongest few rings per station */
      const perStation = {};
      win.forEach(w => (perStation[w.ev.slug] ||= []).push(w));
      const keep = [];
      Object.values(perStation).forEach(arr => {
        arr.sort((a, b) => b.intensity - a.intensity);
        keep.push(...arr.slice(0, LTG.perStation));
      });

      keep.forEach(w => {
        const fade = Math.pow(1 - w.ageMin / LTG.windowMin, LTG.fadePow);
        const alpha = (0.30 + 0.55 * w.intensity) * fade;
        if (alpha < LTG.minAlpha) return;         /* too weak/old to bother */
        L.circle([w.s.lat, w.s.lon], {
          radius: w.ev.distance_km * 1000, fill: false,
          color: `hsl(42,85%,${(46 + 30 * w.intensity).toFixed(0)}%)`, /* ochre→gold */
          weight: 1 + 1.8 * w.intensity,
          opacity: alpha,
        }).bindTooltip(`⚡ ${w.ev.distance_km} km · ${new Date(w.ev.ts)
            .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`)
          .addTo(state.rings);
      });
    }
    /* strike history cache: 24 h covers every scrubbable moment AND the live
       window, so one endpoint call serves both (10-min TTL) */
    async function ensureStrikes() {
      if (state.ltg && Date.now() - state.ltgAt < 10 * 60 * 1000) return;
      const d = await getJSON('/lightning?hours=24');
      state.ltg = d.events || [];
      state.ltgAt = Date.now();
    }
    async function ringsUpdate() {
      if (!map.hasLayer(state.rings)) return;
      await ensureStrikes();
      drawRings(state.ltg, state.scrubAt != null ? state.scrubAt * 1000 : Date.now());
    }

    /* ---- human reports layer ----
       Emoji pins that fade with age over a 6 h window; popup carries the
       details. Same shape as the lightning rings: a toggle, a cached fetch
       (5-min TTL), a 60 s redraw so the fade is visible. */
    state.reports = L.layerGroup();
    const RP_GLYPH = { precip: '🌧', hail: '🧊', fog: '🌫', snow_line: '❄',
                       wind_damage: '💨', road_blocked: '🚧', flood: '🌊' };
    /* each kind gets a ring color so pins read against any basemap — the fog
       glyph alone is a grey blob on a grey map */
    const RP_COLOR = { precip: '#4a8fd4', hail: '#6ec6d8', fog: '#8d99ab',
                       snow_line: '#a8c4e0', wind_damage: '#2fa08c',
                       road_blocked: '#e0a020', flood: '#7f5fc4' };
    const RP_WINDOW_H = 6;
    async function ensureReports() {
      if (state.rp && Date.now() - state.rpAt < 5 * 60 * 1000) return;
      const d = await getJSON(`/reports?hours=${RP_WINDOW_H}`);
      state.rp = d.enabled === false ? null : (d.reports || []);
      state.rpAt = Date.now();
    }
    function drawReports() {
      state.reports.clearLayers();
      /* stations are the anchor and never move; report pins that would land
         on a chip (the "near which station?" picker puts them at EXACTLY the
         station's coords) or on each other fan out in a small arc instead of
         stacking. Pixel-space, so it's redrawn on zoom. */
      const stationPts = sited().map(s => map.latLngToLayerPoint([s.lat, s.lon]));
      const placedPts = [];
      const collides = pt =>
        stationPts.some(sp => sp.distanceTo(pt) < 30) ||
        placedPts.some(pp => pp.distanceTo(pt) < 26);
      (state.rp || []).forEach(r => {
        const ageH = (Date.now() - new Date(r.ts).getTime()) / 3600e3;
        if (ageH < 0 || ageH > RP_WINDOW_H) return;
        const fade = Math.max(0.45, 1 - ageH / RP_WINDOW_H);
        const fresh = ageH < 0.5 ? ' fresh' : '';
        let pt = map.latLngToLayerPoint([r.lat, r.lon]);
        if (collides(pt)) {
          for (let k = 0; k < 12; k++) {
            const a = (k * 60 - 30) * Math.PI / 180;
            const rad = 32 + 10 * Math.floor(k / 6);
            const q = L.point(pt.x + rad * Math.cos(a), pt.y + rad * Math.sin(a));
            if (!collides(q)) { pt = q; break; }
          }
        }
        placedPts.push(pt);
        const icon = L.divIcon({
          className: 'rp-pin-wrap',
          html: `<div class="rp-pin${fresh}" style="opacity:${fade.toFixed(2)};` +
                `--rp-c:${RP_COLOR[r.kind] || 'var(--accent-2)'}">${RP_GLYPH[r.kind] || '💬'}</div>`,
          iconSize: null, iconAnchor: [15, 15],
        });
        const label = r.kind.replace(/_/g, ' ')
          + (r.intensity ? [' (light)', ' (moderate)', ' (heavy)'][r.intensity - 1] : '');
        L.marker(map.layerPointToLatLng(pt), { icon, keyboard: false }).addTo(state.reports)
          .bindTooltip(`${label} · ${agoLabel(r.ts)}`)
          .bindPopup(`<div class="map-pop"><h4>💬 ${label}
              ${r.qc_flag === 'corroborated' ? '<span class="badge ok">✓ station agrees</span>' : ''}</h4>
            <div class="l">${agoLabel(r.ts)} · ${r.reporter || 'someone nearby'}${r.trusted ? ' ★' : ''}</div>
            ${r.note ? `<div class="r"><span>note</span><b>${r.note.replace(/</g, '&lt;')}</b></div>` : ''}
          </div>`, { maxWidth: 240 });
      });
    }
    async function reportsUpdate() {
      if (!map.hasLayer(state.reports)) return;
      await ensureReports();
      drawReports();
    }
    /* the fan-out is computed in pixels — re-lay it out when the scale changes */
    map.on('zoomend', () => { if (map.hasLayer(state.reports)) drawReports(); });

    /* ---- you are here ----
       Auto-centering NEVER prompts: it only uses a geolocation grant the
       user already made (the report dialog is where asking happens). The 📍
       tool asks explicitly. Centering on the user only makes sense when
       they're actually near the mesh — from far away, stay on the stations. */
    const NEAR_MESH_KM = 60;
    function _kmTo(lat, lon, s) {
      return Math.hypot((s.lat - lat) * 111.32,
                        (s.lon - lon) * 111.32 * Math.cos(lat * Math.PI / 180));
    }
    function showMe(lat, lon, center) {
      if (state.meMarker) state.meMarker.remove();
      state.meMarker = L.marker([lat, lon], {
        icon: L.divIcon({ className: 'me-dot-wrap', html: '<div class="me-dot"></div>',
                          iconSize: [14, 14], iconAnchor: [7, 7] }),
        keyboard: false, interactive: false, zIndexOffset: 500,
      }).addTo(map);
      const nearest = Math.min(Infinity, ...sited().map(s => _kmTo(lat, lon, s)));
      if (center && nearest <= NEAR_MESH_KM) {
        map.setView([lat, lon], Math.max(map.getZoom(), 12));
      }
    }
    (async () => {
      try {
        if (!navigator.permissions || !navigator.geolocation) return;
        const p = await navigator.permissions.query({ name: 'geolocation' });
        if (p.state !== 'granted') return;
        navigator.geolocation.getCurrentPosition(
          pos => showMe(pos.coords.latitude, pos.coords.longitude, true),
          () => {}, { enableHighAccuracy: false, timeout: 6000, maximumAge: 300000 });
      } catch { /* no permission API — the 📍 button still works */ }
    })();

    /* ---- "you are here" ----
       Auto-centering NEVER prompts: it only uses a geolocation grant the
       user already gave (the report dialog is where asking happens). The 📍
       tool asks explicitly. Centering happens only when the user is within
       valley range of the mesh — centering a viewer in Delhi on themselves
       would show an empty map. */
    const NEAR_KM = 60;
    /* center: false = dot only · true = polite (center only near the mesh,
       for the silent auto-locate) · 'force' = the user pressed the button,
       center on them regardless — google-maps behavior */
    function showMe(lat, lon, center) {
      if (state.meMarker) state.meMarker.remove();
      state.meMarker = L.marker([lat, lon], {
        icon: L.divIcon({ className: 'me-dot-wrap', html: '<div class="me-dot"></div>',
                          iconSize: [12, 12], iconAnchor: [6, 6] }),
        keyboard: false, interactive: false, zIndexOffset: 500,
      }).addTo(map);
      el.querySelector('.wx-tools [data-t="me"]')?.classList.add('live');
      const nearest = Math.min(...sited().map(s => Math.hypot(
        (s.lat - lat) * 111.32,
        (s.lon - lon) * 111.32 * Math.cos(lat * Math.PI / 180))));
      if (center === 'force') {
        map.setView([lat, lon], nearest <= NEAR_KM ? Math.max(map.getZoom(), 12)
                                                   : map.getZoom());
      } else if (center && nearest <= NEAR_KM) {
        map.setView([lat, lon], Math.max(map.getZoom(), 12));
      }
    }
    (async () => {
      try {
        if (!navigator.permissions || !navigator.geolocation) return;
        const p = await navigator.permissions.query({ name: 'geolocation' });
        if (p.state !== 'granted') return;
        navigator.geolocation.getCurrentPosition(
          pos => showMe(pos.coords.latitude, pos.coords.longitude, true),
          () => {}, { enableHighAccuracy: false, timeout: 6000, maximumAge: 300000 });
      } catch { /* no permissions API — stay quiet, the 📍 tool still works */ }
    })();

    /* ---- controls: modes row + tools row, ONE control so the block sits
       beside the zoom column (row layout via CSS on .leaflet-top.leaflet-left) */
    const ctl = L.control({ position: 'topleft' });
    ctl.onAdd = () => {
      const wrap = L.DomUtil.create('div', 'wx-ctl');
      L.DomEvent.disableClickPropagation(wrap);
      L.DomEvent.disableScrollPropagation(wrap);

      const modes = L.DomUtil.create('div', 'wx-modes leaflet-bar', wrap);
      modes.innerHTML = Object.entries(MODES).map(([k, m]) =>
        `<button type="button" data-mode="${k}" class="${k === state.mode ? 'on' : ''}">${m.label}</button>`).join('');
      modes.addEventListener('click', e => {
        const b = e.target.closest('button[data-mode]');
        if (!b) return;
        state.mode = b.dataset.mode;
        modes.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
        renderMarkers(); renderLegend();
      });

      const tools = L.DomUtil.create('div', 'wx-tools leaflet-bar', wrap);
      tools.innerHTML = `<button type="button" data-t="radar" title="rain radar (RainViewer)">☂</button>
                     <button type="button" data-t="ltg" title="recent lightning">⚡</button>
                     <button type="button" data-t="rep" title="human weather reports, last 6 h">💬</button>
                     <button type="button" data-t="scrub" title="time travel, last 24 h">⏱</button>
                     <button type="button" data-t="me" title="center on my location"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 1.5v4M12 18.5v4M1.5 12h4M18.5 12h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="12" r="2.4" fill="currentColor"/></svg></button>
                     <button type="button" data-t="fit" title="fit stations">⌖</button>` +
        (opts.compact ? '' : `<button type="button" data-t="fs" title="fullscreen">⛶</button>`);
      tools.addEventListener('click', async e => {
        const b = e.target.closest('button[data-t]'); if (!b) return;
        if (b.dataset.t === 'fit') fit();
        if (b.dataset.t === 'me') {
          if (!navigator.geolocation) { b.title = 'this browser has no geolocation'; return; }
          b.classList.add('on');
          navigator.geolocation.getCurrentPosition(
            pos => { b.classList.remove('on');
                     showMe(pos.coords.latitude, pos.coords.longitude, 'force'); },
            ()  => { b.classList.remove('on');
                     b.title = 'no location fix — check browser & OS permissions'; },
            { enableHighAccuracy: false, timeout: 8000, maximumAge: 120000 });
        }
        if (b.dataset.t === 'fs') {
          const full = el.closest('.map-panel, .grid-stack-item-content, body')
                         .classList.toggle('map-full');
          /* the button must confess what the next click does */
          b.classList.toggle('on', full);
          b.textContent = full ? '✕' : '⛶';
          b.title = full ? 'exit fullscreen' : 'fullscreen';
          setTimeout(() => { map.invalidateSize(); fit(); }, 220);
        }
        if (b.dataset.t === 'ltg') {
          if (map.hasLayer(state.rings)) {
            map.removeLayer(state.rings);
            clearInterval(state.ringsTimer); b.classList.remove('on');
          } else {
            try {
              state.rings.addTo(map);
              await ringsUpdate();           /* honors scrubAt if time-traveling */
              b.classList.add('on');
              /* redraw every 60 s so the live fade is visible; the fetch
                 inside ensureStrikes stays throttled to its 10-min TTL */
              state.ringsTimer = setInterval(() => ringsUpdate().catch(() => {}),
                                             60 * 1000);
            } catch { map.removeLayer(state.rings); b.title = 'lightning feed unavailable'; }
          }
        }
        if (b.dataset.t === 'rep') {
          if (map.hasLayer(state.reports)) {
            map.removeLayer(state.reports);
            clearInterval(state.reportsTimer); b.classList.remove('on');
          } else {
            try {
              state.reports.addTo(map);
              await reportsUpdate();
              b.classList.add('on');
              state.reportsTimer = setInterval(() => reportsUpdate().catch(() => {}),
                                               60 * 1000);
            } catch { map.removeLayer(state.reports); b.title = 'reports unavailable'; }
          }
        }
        if (b.dataset.t === 'scrub') toggleScrub(b);
        if (b.dataset.t === 'radar') {
          if (state.radar) {
            map.removeLayer(state.radar); state.radar = null;
            clearInterval(state.radarTimer); b.classList.remove('on');
          } else {
            try {
              /* radar composites are native only to low zooms — upscale past
                 that or RainViewer serves "Zoom Level Not Supported" tiles */
              state.radar = L.tileLayer(await radarUrl(),
                { opacity: 0.65, maxNativeZoom: 7, maxZoom: 19 }).addTo(map);
              b.classList.add('on');
              state.radarTimer = setInterval(async () => {
                try { state.radar && state.radar.setUrl(await radarUrl()); } catch {}
              }, 10 * 60 * 1000);
            } catch { b.title = 'radar unavailable right now'; }
          }
        }
      });
      return wrap;
    };
    ctl.addTo(map);

    /* ---- time scrubber: replay the mesh's last 24 h ---- */
    const SCRUB_METRICS = 'temp_c,wind_avg_ms,wind_gust_ms,wind_dir_deg,rain_mm,pm25,pm10,batt_v';
    const scrubEl = L.DomUtil.create('div', 'wx-scrub', el);
    scrubEl.innerHTML = `<button type="button" class="play" title="play the last 24 h">▶</button>
      <button type="button" class="live">live</button>
      <input type="range" min="0" max="1000" value="1000" aria-label="time scrubber" />
      <span class="t">now</span>`;
    scrubEl.style.display = 'none';
    L.DomEvent.disableClickPropagation(scrubEl);
    L.DomEvent.disableScrollPropagation(scrubEl);
    scrubEl.addEventListener('pointerdown', ev => ev.stopPropagation());
    const scrubInput = scrubEl.querySelector('input');
    const scrubLabel = scrubEl.querySelector('.t');
    const playBtn    = scrubEl.querySelector('.play');

    async function loadHistory() {
      /* per-station history, fetched on first need, refreshed when >10 min old */
      if (state.tl && Date.now() - state.tlAt <= 10 * 60 * 1000) return;
      scrubLabel.textContent = 'loading…';
      state.tl = {};
      state.tlAt = Date.now();
      await Promise.all(sited().map(async s => {
        try {
          state.tl[s.slug] = await getJSON(
            `/stations/${s.slug}/series?metrics=${SCRUB_METRICS}&hours=24`);
        } catch { /* station without history scrubs as blank */ }
      }));
      scrubLabel.textContent = 'now';
    }

    /* the ONE place scrub position becomes UI state — the slider's input
       event, the player, and the live button all funnel through here      */
    function setScrub(permille) {
      scrubInput.value = permille;
      if (permille >= 1000) {
        state.scrubAt = null;
        scrubLabel.textContent = 'now';
      } else {
        state.scrubAt = Date.now() / 1000 - (1 - permille / 1000) * 24 * 3600;
        scrubLabel.textContent = new Date(state.scrubAt * 1000)
          .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      renderMarkers();
      ringsUpdate().catch(() => {});   /* rings follow the browsed moment */
    }
    scrubInput.addEventListener('input', ev => {
      stopPlay();
      setScrub(Number(ev.target.value));
    });
    scrubEl.querySelector('.live').addEventListener('click', () => {
      stopPlay();
      setScrub(1000);
    });

    /* ---- playback: ▶ sweeps the window to now (~13 s); ⏸ pauses in place;
       pressing ▶ again resumes from the pause point (from the start when
       already live). Ends by landing back on live.                          */
    function stopPlay() {
      if (!state.playTimer) return;
      clearInterval(state.playTimer); state.playTimer = null;
      playBtn.textContent = '▶'; playBtn.title = 'play the last 24 h';
      playBtn.classList.remove('on');
    }
    playBtn.addEventListener('click', async () => {
      if (state.playTimer) { stopPlay(); return; }
      await loadHistory();
      try { await ensureStrikes(); } catch { /* rings just won't animate */ }
      playBtn.textContent = '⏸'; playBtn.title = 'pause';
      playBtn.classList.add('on');
      let v = Number(scrubInput.value);
      if (v >= 1000) v = 0;            /* starting from live = start of window */
      setScrub(v);
      state.playTimer = setInterval(() => {
        v += 8;
        if (v >= 1000) { stopPlay(); setScrub(1000); return; }
        setScrub(v);
      }, 110);
    });

    async function toggleScrub(btn) {
      if (scrubEl.style.display !== 'none') {
        stopPlay();
        scrubEl.style.display = 'none'; btn.classList.remove('on');
        el.classList.remove('scrubbing');
        setScrub(1000);                /* leave time travel = return to live */
        return;
      }
      btn.classList.add('on');
      scrubEl.style.display = 'flex';
      el.classList.add('scrubbing');   /* CSS hides the legend on small screens */
      await loadHistory();
    }

    function scrubSample(s, atS) {
      const tl = state.tl && state.tl[s.slug];
      if (!tl || !tl.ts || !tl.ts.length) return { ...s, sampleOk: false };
      let best = -1, bestD = Infinity;
      for (let i = 0; i < tl.ts.length; i++) {
        const d = Math.abs(tl.ts[i] - atS);
        if (d < bestD) { bestD = d; best = i; }
      }
      if (bestD > 1800) return { ...s, sampleOk: false };  /* >30 min gap */
      const out = { ...s, sampleOk: true };
      for (const k of Object.keys(tl.series || {})) out[k] = tl.series[k][best];
      return out;
    }

    /* legend */
    const legendCtl = L.control({ position: 'bottomleft' });
    let legendEl = null;
    legendCtl.onAdd = () => {
      legendEl = L.DomUtil.create('div', 'wx-legend');
      return legendEl;
    };
    if (!opts.compact) legendCtl.addTo(map);
    const renderLegend = () => { if (legendEl) legendEl.innerHTML = legendHtml(state.mode); };

    function renderMarkers() {
      state.markers.forEach(m => m.remove());
      const scrub = state.scrubAt != null;
      state.markers = sited().map(orig => {
        const s = scrub ? scrubSample(orig, state.scrubAt) : orig;
        const staleOverride = scrub ? !s.sampleOk : undefined;
        return L.marker([s.lat, s.lon],
                        { icon: chipIcon(s, state.mode, staleOverride), keyboard: false })
          .addTo(map).bindPopup(popupHtml(scrub ? orig : s), { maxWidth: 280 });
      });                          /* popups always show LIVE data */
    }

    map.on('popupopen', ev => fillCam(ev.popup.getElement()));

    state.stations = stations;
    fit(); renderMarkers(); renderLegend();
    window.addEventListener('themechange', renderMarkers);

    return {
      map,
      update(next) {
        state.stations = next;
        if (state.scrubAt == null) renderMarkers();
      },
      destroy() {
        clearInterval(state.radarTimer);
        clearInterval(state.ringsTimer);
        clearInterval(state.reportsTimer);
        clearInterval(state.playTimer);
        window.removeEventListener('themechange', renderMarkers);
        map.remove();
      },
    };
  }

  return create;
})();
