/* The hero's wind kit, moving.
 *
 * The hero photo is shown with its vane and cups painted out (tools/hero_anim.py
 * makes the plate and sprites and writes hero-anim.json). Here they are drawn back
 * on a canvas laid exactly over the cover-fitted background: the vane is the
 * photo's own pixels, yawing a few degrees about its pivot; the cups are small
 * projected cones turning round the rotor axis, passing behind the hub. A slow
 * gust curve drives both, so they speed up and settle together.
 *
 * If anything fails to load the page keeps the static photo, which still has
 * the vane and cups in it. Reduced motion gets one still frame.
 */
(function () {
  'use strict';
  const hero = document.querySelector('.hero');
  const canvas = hero && hero.querySelector('.hero-wind');
  if (!hero || !canvas || !canvas.getContext) return;

  const ctx = canvas.getContext('2d');
  // Pin the canvas's layout here too: if a cached stylesheet lacks these, a static
  // canvas would size the hero, and resize() would grow it without end.
  Object.assign(canvas.style, {
    position: 'absolute', left: '0', top: '0', width: '100%', height: '100%',
    zIndex: '0', pointerEvents: 'none'
  });
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const narrow = window.matchMedia('(max-width: 700px)');   // same breakpoint as styles.css
  const PSI0 = 25 * Math.PI / 180;   // how far the vane already stands out of the picture plane
  const TAU = Math.PI * 2;

  let config = null, cfg = null, sprites = {}, fit = null;
  let running = false, visible = true, last = 0, t = 0, spin = 0.4, raf = 0;

  function load(src) {
    return new Promise(function (ok, fail) {
      const img = new Image();
      img.onload = function () { ok(img); };
      img.onerror = fail;
      img.src = src;
    });
  }

  function variant() { return narrow.matches ? config.mobile : config.desktop; }

  function use(v) {
    return Promise.all([load(v.plate), load(v.vane.src), load(v.hub.src)]).then(function (imgs) {
      sprites = { vane: imgs[1], hub: imgs[2] };
      cfg = v;
      hero.classList.add('wind-on');
      resize();
    });
  }

  // background-size: cover; background-position: center
  function resize() {
    if (!cfg) return;
    const W = hero.clientWidth, H = hero.clientHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    const s = Math.max(W / cfg.w, H / cfg.h);
    fit = { s: s, ox: (W - cfg.w * s) / 2, oy: (H - cfg.h * s) / 2, dpr: dpr };
    draw();
  }

  // ---- the wind: one slow gust curve drives cups and vane ----
  function gust(t) {
    return 1 + 0.35 * Math.sin(0.23 * t) + 0.2 * Math.sin(0.71 * t + 1.3) + 0.08 * Math.sin(1.9 * t);
  }
  function yaw(t) {
    const d = Math.PI / 180;
    return 7 * d * Math.sin(0.9 * t) * (0.6 + 0.4 * Math.sin(0.23 * t))
         + 3 * d * Math.sin(2.3 * t + 0.5)
         + 1.2 * d * Math.sin(5.3 * t + 2);
  }

  // ---- cups ----
  function cup(c, phi) {
    const sin = Math.sin(phi), cos = Math.cos(phi);
    const z = c.R * cos;                          // + toward the viewer
    const x = c.cx + c.R * sin, y = c.cy + c.e * z;
    const r = c.r, a = Math.max(r * Math.abs(sin), r * 0.06);
    const ax = x + c.h * cos, ay = y - c.e * c.h * sin;   // apex leads the turn
    const shade = 0.78 + 0.22 * (z / c.R);

    ctx.globalAlpha = 1;
    // arm, from the hub's skin to the cup
    ctx.strokeStyle = c.base;
    ctx.lineWidth = r * 0.2;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(c.cx + c.hubR * sin, c.cy + c.e * c.hubR * cos);
    ctx.lineTo(x, y);
    ctx.stroke();

    // outer cone: the hull of mouth and apex, lit from above
    const g = ctx.createLinearGradient(0, y - r, 0, y + r);
    g.addColorStop(0, c.light);
    g.addColorStop(0.5, c.base);
    g.addColorStop(1, c.dark);
    ctx.fillStyle = g;
    const ux = (ax - x) / a, uy = (ay - y) / r, d = Math.hypot(ux, uy);
    ctx.beginPath();
    if (d > 1.001) {
      // apex outside the mouth: two tangents and the far side of the rim
      const p = Math.atan2(uy, ux), w = Math.acos(1 / d);
      ctx.moveTo(ax, ay);
      ctx.lineTo(x + a * Math.cos(p + w), y + r * Math.sin(p + w));
      ctx.ellipse(x, y, a, r, 0, p + w, p - w + TAU, false);
      ctx.closePath();
    } else {
      ctx.ellipse(x, y, a, r, 0, 0, TAU);
    }
    ctx.fill();
    // the cone turns away from the light toward its tip
    const gt = d > 1.001
      ? ctx.createLinearGradient(x, y, ax, ay)
      : ctx.createRadialGradient(ax, ay, 0, ax, ay, r * 1.1);
    gt.addColorStop(0, d > 1.001 ? 'rgba(11,12,14,0)' : 'rgba(255,240,220,0.10)');
    gt.addColorStop(1, 'rgba(11,12,14,0.45)');
    ctx.fillStyle = gt;
    ctx.fill();

    if (sin > 0) {
      // mouth toward us: the shadowed inside, its lower far wall catching light
      const gi = ctx.createRadialGradient(x - a * 0.15, y - r * 0.35, r * 0.1, x, y, r);
      gi.addColorStop(0, c.dark);
      gi.addColorStop(0.7, c.dark);
      gi.addColorStop(1, c.base);
      ctx.fillStyle = gi;
      ctx.beginPath();
      ctx.ellipse(x, y, a * 0.86, r * 0.86, 0, 0, TAU);
      ctx.fill();
    }
    // the rolled rim, lit along its top
    const gr = ctx.createLinearGradient(0, y - r, 0, y + r);
    gr.addColorStop(0, c.light);
    gr.addColorStop(1, c.dark);
    ctx.strokeStyle = gr;
    ctx.lineWidth = r * 0.12;
    ctx.beginPath();
    ctx.ellipse(x, y, a, r, 0, 0, TAU);
    ctx.stroke();

    // further away reads darker in the dusk
    if (shade < 1) {
      ctx.globalAlpha = (1 - shade) * 1.6;
      ctx.fillStyle = '#0b0c0e';
      ctx.beginPath();
      ctx.ellipse(x, y, a, r, 0, 0, TAU);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
    return z;
  }

  function drawCups(c) {
    const phis = [0, 1, 2].map(function (i) { return spin + i * TAU / 3; });
    phis.sort(function (p, q) { return Math.cos(p) - Math.cos(q); });   // back to front
    let hubDrawn = false;
    phis.forEach(function (phi) {
      if (!hubDrawn && Math.cos(phi) >= 0) { ctx.drawImage(sprites.hub, cfg.hub.x, cfg.hub.y); hubDrawn = true; }
      cup(c, phi);
    });
    if (!hubDrawn) ctx.drawImage(sprites.hub, cfg.hub.x, cfg.hub.y);
  }

  // ---- vane: a rigid yaw seen from the side shortens it along its own axis ----
  function drawVane(v, psi) {
    const k = Math.cos(PSI0 + psi) / Math.cos(PSI0);
    const px = v.pivot[0], py = v.pivot[1];
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(v.axis);
    ctx.scale(k, 1);
    ctx.rotate(-v.axis + psi * 0.06);
    ctx.translate(-px, -py);
    ctx.drawImage(sprites.vane, v.x, v.y);
    ctx.restore();
  }

  function draw() {
    if (!fit || !cfg) return;
    const f = fit, c = cfg.cups;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(f.s * f.dpr, 0, 0, f.s * f.dpr, f.ox * f.dpr, f.oy * f.dpr);
    drawCups(c);
    drawVane(cfg.vane, reduced ? 0 : yaw(t));
  }

  function frame(now) {
    raf = 0;
    if (!running) return;
    const dt = last ? Math.min((now - last) / 1000, 0.05) : 0;
    last = now;
    t += dt;
    spin += dt * TAU * 1.1 * gust(t);   // about a turn a second in a steady breeze
    draw();
    raf = requestAnimationFrame(frame);
  }

  function setRunning() {
    const want = !reduced && visible && !document.hidden && !!cfg;
    if (want === running) return;
    running = want;
    last = 0;
    if (running && !raf) raf = requestAnimationFrame(frame);
  }

  fetch('hero-anim.json', { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (json) { config = json; return use(variant()); })
    .then(function () {
      new IntersectionObserver(function (es) {
        visible = es[0].isIntersecting;
        setRunning();
      }).observe(hero);
      document.addEventListener('visibilitychange', setRunning);
      if (window.ResizeObserver) new ResizeObserver(resize).observe(hero);
      else window.addEventListener('resize', resize);
      narrow.addEventListener('change', function () {
        hero.classList.remove('wind-on');
        cfg = null;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        use(variant()).then(setRunning).catch(function () {});
      });
      setRunning();
    })
    .catch(function () { hero.classList.remove('wind-on'); });
})();
