/* forsyth board — layout engine: GridStack + widget registry + auth. */
'use strict';

const B = { user: null, grid: null, editing: false, meta: new Map(), title: '' };
let widSeq = 0;

/* ---------- api ---------- */

async function postJSON(path, body) {
  const r = await fetch(API + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), credentials: 'same-origin',
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.status);
  return r.json();
}

async function whoami() {
  try { return (await (await fetch(API + '/auth/me', { credentials: 'same-origin' })).json()).username || null; }
  catch { return null; }
}

/* ---------- widget DOM ---------- */

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

async function renderWidget(el) {
  const meta = B.meta.get(el.dataset.wid);
  if (!meta) return;
  const body = el.querySelector('.wg-body');
  try { await Widgets.REGISTRY[meta.type].render(body, meta.config); }
  catch (e) { body.innerHTML = `<p class="wg-empty">widget unhappy: ${e.message}</p>`; }
}

function renderAll() {
  document.querySelectorAll('.grid-stack-item').forEach(renderWidget);
}

/* ---------- board load/save ---------- */

async function loadBoard() {
  const path = B.user ? '/boards/mine' : '/boards/default';
  const { layout } = await (await fetch(API + path, { credentials: 'same-origin' })).json();
  B.title = layout.title || 'The mesh, at a glance';
  document.getElementById('board-heading').textContent = B.title;
  document.getElementById('board-title').value = B.title;
  document.getElementById('board-sub').textContent = B.user
    ? `Signed in as ${B.user}. This board is yours to rearrange.`
    : 'The public arrangement. Sign in to make your own.';

  B.grid.removeAll();
  B.meta.clear();
  for (const w of layout.widgets) {
    const el = widgetEl(w);
    document.getElementById('grid').appendChild(el);
    B.grid.makeWidget(el);
  }
  renderAll();
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
  return { title: document.getElementById('board-title').value || B.title, widgets };
}

async function saveBoard() {
  const setDefault = document.getElementById('set-default').checked;
  await fetch(API + '/boards/mine?set_default=' + setDefault, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin', body: JSON.stringify({ layout: collectLayout() }),
  }).then(r => { if (!r.ok) throw new Error('save failed: ' + r.status); });
  document.getElementById('board-heading').textContent =
    document.getElementById('board-title').value || B.title;
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
  const opt = (slug, cur) => stations.map(s =>
    `<option value="${s.slug}" ${s.slug === cur ? 'selected' : ''}>${s.name}</option>`).join('');
  const METRICS = ['temp_c','rh','pressure_pa','wind_avg_ms','wind_gust_ms','rain_mm','pm25','pm10','batt_v','rssi_dbm'];

  let html = '';
  for (const f of reg.fields) {
    if (f === 'station') html += `<label>station <select name="station">${opt('station', meta.config.station || stations[0]?.slug)}</select></label>`;
    if (f === 'stationOrAll') html += `<label>station <select name="station"><option value="">all stations</option>${opt('station', meta.config.station)}</select></label>`;
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

function wireLogin() {
  const btn = document.getElementById('btn-login');
  const dlg = document.getElementById('login-dlg');
  const err = document.getElementById('login-err');

  btn.onclick = async () => {
    if (B.user) {                       // acting as logout
      await postJSON('/auth/logout', {});
      B.user = null;
      applyAuthUI();
      setEditing(false);
      loadBoard();
      return;
    }
    err.textContent = '';
    dlg.showModal();
  };

  document.getElementById('login-submit').onclick = async (ev) => {
    ev.preventDefault();
    const form = document.getElementById('login-form');
    try {
      const r = await postJSON('/auth/login', {
        username: form.username.value.trim(), password: form.password.value,
      });
      B.user = r.username;
      dlg.close('done');
      applyAuthUI();
      loadBoard();
    } catch (e) {
      err.textContent = 'The station does not recognise you. (' + e.message + ')';
    }
  };
}

function applyAuthUI() {
  document.getElementById('btn-login').textContent = B.user ? `sign out (${B.user})` : 'sign in';
  document.getElementById('btn-edit').hidden = !B.user;
}

/* ---------- boot ---------- */

async function boot() {
  B.grid = GridStack.init({
    column: 12, cellHeight: 80, margin: 8, staticGrid: true, float: false,
  }, '#grid');

  wireLogin();
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

  B.user = await whoami();
  applyAuthUI();
  await loadBoard();

  window.addEventListener('themechange', renderAll);
  setInterval(() => { Widgets.invalidate(); if (!B.editing) renderAll(); }, 60_000);
}

boot();
