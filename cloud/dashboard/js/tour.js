/* forsyth — first-run walkthrough. Shown once per browser after signing in
   (or any time with ?tour=1). No library: a spotlight hole, a card, five
   short stops. Steps whose target isn't on the page are skipped. */
'use strict';

const Tour = (() => {
  const KEY = 'forsyth-tour-done';
  const STEPS = [
    { sel: null, title: 'Welcome to forsyth',
      text: 'A mesh of small weather stations in the hills — plus forecasts that are checked, hour by hour, against what actually happened. A quick look around?' },
    { sel: '.wg-banner, .wx-banner', title: 'The banner speaks first',
      text: 'One sentence on what the sky is doing: observed now, expected soon. When the stations disagree with the models, the stations win.' },
    { sel: '.wg-range', title: 'Time is a tap away',
      text: 'Widgets carry their own range — 24 hours, a week, a month. Inside any chart: hover for values, drag to zoom, double-click to reset.' },
    { sel: '.report-fab', title: 'Report the sky',
      text: 'Your eyes count. Rain, hail, fog, a blocked road — reports are cross-checked against the nearest station and sharpen the warnings for everyone.' },
    { sel: '#btn-new-board', title: 'A board of your own',
      text: 'This arrangement is just the default. Make your own — pick stations, charts, the map — and share it if you like.' },
  ];

  let i = 0, hole = null, card = null;

  function destroy(markDone) {
    if (markDone) localStorage.setItem(KEY, '1');
    hole?.remove(); card?.remove();
    hole = card = null;
    document.removeEventListener('keydown', onKey);
    removeEventListener('scroll', onMove, true);
    removeEventListener('resize', onMove);
  }
  function onKey(e) { if (e.key === 'Escape') destroy(true); }
  /* the spotlight must follow its target if the user scrolls or resizes */
  let raf = 0;
  function onMove() {
    if (!hole || raf) return;
    raf = requestAnimationFrame(() => { raf = 0; if (hole) show(); });
  }

  function target(step) {
    if (!step.sel) return null;
    return [...document.querySelectorAll(step.sel)]
      .find(el => el.getClientRects().length);
  }

  let shownStep = -1;
  function show() {
    while (i < STEPS.length && STEPS[i].sel && !target(STEPS[i])) i++;
    if (i >= STEPS.length) { destroy(true); return; }
    const step = STEPS[i], t = target(step);
    /* scroll to the target only on step entry — repositioning on the user's
       own scroll must not yank the page back */
    if (t && shownStep !== i) t.scrollIntoView({ block: 'center', behavior: 'instant' });
    shownStep = i;
    const r = t ? t.getBoundingClientRect() : null;
    if (r) {
      Object.assign(hole.style, { display: 'block', left: r.left - 6 + 'px',
        top: r.top - 6 + 'px', width: r.width + 12 + 'px', height: r.height + 12 + 'px' });
    } else {
      /* no target: park the hole offscreen at zero size — its giant shadow
         still dims the page evenly for the centered card */
      Object.assign(hole.style, { display: 'block', left: '-20px', top: '-20px',
        width: '0px', height: '0px' });
    }
    card.querySelector('h4').textContent = step.title;
    card.querySelector('p').textContent = step.text;
    card.querySelector('.n').textContent = `${i + 1} / ${STEPS.length}`;
    card.querySelector('.next').textContent = i === STEPS.length - 1 ? 'done' : 'next →';
    if (r) {
      const ch = card.offsetHeight || 170;
      const below = r.bottom + 12 + ch < innerHeight;
      card.style.top = (below ? r.bottom + 12 : Math.max(12, r.top - ch - 12)) + 'px';
      card.style.left = Math.min(Math.max(12, r.left), innerWidth - 312) + 'px';
      card.style.transform = 'none';
    } else {
      card.style.top = '50%'; card.style.left = '50%';
      card.style.transform = 'translate(-50%,-50%)';
    }
  }

  function start() {
    if (hole) return;
    hole = document.createElement('div');
    hole.className = 'tour-hole';
    card = document.createElement('div');
    card.className = 'tour-card';
    card.innerHTML = `<h4></h4><p></p>
      <div class="row"><span class="n"></span>
        <button type="button" class="tool-btn skip">skip</button>
        <button type="button" class="tool-btn save next">next →</button></div>`;
    document.body.append(hole, card);
    card.querySelector('.skip').onclick = () => destroy(true);
    card.querySelector('.next').onclick = () => {
      i++;
      if (i >= STEPS.length) destroy(true); else show();
    };
    document.addEventListener('keydown', onKey);
    addEventListener('scroll', onMove, true);
    addEventListener('resize', onMove);
    i = 0;
    show();
  }

  function maybeStart() {
    if (new URLSearchParams(location.search).get('tour') === '1') { start(); return; }
    if (!localStorage.getItem(KEY)) start();
  }

  return { start, maybeStart };
})();
