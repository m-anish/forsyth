/* forsyth board — layout engine: GridStack + widget registry + auth + multi-boards.
   URL: board.html            → the site homepage board ('default')
        board.html?b=<slug>   → a specific board (owner always; others if public) */
'use strict';

const B = { user: null, grid: null, editing: false, meta: new Map(),
            slug: new URLSearchParams(location.search).get('b') || 'default',
            board: null };
let widSeq = 0;

/* ---------- api ---------- */

async function apiJSON(path, opts = {}) {
  const r = await fetch(API + path, {
    credentials: 'same-origin',
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    ...opts,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
}

async function whoami() {
  try { return await apiJSON('/auth/me'); } catch { return null; }
}

/* ---------- widget DOM (unchanged mechanics) ---------- */

function widgetEl(w) {
  const el = document.createElement('div');
  el.className = 'grid-stack-item';
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
  document.getElementById('board-heading').textContent = board.title || layout.title || 'Board';
  document.getElementById('board-title').value = board.title || '';
  document.getElementById('is-public').checked = !!board.is_public;
  document.getElementById('vis-wrap').style.display = B.slug === 'default' ? 'none' : '';
  document.getElementById('btn-delete-board').hidden = B.slug === 'default';
  document.getElementById('btn-publish-home').hidden = !(B.user && B.user.is_admin && B.slug !== 'default');
  document.getElementById('btn-edit').hidden = !board.can_edit;

  const sub = document.getElementById('board-sub');
  if (B.slug === 'default') {
    sub.textContent = B.user
      ? (B.user.is_admin ? 'The homepage board. What visitors see; you can edit it.'
                         : 'The homepage board. Make your own with “+ board”.')
      : 'The public arrangement. Sign in to make your own.';
  } else {
    sub.textContent = `${board.owner}'s board · ${board.is_public ? 'public — anyone with this link' : 'private'}`;
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
    `<option value="default" ${B.slug === 'default' ? 'selected' : ''}>· homepage board ·</option>` +
    boards.map(b => `<option value="${b.slug}" ${b.slug === B.slug ? 'selected' : ''}>
        ${b.title}${b.is_public ? ' ⚭' : ''}</option>`).join('');
  picker.hidden = false;
  picker.onchange = () => {
    location.href = picker.value === 'default' ? 'board.html' : `board.html?b=${picker.value}`;
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
  document.getElementById('btn-login').textContent = B.user ? `sign out (${B.user.username})` : 'sign in';
  document.getElementById('btn-new-board').hidden = !B.user;
  document.getElementById('admin-link').hidden = !(B.user && B.user.is_admin);
}

function wireChrome() {
  const loginBtn = document.getElementById('btn-login');
  const dlg = document.getElementById('login-dlg');
  const err = document.getElementById('login-err');

  /* sign-in dialog doubles as sign-up; OAuth buttons appear when the server
     has providers configured (GET /auth/methods) */
  let signupMode = false;
  function setMode(signup) {
    signupMode = signup;
    document.getElementById('login-title').textContent = signup ? 'Create an account' : 'Sign in';
    document.getElementById('login-submit').textContent = signup ? 'create account' : 'sign in';
    document.getElementById('signup-toggle').textContent =
      signup ? 'have an account? sign in' : 'new here? create an account';
  }
  async function prepDialog() {
    try {
      const m = await getJSON('/auth/methods');
      document.getElementById('signup-toggle').hidden = !m.signup;
      const gIcon = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M23.5 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.46a5.53 5.53 0 0 1-2.4 3.63v3h3.88c2.27-2.1 3.56-5.18 3.56-8.82z"/><path fill="#34A853" d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.88-3c-1.08.72-2.45 1.15-4.06 1.15-3.13 0-5.78-2.11-6.72-4.95H1.27v3.1A12 12 0 0 0 12 24z"/><path fill="#FBBC05" d="M5.28 14.29A7.2 7.2 0 0 1 4.9 12c0-.8.14-1.57.38-2.29v-3.1H1.27a12 12 0 0 0 0 10.78l4.01-3.1z"/><path fill="#EA4335" d="M12 4.77c1.76 0 3.34.6 4.59 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.27 6.61l4.01 3.1C6.22 6.88 8.87 4.77 12 4.77z"/></svg>`;
      const ghIcon = `<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.42 7.42 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>`;
      document.getElementById('oauth-row').innerHTML =
        (m.google ? `<a class="tool-btn oauth" href="${API}/auth/oauth/google">${gIcon} continue with Google</a>` : '') +
        (m.github ? `<a class="tool-btn oauth" href="${API}/auth/oauth/github">${ghIcon} continue with GitHub</a>` : '');
    } catch { /* dialog still works as plain sign-in */ }
  }
  document.getElementById('signup-toggle').onclick = (ev) => {
    ev.preventDefault();
    err.textContent = '';
    setMode(!signupMode);
  };

  /* an OAuth round-trip that failed lands back here with ?auth_error= —
     reopen the dialog with the message instead of a bare error page */
  const authErr = new URLSearchParams(location.search).get('auth_error');
  if (authErr) {
    history.replaceState(null, '', location.pathname);
    setMode(false);
    prepDialog();
    err.textContent = authErr;
    dlg.showModal();
  }

  loginBtn.onclick = async () => {
    if (B.user) {
      await apiJSON('/auth/logout', { method: 'POST' });
      location.href = 'board.html';
      return;
    }
    err.textContent = '';
    setMode(false);
    prepDialog();
    dlg.showModal();
  };

  document.getElementById('login-submit').onclick = async (ev) => {
    ev.preventDefault();
    const form = document.getElementById('login-form');
    try {
      await apiJSON(signupMode ? '/auth/signup' : '/auth/login', {
        method: 'POST', body: JSON.stringify({
          username: form.username.value.trim(), password: form.password.value }) });
      dlg.close('done');
      B.user = await whoami();
      applyAuthUI();
      await Promise.all([loadBoard(), loadPicker()]);
    } catch (e) {
      err.textContent = signupMode
        ? 'That didn’t work — usernames are lowercase, passwords ≥ 8 chars, and the name may be taken. (' + e.message + ')'
        : 'The station does not recognise you. (' + e.message + ')';
    }
  };

  document.getElementById('btn-new-board').onclick = async () => {
    const title = prompt('Name the new board:', 'My corner of the sky');
    if (!title) return;
    const r = await apiJSON('/boards', { method: 'POST', body: JSON.stringify({ title }) });
    location.href = `board.html?b=${r.slug}`;
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
    /* phones get a single column instead of twelve slivers */
    columnOpts: { breakpointForWindow: true, breakpoints: [{ w: 640, c: 1 }] },
  }, '#grid');

  wireChrome();
  B.user = await whoami();
  applyAuthUI();
  await Promise.all([loadBoard(), loadPicker()]);

  window.addEventListener('themechange', renderAll);
  setInterval(() => { Widgets.invalidate(); if (!B.editing) renderAll(); }, 60_000);
}

boot();
