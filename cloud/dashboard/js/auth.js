/* forsyth — shared sign-in chrome.
   The navbar's sign-in button, the admin link, and the sign-in/sign-up dialog
   are the same on every page, so they live here instead of in board.js. A page
   opts in by putting #btn-login (and optionally #admin-link) in its navbar and
   calling ForsythAuth.mount(); the dialog markup is injected on demand. */
'use strict';

const ForsythAuth = (() => {

  let user = null;

  const DIALOG_HTML = `
<dialog id="login-dlg">
  <form method="dialog" id="login-form">
    <h3 id="login-title">Sign in</h3>
    <div class="oauth-row" id="oauth-row"></div>
    <label>username <input name="username" autocomplete="username" required /></label>
    <label>password <input name="password" type="password" autocomplete="current-password" required /></label>
    <p class="dlg-err" id="login-err"></p>
    <p class="dlg-alt"><a href="#" id="signup-toggle" hidden>new here? create an account</a></p>
    <div class="dlg-row">
      <button value="cancel" class="tool-btn" formnovalidate>cancel</button>
      <button value="ok" class="tool-btn save" id="login-submit">sign in</button>
    </div>
  </form>
</dialog>`;

  const G_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M23.5 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.46a5.53 5.53 0 0 1-2.4 3.63v3h3.88c2.27-2.1 3.56-5.18 3.56-8.82z"/><path fill="#34A853" d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.88-3c-1.08.72-2.45 1.15-4.06 1.15-3.13 0-5.78-2.11-6.72-4.95H1.27v3.1A12 12 0 0 0 12 24z"/><path fill="#FBBC05" d="M5.28 14.29A7.2 7.2 0 0 1 4.9 12c0-.8.14-1.57.38-2.29v-3.1H1.27a12 12 0 0 0 0 10.78l4.01-3.1z"/><path fill="#EA4335" d="M12 4.77c1.76 0 3.34.6 4.59 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.27 6.61l4.01 3.1C6.22 6.88 8.87 4.77 12 4.77z"/></svg>`;
  const GH_ICON = `<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.42 7.42 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>`;

  async function whoami() {
    try { return await apiJSON('/auth/me'); } catch { return null; }
  }
  async function refresh() { user = await whoami(); return user; }
  function current() { return user; }
  function set(u) { user = u; }

  /* navbar bits every page shares */
  function applyChrome() {
    const b = document.getElementById('btn-login');
    if (b) b.textContent = user ? `sign out (${user.username})` : 'sign in';
    const a = document.getElementById('admin-link');
    if (a) a.hidden = !(user && user.is_admin);
  }

  function ensureDialog() {
    if (!document.getElementById('login-dlg'))
      document.body.insertAdjacentHTML('beforeend', DIALOG_HTML);
    return document.getElementById('login-dlg');
  }

  /* Wires #btn-login and the dialog.
     opts.onSignIn  — after a successful sign-in (page reloads its own data)
     opts.onSignOut — after sign-out; default is a plain reload */
  function mount(opts = {}) {
    const loginBtn = document.getElementById('btn-login');
    if (!loginBtn) return;
    const dlg = ensureDialog();
    const err = document.getElementById('login-err');

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
        document.getElementById('oauth-row').innerHTML =
          (m.google ? `<a class="tool-btn oauth" href="${API}/auth/oauth/google">${G_ICON} continue with Google</a>` : '') +
          (m.github ? `<a class="tool-btn oauth" href="${API}/auth/oauth/github">${GH_ICON} continue with GitHub</a>` : '');
      } catch { /* dialog still works as plain sign-in */ }
    }
    document.getElementById('signup-toggle').onclick = (ev) => {
      ev.preventDefault(); err.textContent = ''; setMode(!signupMode);
    };

    /* an OAuth round-trip that failed lands back here with ?auth_error= —
       reopen the dialog with the message instead of a bare error page */
    const authErr = new URLSearchParams(location.search).get('auth_error');
    if (authErr) {
      history.replaceState(null, '', location.pathname + location.hash);
      setMode(false); prepDialog();
      err.textContent = authErr;
      dlg.showModal();
    }

    loginBtn.onclick = async () => {
      if (user) {
        await apiJSON('/auth/logout', { method: 'POST' });
        if (opts.onSignOut) opts.onSignOut(); else location.reload();
        return;
      }
      err.textContent = ''; setMode(false); prepDialog();
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
        await refresh();
        applyChrome();
        if (opts.onSignIn) await opts.onSignIn(user);
      } catch (e) {
        err.textContent = signupMode
          ? 'That didn’t work — usernames are lowercase, passwords ≥ 8 chars, and the name may be taken. (' + e.message + ')'
          : 'The station does not recognise you. (' + e.message + ')';
      }
    };

    /* a page that only wants the button (no dialog markup of its own) still
       needs the opener reachable by keyboard shortcut hosts */
    loginBtn.hidden = false;
  }

  /* one-call setup for pages with no auth-specific behaviour of their own */
  async function boot(opts = {}) {
    await refresh();
    applyChrome();
    mount(opts);
  }

  return { whoami, refresh, current, set, applyChrome, mount, boot, ensureDialog };
})();

window.ForsythAuth = ForsythAuth;
