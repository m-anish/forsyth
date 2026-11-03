/* tools/scene-audit.js — paste into the browser console on a page showing the
 * hero widget (the board, or a station page once one carries it).
 *
 *   await sceneAudit()            // the current palette and scene
 *   await sceneAudit.sweep()      // all 4 palette steps x all 5 sky states
 *
 * It checks ONE property, and it is the property the design rests on: that no
 * text in the hero intersects the scene's band. Nothing is read against the
 * scene, so there is no composite to measure and no alpha to keep verified.
 *
 * It started as a contrast meter instead, compositing the scene over the card
 * and reading the pixels under each glyph. That version earned its keep — it
 * found three real defects the arithmetic had missed: stars drawn with no
 * alpha ceiling measuring 1.06:1 under the trend chip, a moon placed at the
 * sun's azimuth landing on that same chip, and a dark-palette alpha that was
 * wrong in the direction I was most confident about, because --text sitting at
 * 14.7:1 says nothing about --text-mute sitting at 4.84:1.
 *
 * But every one of those was a symptom of putting a picture behind text and
 * then dimming it until it was safe. The scene was given its own band instead,
 * which makes all three impossible rather than merely measured, and turns this
 * file into a geometry check that cannot go stale when someone moves a cloud.
 *
 * ONE TRAP worth keeping in mind if you extend it: html/body transition
 * `color` over 250ms, and the desktop app's browser pane runs as a background
 * page when hidden, which STALLS transitions — getComputedStyle then returns a
 * colour halfway between the two themes, and a light page reports the dark
 * palette's text. This file injects a transition kill-switch first.
 */

(() => {
  const kill = () => {
    let s = document.getElementById('__scene-audit-nt');
    if (!s) { s = document.createElement('style'); s.id = '__scene-audit-nt'; document.head.appendChild(s); }
    s.textContent = '*,*::before,*::after{transition:none!important;animation:none!important}';
  };

  const overlap = (a, b) => !(a.right <= b.left || a.left >= b.right
                           || a.bottom <= b.top || a.top >= b.bottom);

  function sceneAudit() {
    kill();
    const sky = document.querySelector('.hero-sky');
    const hero = document.querySelector('.hero');
    if (!hero) return { error: 'no .hero on this page' };
    if (!sky) return { note: 'no scene (no forecast, or a station without one)', clean: true };
    const band = sky.getBoundingClientRect();

    /* Every leaf that renders text, plus .hero-temp, which has a child and so
       is not a leaf but is the tallest thing under the band and the first
       thing that would collide if the padding and the height drifted apart. */
    const nodes = [...hero.querySelectorAll('*')]
      .filter(e => !e.children.length && (e.textContent || '').trim());
    const temp = hero.querySelector('.hero-temp');
    if (temp) nodes.push(temp);
    /* the sparkline and any canvas count too: they are content, not chrome */
    nodes.push(...hero.querySelectorAll('svg.spark, canvas'));

    const hits = [];
    for (const el of nodes) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (!overlap(r, band)) continue;
      hits.push({ el: String(el.className) || el.tagName,
                  text: (el.textContent || '').trim().slice(0, 16),
                  overlapPx: Math.round(Math.min(r.bottom, band.bottom) - Math.max(r.top, band.top)) });
    }
    const de = document.documentElement.dataset;
    return {
      theme: de.theme, sky: de.sky || '(none)',
      bandH: Math.round(band.height),
      heroPadTop: Math.round(parseFloat(getComputedStyle(hero).paddingTop)),
      clean: hits.length === 0,
      /* the band and the padding are set from the same custom property, so a
         mismatch here means someone overrode one of them */
      matches: Math.abs(band.height - parseFloat(getComputedStyle(hero).paddingTop)) < 1,
      overlaps: hits,
    };
  }

  /* Every palette step against every sky state, at the current width.
     Restores whatever it found. */
  sceneAudit.sweep = async () => {
    const de = document.documentElement;
    const was = { theme: de.dataset.theme, sky: de.dataset.sky };
    const hero = document.querySelector('.hero');
    const body = hero?.parentElement;
    if (!body) return { error: 'no hero on this page' };
    const wasSky = body.querySelector('.hero-sky')?.outerHTML || null;
    const out = {};
    try {
      for (const [theme, sky, night] of
           [['light', 'day', false], ['light', 'golden', false],
            ['dark', 'dusk', true], ['dark', 'night', true]]) {
        de.dataset.theme = theme; de.dataset.sky = sky;
        out[sky] = {};
        for (const kind of ['clear', 'partly', 'cloud', 'rain', 'snow']) {
          body.querySelector('.hero-sky')?.remove();
          const d = document.createElement('div');
          d.className = 'hero-sky';
          d.innerHTML = wxScene(kind, night, Sky.sunX());
          body.insertBefore(d, body.firstChild);
          await new Promise(r => requestAnimationFrame
            ? requestAnimationFrame(() => r()) : setTimeout(r, 16));
          const a = sceneAudit();
          out[sky][kind] = a.clean && a.matches ? `ok (band ${a.bandH}px)`
            : (a.overlaps || []).map(h => `${h.el}/${h.text} by ${h.overlapPx}px`)
                .concat(a.matches ? [] : ['band and padding disagree']);
        }
      }
    } finally {
      if (was.theme) de.dataset.theme = was.theme; else delete de.dataset.theme;
      if (was.sky) de.dataset.sky = was.sky; else delete de.dataset.sky;
      body.querySelector('.hero-sky')?.remove();
      if (wasSky) body.insertAdjacentHTML('afterbegin', wasSky);
    }
    return out;
  };

  window.sceneAudit = sceneAudit;
  return 'sceneAudit() and sceneAudit.sweep() are ready';
})()
