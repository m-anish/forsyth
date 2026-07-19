/* forsyth live — human weather reports: floating button + one-thumb dialog.
   Anonymous-first (engagement-roadmap §3): kind → optional intensity →
   optional note → send. Location comes from the browser; a page can offer a
   fallback (the station's coords) via Report.mount({fallback}). If the server
   says reports are disabled, no UI appears at all. */
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
  const INTENSITY = [[1, 'light'], [2, 'moderate'], [3, 'heavy']];
  const GLYPH = Object.fromEntries(KINDS.map(([k, g]) => [k, g]));

  let dlg = null, state = {}, fallbackFn = null;

  function build() {
    dlg = document.createElement('dialog');
    dlg.id = 'report-dlg';
    dlg.innerHTML = `
      <form method="dialog">
        <h3>What is the sky doing?</h3>
        <p class="rp-why">The stations measure; you see. A ten-second report is
          checked against the nearest station and sharpens the mesh's warnings
          for everyone in the valley.</p>
        <div class="kind-grid">${KINDS.map(([k, g, label]) =>
          `<button type="button" class="kind" data-kind="${k}"><span class="g">${g}</span>${label}</button>`).join('')}
        </div>
        <div class="chips" id="rp-intensity" hidden>${INTENSITY.map(([v, label]) =>
          `<button type="button" class="chip" data-i="${v}">${label}</button>`).join('')}
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

    dlg.querySelectorAll('.kind').forEach(b => b.onclick = () => {
      state.kind = b.dataset.kind;
      dlg.querySelectorAll('.kind').forEach(x => x.classList.toggle('on', x === b));
      /* intensity makes sense for weather you can have more of */
      const wantsIntensity = ['precip', 'hail', 'fog'].includes(state.kind);
      document.getElementById('rp-intensity').hidden = !wantsIntensity;
      if (!wantsIntensity) state.intensity = null;
      document.getElementById('rp-send').disabled = !state.pos;
    });
    dlg.querySelectorAll('.chip').forEach(b => b.onclick = () => {
      const v = Number(b.dataset.i);
      state.intensity = state.intensity === v ? null : v;
      dlg.querySelectorAll('.chip').forEach(x =>
        x.classList.toggle('on', Number(x.dataset.i) === state.intensity));
    });
    document.getElementById('rp-send').onclick = send;
  }

  function locate() {
    const el = document.getElementById('rp-loc');
    const useFallback = () => {
      const fb = fallbackFn && fallbackFn();
      if (fb && fb.lat != null) {
        state.pos = fb;
        el.textContent = `location: near ${fb.name || 'this station'}`;
        if (state.kind) document.getElementById('rp-send').disabled = false;
      } else {
        el.textContent = 'location unavailable — allow location access to report';
      }
    };
    el.textContent = 'finding you…';
    if (!navigator.geolocation) { useFallback(); return; }
    navigator.geolocation.getCurrentPosition(
      p => {
        state.pos = { lat: p.coords.latitude, lon: p.coords.longitude };
        el.textContent = 'location: right where you are';
        if (state.kind) document.getElementById('rp-send').disabled = false;
      },
      useFallback,
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 120000 },
    );
  }

  async function send() {
    const err = document.getElementById('rp-err');
    const btn = document.getElementById('rp-send');
    btn.disabled = true; err.textContent = '';
    try {
      const r = await fetch(`${API}/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: state.kind, lat: state.pos.lat, lon: state.pos.lon,
          intensity: state.intensity ?? null,
          note: document.getElementById('rp-note').value.trim() || null,
        }),
      });
      if (r.status === 429) { err.textContent = 'one report at a time, please — try again in a few minutes'; return; }
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      err.textContent = '';
      dlg.querySelector('h3').textContent =
        d.qc_flag === 'corroborated' ? 'Noted — and the stations agree.' : 'Noted. Thank you for the eyes.';
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
    state = { kind: null, intensity: null, pos: null };
    dlg.querySelector('h3').textContent = 'What is the sky doing?';
    dlg.querySelectorAll('.kind, .chip').forEach(b => b.classList.remove('on'));
    document.getElementById('rp-intensity').hidden = true;
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
    fab.innerHTML = '<span class="g">👁</span> report the sky';
    fab.onclick = open;
    document.body.appendChild(fab);
  }

  return { mount, open, GLYPH };
})();
