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

function locLabel(s) {
  if (s.lat == null || s.lon == null) return '<span class="wg-empty">not located</span>';
  const el = s.elevation_m != null ? ` · ${Math.round(s.elevation_m)}m` : '';
  return `<span class="mono">${s.lat.toFixed(4)}, ${s.lon.toFixed(4)}${el}</span>`;
}

async function loadStations() {
  const { stations } = await getJSON('/stations');
  const tb = document.querySelector('#stations-table tbody');
  tb.innerHTML = stations.map(s => `
    <tr>
      <td class="mono">${s.slug}</td>
      <td>${s.name}</td>
      <td>${locLabel(s)}</td>
      <td>${s.is_simulated ? '<span class="badge sim">rehearsal</span>' : 'real'}</td>
      <td class="mono">${agoLabel(s.last_seen)}</td>
      <td>
        <button class="tool-btn" data-loc-station="${s.slug}">locate</button>
        <button class="tool-btn danger" data-del-station="${s.slug}">delete</button>
      </td>
    </tr>`).join('');
  tb.querySelectorAll('[data-loc-station]').forEach(b => b.onclick = () =>
    openLocEditor(stations.find(s => s.slug === b.dataset.locStation)));
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
    const r = await api('/stations', { method: 'POST', body: JSON.stringify({
      slug: f.slug.value.trim(), name: f.name.value.trim() }) });
    document.getElementById('key-reveal').hidden = false;
    document.getElementById('key-value').textContent = r.api_key;
    f.reset();
    await loadStations();
  } catch (e) { alert(e.message); }
};

/* ---------- station location editor (map picker + geolocation) ---------- */

let LOC = { map: null, marker: null, slug: null };

function locFields() {
  const f = document.getElementById('loc-form');
  return { lat: f.lat, lon: f.lon, elev: f.elevation_m };
}

function setLocPin(lat, lon, moveMap) {
  const { lat: fl, lon: fo } = locFields();
  fl.value = lat.toFixed(6); fo.value = lon.toFixed(6);
  if (LOC.marker) LOC.marker.setLatLng([lat, lon]);
  if (moveMap) LOC.map.setView([lat, lon], Math.max(LOC.map.getZoom(), 12));
  fetchElevation(lat, lon);
}

/* client-side elevation prefill for instant feedback; the server backfill is
   the backstop, so a failure here is silent */
let elevTimer = null;
function fetchElevation(lat, lon) {
  clearTimeout(elevTimer);
  elevTimer = setTimeout(async () => {
    try {
      const r = await fetch(`https://api.open-meteo.com/v1/elevation?latitude=${lat}&longitude=${lon}`);
      const d = await r.json();
      if (d.elevation && d.elevation[0] != null)
        locFields().elev.value = Math.round(d.elevation[0]);
    } catch { /* server backfill will handle it */ }
  }, 400);
}

function openLocEditor(s) {
  LOC.slug = s.slug;
  document.getElementById('loc-slug').textContent = s.slug;
  document.getElementById('loc-err').textContent = '';
  const { lat: fl, lon: fo, elev } = locFields();
  const hasLoc = s.lat != null && s.lon != null;
  fl.value = hasLoc ? s.lat : ''; fo.value = hasLoc ? s.lon : '';
  elev.value = s.elevation_m != null ? Math.round(s.elevation_m) : '';
  document.getElementById('loc-dlg').showModal();

  const start = hasLoc ? [s.lat, s.lon] : [29.44, 79.61];   // Himalaya-ish default
  setTimeout(() => {
    if (!LOC.map) {
      LOC.map = L.map('loc-map');
      const dark = document.documentElement.dataset.theme === 'light' ? 'light_all' : 'dark_all';
      L.tileLayer(`https://{s}.basemaps.cartocdn.com/${dark}/{z}/{x}/{y}{r}.png`,
        { subdomains: 'abcd', maxZoom: 19,
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/attributions">CARTO</a>' }).addTo(LOC.map);
      LOC.marker = L.marker(start, { draggable: true }).addTo(LOC.map);
      LOC.marker.on('dragend', () => {
        const p = LOC.marker.getLatLng(); setLocPin(p.lat, p.lng, false);
      });
      LOC.map.on('click', e => setLocPin(e.latlng.lat, e.latlng.lng, false));
    } else {
      LOC.marker.setLatLng(start);
    }
    LOC.map.setView(start, hasLoc ? 13 : 6);
    LOC.map.invalidateSize();
    // keep manual typing in sync with the pin
    fl.oninput = fo.oninput = () => {
      const la = parseFloat(fl.value), lo = parseFloat(fo.value);
      if (isFinite(la) && isFinite(lo)) { LOC.marker.setLatLng([la, lo]); LOC.map.panTo([la, lo]); }
    };
  }, 60);
}

document.getElementById('loc-here').onclick = () => {
  const err = document.getElementById('loc-err');
  if (!navigator.geolocation) { err.textContent = 'This browser has no geolocation.'; return; }
  err.textContent = 'locating…';
  navigator.geolocation.getCurrentPosition(
    p => { err.textContent = ''; setLocPin(p.coords.latitude, p.coords.longitude, true); },
    e => { err.textContent = 'location denied/failed (' + e.message + ')'; },
    { enableHighAccuracy: true, timeout: 10000 });
};

document.getElementById('loc-save').onclick = async (ev) => {
  ev.preventDefault();
  const { lat: fl, lon: fo, elev } = locFields();
  const body = {};
  if (fl.value) body.lat = Number(fl.value);
  if (fo.value) body.lon = Number(fo.value);
  if (elev.value) body.elevation_m = Number(elev.value);
  try {
    await api(`/stations/${LOC.slug}`, { method: 'PATCH', body: JSON.stringify(body) });
    document.getElementById('loc-dlg').close('done');
    await loadStations();
  } catch (e) { document.getElementById('loc-err').textContent = e.message; }
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
