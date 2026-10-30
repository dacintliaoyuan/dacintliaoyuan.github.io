// The opening's loading shell (CONTEXT: 加载画面): a camera iris over a ruler, no lettering. It is
// shown only when a first visit's opening is about to play and what it needs is still not in 0.6 s
// after the visitor opened the page. The opening's pictures are fetched here as soon as manifest.js is
// in, long before main.js, and counted as their bytes come in: the iris opens and the ruler fills with
// what has really arrived, never a made-up share, while the dial round the iris turns on its own and
// never counts as progress. main.js takes the pictures from here (art) and says when the opening can
// start; the sharp layer may still be on its way then, if it can be expected in by the focus pull (defer,
// startable). The shell then opens into the opening's first frame (handoff): the iris opens out to the
// opening's ring and the ruler rises onto its horizontal guide, and the opening draws over them. Without
// a real step for 15 s it gives up, and the page shows its opening screen instead. A tap or a key skips
// the wait too (not the wheel: turned by habit, it would lose the visitor the whole opening). Timers
// pause in a background tab.
(() => {
  'use strict';
  // main.js may have installed its own real fallback first (boot.js was slow or failed); then this
  // script stands down, so the two controllers never run their timers or shell together.
  if (window.HOME_BOOT) return;

  const SHOW_AFTER = 600;      // after the visitor opened the page (performance.now() counts from then)
  const GIVE_UP_AFTER = 15000;
  const FADE_IN = 320;         // the shell's own fade in (index.html), which a handoff waits out
  const OPEN = 500;            // the handoff: the iris opens out to the ring, the ruler rises onto the guide
  const RELEASE = 950;         // ...and they stay over the opening until it has drawn its own guide and ring
  const STEP = 32;             // the opening's guide ticks (main.js: drawGuides): the ruler is that guide
  const SAFETY = 0.75;         // a deferred picture must be expected in within this share of its time
  // Without bytes to go by (no fetch, a page opened from a file), the stages main.js reaches.
  const STAGES = ['styles', 'fonts', 'feather', 'clouds', 'far', 'near', 'fill'];
  const FRACTIONS = { styles: 0.06, fonts: 0.12, feather: 0.22, clouds: 0.34, far: 0.58, near: 0.8, fill: 0.96 };
  const MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'AltGraph', 'Meta', 'OS', 'CapsLock', 'Fn']);
  const SKIP_EVENTS = ['pointerdown', 'keydown', 'touchstart'];
  const SVG_NS = 'http://www.w3.org/2000/svg';

  let seen = false;
  try { seen = Boolean(sessionStorage.getItem('home:opening-seen')); } catch { /* no storage: a first visit */ }
  let reduced = false;
  try { reduced = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { /* no media queries */ }
  let debug = false;
  try { debug = new URLSearchParams(location.search).has('debug'); } catch { /* no query */ }
  let enabled = !seen && !/^#(about|projects|contact|settings)$/.test(location.hash) && !reduced && !debug;

  let active = false, done = false, shellShown = false, skipped = false, timedOut = false;
  let fallbackPending = false, skipBound = false;
  let lastStage = -1, stageValue = 0;
  let showAt = 0, deadline = 0, hiddenAt = 0;
  let showTimer = 0, watchTimer = 0, releaseTimer = 0, shell = null;
  const skipHandlers = [], fallbackHandlers = [];

  const now = () => performance.now();
  const clamp01 = v => Math.min(1, Math.max(0, v));
  const seg = (t, start, length) => clamp01((t - start) / length);
  const inOut = p => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
  const lerp = (a, b, p) => a + (b - a) * p;
  const fixed = v => v.toFixed(1);
  const shellEl = () => {
    if (!shell) shell = document.getElementById('boot');
    return shell;
  };
  function clearTimers() {
    clearTimeout(showTimer);
    clearTimeout(watchTimer);
    showTimer = watchTimer = 0;
  }
  function call(handlers) {
    for (const handler of handlers) {
      try { handler(); } catch (error) { console.error(error); }
    }
  }

  // ---------- where it is drawn ----------

  // Centred on the shot's window, which the opening's guides cross and its ring goes round (main.js:
  // layout, drawGuides; the same sums). The iris is 280 px across on a desktop screen; the ruler under it
  // runs a whole number of the guide's ticks either side of the centre, clear of the dial.
  let G = null, parts = null;
  function measure() {
    const W = Math.max(1, innerWidth), H = Math.max(1, innerHeight);
    const win = W < H ? { x: 0.06 * W, y: 0.15 * H, w: 0.88 * W, h: 0.55 * H }
      : { x: 0.18 * W, y: 0.1 * H, w: 0.64 * W, h: 0.66 * H };
    const r = Math.min(140, 0.25 * W, 0.155 * H);
    G = {
      cx: win.x + win.w / 2, cy: win.y + win.h / 2, r, ring: 0.42 * Math.min(win.w, win.h),
      half: STEP * Math.min(6, Math.max(3, Math.round(1.35 * r / STEP))),
    };
    G.rulerY = G.cy + 1.2 * r + 14;
    const el = shellEl();
    if (!el) return;
    el.style.setProperty('--boot-x', `${fixed(G.cx)}px`);
    el.style.setProperty('--boot-y', `${fixed(G.cy)}px`);
    el.style.setProperty('--boot-r', `${fixed(r)}px`);
  }

  function build() {
    const el = shellEl(), lines = el && el.querySelector('.boot-lines');
    if (parts || !lines) return;
    const make = (tag, cls) => {
      const node = document.createElementNS(SVG_NS, tag);
      node.setAttribute('class', cls);
      lines.appendChild(node);
      return node;
    };
    parts = {
      rim: make('circle', 'rim'), hair: make('circle', 'rim-hair'), blades: make('path', 'blades'),
      hole: make('path', 'hole'), rule: make('path', 'rule'), ticks: make('path', 'ticks'),
      centre: make('path', 'ticks'), fill: make('path', 'fill'),
    };
    el.classList.add('drawn');   // (the dial's own rim, for a shell without this script, stands down)
  }

  // The shell at progress p and handoff h (both 0 to 1). Six blades round a hexagonal opening that
  // widens with p and turns a little as it does, like an iris; the rim round them; the ruler under them
  // filled to p. In the handoff the blades open right out and go, the rim widens to the opening's ring and
  // turns to its hairline, and the ruler rises onto the guide line through the window's centre, its blue
  // fading out.
  function draw(p, h) {
    if (!G || !parts) return;
    const { cx, cy, r } = G;
    // (an iris opens at once and settles; the rim widens once the blades are in it)
    const open = 1 - (1 - seg(h, 0, 0.6)) ** 2, grow = inOut(seg(h, 0.3, 0.7)), rise = inOut(seg(h, 0.2, 0.8));
    const a = r * lerp(lerp(0.1, 0.62, p), 1, open);
    const turn = (-90 + 18 * p + 12 * open) * Math.PI / 180;
    const V = [];
    for (let i = 0; i < 6; i++) V.push([cx + a * Math.cos(turn + i * Math.PI / 3), cy + a * Math.sin(turn + i * Math.PI / 3)]);
    let blades = '';
    V.forEach(([x0, y0], i) => {
      // each side of the opening runs on past the next corner to the rim: one blade's edge
      const [x1, y1] = V[(i + 1) % 6], length = Math.hypot(x1 - x0, y1 - y0) || 1;
      const dx = (x1 - x0) / length, dy = (y1 - y0) / length, b = (x1 - cx) * dx + (y1 - cy) * dy;
      const t = -b + Math.sqrt(Math.max(0, b * b - ((x1 - cx) ** 2 + (y1 - cy) ** 2 - r * r)));
      blades += `M${fixed(x0)} ${fixed(y0)}L${fixed(x1 + t * dx)} ${fixed(y1 + t * dy)}`;
    });
    const gone = (1 - seg(open, 0.3, 0.55)).toFixed(3);   // (the blades go into the rim)
    parts.blades.setAttribute('d', blades);
    parts.hole.setAttribute('d', `M${V.map(([x, y]) => `${fixed(x)} ${fixed(y)}`).join('L')}Z`);
    parts.blades.style.opacity = parts.hole.style.opacity = gone;
    for (const rim of [parts.rim, parts.hair]) {
      rim.setAttribute('cx', fixed(cx));
      rim.setAttribute('cy', fixed(cy));
      rim.setAttribute('r', fixed(lerp(r, G.ring, grow)));
    }
    parts.rim.style.opacity = (1 - grow).toFixed(3);
    parts.hair.style.opacity = grow.toFixed(3);
    const y = lerp(G.rulerY, cy, rise), left = cx - G.half;
    let ticks = '';
    for (let i = 1; i * STEP <= G.half; i++) {
      const len = i % 5 ? 4 : 9;
      for (const sign of [-1, 1]) ticks += `M${fixed(cx + sign * i * STEP)} ${fixed(y - len)}v${2 * len}`;
    }
    parts.rule.setAttribute('d', `M${fixed(left)} ${fixed(y)}H${fixed(cx + G.half)}`);
    parts.ticks.setAttribute('d', ticks);
    // (the guide has no tick at its centre: the vertical guide crosses there)
    parts.centre.setAttribute('d', `M${fixed(cx)} ${fixed(y - 9)}v18`);
    parts.centre.style.opacity = (1 - seg(h, 0.3, 0.4)).toFixed(3);
    parts.fill.setAttribute('d', `M${fixed(left)} ${fixed(y)}H${fixed(left + 2 * G.half * p)}`);
    parts.fill.style.opacity = (1 - seg(h, 0.35, 0.5)).toFixed(3);
  }

  // The shell's frames: the progress shown eases after the real one (a chunk of bytes is a step, not a
  // jump) and the handoff runs to its end. Nothing is drawn while the shell is hidden or in a background
  // tab (the dial is CSS and turns on regardless).
  let frame = 0, lastAt = 0, shown = 0, target = 0, opening = null;
  function paint(at) {
    frame = 0;
    if (!shellShown || !parts) return;
    const dt = lastAt ? Math.min(100, at - lastAt) : 16;
    lastAt = at;
    shown += (target - shown) * Math.min(1, dt / 240);
    if (Math.abs(target - shown) < 0.001) shown = target;
    let h = 0, p = shown;
    if (opening && opening.start) {
      if (!opening.from) opening.from = { at, p: shown };
      h = clamp01((at - opening.from.at) / OPEN);
      p = lerp(opening.from.p, 1, inOut(seg(h, 0, 0.3)));   // (the ruler fills up first)
    }
    draw(p, h);
    if (opening && h >= 1) { release(); return; }
    if (shown !== target || opening) frame = requestAnimationFrame(paint);
  }
  function kick() {
    if (frame || !enabled || !shellShown || !parts || typeof requestAnimationFrame !== 'function') return;
    lastAt = 0;
    frame = requestAnimationFrame(paint);
  }
  addEventListener('resize', () => {
    if (!enabled || !shellShown || done) return;
    measure();
    draw(shown, 0);
  });

  function showShell() {
    if (!enabled || done || skipped || timedOut || shellShown) return;
    const el = shellEl();
    if (!el) {
      // (the page is not parsed as far as the shell yet; DOMContentLoaded would wait for main.js too)
      if (document.readyState === 'loading') showTimer = setTimeout(showShell, 50);
      return;
    }
    shellShown = true;
    measure();
    build();
    shown = target;
    draw(shown, 0);
    el.hidden = false;
    el.dataset.shown = String(Math.round(performance.now()));
    document.documentElement.classList.add('booting');
    addSkip();
    const on = () => { if (shellShown && !done) el.classList.add('on'); };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(on);
    else setTimeout(on, 0);
    kick();
  }
  function settleOpening() {
    if (!opening) return;
    const resolve = opening.resolve;
    opening = null;
    resolve();
  }
  // Ends the wait without a handoff (skipped, given up, the opening screen instead): the shell fades out.
  function finish() {
    active = false;
    done = true;
    enabled = false;   // (the shell is for the first opening only, not a replay)
    clearTimers();
    removeSkip();
    settleOpening();
    gateOff();
    const el = shellEl();
    if (el && shellShown && !el.hidden) {
      clearTimeout(releaseTimer);
      el.classList.remove('on', 'open', 'opening');
      el.classList.add('done');
      releaseTimer = setTimeout(() => {
        el.hidden = true;
        el.classList.remove('done');
      }, 520);
    }
    document.documentElement.classList.remove('booting');
  }
  // The end of a handoff: the opening is under way, its first frame showing through the shell, which
  // keeps its rim and ruler over the opening's own ring and guide until those are drawn.
  function release() {
    active = false;
    done = true;
    enabled = false;
    clearTimers();
    removeSkip();
    gateOff();
    const el = shellEl();
    el.classList.add('open');
    document.documentElement.classList.remove('booting');
    releaseTimer = setTimeout(() => {
      el.hidden = true;
      el.classList.remove('on', 'open', 'opening');
    }, RELEASE);
    settleOpening();
  }
  // Watches for a wait without a real step (the deadline moves with every one), and shows the shell once
  // the wait has gone on for SHOW_AFTER.
  function schedule() {
    clearTimers();
    if (!active || document.hidden) return;
    const at = now();
    if (enabled && !shellShown && at >= showAt) showShell();
    if (at >= deadline) { fallbackNow(); return; }
    if (enabled && !shellShown) showTimer = setTimeout(showShell, Math.max(0, showAt - at));
    watchTimer = setTimeout(watch, Math.max(0, deadline - at));
  }
  function watch() {
    if (now() >= deadline) fallbackNow();
    else watchTimer = setTimeout(watch, deadline - now());
  }
  function onSkip(event) {
    if (event.type === 'keydown') {
      if (event.ctrlKey || event.altKey || event.metaKey || MODIFIERS.has(event.key)) return;
      // the page's own keys wait for the opening to end: this key has skipped it already
      event.stopImmediatePropagation();
    }
    skipNow();
  }
  function addSkip() {
    if (skipBound) return;
    skipBound = true;
    for (const type of SKIP_EVENTS) addEventListener(type, onSkip, { passive: type !== 'keydown' });
  }
  function removeSkip() {
    if (!skipBound) return;
    skipBound = false;
    for (const type of SKIP_EVENTS) removeEventListener(type, onSkip);
  }
  function skipNow() {
    if (!active || done || skipped || timedOut) return;
    skipped = true;
    finish();
    call(skipHandlers);
  }
  function fallbackNow() {
    if (!active || done || skipped || timedOut) return;
    timedOut = true;
    finish();
    if (!fallbackHandlers.length) { fallbackPending = true; return; }
    call(fallbackHandlers);
  }

  // ---------- the opening's pictures ----------

  // Fetched from here for the first opening only, and handed to the page as blob URLs once in, so the
  // bytes counted are the bytes shown. A picture is wanted from the opening's first frame unless it is
  // deferrable (the sharp layer): one of those waits for the others to be nearly in, so as not to slow them
  // down, and once main.js says how far into the opening it is needed (defer), the opening may start
  // without it if it can be expected in by then at the rate the bytes are coming (startable). A picture
  // that cannot be fetched is handed back as its own path, for the page to load (or fail on) as before.
  const art = new Map();   // path -> { got, size, started, settled, deferrable, later, promise, resolve }
  const flow = [];         // [when, bytes in so far], over the last 2 s, for the rate
  const waiters = [];
  let artOn = false, gated = false, received = 0;
  function rate() {
    const at = now();
    while (flow.length > 1 && flow[1][0] <= at - 2000) flow.shift();
    if (!flow.length) return 0;
    const [from, before] = flow[0], span = (at - from) / 1000;
    return span < 0.25 ? 0 : (received - before) / span;
  }
  function track(path, deferrable) {
    let entry = art.get(path);
    if (entry) return entry;
    entry = { path, got: 0, size: 0, started: false, settled: false, deferrable, later: null };
    entry.promise = new Promise(resolve => { entry.resolve = resolve; });
    art.set(path, entry);
    if (deferrable) pump();
    else pull(entry);
    return entry;
  }
  // Only the site's own pictures are fetched from here: a relative path under assets/ or ornaments/,
  // never another host, an absolute path or .. (the manifest is the site's own, but no path is trusted
  // to point off the site). Anything else is handed back as its path, for the page to load as before.
  function own(path) {
    if (typeof path !== 'string' || path.startsWith('/') || path.includes('\\')) return false;
    const parts = path.split('/');
    if (parts.length < 2 || (parts[0] !== 'assets' && parts[0] !== 'ornaments')) return false;
    return parts.every(part => part && part !== '.' && part !== '..' && /^[A-Za-z0-9._-]+$/.test(part));
  }
  function pull(entry) {
    entry.started = true;
    if (!own(entry.path)) { settle(entry, entry.path); return; }
    fetch(entry.path, { credentials: 'same-origin' })
      .then(response => {
        if (!response.ok) throw new Error(`${entry.path}: HTTP ${response.status}`);
        entry.size = Number(response.headers.get('Content-Length')) || 0;
        const type = response.headers.get('Content-Type') || '';
        if (!response.body || !response.body.getReader) return response.blob();
        const reader = response.body.getReader(), chunks = [];
        const next = () => reader.read().then(({ done: end, value }) => {
          if (end) return new Blob(chunks, { type });
          chunks.push(value);
          took(entry, value.byteLength);
          return next();
        });
        return next();
      })
      .then(blob => {
        if (blob.size > entry.got) took(entry, blob.size - entry.got);
        settle(entry, URL.createObjectURL(blob));
      }, error => {
        console.warn('[boot] fetching a picture failed; the page loads it itself', error);
        settle(entry, entry.path);
      });
  }
  function took(entry, bytes) {
    entry.got += bytes;
    if (entry.size && entry.got > entry.size) entry.size = entry.got;
    received += bytes;
    const at = now();
    flow.push([at, received]);
    deadline = at + GIVE_UP_AFTER;   // bytes coming in are progress
    changed();
  }
  function settle(entry, url) {
    entry.settled = true;
    entry.resolve(url);
    changed();
  }
  function changed() {
    pump();
    update();
    if (waiters.length && startable()) call(waiters.splice(0));
  }
  // A deferrable picture starts once the others are in, or nearly (half a second of bytes at the rate
  // they come), or the shell no longer holds it back.
  function pump() {
    let left = 0;
    for (const e of art.values()) if (!e.deferrable && !e.settled) left += e.size ? e.size - e.got : Infinity;
    if (gated && left > 0.5 * rate()) return;
    for (const e of art.values()) if (!e.started) pull(e);
  }
  function gateOff() {
    artOn = gated = false;
    pump();
    call(waiters.splice(0));
  }
  // Whether the opening can start as far as the pictures go: all of them in but the deferred ones, and
  // those expected in (in the order they are needed) within SAFETY of their time.
  function startable() {
    const later = [], bps = rate();
    for (const e of art.values()) {
      if (e.settled) continue;
      if (!e.deferrable || e.later == null) return false;
      later.push(e);
    }
    let left = 0;
    for (const e of later.sort((a, b) => a.later - b.later)) {
      if (!e.size || !bps) return false;
      left += e.size - e.got;
      if (left / bps > SAFETY * e.later / 1000) return false;
    }
    return true;
  }
  // The share of the way to a start: the bytes in, against those still to come before the opening can
  // start (a deferred picture's last bytes may come after). null without any bytes to go by.
  function byteProgress() {
    let got = 0, need = 0, unknown = false;
    const bps = rate();
    for (const e of art.values()) {
      got += e.got;
      if (e.settled) continue;
      if (!e.size) { unknown = true; continue; }
      const left = e.size - e.got;
      need += e.later == null ? left : Math.max(0, left - bps * SAFETY * e.later / 1000);
    }
    if (!got) return null;
    const p = got / (got + need);
    return unknown ? Math.min(0.9, p) : p;
  }
  // The progress the shell shows goes on to the end of the ruler only in the handoff.
  function update() {
    if (!active || done) return;
    const bytes = byteProgress();
    target = Math.max(target, Math.min(0.97, bytes == null ? stageValue : bytes));
    kick();
  }

  // The first opening's picture (main.js: pickScene and sharpOf make the same choice, and take this one
  // up through pick), so its files are on their way before main.js is in.
  function startArt(manifest) {
    if (!artOn || !manifest) return;
    const scenes = manifest.scenes || [], sky = manifest.sky || {};
    let prefs = {};
    try { prefs = JSON.parse(sessionStorage.getItem('home:prefs') || 'null') || {}; } catch { /* no storage */ }
    let index = scenes.findIndex(s => s.far === prefs.scene);
    if (index < 0 && scenes.length) {
      let period = 'day';
      try { period = window.HOME_TIME.at(new Date(), prefs.time).period; } catch { /* always day */ }
      const all = scenes.map((_, i) => i), own = all.filter(i => scenes[i].time === period);
      const free = all.filter(i => !scenes[i].time);
      const pool = [...(Math.random() < 0.5 ? [own, free] : [free, own]), all].find(p => p.length);
      index = pool[Math.floor(Math.random() * pool.length)];
    }
    api.pick = index;
    for (const info of Object.values(sky)) track(`assets/${info.file}`, false);
    const s = scenes[index];
    if (!s) return;
    track(`assets/${s.far}`, false);
    track(`assets/${s.thumb || s.far}`, false);
    const W = Math.max(1, innerWidth), H = Math.max(1, innerHeight);
    const size = s.h * Math.min(W / s.w, H / s.h) * (window.devicePixelRatio || 1);
    track(`assets/${s.full && size > s.nearH ? s.full : s.near}`, true);
  }

  const api = {
    enabled,
    pick: -1,
    get active() { return active; },
    get done() { return done; },
    get shellShown() { return shellShown; },
    get skipped() { return skipped; },
    get timedOut() { return timedOut; },
    get fallbackPending() { return fallbackPending; },
    // A real step main.js has reached (bytes, where there are some to go by, are shown instead).
    progress(stage, value) {
      if (!active || done) return;
      deadline = now() + GIVE_UP_AFTER;   // a real step, never the dial turning
      const index = STAGES.indexOf(stage);
      if (index >= 0 && index >= lastStage) {
        lastStage = index;
        stageValue = Math.max(stageValue, Number.isFinite(value) ? value : FRACTIONS[stage]);
      }
      update();
    },
    // The URL to show a picture from (a promise): this script's copy, once in, for a picture it has or is
    // still fetching for the first opening; null for any other (the page loads that itself). Only what
    // startArt has begun is answered: the page never makes the shell fetch a path of its own naming.
    art(path) {
      const entry = art.get(path);
      return entry ? entry.promise : null;
    },
    // A picture the opening first needs ms into it (main.js knows when): it need not be in at the start.
    defer(path, ms) {
      const entry = art.get(path);   // (only a picture the shell has begun; the page loads any other)
      if (!entry) return;
      entry.deferrable = true;
      entry.later = ms;
      changed();
    },
    // Resolves once the opening can start as far as the pictures go; null without them to go by.
    startable() {
      if (!artOn) return null;
      return new Promise(resolve => {
        if (startable()) resolve();
        else waiters.push(resolve);
      });
    },
    begin() {
      if (active) return;
      active = true;
      done = false;
      skipped = false;
      timedOut = false;
      fallbackPending = false;
      lastStage = -1;
      stageValue = target = 0;
      const at = now();
      showAt = at + SHOW_AFTER;
      deadline = at + GIVE_UP_AFTER;
      hiddenAt = document.hidden ? at : 0;
      schedule();
    },
    // The opening can start: the shell, if it is up, opens into the opening's first frame (once its own
    // fade in is over) and the promise resolves as the opening is to begin; without a shell, at once.
    handoff() {
      if (done) return Promise.resolve();
      // (a replay has no shell of its own: enabled is off after the first opening, even though
      // shellShown still records that the first visit's shell was up)
      if (!enabled || !shellShown) {
        finish();
        return Promise.resolve();
      }
      if (opening) return opening.promise;
      opening = { start: false, from: null };
      opening.promise = new Promise(resolve => { opening.resolve = resolve; });
      const wait = Math.max(0, Number(shellEl().dataset.shown) + FADE_IN - now());
      const promise = opening.promise;
      setTimeout(() => {
        if (!opening || opening.promise !== promise) return;
        opening.start = true;
        target = 1;
        shellEl().classList.add('opening');
        kick();
      }, wait);
      return promise;
    },
    // The wait is over another way (the opening screen instead): the shell fades out; a shell still over
    // the start of the opening is taken away at once.
    ready() {
      if (!done) { finish(); return; }
      const el = shellEl();
      if (el && el.classList.contains('open')) {
        clearTimeout(releaseTimer);
        el.hidden = true;
        el.classList.remove('on', 'open', 'opening');
      }
    },
    skip: skipNow,
    onSkip(handler) {
      skipHandlers.push(handler);
      if (skipped) handler();
    },
    onFallback(handler) {
      fallbackHandlers.push(handler);
      if (timedOut) handler();
    },
  };
  window.HOME_BOOT = api;

  if (enabled) {
    active = true;
    showAt = SHOW_AFTER;
    deadline = now() + GIVE_UP_AFTER;
    hiddenAt = document.hidden ? now() : 0;
    schedule();
    // fetch counts the bytes as they come, where it can (not from a page opened from a file)
    artOn = gated = typeof fetch === 'function' && typeof Blob === 'function' && /^https?:$/.test(location.protocol);
    if (artOn) {
      if (window.HOME_MANIFEST) startArt(window.HOME_MANIFEST);
      else {
        // manifest.js is deferred at the end of the page; its load comes before main.js runs
        document.addEventListener('load', function manifestIn(event) {
          const el = event.target;
          if (!el || el.tagName !== 'SCRIPT' || !/(^|\/)assets\/manifest\.js$/.test(el.getAttribute('src') || '')) return;
          document.removeEventListener('load', manifestIn, true);
          startArt(window.HOME_MANIFEST);
        }, true);
      }
    }
  }
  document.addEventListener('visibilitychange', () => {
    if (!active) return;
    const at = now();
    if (document.hidden) {
      if (!hiddenAt) hiddenAt = at;
      clearTimers();
      return;
    }
    if (hiddenAt) {
      const away = at - hiddenAt;
      showAt += away;
      deadline += away;
      hiddenAt = 0;
    }
    schedule();
  });
})();
