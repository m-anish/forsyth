/* forsyth live — human weather reports: floating button + one-thumb dialog.
   Anonymous-first (engagement-roadmap §3). A report is COMPOSITE: pick every
   thing you see (fog AND rain AND a blocked road), each with its own intensity,
   and optionally raise a weather alert (yellow/orange/red) which the server
   weights by how many — and how trusted — the voices are. Location comes from
   the browser; a page can offer a fallback (the station's coords) via
   Report.mount({fallback}). If the server disables reports, no UI appears. */
'use strict';

const Report = (() => {

  const KINDS = [
    ['precip',      '🌧', 'rain'],
    ['hail',        '🧊', 'hail'],
    ['fog',         '🌫', 'fog'],
    ['snow_line',   '❄',  'snow'],
    ['wind_damage', '💨', 'wind damage'],
    ['road_blocked','🚧', 'road blocked'],
    ['flood',       '🌊', 'flood'],
  ];
  const HAS_INTENSITY = new Set(['precip', 'hail', 'fog']);
  const INTENSITY = [[1, 'light'], [2, 'moderate'], [3, 'heavy']];
  const ALERTS = [[0, 'no alert'], [1, 'yellow'], [2, 'orange'], [3, 'red']];
  const GLYPH = Object.fromEntries(KINDS.map(([k, g]) => [k, g]));

  let dlg = null, state = {}, fallbackFn = null;

  function build() {
    dlg = document.createElement('dialog');
    dlg.id = 'report-dlg';
    dlg.innerHTML = `
      <form method="dialog">
        <h3>What is the sky doing?</h3>
        <p class="rp-why">The stations measure; you see. Tap everything you're
          seeing — it's checked against the nearest station and sharpens the
          mesh's warnings for everyone in the valley.</p>
        <div class="kind-grid">${KINDS.map(([k, g, label]) =>
          `<button type="button" class="kind" data-kind="${k}"><span class="g">${g}</span>${label}</button>`).join('')}
        </div>
        <div id="rp-intensity"></div>
        <div class="rp-alert" id="rp-alert" hidden>
          <span class="rp-alert-q">Is this dangerous? Raise an alert</span>
          <div class="chips">${ALERTS.map(([v, label]) =>
            `<button type="button" class="chip alert-${v}" data-a="${v}">${label}</button>`).join('')}</div>
        </div>
        <input id="rp-note" maxlength="140" placeholder="a few words, if it helps (optional)" autocomplete="off" />
        <div class="rp-status">
          <p class="rp-loc" id="rp-loc">…</p>
          <p class="rp-me" id="rp-me"></p>
        </div>
        <details class="rp-more">
          <summary>how reports are used</summary>
          <ul>
            <li>Cross-checked against the nearest station — agreement earns a ✓
                and more weight in the warnings.</li>
            <li>Two matching reports nearby (or one from a ★ trusted observer)
                raise the banner for the whole mesh.</li>
            <li>An alert (yellow/orange/red) is weighted: one anonymous voice
                won't turn the valley red — agreement between people, and a
                trusted observer's word, is what escalates it.</li>
            <li>Shown on the map for six hours at ~100 m accuracy — the weather's
                location, never your front door. <a href="privacy.html">privacy</a></li>
          </ul>
        </details>
        <p class="dlg-err" id="rp-err"></p>
        <div class="dlg-row">
          <button value="cancel" class="tool-btn" formnovalidate>cancel</button>
          <button type="button" class="tool-btn save" id="rp-send" disabled>report it</button>
        </div>
      </form>`;
    document.body.appendChild(dlg);

    /* kinds toggle on/off (composite); selecting any reveals the alert row */
    dlg.querySelectorAll('.kind').forEach(b => b.onclick = () => {
      const k = b.dataset.kind;
      if (k in state.obs) delete state.obs[k];
      else state.obs[k] = null;                 // selected, intensity unset
      b.classList.toggle('on', k in state.obs);
      renderIntensity();
      document.getElementById('rp-alert').hidden = Object.keys(state.obs).length === 0;
      armSend();
    });

    dlg.querySelectorAll('.alert-0, .alert-1, .alert-2, .alert-3').forEach(b => b.onclick = () => {
      const v = Number(b.dataset.a);
      state.alert = state.alert === v ? 0 : v;
      dlg.querySelectorAll('[data-a]').forEach(x =>
        x.classList.toggle('on', Number(x.dataset.a) === state.alert && state.alert !== 0));
    });
    document.getElementById('rp-send').onclick = send;
  }

  /* one intensity row per selected kind that has degrees (rain/hail/fog) */
  function renderIntensity() {
    const wrap = document.getElementById('rp-intensity');
    const kinds = Object.keys(state.obs).filter(k => HAS_INTENSITY.has(k));
    wrap.innerHTML = kinds.map(k => `
      <div class="rp-int-row" data-kind="${k}">
        <span class="rp-int-label">${GLYPH[k]} ${labelFor(k)}</span>
        <span class="chips">${INTENSITY.map(([v, l]) =>
          `<button type="button" class="chip${state.obs[k] === v ? ' on' : ''}" data-i="${v}">${l}</button>`).join('')}</span>
      </div>`).join('');
    wrap.querySelectorAll('.rp-int-row').forEach(row => {
      const k = row.dataset.kind;
      row.querySelectorAll('.chip').forEach(b => b.onclick = () => {
        const v = Number(b.dataset.i);
        state.obs[k] = state.obs[k] === v ? null : v;
        row.querySelectorAll('.chip').forEach(x =>
          x.classList.toggle('on', Number(x.dataset.i) === state.obs[k]));
      });
    });
  }
  const labelFor = k => (KINDS.find(x => x[0] === k) || [,, k])[2];

  function armSend() {
    const ok = Object.keys(state.obs).length > 0 && state.pos;
    document.getElementById('rp-send').disabled = !ok;
  }

  /* When the browser can't (or won't) say where you are — Brave and other
     desktop browsers often can't, even on https — fall back to "near which
     station?": always works, and station-adjacent is exactly where QC has a
     sensor to check against anyway. */
  async function stationPicker(msg) {
    const el = document.getElementById('rp-loc');
    let sts = [];
    try { sts = (await getJSON('/stations')).stations.filter(s => s.lat != null); } catch {}
    if (!sts.length) {
      el.textContent = 'location unavailable, and no stations to pin to — cannot report';
      return;
    }
    el.innerHTML = `${msg}
      <select id="rp-station" aria-label="report near which station">
        <option value="">near which station?</option>
        ${sts.map(s => `<option value="${s.slug}">${s.name}</option>`).join('')}
      </select>`;
    el.querySelector('#rp-station').onchange = ev => {
      const s = sts.find(x => x.slug === ev.target.value);
      if (!s) return;
      state.pos = { lat: s.lat, lon: s.lon, name: s.name };
      armSend();
    };
  }

  function locate() {
    const el = document.getElementById('rp-loc');
    const failed = (err) => {
      const fb = fallbackFn && fallbackFn();
      if (fb && fb.lat != null) {
        state.pos = fb;
        el.textContent = `location: near ${fb.name || 'this station'}`;
        armSend();
        return;
      }
      stationPicker(err && err.code === 1
        ? 'location denied —' : 'no location fix from this browser —');
    };
    el.textContent = 'finding you… (your browser may ask)';
    if (!navigator.geolocation) { failed(); return; }
    navigator.geolocation.getCurrentPosition(
      p => {
        state.pos = { lat: p.coords.latitude, lon: p.coords.longitude };
        el.textContent = 'location: right where you are';
        armSend();
      },
      failed,
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 120000 },
    );
  }

  async function send() {
    const err = document.getElementById('rp-err');
    const btn = document.getElementById('rp-send');
    btn.disabled = true; err.textContent = '';
    const observations = Object.entries(state.obs)
      .map(([kind, intensity]) => ({ kind, intensity: intensity ?? null }));
    try {
      const r = await fetch(`${API}/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: state.pos.lat, lon: state.pos.lon, observations,
          alert_level: state.alert || 0,
          note: document.getElementById('rp-note').value.trim() || null,
        }),
      });
      if (r.status === 429) { err.textContent = 'one report at a time, please — try again in a few minutes'; return; }
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      const agreed = (d.observations || []).some(o => o.qc_flag === 'corroborated');
      dlg.querySelector('h3').textContent =
        agreed ? 'Noted — and the stations agree.' : 'Noted. Thank you for the eyes.';
      setTimeout(() => dlg.close(), 1300);
    } catch {
      err.textContent = 'that didn’t go through — try again';
      btn.disabled = false;
    }
  }

  /* attribution line: who's reporting, and what their eyes have earned */
  async function whoLine() {
    const el = document.getElementById('rp-me');
    try {
      const me = await getJSON('/auth/me');
      const r = me.reports || {};
      const bits = [`reporting as ${me.username}`];
      if (r.streak_days > 1) bits.push(`${r.streak_days}-day streak`);
      if (r.trusted) bits.push('trusted observer ★');
      el.textContent = bits.join(' · ');
    } catch {
      el.innerHTML = 'reporting anonymously — <a href="board.html">sign in</a> to build a streak';
    }
  }

  function open() {
    if (!dlg) build();
    state = { obs: {}, alert: 0, pos: null };
    dlg.querySelector('h3').textContent = 'What is the sky doing?';
    dlg.querySelectorAll('.kind, .chip').forEach(b => b.classList.remove('on'));
    document.getElementById('rp-intensity').innerHTML = '';
    document.getElementById('rp-alert').hidden = true;
    document.getElementById('rp-note').value = '';
    document.getElementById('rp-err').textContent = '';
    document.getElementById('rp-send').disabled = true;
    dlg.showModal();
    locate();
    whoLine();
  }

  /* mount the floating button — hidden entirely if the server disables reports */
  async function mount(opts = {}) {
    fallbackFn = opts.fallback || null;
    try {
      const d = await getJSON('/reports?hours=1');
      if (d.enabled === false) return;
    } catch { return; }
    const fab = document.createElement('button');
    fab.className = 'report-fab';
    fab.type = 'button';
    fab.title = 'report what the sky is doing';
    fab.innerHTML = '<span class="g">💬</span> report the sky';
    fab.onclick = open;
    document.body.appendChild(fab);
  }

  return { mount, open, GLYPH };
})();
