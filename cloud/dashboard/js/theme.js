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
  });
  // set the attribute as early as possible to avoid a flash of wrong theme
  document.documentElement.dataset.theme = resolved();

  return { pref, resolved, cycle };
})();
