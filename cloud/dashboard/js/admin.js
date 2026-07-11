/* forsyth admin console — users, stations, jobs. Requires an is_admin session. */
'use strict';

async function api(path, opts = {}) {
  const r = await fetch(API + path, {
    credentials: 'same-origin',
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    ...opts,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
}

let ME = null;

/* ---------- gate ---------- */

async function gate() {
  try { ME = await api('/auth/me'); } catch { ME = null; }
  const msg = document.getElementById('gate-msg');
  const btn = document.getElementById('btn-login');
  btn.textContent = ME ? `sign out (${ME.username})` : 'sign in';
  if (!ME) {
    msg.textContent = 'Sign in with an admin account to open the back office.';
    document.getElementById('console').hidden = true;
    return;
  }
  if (!ME.is_admin) {
    msg.textContent = `Signed in as ${ME.username} — but the back office needs an admin. It's not personal.`;
    document.getElementById('console').hidden = true;
    return;
  }
  msg.textContent = `Signed in as ${ME.username}. Handle with the usual care.`;
  document.getElementById('console').hidden = false;
  await Promise.all([loadUsers(), loadStations()]);
}

/* ---------- users ---------- */

async function loadUsers() {
  const { users } = await api('/users');
  const tb = document.querySelector('#users-table tbody');
  tb.innerHTML = users.map(u => `
    <tr>
      <td class="mono">${u.username}</td>
      <td>${u.is_admin ? '<span class="badge sim">admin</span>' : 'user'}</td>
      <td class="mono">${u.boards}</td>
      <td class="mono">${new Date(u.created_at).toLocaleDateString()}</td>
      <td>${u.username === ME.username ? '<span class="wg-empty">you</span>'
            : `<button class="tool-btn danger" data-del-user="${u.username}">delete</button>`}</td>
    </tr>`).join('');
  tb.querySelectorAll('[data-del-user]').forEach(b => b.onclick = async () => {
    const name = b.dataset.delUser;
    if (!confirm(`Delete user "${name}" and all their boards?`)) return;
    await api(`/users/${name}`, { method: 'DELETE' });
    loadUsers();
  });
}

document.getElementById('user-form').onsubmit = async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  try {
    await api('/users', { method: 'POST', body: JSON.stringify({
      username: f.username.value.trim(), password: f.password.value,
      is_admin: f.is_admin.checked }) });
    f.reset();
    loadUsers();
  } catch (e) { alert(e.message); }
};

/* ---------- stations ---------- */

async function loadStations() {
  const { stations } = await getJSON('/stations');
  const tb = document.querySelector('#stations-table tbody');
  tb.innerHTML = stations.map(s => `
    <tr>
      <td class="mono">${s.slug}</td>
      <td>${s.name}</td>
      <td>${s.is_simulated ? '<span class="badge sim">rehearsal</span>' : 'real'}</td>
      <td class="mono">${agoLabel(s.last_seen)}</td>
      <td><button class="tool-btn danger" data-del-station="${s.slug}">delete</button></td>
    </tr>`).join('');
  tb.querySelectorAll('[data-del-station]').forEach(b => b.onclick = async () => {
    const slug = b.dataset.delStation;
    if (!confirm(`Delete station "${slug}" and ALL its data (readings, frames, timelapses)? This is the big red switch.`)) return;
    await api(`/stations/${slug}`, { method: 'DELETE' });
    loadStations();
  });
}

document.getElementById('station-form').onsubmit = async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  try {
    const body = { slug: f.slug.value.trim(), name: f.name.value.trim() };
    for (const k of ['lat', 'lon', 'elevation_m']) if (f[k].value) body[k] = Number(f[k].value);
    const r = await api('/stations', { method: 'POST', body: JSON.stringify(body) });
    document.getElementById('key-reveal').hidden = false;
    document.getElementById('key-value').textContent = r.api_key;
    f.reset();
    loadStations();
  } catch (e) { alert(e.message); }
};

/* ---------- jobs ---------- */

document.querySelectorAll('[data-job]').forEach(b => b.onclick = async () => {
  const out = document.getElementById('job-out');
  out.textContent = `running ${b.dataset.job}…`;
  try {
    const r = await api(`/admin/run/${b.dataset.job}`, { method: 'POST' });
    out.textContent = JSON.stringify(r.result, null, 2);
  } catch (e) { out.textContent = 'failed: ' + e.message; }
});

/* ---------- login (shared pattern) ---------- */

document.getElementById('btn-login').onclick = async () => {
  if (ME) { await api('/auth/logout', { method: 'POST' }); location.reload(); return; }
  document.getElementById('login-err').textContent = '';
  document.getElementById('login-dlg').showModal();
};
document.getElementById('login-submit').onclick = async (ev) => {
  ev.preventDefault();
  const form = document.getElementById('login-form');
  try {
    await api('/auth/login', { method: 'POST', body: JSON.stringify({
      username: form.username.value.trim(), password: form.password.value }) });
    document.getElementById('login-dlg').close('done');
    gate();
  } catch (e) {
    document.getElementById('login-err').textContent = 'No. (' + e.message + ')';
  }
};

gate();
