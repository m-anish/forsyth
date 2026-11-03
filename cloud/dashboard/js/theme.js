/* forsyth live — theme manager. Pref cycles auto → light → dark → sky
   (localStorage); 'auto' follows prefers-color-scheme live, 'sky' follows the
   sun, which js/sky.js works out. Emits 'themechange' on <window>.
   See docs/sky-design.md.

   'sky' is a FOURTH mode and not a redefinition of 'auto', on purpose. A lot
   of people set dark permanently and mean it; answering that with "but it is
   noon in Bir" overrides a stated preference. Nobody gets this who has not
   asked for it. */
'use strict';

const Theme = (() => {
  const KEY = 'forsyth-theme';
  const MODES = ['auto', 'light', 'dark', 'sky'];
  const media = matchMedia('(prefers-color-scheme: dark)');
  /* More contrast pins the palette to the plain light/dark pair, which are the
     two with the most headroom. prefers-reduced-motion deliberately does NOT:
     the palette turns four times a day behind a 250ms crossfade, which is not
     motion in the sense that setting is about, and honouring it there would
     deny the whole feature to anyone who merely dislikes animation. */
  const contrast = matchMedia('(prefers-contrast: more)');

  /* localStorage throws rather than returning null in some privacy modes, and
     the first thing this file does happens BEFORE first paint. An exception
     there would leave data-theme unset and paint every reader the default dark
     regardless of what they chose. */
  function ls(k) { try { return localStorage.getItem(k); } catch { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } }

  function pref() {
    const p = ls(KEY);
    return MODES.indexOf(p) >= 0 ? p : 'auto';
  }

  /* --- what the sky is doing -------------------------------------------- */

  /* js/sky.js owns the sun. This file only decides whether to paint it: null
     means the reader did not ask for a sky palette, or asked for more contrast
     and should get the two palettes with the most headroom, or there are no
     coordinates yet (a first-ever visit, which falls back to 'auto' rather
     than guessing a hemisphere). */
  function step() {
    if (pref() !== 'sky' || contrast.matches) return null;
    return Sky.step();
  }

  /* Still light-or-dark, because that is what the map tiles and the charts
     ask for and neither has four variants to offer. */
  function resolved() {
    const s = step();
    if (s) return Sky.base(s);
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

    /* Announce only a real change. Sky's re-check would otherwise rebuild
       every chart on the page 288 times a day and throw away the reader's
       cursor and zoom each time. It also quietly stops the existing no-op
       cases — auto → light on a light OS is a new label and the same palette,
       and used to rebuild everything. */
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
  /* Sky watches the clock and announces a turn; this file does not keep its
     own timer for it. The event fires only on a real change, so apply() is
     reached about four times a day rather than every five minutes. */
  window.addEventListener('skychange', () => { if (pref() === 'sky') apply(); });

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
     Both of them: Sky computes the step from its cached place synchronously,
     so a returning reader paints golden at golden and never sees a correction. */
  const s0 = step();
  document.documentElement.dataset.theme = resolved();
  if (s0) document.documentElement.dataset.sky = s0;

  return { pref, resolved, step, cycle };
})();
