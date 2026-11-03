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

  /* How high the sun is right now, in degrees, or null with no place. The
     scene uses it for the one thing the four palette STEPS cannot answer:
     how warm the light is. Steps only exist in 'sky' theme mode, and the
     scene is drawn for everyone, so a low-sun colour keyed to [data-sky]
     would simply never appear for most readers. */
  function sunAlt(atMs) {
    const p = coords();
    if (!p) return null;
    const a = sunPosition(atMs === undefined ? Date.now() : atMs, p.lat, p.lon).altitude;
    return Number.isFinite(a) ? a : null;
  }

  /* Where the moon is and what it looks like, or null when there is nothing
     to draw — no coordinates, below the horizon, or so near new that there is
     no lit limb to see. A moon is NOT up all night: it rises about fifty
     minutes later each day, so for much of the month the small hours have no
     moon in them at all, and drawing one anyway would be the most visible
     possible way of being wrong. */
  function moon(atMs) {
    const p = coords();
    if (!p) return null;
    const t = atMs === undefined ? Date.now() : atMs;
    const pos = moonPosition(t, p.lat, p.lon);
    if (!(pos.altitude > 1)) return null;
    const ill = moonIllumination(t);
    if (ill.fraction < 0.03) return null;        // new: nothing lit to draw
    return {
      x: across(pos.azimuth),
      alt: pos.altitude,
      fraction: ill.fraction,
      waxing: ill.waxing,
    };
  }

  /* A compass bearing as a position across the card: 0 at the left, 1 at the
     right, east to west.

     The window is 60..300, not 90..270. The narrower one assumed nothing
     rises north of due east, which is false for both bodies here: a
     high-declination full moon rises around 60 degrees and set around 300,
     and it spent the first four hours of a November night pinned motionless
     against the left edge before the clamp let go. The midsummer sun does the
     same thing. The clamp still has to exist — something behind the viewer
     has no place on a card showing the southern sky — but it should bite at
     the horizon, not in the middle of the evening. */
  const across = az => Math.min(1, Math.max(0, (az - 60) / 240));

  /* Where the sun is across the card. The scene puts its light here, so the
     glow drifts over the day instead of sitting in a corner like a logo.
     0.5 with no place, which is the least wrong guess. */
  function sunX(atMs) {
    const p = coords();
    if (!p) return 0.5;
    return across(sunPosition(atMs === undefined ? Date.now() : atMs, p.lat, p.lon).azimuth);
  }

  /* The sun's bearing itself, which is what the ray angle needs. Drawing
     position and lighting direction are different questions: `across` is
     clamped and windowed for the card, and a slant built on it would change
     every time the window did. */
  function sunAz(atMs) {
    const p = coords();
    if (!p) return 180;
    return sunPosition(atMs === undefined ? Date.now() : atMs, p.lat, p.lon).azimuth;
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

  return { place, coords, step, base, sunX, sunAz, sunAlt, shadow, moon,
           forecast, state, kind: () => kind };
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
/* Shared celestial plumbing. The sun series was here first and the moon needs
   the same three steps — days since J2000, ecliptic to equatorial, and then
   equatorial to the local horizon — so they are written once. The obliquity,
   the sidereal-time constant and the sign convention are the kind of thing
   that drift apart if two copies exist. */
const CEL = {
  rad: Math.PI / 180,
  e: (Math.PI / 180) * 23.4397,          // obliquity of the ecliptic
  /* days since J2000.0, the epoch every series below is written against */
  days: ms => ms / 86400000 - 0.5 + 2440588 - 2451545,
  /* ecliptic longitude l and latitude b -> right ascension and declination */
  ra: (l, b) => Math.atan2(Math.sin(l) * Math.cos(CEL.e)
                         - Math.tan(b) * Math.sin(CEL.e), Math.cos(l)),
  dec: (l, b) => Math.asin(Math.sin(b) * Math.cos(CEL.e)
                         + Math.cos(b) * Math.sin(CEL.e) * Math.sin(l)),
  /* Greenwich mean sidereal time, as an hour angle at this longitude */
  sidereal: (d, lon) => CEL.rad * (280.16 + 360.9856235 * d) - CEL.rad * -lon,
  /* hour angle + latitude + declination -> where it is in the local sky */
  horizon: (H, phi, dec) => ({
    altitude: Math.asin(Math.sin(phi) * Math.sin(dec)
                      + Math.cos(phi) * Math.cos(dec) * Math.cos(H)) / CEL.rad,
    /* measured from south in this formulation; +180 puts it clockwise from
       north, which is how a compass bearing is read */
    azimuth: (Math.atan2(Math.sin(H),
              Math.cos(H) * Math.sin(phi) - Math.tan(dec) * Math.cos(phi))
              / CEL.rad + 360 + 180) % 360,
  }),
};

/* The sun's ecliptic longitude, and its mean anomaly, which the moon's
   illumination needs as well as its own position. */
function sunEcliptic(d) {
  const rad = CEL.rad;
  const M = rad * (357.5291 + 0.98560028 * d);
  const C = rad * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M));
  return { M, L: M + C + rad * 102.9372 + Math.PI };
}

function sunPosition(dateMs, lat, lon) {
  const d = CEL.days(dateMs);
  const { L } = sunEcliptic(d);
  const dec = Math.asin(Math.sin(L) * Math.sin(CEL.e));
  const ra = Math.atan2(Math.sin(L) * Math.cos(CEL.e), Math.cos(L));
  return CEL.horizon(CEL.sidereal(d, lon) - ra, CEL.rad * lat, dec);
}

/* The moon's geocentric ecliptic position and its distance, to the precision
   the Astronomical Almanac calls "low" — a few arcminutes, which at the size
   this is drawn is several orders of magnitude more than is needed. */
function moonEcliptic(d) {
  const rad = CEL.rad;
  const L = rad * (218.316 + 13.176396 * d);   // mean longitude
  const M = rad * (134.963 + 13.064993 * d);   // mean anomaly
  const F = rad * (93.272 + 13.229350 * d);    // argument of latitude
  return {
    l: L + rad * 6.289 * Math.sin(M),          // ecliptic longitude
    b: rad * 5.128 * Math.sin(F),              // ecliptic latitude
    dist: 385001 - 20905 * Math.cos(M),        // km
  };
}

function moonPosition(dateMs, lat, lon) {
  const d = CEL.days(dateMs), c = moonEcliptic(d);
  const ra = CEL.ra(c.l, c.b), dec = CEL.dec(c.l, c.b);
  const p = CEL.horizon(CEL.sidereal(d, lon) - ra, CEL.rad * lat, dec);
  /* Refraction lifts a low moon visibly — about half a degree at the horizon,
     which is the moon's own width, so it decides whether it has risen. */
  const h = p.altitude * CEL.rad;
  p.altitude += (0.017 / Math.tan(h + 0.0017 / (h + 0.089))) / CEL.rad * (h > -0.05 ? 1 : 0);
  return p;
}

/* How much of the moon is lit, and which side.

   `fraction` is 0 at new and 1 at full. `waxing` says which limb carries the
   light: growing moons are lit on the right from the northern hemisphere,
   shrinking ones on the left, and getting that backwards draws a moon that
   is three days out of date in a way anyone who looks up would notice. */
function moonIllumination(dateMs) {
  const d = CEL.days(dateMs);
  const { L } = sunEcliptic(d);
  const sdec = Math.asin(Math.sin(L) * Math.sin(CEL.e));
  const sra = Math.atan2(Math.sin(L) * Math.cos(CEL.e), Math.cos(L));
  const m = moonEcliptic(d);
  const mra = CEL.ra(m.l, m.b), mdec = CEL.dec(m.l, m.b);
  const SUN_KM = 149598000;
  /* elongation: the sun-earth-moon angle */
  const phi = Math.acos(Math.sin(sdec) * Math.sin(mdec)
            + Math.cos(sdec) * Math.cos(mdec) * Math.cos(sra - mra));
  /* phase angle: sun-moon-earth, which is what the terminator follows */
  const inc = Math.atan2(SUN_KM * Math.sin(phi), m.dist - SUN_KM * Math.cos(phi));
  const angle = Math.atan2(Math.cos(sdec) * Math.sin(sra - mra),
                           Math.sin(sdec) * Math.cos(mdec)
                         - Math.cos(sdec) * Math.sin(mdec) * Math.cos(sra - mra));
  return { fraction: (1 + Math.cos(inc)) / 2, waxing: angle < 0 };
}

function sunAltitude(dateMs, lat, lon) {
  return sunPosition(dateMs, lat, lon).altitude;
}
