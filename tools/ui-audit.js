/* tools/ui-audit.js — paste into the browser console on any Forsyth page.
 *
 *   Returns {counts, findings}. Run it at 375 / 768 / 1440 px in BOTH themes:
 *   several real defects only appeared in one of the four combinations.
 *
 * Written 2026-11-01 for the v2 completeness audit, after three defects in a
 * row got past a visual review — the hero's stat row reading "66% Wind", the
 * forecast chart silently absent, and a pressure axis printing 838.75 as
 * "38.75". A number that is merely wrong is easy to miss; one that is still
 * perfectly readable is almost impossible to.
 *
 * Known limitation, do not "fix" what it reports blindly: the a11y-name check
 * looks for aria-label, title and label[for], and so flags inputs wrapped in
 * <label>text <input></label>, which is a valid implicit association. It
 * reported three false positives on the station page's download form.
 *
 * Deliberately synchronous and rAF-free: the desktop app's browser pane runs
 * as a background page when hidden, which stalls requestAnimationFrame.
 */

(() => {
  const F = [];
  const add = (sev, kind, msg, el) => F.push({
    sev, kind, msg,
    where: el ? (el.id ? '#' + el.id
      : (el.className && String(el.className).trim().split(/\s+/).slice(0, 2).join('.')) || el.tagName)
      : null,
  });

  const vis = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };

  /* --- 1. page-level horizontal overflow (the classic phone defect) ------ */
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 1) {
    const wide = [...document.querySelectorAll('body *')].filter(el => {
      const r = el.getBoundingClientRect();
      return r.right > de.clientWidth + 1 && vis(el);
    }).slice(0, 4);
    add('high', 'overflow',
      `page scrolls horizontally (${de.scrollWidth} > ${de.clientWidth})`,
      wide[0]);
  }

  /* --- 2. clipped text: content wider/taller than its own box ------------ */
  for (const el of document.querySelectorAll(
    '.wg-body *, .panel *, .hero-stats *, .kv *, .trend-chip *, .fc-seg *')) {
    if (!vis(el)) continue;
    if (el.children.length) continue;                 // leaf nodes only
    const cs = getComputedStyle(el);
    if (cs.overflow === 'visible' && cs.overflowX === 'visible') continue;
    if (el.scrollWidth > el.clientWidth + 2) {
      add('high', 'clipped',
        `"${(el.textContent || '').trim().slice(0, 36)}" cut off `
        + `(${el.scrollWidth} > ${el.clientWidth})`, el);
    }
  }

  /* --- 3. inner scrollbars on a card (you should scroll the page) -------- */
  for (const b of document.querySelectorAll('.wg-body, .grid-stack-item-content')) {
    if (!vis(b)) continue;
    if (b.scrollHeight > b.clientHeight + 4 &&
        ['auto', 'scroll'].includes(getComputedStyle(b).overflowY)) {
      add('med', 'inner-scroll',
        `card scrolls inside itself (${b.scrollHeight} > ${b.clientHeight})`, b);
    }
  }

  /* --- 4. dead canvases / zero-size charts and maps ---------------------- */
  for (const c of document.querySelectorAll('canvas, .leaflet-container, svg.rose, svg.spark')) {
    const r = c.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) {
      add('high', 'zero-size', `${c.tagName.toLowerCase()} rendered at ${Math.round(r.width)}x${Math.round(r.height)}`, c);
    }
  }

  /* --- 5. accessible names on interactive things ------------------------ */
  for (const el of document.querySelectorAll('button, a[href], select, input')) {
    if (!vis(el)) continue;
    const name = (el.getAttribute('aria-label') || el.textContent || el.title
      || el.getAttribute('alt') || '').trim();
    if (!name) add('med', 'a11y-name', `${el.tagName.toLowerCase()} has no accessible name`, el);
  }
  for (const img of document.querySelectorAll('img')) {
    if (!img.hasAttribute('alt')) add('med', 'a11y-name', 'img has no alt attribute', img);
    if (img.complete && img.naturalWidth === 0 && img.src) {
      add('high', 'broken-img', `image failed to load: ${img.src.slice(0, 60)}`, img);
    }
  }

  /* --- 6. touch targets (WCAG 2.5.8 wants 24px, Apple suggests 44) ------ */
  if (innerWidth < 768) {
    for (const el of document.querySelectorAll('button, a[href], select')) {
      if (!vis(el)) continue;
      if (el.closest('.leaflet-control-attribution')) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 24 || r.height < 24) {
        add('low', 'touch-target',
          `${Math.round(r.width)}x${Math.round(r.height)} — "${(el.textContent || el.title || '').trim().slice(0, 18)}"`, el);
      }
    }
  }

  /* --- 7. text contrast against the nearest painted background ---------- */
  const lum = c => {
    const s = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2];
  };
  const parse = s => {
    const m = /rgba?\(([^)]+)\)/.exec(s || '');
    if (!m) return null;
    const p = m[1].split(',').map(Number);
    return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 };
  };
  const bgOf = el => {
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const b = parse(getComputedStyle(n).backgroundColor);
      if (b && b.a > 0.5) return b.rgb;
    }
    const b = parse(getComputedStyle(document.body).backgroundColor);
    return b ? b.rgb : [0, 0, 0];
  };
  const seen = new Set();
  for (const el of document.querySelectorAll(
    'p, span, div, h1, h2, h3, h4, a, button, td, th, li, label, option')) {
    if (!vis(el) || el.children.length) continue;
    const txt = (el.textContent || '').trim();
    if (txt.length < 2) continue;
    const cs = getComputedStyle(el);
    const fg = parse(cs.color);
    if (!fg || fg.a < 0.5) continue;
    const bg = bgOf(el);
    const L1 = lum(fg.rgb), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const px = parseFloat(cs.fontSize);
    const bold = (parseInt(cs.fontWeight, 10) || 400) >= 700;
    const large = px >= 24 || (px >= 18.66 && bold);
    const need = large ? 3 : 4.5;
    if (ratio < need) {
      const key = cs.color + '|' + bg.join(',') + '|' + Math.round(px);
      if (seen.has(key)) continue;
      seen.add(key);
      add(ratio < need - 1.2 ? 'med' : 'low', 'contrast',
        `${ratio.toFixed(2)}:1 (needs ${need}) ${Math.round(px)}px "${txt.slice(0, 28)}"`, el);
    }
  }

  return {
    url: location.pathname + location.search,
    width: innerWidth,
    theme: document.documentElement.dataset.theme || 'auto',
    counts: F.reduce((a, f) => (a[f.sev] = (a[f.sev] || 0) + 1, a), {}),
    findings: F,
  };
})()
