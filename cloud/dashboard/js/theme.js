/* forsyth live — theme manager. Pref cycles auto → light → dark (localStorage);
   'auto' follows prefers-color-scheme live. Emits 'themechange' on <window>. */
'use strict';

const Theme = (() => {
  const KEY = 'forsyth-theme';
  const media = matchMedia('(prefers-color-scheme: dark)');

  function pref() { return localStorage.getItem(KEY) || 'auto'; }

  function resolved() {
    const p = pref();
    return p === 'auto' ? (media.matches ? 'dark' : 'light') : p;
  }

  function apply() {
    document.documentElement.dataset.theme = resolved();
    const btn = document.querySelector('.theme-btn');
    if (btn) {
      const p = pref();
      const icon = p === 'auto' ? '◐' : p === 'light' ? '○' : '●';
      /* label in its own span so mobile CSS can keep just the icon */
      btn.innerHTML = icon + ' <span class="tl">' + p + '</span>';
      btn.title = 'theme: ' + p + ' (click to change)';
    }
    window.dispatchEvent(new CustomEvent('themechange', { detail: resolved() }));
  }

  function cycle() {
    const order = ['auto', 'light', 'dark'];
    localStorage.setItem(KEY, order[(order.indexOf(pref()) + 1) % 3]);
    apply();
  }

  media.addEventListener('change', () => { if (pref() === 'auto') apply(); });
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
  // set the attribute as early as possible to avoid a flash of wrong theme
  document.documentElement.dataset.theme = resolved();

  return { pref, resolved, cycle };
})();
