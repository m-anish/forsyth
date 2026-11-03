/* forsyth live — theme manager. Pref cycles auto → light → dark → sky
   (localStorage); 'auto' follows prefers-color-scheme live, 'sky' follows the
   sun. Emits 'themechange' on <window>. See docs/sky-design.md.

   'sky' is a FOURTH mode and not a redefinition of 'auto', on purpose. A lot
   of people set dark permanently and mean it; answering that with "but it is
   noon in Bir" overrides a stated preference. Nobody gets this who has not
   asked for it. */
'use strict';

const Theme = (() => {
  const KEY = 'forsyth-theme';
  const PLACE = 'forsyth-sky-place';
  const MODES = ['auto', 'light', 'dark', 'sky'];
  const media = matchMedia('(prefers-color-scheme: dark)');
  /* More contrast pins the palette to the plain light/dark pair, which are the
     two with the most headroom. prefers-reduced-motion deliberately does NOT:
     the palette turns four times a day behind a 250ms crossfade, which is not
     motion in the sense that setting is about, and honouring it there would
     deny the whole feature to anyone who merely dislikes animation. */
  const contrast = matchMedia('(prefers-contrast: more)');

  /* localStorage throws rather than returning null in some privacy modes, and
     the first thing this file does now happens BEFORE first paint. An
     exception there would leave data-theme unset and paint every reader the
     default dark regardless of what they chose. */
  function ls(k) { try { return localStorage.getItem(k); } catch { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } }

  function pref() {
    const p = ls(KEY);
    return MODES.indexOf(p) >= 0 ? p : 'auto';
  }

  /* --- where ------------------------------------------------------------- */

  /* The sun's altitude needs a place, and the place comes from the API, which
     is asynchronous — while the palette has to be right before first paint or
     every single load flashes night and then jumps. So the coordinates are
     cached here and the step is computed from the cache at parse time.
     Only the coordinates are cached, not the step: sunAltitude is pure
     arithmetic, so a cached place gives the exact current step for free, and a
     cached step would be a second thing to keep honest for no gain. */
  function readPlace() {
    try {
      const p = JSON.parse(ls(PLACE) || 'null');
      return p && Number.isFinite(p.lat) && Number.isFinite(p.lon) ? p : null;
    } catch { return null; }
  }

  /* Pages that know which station they are showing call this (station.js, and
     the board via Widgets.stations). Coordinates move by metres, never miles,
     so a tolerance stops this writing to storage on every refresh. */
  function place(lat, lon) {
    /* Number.isFinite, not the global one: isFinite(null) is TRUE, because it
       coerces, and a station with no coordinates would have cached (0, 0) and
       put the sun over the Gulf of Guinea. */
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const cur = readPlace();
    if (cur && Math.abs(cur.lat - lat) < 0.01 && Math.abs(cur.lon - lon) < 0.01) return;
    lsSet(PLACE, JSON.stringify({ lat: +lat, lon: +lon }));
    if (pref() === 'sky') apply();
  }

  /* --- which step ------------------------------------------------------- */

  /* Anchored to the sun's altitude rather than the clock, so dawn and dusk are
     the same two steps in reverse and nothing is an arbitrary hour. -0.833° is
     the horizon with refraction and the sun's own radius allowed for; -12° is
     where civil twilight has effectively gone. Ordered brightest first. */
  const STEPS = [[6, 'day'], [-0.833, 'golden'], [-12, 'dusk']];
  const BASE = { day: 'light', golden: 'light', dusk: 'dark', night: 'dark' };

  /* null means "not in sky mode, or not able to be" — no preference for it, a
     reader who asked for more contrast, or no coordinates yet (a first-ever
     visit, which falls back to 'auto' rather than guessing a hemisphere). */
  function step() {
    if (pref() !== 'sky' || contrast.matches) return null;
    const p = readPlace();
    if (!p) return null;
    const alt = sunAltitude(Date.now(), p.lat, p.lon);
    if (!Number.isFinite(alt)) return null;
    for (const [min, name] of STEPS) if (alt > min) return name;
    return 'night';
  }

  /* Still light-or-dark, because that is what the map tiles and the charts
     ask for and neither has four variants to offer. */
  function resolved() {
    const s = step();
    if (s) return BASE[s];
    const p = pref();
    return (p === 'auto' || p === 'sky') ? (media.matches ? 'dark' : 'light') : p;
  }

  /* --- applying it ------------------------------------------------------ */

  const GLYPH = { auto: '◐', light: '○', dark: '●', sky: '◉' };
  let announced = null;

  function apply() {
    const s = step(), base = resolved();
    const de = document.documentElement;
    de.dataset.theme = base;
    /* data-theme keeps carrying the base, which is what lets every
       [data-theme="light"] rule, color-scheme, the map tiles and the charts go
       on working without knowing the sky steps exist. data-sky is the overlay
       the two new palettes hang off. */
    if (s) de.dataset.sky = s; else delete de.dataset.sky;

    const btn = document.querySelector('.theme-btn');
    if (btn) {
      const p = pref();
      /* label in its own span so mobile CSS can keep just the icon */
      btn.innerHTML = GLYPH[p] + ' <span class="tl">' + p + '</span>';
      btn.title = 'theme: ' + p
        + (p === 'sky' ? (s ? ' · ' + s : ' · waiting for a location') : '')
        + ' (click to change)';
    }

    /* Announce only a real change. The five-minute re-check below would
       otherwise rebuild every chart on the page 288 times a day and throw away
       the reader's cursor and zoom each time. It also quietly stops the
       existing no-op cases — auto → light on a light OS is a new label and the
       same palette, and used to rebuild everything. */
    const sig = base + '/' + (s || '');
    if (sig !== announced) {
      announced = sig;
      window.dispatchEvent(new CustomEvent('themechange', { detail: base }));
    }
  }

  function cycle() {
    lsSet(KEY, MODES[(MODES.indexOf(pref()) + 1) % MODES.length]);
    apply();
  }

  media.addEventListener('change', () => { if (pref() !== 'light' && pref() !== 'dark') apply(); });
  contrast.addEventListener('change', () => { if (pref() === 'sky') apply(); });

  /* The step turns on its own. Five minutes is at most 1.25° of altitude even
     at the equator, so no boundary is passed by more than that, and apply() is
     silent unless the step really changed. Skipped while hidden — the desktop
     app's browser pane and every background tab throttle timers anyway — and
     re-checked on the way back, which is the laptop-reopened-at-dusk case. */
  setInterval(() => { if (!document.hidden && pref() === 'sky') apply(); }, 300000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && pref() === 'sky') apply();
  });

  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.querySelector('.theme-btn');
    if (btn) btn.addEventListener('click', cycle);
    apply();

    // mobile nav: the ☰ button toggles the .right cluster into a dropdown, so
    // the bar stays clean and busy pages (board, logged in) never overflow.
    const menu = document.querySelector('.nav-menu');
    const right = document.querySelector('.topbar .right');
    if (menu && right) {
      const close = () => { right.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); };
      menu.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = right.classList.toggle('open');
        menu.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      // tapping a nav item or anywhere outside closes it
      right.addEventListener('click', (e) => { if (e.target.closest('a, button:not(.theme-btn)')) close(); });
      document.addEventListener('click', (e) => { if (!e.target.closest('.topbar')) close(); });
    }
  });

  /* set the attributes as early as possible to avoid a flash of wrong theme.
     Both of them: the sky step is computed from the cached place here, so a
     returning reader paints golden at golden and never sees the correction. */
  const s0 = step();
  document.documentElement.dataset.theme = resolved();
  if (s0) document.documentElement.dataset.sky = s0;

  return { pref, resolved, step, place, cycle };
})();

/* How high the sun is, in degrees, at an instant and a place — the standard
   NOAA/SunCalc approximation, good to about a minute at these latitudes.

   It lives HERE, in the <head> script, rather than with the rest of the solar
   maths in common.js, because the sky palette has to be decided before first
   paint and common.js loads at the end of <body>. common.js's sunTimes() and
   nightBands() use it from this file; every page that loads common.js loads
   theme.js first, so the order holds. */
function sunAltitude(dateMs, lat, lon) {
  const rad = Math.PI / 180, J1970 = 2440588, J2000 = 2451545;
  const d = dateMs / 86400000 - 0.5 + J1970 - J2000;
  const M = rad * (357.5291 + 0.98560028 * d);
  const C = rad * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M));
  const L = M + C + rad * 102.9372 + Math.PI;
  const e = rad * 23.4397;
  const dec = Math.asin(Math.sin(L) * Math.sin(e));
  const ra = Math.atan2(Math.sin(L) * Math.cos(e), Math.cos(L));
  const H = rad * (280.16 + 360.9856235 * d) - rad * -lon - ra;
  return Math.asin(Math.sin(rad * lat) * Math.sin(dec) +
                   Math.cos(rad * lat) * Math.cos(dec) * Math.cos(H)) / rad;
}
