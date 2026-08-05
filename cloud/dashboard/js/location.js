/* js/location.js — the homepage's "active location": which station the
   location-bound widgets (forecast, current conditions, wind rose, temp/RH)
   follow. Resolved, in order: a saved choice, else the nearest sited station
   to an ALREADY-GRANTED geolocation (never prompts on load), else null — in
   which case those widgets show a "pick a location" placeholder and the rest of
   the page (map, reports, lightning, health) stays fully live.

   Widgets read this via the '@here' sentinel in their config.station; the
   sticky banner (board.js) lets the reader switch or use their location. */
'use strict';

const ForsythLoc = (() => {
  const KEY = 'forsyth.loc';
  let activeSlug = null;
  let sited = [];
  const subs = [];

  const active = () => activeSlug;
  const stations = () => sited;
  const activeStation = () => sited.find(s => s.slug === activeSlug) || null;
  const onChange = (fn) => subs.push(fn);
  const notify = () => subs.forEach(fn => { try { fn(); } catch {} });

  function set(slug, persist = true) {
    activeSlug = slug || null;
    if (persist && activeSlug) localStorage.setItem(KEY, activeSlug);
    notify();
  }

  function kmTo(lat, lon, s) {
    const R = 6371, r = Math.PI / 180;
    const dLat = (s.lat - lat) * r, dLon = (s.lon - lon) * r;
    const a = Math.sin(dLat / 2) ** 2 +
      Math.cos(lat * r) * Math.cos(s.lat * r) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }
  function nearest(lat, lon) {
    let best = null, bestD = Infinity;
    for (const s of sited) { const d = kmTo(lat, lon, s); if (d < bestD) { bestD = d; best = s; } }
    return best;
  }
  function getPosition(opts) {
    return new Promise((res, rej) => navigator.geolocation.getCurrentPosition(res, rej, opts));
  }

  async function init() {
    try { sited = (await getJSON('/stations')).stations.filter(s => s.lat != null && s.lon != null); }
    catch { sited = []; }
    if (!sited.length) { activeSlug = null; return; }

    /* 1) a remembered choice wins */
    const saved = localStorage.getItem(KEY);
    if (saved && sited.some(s => s.slug === saved)) { activeSlug = saved; return; }

    /* 2) an already-granted geolocation → nearest station (never prompt here;
          match map.js's discipline of using a grant but not soliciting one) */
    try {
      if (navigator.permissions && navigator.geolocation) {
        const p = await navigator.permissions.query({ name: 'geolocation' });
        if (p.state === 'granted') {
          const pos = await getPosition({ timeout: 8000, maximumAge: 300000 });
          const s = nearest(pos.coords.latitude, pos.coords.longitude);
          if (s) { activeSlug = s.slug; return; }   /* auto-detected: don't persist, re-detect each visit */
        }
      }
    } catch { /* fall through to placeholder */ }

    /* 3) nothing → let the reader choose */
    activeSlug = null;
  }

  /* on-demand: the reader tapped "use my location" — here we may prompt */
  async function useMyLocation() {
    if (!navigator.geolocation) return false;
    try {
      const pos = await getPosition({ timeout: 8000, maximumAge: 120000 });
      const s = nearest(pos.coords.latitude, pos.coords.longitude);
      if (s) { set(s.slug); return true; }
    } catch { /* denied or timed out */ }
    return false;
  }

  return { init, active, activeStation, stations, set, onChange, useMyLocation };
})();

window.ForsythLoc = ForsythLoc;
