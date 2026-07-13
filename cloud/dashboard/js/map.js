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
  function chipIcon(s, mode) {
    const m = MODES[mode];
    const v = m.value(s);
    const stale = isStale(s.last_seen);
    const bg = stale || v == null ? 'hsl(215,12%,52%)' : m.color(v);
    const arrow = (s.wind_dir_deg != null && !stale)
      ? `<span class="wc-a" style="transform:rotate(${(s.wind_dir_deg + 180) % 360}deg)">↑</span>` : '';
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
      <a href="station.html?slug=${s.slug}">station page →</a>
    </div>`;
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
    /* wheel zoom armed by intent (click), disarmed when the pointer leaves —
       stops the page-scroll hijack without making zoom unreachable */
    map.on('click focus', () => map.scrollWheelZoom.enable());
    el.addEventListener('mouseleave', () => map.scrollWheelZoom.disable());

    const carto = L.tileLayer(cartoUrl(), {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: 'abcd', maxZoom: 19 });
    const topo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
      attribution: '© OSM © <a href="https://opentopomap.org">OpenTopoMap</a>', maxZoom: 17 });
    carto.addTo(map);
    window.addEventListener('themechange', () => carto.setUrl(cartoUrl()));
    L.control.layers({ 'streets': carto, 'terrain': topo }, {}, { position: 'topright', collapsed: true }).addTo(map);

    const fit = () => map.fitBounds(sited().map(s => [s.lat, s.lon]), { padding: [40, 40], maxZoom: 13 });

    /* mode switcher */
    const modeCtl = L.control({ position: 'topleft' });
    modeCtl.onAdd = () => {
      const d = L.DomUtil.create('div', 'wx-modes leaflet-bar');
      d.innerHTML = Object.entries(MODES).map(([k, m]) =>
        `<button type="button" data-mode="${k}" class="${k === state.mode ? 'on' : ''}">${m.label}</button>`).join('');
      L.DomEvent.disableClickPropagation(d);
      d.addEventListener('click', e => {
        const b = e.target.closest('button[data-mode]');
        if (!b) return;
        state.mode = b.dataset.mode;
        d.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
        renderMarkers(); renderLegend();
      });
      return d;
    };
    modeCtl.addTo(map);

    /* radar toggle + refit + fullscreen, one bar */
    const toolCtl = L.control({ position: 'topleft' });
    toolCtl.onAdd = () => {
      const d = L.DomUtil.create('div', 'wx-tools leaflet-bar');
      d.innerHTML = `<button type="button" data-t="radar" title="rain radar (RainViewer)">☂</button>
                     <button type="button" data-t="fit" title="fit stations">⌖</button>` +
        (opts.compact ? '' : `<button type="button" data-t="fs" title="fullscreen">⛶</button>`);
      L.DomEvent.disableClickPropagation(d);
      d.addEventListener('click', async e => {
        const b = e.target.closest('button[data-t]'); if (!b) return;
        if (b.dataset.t === 'fit') fit();
        if (b.dataset.t === 'fs') {
          el.closest('.map-panel, .grid-stack-item-content, body').classList.toggle('map-full');
          setTimeout(() => { map.invalidateSize(); fit(); }, 220);
        }
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
      return d;
    };
    toolCtl.addTo(map);

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
      state.markers = sited().map(s =>
        L.marker([s.lat, s.lon], { icon: chipIcon(s, state.mode), keyboard: false })
          .addTo(map).bindPopup(popupHtml(s), { maxWidth: 280 }));
    }

    state.stations = stations;
    fit(); renderMarkers(); renderLegend();
    window.addEventListener('themechange', renderMarkers);

    return {
      map,
      update(next) { state.stations = next; renderMarkers(); },
      destroy() {
        clearInterval(state.radarTimer);
        window.removeEventListener('themechange', renderMarkers);
        map.remove();
      },
    };
  }

  return create;
})();
