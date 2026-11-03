#!/usr/bin/env node
/* tools/palette-contrast.js — sweep every palette in css/dash.css for WCAG
 * contrast, without a browser.
 *
 *   node tools/palette-contrast.js            # all palettes, failures only
 *   node tools/palette-contrast.js --all      # every pair, including passes
 *   node tools/palette-contrast.js dusk       # one palette
 *
 * Written 2026-11-03 for the sky palettes (docs/sky-design.md phase 1). The
 * existing light palette's --text-mute carries a comment recording that a
 * first pass solved it against --bg-card alone and still failed at 4.13 on the
 * darker --bg-elev panels. That is the bug this file exists to prevent: every
 * foreground is checked against ALL THREE painted backgrounds, and the worst
 * of the three is what counts.
 *
 * ui-audit.js is the companion and not a substitute — it measures what a real
 * page actually renders, including pairs no token table predicts. This checks
 * the table itself, which is cheap enough to run on every palette edit.
 *
 * Thresholds are WCAG 2.1 AA: 4.5:1 for body text, 3:1 for large text and for
 * graphics that carry meaning. Which bucket a token is in is a judgement about
 * how it is USED, so it lives in the ROLES table below; a token this file does
 * not know about is reported as unclassified rather than silently skipped.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const CSS = path.join(__dirname, '..', 'cloud', 'dashboard', 'css', 'dash.css');

/* The three painted backgrounds. Anything that sits on a card sits on one of
   these, and --bg-elev is the one that catches people out: it is darker than
   --bg-card in the light palettes, so solving against the card alone is not
   solving anything. */
const BACKGROUNDS = ['--bg', '--bg-elev', '--bg-card'];

/* need: 4.5 = body text, 3 = large text (>=24px, or >=18.66px bold) and
   graphics conveying meaning (WCAG 1.4.11). */
const ROLES = {
  '--text':      { need: 4.5, what: 'body text' },
  '--text-dim':  { need: 4.5, what: 'secondary text' },
  '--text-mute': { need: 4.5, what: 'muted text (captions, units)' },
  '--accent':    { need: 4.5, what: 'links' },
  '--accent-2':  { need: 3.0, what: 'tags and chips (large/graphic)' },
  '--good':      { need: 4.5, what: 'status text' },
  '--warn':      { need: 4.5, what: 'status text' },
  '--bad':       { need: 4.5, what: 'status text' },
  '--ch-axis':   { need: 3.0, what: 'chart axis labels (graphic)' },
  '--ch-temp':   { need: 3.0, what: 'chart series' },
  '--ch-rh':     { need: 3.0, what: 'chart series' },
  '--ch-pres':   { need: 3.0, what: 'chart series' },
  '--ch-wind':   { need: 3.0, what: 'chart series' },
  '--ch-gust':   { need: 3.0, what: 'chart series' },
  '--ch-rain':   { need: 3.0, what: 'chart series' },
  '--ch-pm25':   { need: 3.0, what: 'chart series' },
  '--ch-pm10':   { need: 3.0, what: 'chart series' },
  '--ch-batt':   { need: 3.0, what: 'chart series' },
  '--wx-sun':    { need: 3.0, what: 'sky icon' },
  '--wx-moon':   { need: 3.0, what: 'sky icon' },
  '--wx-cloud':  { need: 3.0, what: 'sky icon' },
  '--rose-3':    { need: 3.0, what: 'wind rose (darkest petal)' },
  '--rose-4':    { need: 3.0, what: 'wind rose (needle)' },
};

/* Tokens that are deliberately low-contrast and must NOT be swept: hairlines,
   fills under a stroke, shadows, and the rose's pale petals, which are read as
   a group against each other rather than against the paper. */
const SKIP = /^--(border|border-2|ch-grid|night-band|topbar-bg|shadow|rose-1|rose-2|.*-fill)$/;

/* ------------------------------------------------------------------ parsing */

function palettes(css) {
  const out = new Map();
  /* Each palette is one `:root, [data-theme=…] { … }` or `[data-sky=…] { … }`
     block. Later blocks inherit from their base, which is why `inherits`
     exists: a sky palette only overrides what it changes. */
  const re = /(^|\n)([^{}\n][^{}]*?)\{([^}]*)\}/g;
  let m;
  while ((m = re.exec(css))) {
    const sel = m[2].trim(), body = m[3];
    if (!/--bg\s*:|--text\s*:|data-sky|data-theme/.test(sel + body)) continue;
    const names = [];
    if (/:root|\[data-theme="dark"\]/.test(sel)) names.push('dark');
    const t = /\[data-theme="(light)"\]/.exec(sel);
    if (t && !/\s[.#]/.test(sel)) names.push(t[1]);
    const s = /\[data-sky="([a-z]+)"\]/.exec(sel);
    if (s && !/\s[.#]/.test(sel)) names.push(s[1]);
    if (!names.length) continue;

    const vars = {};
    for (const d of body.split(';')) {
      const kv = /^\s*(--[a-z0-9-]+)\s*:\s*([^;]+?)\s*$/i.exec(d.replace(/\/\*[\s\S]*?\*\//g, ''));
      if (kv) vars[kv[1]] = kv[2].trim();
    }
    if (!Object.keys(vars).length) continue;
    for (const n of names) {
      const prev = out.get(n);
      out.set(n, { name: n, vars: Object.assign(prev ? prev.vars : {}, vars) });
    }
  }
  /* sky steps are overlays: day and golden sit on light, dusk and night on
     dark. Resolve them so a sweep sees the palette a browser would compute. */
  const inherits = { day: 'light', golden: 'light', dusk: 'dark', night: 'dark' };
  for (const [n, base] of Object.entries(inherits)) {
    const p = out.get(n), b = out.get(base);
    if (p && b) p.vars = Object.assign({}, b.vars, p.vars);
  }
  return out;
}

/* --------------------------------------------------------------- the colour */

function rgb(v) {
  let m = /^#([0-9a-f]{6})$/i.exec(v);
  if (m) {
    const h = parseInt(m[1], 16);
    return [(h >> 16) & 255, (h >> 8) & 255, h & 255];
  }
  m = /^#([0-9a-f]{3})$/i.exec(v);
  if (m) return [...m[1]].map(c => parseInt(c + c, 16));
  m = /^rgba?\(([^)]+)\)/i.exec(v);
  if (m) {
    const p = m[1].split(',').map(x => parseFloat(x));
    /* A translucent foreground has no single ratio — it depends on what is
       behind it. Report rather than guess: nothing in ROLES is translucent. */
    if (p.length > 3 && p[3] < 0.999) return null;
    return p.slice(0, 3);
  }
  return null;
}

const lum = c => {
  const s = c.map(v => (v /= 255, v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2];
};

const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};

/* ----------------------------------------------------------------- the sweep */

function sweep(p) {
  const rows = [], unknown = [], unparsed = [];
  const bgs = BACKGROUNDS.map(b => [b, rgb(p.vars[b])]).filter(([, c]) => c);

  for (const [name, raw] of Object.entries(p.vars)) {
    if (SKIP.test(name) || BACKGROUNDS.includes(name)) continue;
    const role = ROLES[name];
    if (!role) { unknown.push(name); continue; }
    const fg = rgb(raw);
    if (!fg) { unparsed.push(name + ': ' + raw); continue; }
    let worst = null;
    for (const [bn, bc] of bgs) {
      const r = ratio(fg, bc);
      if (!worst || r < worst.r) worst = { r, on: bn };
    }
    rows.push({ name, raw, need: role.need, what: role.what, ...worst });
  }
  rows.sort((a, b) => (a.r - a.need) - (b.r - b.need));
  return { rows, unknown, unparsed };
}

/* ------------------------------------------------------------------- report */

const args = process.argv.slice(2);
const showAll = args.includes('--all');
const only = args.filter(a => !a.startsWith('--'));

const all = palettes(fs.readFileSync(CSS, 'utf8'));
const order = ['light', 'dark', 'day', 'golden', 'dusk', 'night']
  .filter(n => all.has(n) && (!only.length || only.includes(n)));

if (!order.length) {
  console.error('no palettes matched. found: ' + [...all.keys()].join(', '));
  process.exit(2);
}

let fails = 0, tight = 0;
for (const name of order) {
  const p = all.get(name);
  const { rows, unknown, unparsed } = sweep(p);
  console.log(`\n\x1b[1m${name}\x1b[0m  (bg ${p.vars['--bg']}, card ${p.vars['--bg-card']}, elev ${p.vars['--bg-elev']})`);
  for (const r of rows) {
    const bad = r.r < r.need;
    const near = !bad && r.r < r.need + 0.35;
    if (bad) fails++;
    if (near) tight++;
    if (!bad && !near && !showAll) continue;
    const mark = bad ? '\x1b[31mFAIL\x1b[0m' : near ? '\x1b[33mtight\x1b[0m' : '\x1b[32m ok  \x1b[0m';
    console.log(`  ${mark} ${r.name.padEnd(12)} ${r.raw.padEnd(9)} ` +
      `${r.r.toFixed(2)}:1 on ${r.on.padEnd(9)} (needs ${r.need})  ${r.what}`);
  }
  if (unparsed.length) console.log('  \x1b[33m?\x1b[0m    not a flat colour: ' + unparsed.join(', '));
  if (unknown.length) console.log('  \x1b[90m-\x1b[0m    unclassified, not swept: ' + unknown.join(' '));
}

console.log(`\n${order.length} palette(s): ${fails} failing, ${tight} within 0.35 of the limit.`);
process.exit(fails ? 1 : 0);
