/* forsyth board — layout engine: GridStack + widget registry + auth + multi-boards.
   URL: board.html            → the site homepage board ('default')
        board.html?b=<slug>   → a specific board (owner always; others if public) */
'use strict';

const B = { user: null, grid: null, editing: false, meta: new Map(),
            slug: new URLSearchParams(location.search).get('b') || 'default',
            board: null };
let widSeq = 0;

/* apiJSON (the credentialed fetch) now lives in js/common.js, since js/auth.js
   needs it on every page — not just this one.
   Sign-in itself lives in js/auth.js (shared with the station page). */
const whoami = () => ForsythAuth.whoami();

/* ---------- widget DOM (unchanged mechanics) ---------- */

function widgetEl(w) {
  const el = document.createElement('div');
  el.className = 'grid-stack-item gs-type-' + w.type;
  el.setAttribute('gs-x', w.x); el.setAttribute('gs-y', w.y);
  el.setAttribute('gs-w', w.w); el.setAttribute('gs-h', w.h);
  const id = w.id || `w${Date.now()}_${widSeq++}`;
  el.dataset.wid = id;
  B.meta.set(id, { type: w.type, config: w.config || {} });
  const reg = Widgets.REGISTRY[w.type];
  el.innerHTML = `
    <div class="grid-stack-item-content">
      <div class="wg-head">
        <h3>${(w.config && w.config.title) || reg.label}</h3>
        <span class="wg-range"></span>
        <span class="wg-tools">
          <button type="button" data-act="cfg" title="configure">⚙</button>
          <button type="button" data-act="del" title="remove">✕</button>
        </span>
      </div>
      <div class="wg-body"></div>
    </div>`;
  el.querySelector('[data-act=cfg]').onclick = () => openConfig(el);
  el.querySelector('[data-act=del]').onclick = () => { B.grid.removeWidget(el); B.meta.delete(id); };
  return el;
}

/* one-tap range presets in the header — a per-widget switch, no dialog.
   Mutates config, so "save" while arranging persists the choice; outside
   edit mode it simply lasts the session. */
function rangeChips(el) {
  const meta = B.meta.get(el.dataset.wid);
  const span = el.querySelector('.wg-range');
  if (!meta || !span) return;
  const reg = Widgets.REGISTRY[meta.type];
  if (!reg.ranges) { span.innerHTML = ''; return; }
  const cur = Number(meta.config.hours || reg.defaultHours);
  span.innerHTML = reg.ranges.map(([h, l]) =>
    `<button type="button" data-h="${h}" class="${h === cur ? 'on' : ''}">${l}</button>`).join('');
  span.querySelectorAll('button').forEach(b => b.onclick = () => {
    meta.config.hours = Number(b.dataset.h);
    rangeChips(el);
    renderWidget(el);
  });
}

async function renderWidget(el) {
  const meta = B.meta.get(el.dataset.wid);
  if (!meta) return;
  rangeChips(el);
  const body = el.querySelector('.wg-body');
  try { await Widgets.REGISTRY[meta.type].render(body, meta.config); }
  catch (e) { body.innerHTML = `<p class="wg-empty">widget unhappy: ${e.message}</p>`; }
  if (Widgets.REGISTRY[meta.type].sizeToContent) fitToContent(el);
}

/* Grow a widget's row span to whatever its content actually needs. The local
   panel's sub-cards are content-sized and the total differs a lot between one
   column and two, so a fixed gs-h either clipped it or left a gap. GridStack's
   own sizeToContent reshuffled the board, so measure and set gs-h ourselves —
   rows are exactly cellHeight tall. Never shrinks below the widget's default. */
function fitToContent(el) {
  if (!B.grid || B.editing) return;
  requestAnimationFrame(() => {
    const content = el.querySelector('.grid-stack-item-content');
    const head = el.querySelector('.wg-head');
    const body = el.querySelector('.wg-body');
    if (!content || !body) return;
    const cs = getComputedStyle(body);
    const headH = head && head.offsetParent ? head.offsetHeight : 0;   // hidden on this widget
    const needed = body.scrollHeight + parseFloat(cs.paddingBottom) + headH;
    const cell = B.grid.getCellHeight(true) || 80;
    const rows = Math.max(1, Math.ceil(needed / cell));
    const node = el.gridstackNode;
    if (node && rows !== node.h) B.grid.update(el, { h: rows });
  });
}

function renderAll() {
  document.querySelectorAll('.grid-stack-item').forEach(renderWidget);
}


/* ---------- board load/save ---------- */

async function loadBoard() {
  let board;
  try {
    board = await apiJSON(`/boards/${B.slug}`);
  } catch (e) {
    document.getElementById('board-heading').textContent = 'No such board.';
    document.getElementById('board-sub').textContent =
      e.message.includes('private') ? 'This board is private. Its owner likes it that way.'
                                    : 'Nothing lives at this address.';
    return;
  }
  B.board = board;
  const layout = board.layout;
  /* On the homepage the weather is the headline — the banner does the talking,
     so the page furniture gets out of its way entirely. Named boards keep
     their title, because the owner chose it. */
  const isHome = B.slug === 'default';
  document.querySelector('.topbar .crumb').textContent = isHome ? '/ live' : '/ live / board';
  document.querySelector('.pagehead').classList.toggle('minimal', isHome);
  document.getElementById('board-kicker').hidden = true;
  document.getElementById('board-heading').hidden = isHome;
  document.getElementById('board-heading').textContent = board.title || layout.title || 'Board';
  applyHomeBtn();
  document.getElementById('board-title').value = board.title || '';
  document.getElementById('is-public').checked = !!board.is_public;
  document.getElementById('vis-wrap').style.display = B.slug === 'default' ? 'none' : '';
  document.getElementById('btn-delete-board').hidden = B.slug === 'default';
  document.getElementById('btn-publish-home').hidden = !(B.user && B.user.is_admin && B.slug !== 'default');
  document.getElementById('btn-edit').hidden = !board.can_edit;

  const sub = document.getElementById('board-sub');
  if (!isHome) {
    sub.textContent = board.is_public ? 'Public — anyone with this link' : 'Private';
  } else if (B.user && B.user.is_admin) {
    /* the admin's one reminder that this board is everybody's */
    sub.textContent = 'The public homepage — “arrange” changes what every visitor sees.';
  } else if (B.user) {
    sub.textContent = '';
  } else {
    sub.innerHTML = '<a href="#" id="signin-hint">Sign in</a> to customize.';
    sub.querySelector('#signin-hint').onclick = (ev) => {
      ev.preventDefault();
      document.getElementById('btn-login').click();
    };
  }

  B.grid.removeAll();
  B.meta.clear();
  for (const w of layout.widgets) {
    const el = widgetEl(w);
    document.getElementById('grid').appendChild(el);
    B.grid.makeWidget(el);
  }
  renderAll();
}

async function loadPicker() {
  const picker = document.getElementById('board-picker');
  if (!B.user) { picker.hidden = true; return; }
  const { boards } = await apiJSON('/boards');
  picker.innerHTML =
    `<option value="__home__" ${B.slug === 'default' ? 'selected' : ''}>· homepage board ·</option>` +
    boards.map(b => `<option value="${b.slug}" ${b.slug === B.slug ? 'selected' : ''}>
        ${b.title}${b.slug === B.user.default_board ? ' ★' : ''}${b.is_public ? ' ⚭' : ''}</option>`).join('');
  picker.hidden = false;
  picker.onchange = () => {
    /* __home__ forces the site board even when you have a personal default */
    location.href = picker.value === '__home__' ? 'board.html?b=default' : `board.html?b=${picker.value}`;
  };
}

function collectLayout() {
  const widgets = [];
  for (const node of B.grid.engine.nodes) {
    const id = node.el.dataset.wid;
    const meta = B.meta.get(id);
    if (!meta) continue;
    widgets.push({ id, type: meta.type, x: node.x, y: node.y, w: node.w, h: node.h,
                   config: meta.config });
  }
  const title = document.getElementById('board-title').value || B.board.title || 'Board';
  return { title, widgets };
}

async function saveBoard() {
  const layout = collectLayout();
  await apiJSON(`/boards/${B.slug}`, {
    method: 'PUT',
    body: JSON.stringify({
      layout, title: layout.title,
      is_public: B.slug === 'default' ? null : document.getElementById('is-public').checked,
    }),
  });
  document.getElementById('board-heading').textContent = layout.title;
  const btn = document.getElementById('btn-save');
  btn.textContent = 'saved ✓';
  setTimeout(() => { btn.textContent = 'save'; }, 1800);
}

/* ---------- edit mode ---------- */

function setEditing(on) {
  B.editing = on;
  B.grid.setStatic(!on);
  document.getElementById('edit-bar').hidden = !on;
  document.getElementById('grid').classList.toggle('editing', on);
  document.getElementById('btn-edit').textContent = on ? 'arranging…' : 'arrange';
}

async function openConfig(el) {
  const meta = B.meta.get(el.dataset.wid);
  const reg = Widgets.REGISTRY[meta.type];
  const fields = document.getElementById('cfg-fields');
  const stations = await Widgets.stations();
  const opt = (cur) => stations.map(s =>
    `<option value="${s.slug}" ${s.slug === cur ? 'selected' : ''}>${s.name}</option>`).join('');
  const METRICS = ['temp_c','rh','pressure_pa','wind_avg_ms','wind_gust_ms','rain_mm','pm25','pm10','batt_v','rssi_dbm'];

  let html = '';
  for (const f of reg.fields) {
    if (f === 'station') html += `<label>station <select name="station">${opt(meta.config.station || stations[0]?.slug)}</select></label>`;
    if (f === 'stationOrAll') html += `<label>station <select name="station"><option value="">all stations</option>${opt(meta.config.station)}</select></label>`;
    if (f === 'hours') html += `<label>window <select name="hours">
        ${[24, 48, 168, 720].map(h => `<option value="${h}" ${Number(meta.config.hours || 24) === h ? 'selected' : ''}>${h < 48 ? h + ' h' : (h/24) + ' d'}</option>`).join('')}
      </select></label>`;
    if (f === 'metrics') {
      const cur = (meta.config.metrics || 'temp_c').split(',');
      html += `<label>metrics</label><div class="checks">${METRICS.map(m =>
        `<label><input type="checkbox" name="m_${m}" ${cur.includes(m) ? 'checked' : ''}/>${m.replace(/_/g,' ')}</label>`).join('')}</div>`;
    }
    if (f === 'title') html += `<label>title <input name="title" maxlength="60" value="${meta.config.title || ''}"/></label>`;
  }
  fields.innerHTML = html || '<p class="wg-empty">nothing to configure — it simply is.</p>';

  const dlg = document.getElementById('cfg-dlg');
  dlg.returnValue = '';
  dlg.showModal();
  dlg.addEventListener('close', function onClose() {
    dlg.removeEventListener('close', onClose);
    if (dlg.returnValue !== 'ok') return;
    const form = document.getElementById('cfg-form');
    const cfg = { ...meta.config };
    for (const f of reg.fields) {
      if (f === 'station' || f === 'stationOrAll') cfg.station = form.station.value;
      if (f === 'hours') cfg.hours = Number(form.hours.value);
      if (f === 'title') cfg.title = form.title.value;
      if (f === 'metrics') cfg.metrics = METRICS.filter(m => form[`m_${m}`].checked).join(',') || 'temp_c';
    }
    meta.config = cfg;
    el.querySelector('.wg-head h3').textContent = cfg.title || reg.label;
    renderWidget(el);
  });
}

/* ---------- login ---------- */

function applyAuthUI() {
  ForsythAuth.set(B.user);
  ForsythAuth.applyChrome();          // sign-in label + admin link
  document.getElementById('btn-new-board').hidden = !B.user;   // board-only
  applyHomeBtn();
}

/* the ☆/★ "home" toggle: which board you land on with no ?b. Hidden on the
   site 'default' board (landing there = having no preference set). */
function applyHomeBtn() {
  const btn = document.getElementById('btn-home');
  const show = !!B.user && B.slug !== 'default';
  btn.hidden = !show;
  if (!show) return;
  const isHome = B.user.default_board === B.slug;
  btn.textContent = isHome ? '★ home' : '☆ home';
  btn.title = isHome ? 'you land here when you sign in — click to unset'
                     : 'land here when you sign in';
  btn.classList.toggle('on', isHome);
}

function wireChrome() {
  /* sign-in/sign-up dialog + the navbar button: shared (js/auth.js).
     Signing in here also has to reload the board and its picker. */
  ForsythAuth.mount({
    onSignIn: async (u) => {
      B.user = u;
      applyAuthUI();
      await Promise.all([loadBoard(), loadPicker()]);
    },
    onSignOut: () => { location.href = 'board.html'; },
  });

  const nbDlg = document.getElementById('newboard-dlg');
  document.getElementById('btn-new-board').onclick = () => {
    document.getElementById('newboard-form').reset();
    document.getElementById('newboard-err').textContent = '';
    nbDlg.showModal();
  };
  document.getElementById('newboard-form').addEventListener('submit', async (ev) => {
    if (ev.submitter && ev.submitter.value === 'cancel') return;   // let it close
    ev.preventDefault();
    const title = nbDlg.querySelector('[name=title]').value.trim();
    if (!title) return;
    try {
      const r = await apiJSON('/boards', { method: 'POST', body: JSON.stringify({ title }) });
      if (document.getElementById('newboard-home').checked) {
        await apiJSON(`/boards/${r.slug}/default`, { method: 'POST' });
      }
      location.href = `board.html?b=${r.slug}`;
    } catch (e) {
      document.getElementById('newboard-err').textContent = e.message;
    }
  });

  document.getElementById('btn-home').onclick = async (ev) => {
    const r = await apiJSON(`/boards/${B.slug}/default`, { method: 'POST' });
    B.user.default_board = r.default_board;
    applyHomeBtn();
    ev.target.blur();
  };

  document.getElementById('btn-share').onclick = async (ev) => {
    const url = B.slug === 'default'
      ? location.origin + '/board.html'
      : location.origin + '/board.html?b=' + B.slug;
    await navigator.clipboard.writeText(url);
    ev.target.textContent = 'copied ✓';
    setTimeout(() => { ev.target.textContent = 'copy link'; }, 1500);
  };

  document.getElementById('btn-publish-home').onclick = async () => {
    if (!confirm('Copy this board onto the site homepage board?')) return;
    await saveBoard();
    await apiJSON(`/boards/${B.slug}/publish-home`, { method: 'POST' });
    alert('The homepage now shows this arrangement.');
  };

  document.getElementById('btn-delete-board').onclick = async () => {
    if (!confirm(`Delete "${B.board.title}"? There is no undo.`)) return;
    await apiJSON(`/boards/${B.slug}`, { method: 'DELETE' });
    location.href = 'board.html';
  };

  document.getElementById('btn-edit').onclick = () => setEditing(!B.editing);
  document.getElementById('btn-cancel').onclick = () => setEditing(false);
  document.getElementById('btn-save').onclick = () => saveBoard().catch(e => alert(e.message));
  document.getElementById('add-widget').onchange = (ev) => {
    const type = ev.target.value;
    ev.target.value = '';
    if (!type) return;
    const reg = Widgets.REGISTRY[type];
    const el = widgetEl({ type, x: 0, y: 0, w: reg.w, h: reg.h, config: {} });
    document.getElementById('grid').appendChild(el);
    B.grid.makeWidget(el);
    renderWidget(el);
  };
}

/* ---------- boot ---------- */

async function boot() {
  B.grid = GridStack.init({
    column: 12, cellHeight: 80, margin: 8, staticGrid: true, float: false,
    /* Phones get a single column instead of twelve slivers. layout:'list' keeps
       the widgets in the order they are declared — the default repacks by
       position, which buried the local-conditions panel under the right-hand
       column. So the layout array's order IS the phone reading order. */
    columnOpts: { breakpointForWindow: true, layout: 'list', breakpoints: [{ w: 640, c: 1 }] },
  }, '#grid');

  wireChrome();
  B.user = await whoami();
  /* no ?b in the URL: land on the user's chosen home board if they set one,
     otherwise the public 'default'. The homepage ("/") comes through here. */
  const qb = new URLSearchParams(location.search).get('b');
  B.slug = qb || (B.user && B.user.default_board) || 'default';
  applyAuthUI();
  /* the homepage's location-bound widgets (@here) follow the reader's active
     location — resolve it before the first render so they land on the right
     station instead of flashing the placeholder */
  const isHome = B.slug === 'default';
  if (isHome && window.ForsythLoc) await ForsythLoc.init();
  await Promise.all([loadBoard(), loadPicker()]);
  refreshBanner();
  /* changing the active location re-renders the board; the local-conditions
     panel (whose title carries the selector) picks up the new station */
  if (isHome && window.ForsythLoc) ForsythLoc.onChange(renderAll);

  window.addEventListener('themechange', renderAll);
  /* crossing the one-column breakpoint restacks the sub-cards, so a
     grow-to-fit widget needs its height measured again */
  let fitT;
  window.addEventListener('resize', () => {
    clearTimeout(fitT);
    fitT = setTimeout(() => document.querySelectorAll('.grid-stack-item').forEach(el => {
      const m = B.meta.get(el.dataset.wid);
      if (m && Widgets.REGISTRY[m.type].sizeToContent) fitToContent(el);
    }), 200);
  });
  setInterval(() => {
    Widgets.invalidate();
    if (!B.editing) { renderAll(); refreshBanner(); }
  }, 60_000);

  Report.mount();
  /* first sign-in (or ?tour=1) gets the walkthrough, once per browser */
  if (B.user || new URLSearchParams(location.search).get('tour') === '1') {
    setTimeout(() => Tour.maybeStart(), 800);   /* let widgets paint first */
  }
}

boot();
