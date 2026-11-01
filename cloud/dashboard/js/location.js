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

    /* 0) the operator's designated home station, if it is sited. Every rule
          a fallback can invent is arbitrary — "most recently heard" flipped
          between stations reporting a minute apart, alphabetical is stable
          but meaningless — so the honest answer is to let someone say. */
    try {
      await _cfgReady;
      const home = _cfg && _cfg.homeStation;
      if (home && sited.some(s => s.slug === home)) { activeSlug = home; return; }
    } catch { /* no config: fall through to the guesses below */ }

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

    /* 3) nothing known → answer anyway. A weather site whose first words are
          "pick a location" has asked the reader to work before telling them
          anything (docs/v2-design.md §3.3). Default to the first sited station
          — where there is only one, that IS the answer — and deliberately do
          NOT persist it, so a real choice or a later geolocation grant still
          wins on the next visit.
          Prefer a station that has actually been heard from, most recent
          first: a registered-but-silent station (one exists) would otherwise
          become the default and greet every visitor with a confident "—",
          which is worse than asking them to choose. */
    const FRESH_MS = 30 * 60 * 1000, now = Date.now();
    const live = sited.filter(s => s.last_seen &&
      now - new Date(s.last_seen).getTime() < FRESH_MS);
    const everHeard = sited.filter(s => s.last_seen)
      .sort((a, b) => new Date(b.last_seen) - new Date(a.last_seen));
    /* Deterministic, not "whichever reported last". Two stations reporting a
       minute apart made the homepage flip between them from one load to the
       next — a visitor refreshing saw the temperature jump between two
       villages for no reason they could see. Recency still EXCLUDES stations
       that have gone quiet; among the ones that are live the API's own stable
       slug ordering decides, so the same visitor gets the same place every
       time. (A station that has been heard at all, however long ago, still
       beats one that never has.)
       The real answer is a designated home station, which belongs with the
       rest of the admin work — docs/v2-design.md §5 Phase 4. */
    activeSlug = (live[0] || everHeard[0] || sited[0]).slug;
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
