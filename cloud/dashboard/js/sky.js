/* forsyth live — what the sky is doing, in one place. See docs/sky-design.md.

   Two signals live here, and they are deliberately kept apart:

     the STEP   — day / golden / dusk / night, from the sun's altitude.
                  Slow, global, and the thing js/theme.js paints the page with.
     the WEATHER — clear / partly / cloud / rain / snow, from the forecast.
                  An event rather than a mood; phase 3 draws it as a scene.

   Keeping them in different channels is what stops this becoming twenty
   palettes: a rainy night is the night step plus the rain state, and needs no
   rule of its own.

   This file loads in <head>, before js/theme.js, because the step has to be
   decided before first paint or every load flashes the wrong palette. It does
   no work and makes no request at parse time: everything below is either pure
   arithmetic or waits to be asked.

   It also holds the solar maths the charts use (sunAltitude, at the bottom),
   which is why the <head> is the right place for it rather than an accident
   of loading order. */
'use strict';

const Sky = (() => {
  const PLACE = 'forsyth-sky-place';

  /* Anchored to the sun's altitude rather than the clock, so dawn and dusk are
     the same two steps in reverse and nothing is an arbitrary hour. -0.833° is
     the horizon with refraction and the sun's own radius allowed for; -12° is
     where civil twilight has effectively gone. Ordered brightest first. */
  const STEPS = [[6, 'day'], [-0.833, 'golden'], [-12, 'dusk']];
  const BASE = { day: 'light', golden: 'light', dusk: 'dark', night: 'dark' };

  /* One window, asked for once. The API answers every forecast from now - 1 h
     regardless of `hours`, so a 48 h response is a strict superset of the 6 h
     one the hero used to fetch for its glyph alone — same first sample, same
     run. Routing both through here is what turns two requests into one. */
  const WINDOW_H = 48;

  /* localStorage throws rather than returning null in some privacy modes, and
     the first read happens before first paint. An exception there would leave
     the page unpainted, so every access is guarded. */
  function ls(k) { try { return localStorage.getItem(k); } catch { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } }

  /* ------------------------------------------------------------ the place */

  /* The sun's altitude needs coordinates, and those come from the API, which
     is asynchronous — while the palette has to be right before first paint.
     So the place is cached and the step is computed from the cache at parse
     time. Only the place is cached, never the step: sunAltitude is pure
     arithmetic, so a cached place yields the exact current step for free, and
     a cached step would be a second thing to keep honest. */
  function coords() {
    try {
      const p = JSON.parse(ls(PLACE) || 'null');
      return p && Number.isFinite(p.lat) && Number.isFinite(p.lon) ? p : null;
    } catch { return null; }
  }

  /* Pages that know which station they are showing call this: station.js with
     its one station, the board with the reader's chosen location or the first
     station that has coordinates. `slug` is remembered as the primary, so
     state() can be asked "what is the sky doing HERE" with no argument. */
  function place(lat, lon, slug) {
    /* Number.isFinite, not the global one: isFinite(null) is TRUE, because it
       coerces, and a station with no coordinates would have cached (0, 0) and
       put the sun over the Gulf of Guinea. */
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    if (slug) primary = slug;
    const cur = coords();
    /* Coordinates move by metres, never miles — a tolerance stops this writing
       to storage on every one-minute refresh. */
    if (cur && Math.abs(cur.lat - lat) < 0.01 && Math.abs(cur.lon - lon) < 0.01) {
      announce();
      return;
    }
    lsSet(PLACE, JSON.stringify({ lat: +lat, lon: +lon }));
    announce();
  }

  /* -------------------------------------------------------------- the step */

  /* null means the step cannot be known — no coordinates yet, which on a
     first-ever visit is the honest answer rather than a guessed hemisphere.
     Unconditional otherwise: Sky says what the sky is doing, and js/theme.js
     decides separately whether the reader asked for it to be painted. */
  function step(atMs) {
    const p = coords();
    if (!p) return null;
    const alt = sunAltitude(atMs === undefined ? Date.now() : atMs, p.lat, p.lon);
    if (!Number.isFinite(alt)) return null;
    for (const [min, name] of STEPS) if (alt > min) return name;
    return 'night';
  }

  /* Which of the two base palettes a step belongs to. The map tiles and the
     charts have light and dark and nothing else, so this is what they get. */
  function base(s) { return BASE[s] || null; }

  /* Which way, and how far, the sun throws a shadow right now.

     dx away from the sun's azimuth, dy always downward because light comes
     from above, and the length from the altitude — 1/tan is how long a
     shadow actually is, so it stretches as the sun drops and is shortest at
     noon. Clamped, because 1/tan goes to infinity at the horizon and a
     shadow the width of the card is not a nice touch, it is a bug.

     Returns null when there is no sun up to cast anything. */
  function shadow(atMs) {
    const p = coords();
    if (!p) return null;
    const s = sunPosition(atMs === undefined ? Date.now() : atMs, p.lat, p.lon);
    if (!(s.altitude > 2)) return null;          // below 2°: no useful light
    const rad = Math.PI / 180;
    const len = Math.min(3.4, 1 / Math.tan(Math.max(s.altitude, 12) * rad));
    /* Azimuth is clockwise from north and the shadow points the opposite way,
       so its east-west component is -sin(azimuth), eastward-positive. But
       sunX puts EAST at the left of the card, so east-positive is
       screen-NEGATIVE and the sign flips back: +sin. Written out because the
       first version had it backwards and a morning sun threw its shadow
       towards the morning. */
    return { dx: +(Math.sin(s.azimuth * rad) * len * 1.6).toFixed(2),
             dy: +(len * 1.1 + 0.6).toFixed(2) };
  }

  /* Where the sun sits across the sky as a fraction: 0 due east, 0.5 due
     south, 1 due west. The scene uses it to put its light where the light
     actually is, so the glow drifts across the card over a day instead of
     sitting in a fixed corner like a logo.

     Clamped to the 90..270 half because that is the half a scene can show:
     before sunrise and after sunset the sun is behind the viewer, and an
     unclamped azimuth would snap the glow from one edge to the other at
     midnight. Returns 0.5 with no place, which is the least wrong guess. */
  function sunX(atMs) {
    const p = coords();
    if (!p) return 0.5;
    const a = sunPosition(atMs === undefined ? Date.now() : atMs, p.lat, p.lon).azimuth;
    return Math.min(1, Math.max(0, (a - 90) / 180));
  }

  /* ----------------------------------------------------------- the weather */

  let primary = null;
  const cache = new Map();     // slug -> { hours, hour, data }
  const inflight = new Map();  // slug -> Promise, so parallel widgets ask once
  let kind = null;             // the primary station's sky state, or null

  /* The model run changes every three hours and the board refreshes every
     minute, so the cache turns over on the hour rather than per request. */
  const modelHour = () => Math.floor(Date.now() / 3600000);

  /* The sky state a forecast response opens with. wxKind lives in common.js;
     nothing here calls it before that file has loaded. */
  function kindFrom(data) {
    const F = (data && data.series) || {};
    return wxKind((F.precip_mm || [])[0], (F.precip_prob || [])[0],
                  (F.cloud_cover_pct || [])[0], (F.temp_c || [])[0]);
  }

  /* The one way anything on the page asks for a forecast. Serves a cached
     response whenever it covers the window asked for, dedupes requests that
     are already in flight, and never caches a failure — a station with no
     forecast yet should be asked again, not written off for the session. */
  function forecast(slug, hours) {
    const take = Math.max(hours || WINDOW_H, WINDOW_H);
    const hit = cache.get(slug);
    if (hit && hit.hour === modelHour() && hit.hours >= take) {
      return Promise.resolve(hit.data);
    }
    /* A request already on its way for a window at least as wide answers this
       one too — which is what stops a board's parallel widgets each opening
       their own. A wider window has to go out on its own. */
    const pending = inflight.get(slug);
    if (pending && pending.hours >= take) return pending.p;

    const p = getJSON(`/stations/${slug}/forecast?hours=${take}`)
      .then(data => {
        cache.set(slug, { hours: take, hour: modelHour(), data });
        return data;
      })
      .finally(() => {
        if (inflight.get(slug) && inflight.get(slug).p === p) inflight.delete(slug);
      });
    inflight.set(slug, { hours: take, p });
    return p;
  }

  /* What the sky is doing at a station: the step from the sun, the weather
     from the model. Either half may be null, and a caller showing one should
     cope with the other being absent rather than waiting for both — the step
     is known offline, the weather never is. */
  async function state(slug) {
    const s = slug || primary;
    let k = null;
    if (s) {
      try {
        k = kindFrom(await forecast(s));
      } catch {
        /* No forecast for this station. The primary keeps its last known
           state so a blip does not blank the hero's glyph; anything else
           reports not-known rather than borrowing another station's sky. */
        k = s === primary ? kind : null;
      }
      if (s === primary && k !== kind) { kind = k; announce(); }
    }
    const st = step();
    return { step: st, base: base(st), kind: k };
  }

  /* ---------------------------------------------------------- announcements */

  /* Announce only a real change. The re-check below runs on a timer, and a
     listener that redraws (phase 3's scene, and js/theme.js's palette) must
     not be woken 288 times a day to be told nothing moved. */
  let said = null;
  function announce() {
    const sig = (step() || '-') + '/' + (kind || '-');
    if (sig === said) return;
    said = sig;
    window.dispatchEvent(new CustomEvent('skychange', {
      detail: { step: step(), kind },
    }));
  }

  /* The step turns on its own. Five minutes is at most 1.25° of altitude even
     at the equator, so no boundary is passed by more than that, and announce()
     is silent unless it really turned. Skipped while hidden — background tabs
     throttle timers anyway — and re-checked on the way back, which is the
     laptop-reopened-at-dusk case. */
  setInterval(() => { if (!document.hidden) announce(); }, 300000);
  document.addEventListener('visibilitychange', () => {
    hidden();
    if (!document.hidden) announce();
  });

  /* The scene's animations pause on this (css/dash.css). Browsers throttle
     background animation but do not reliably stop it, and the desktop app's
     browser pane runs a hidden page as a background page, so a board left
     open behind another window would otherwise keep compositing rain. */
  function hidden() {
    const de = document.documentElement;
    if (document.hidden) de.dataset.hidden = ''; else delete de.dataset.hidden;
  }
  hidden();

  return { place, coords, step, base, sunX, shadow, forecast, state, kind: () => kind };
})();

/* Where the sun is, at an instant and a place — the standard NOAA/SunCalc
   approximation, good to about a minute at these latitudes. Altitude in
   degrees above the horizon, azimuth in degrees clockwise from north.

   Globals rather than members of Sky because common.js's sunTimes() and
   nightBands() use the altitude for the charts' night shading, and because the
   step has to be computable in <head>, before common.js has loaded at the end
   of <body>. Every page that loads common.js loads this file first.

   One shared body: azimuth is the same series as altitude with one more line
   at the end, and computing them apart would be two chances to drift. */
function sunPosition(dateMs, lat, lon) {
  const rad = Math.PI / 180, J1970 = 2440588, J2000 = 2451545;
  const d = dateMs / 86400000 - 0.5 + J1970 - J2000;
  const M = rad * (357.5291 + 0.98560028 * d);
  const C = rad * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M));
  const L = M + C + rad * 102.9372 + Math.PI;
  const e = rad * 23.4397;
  const dec = Math.asin(Math.sin(L) * Math.sin(e));
  const ra = Math.atan2(Math.sin(L) * Math.cos(e), Math.cos(L));
  const H = rad * (280.16 + 360.9856235 * d) - rad * -lon - ra;
  const phi = rad * lat;
  return {
    altitude: Math.asin(Math.sin(phi) * Math.sin(dec) +
                        Math.cos(phi) * Math.cos(dec) * Math.cos(H)) / rad,
    /* measured from south in this formulation; +180 puts it clockwise from
       north, which is how a compass bearing is read */
    azimuth: (Math.atan2(Math.sin(H),
              Math.cos(H) * Math.sin(phi) - Math.tan(dec) * Math.cos(phi)) / rad + 180) % 360,
  };
}

function sunAltitude(dateMs, lat, lon) {
  return sunPosition(dateMs, lat, lon).altitude;
}
