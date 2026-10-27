// The mouse pointer (CONTEXT: 鼠标指针): Shimamura and Adachi in their summer chibi (the official
// picture put into squares, 46 across, the eyes and mouths drawn again by hand) beside a viewfinder
// corner in the HUD's own hand, white on a faint dark edge, the point at its corner. It is drawn on a
// canvas over the page that follows the mouse, and the system's pointer is hidden meanwhile
// (html.pointer-drawn, styles.css). The art is scaled to SQUARE CSS px a square on every screen, so
// that it is the same size on a 1x and a 2x screen, and a faint dark rim round it keeps it readable on
// a bright picture; the corner and the glyphs are drawn in CSS px, snapped to device pixels. The two
// bob in turn and blink, two seconds round. Over what can be clicked the corner turns blue and three
// more close round the two of them (focus locked; Shimamura smiles, Adachi blushes), drawn in as it
// locks and let go as it unlocks, and a click flashes it light blue; drawn in while it is pressed;
// over what says something when pointed at, a blue question tile sits by the corner. Written text,
// the divider and a ruler's handle have an I-beam, arrows and grip chevrons in the same hand instead,
// the two beside them. What it is over comes from styles.css: each rule that sets a cursor sets
// --pointer with it, so the two cannot disagree (a ruler's handle, a pseudo-element, is found by where
// it is). Only for a mouse: a pen, a finger and forced colours keep the system's pointers (styles.css).
// With less motion asked for, the two hold still and the pointer does not ease. main.js asks where the
// two of them are, for the fill's soft light (figure).
window.HOME_POINTER = (() => {
  'use strict';

  // The picture and the faces are editable data: site/pointer-art.source.json, written out as
  // pointer-art.js by tools/build_pointer_assets.py. The movement, the glyphs and the pointer's
  // behaviour stay here. Without the data, or with a shape this code cannot draw, the system's pointer
  // stays and figure() has nowhere to point (main.js).
  const ART = window.HOME_POINTER_ART;
  const EXPRESSIONS = ['open', 'shut', 'happy', 'squint'];
  const isRows = (rows, w, h, colours) => Array.isArray(rows) && rows.length === h
    && rows.every(line => typeof line === 'string' && line.length === w
      && [...line].every(ch => ch === '.' || Object.prototype.hasOwnProperty.call(colours, ch)));
  const isMask = (mask, colours) => Array.isArray(mask) && mask.length === 5
    && mask.every(line => typeof line === 'string' && line.length === 5
      && [...line].every(ch => ch === '.' || Object.prototype.hasOwnProperty.call(colours, ch)));
  const isEye = (eye, w, h) => Array.isArray(eye) && eye.length === 2 && eye.every(pair =>
    Array.isArray(pair) && pair.length === 2 && pair.every(Number.isInteger)
    && pair[0] >= 0 && pair[1] >= 0 && pair[0] + 5 <= w && pair[1] + 5 <= h);
  function isArt(art) {
    if (!art || typeof art !== 'object' || art.width !== 46 || art.height !== 27) return false;
    const { width, height, colours, picture, split, skin, eyes, lids, shy, faces, layers } = art;
    if (!colours || typeof colours !== 'object' || Array.isArray(colours)
        || !Object.values(colours).every(c => typeof c === 'string' && c)) return false;
    if (!isRows(picture, width, height, colours)) return false;
    if (!Array.isArray(split) || split.length !== height
        || !split.every(cut => Number.isInteger(cut) && cut >= 1 && cut <= width)) return false;
    if (typeof skin !== 'string' || !Object.prototype.hasOwnProperty.call(colours, skin)) return false;
    if (!eyes || typeof eyes !== 'object' || !['shima', 'adachi'].every(who => isEye(eyes[who], width, height))) return false;
    if (!lids || typeof lids !== 'object' || !['shut', 'happy', 'squint'].every(name => isMask(lids[name], colours))) return false;
    if (typeof shy !== 'string' || !shy) return false;
    if (!faces || typeof faces !== 'object' || !['click', 'press', 'grabbing'].every(name => {
      const face = faces[name];
      return Array.isArray(face) && face.length === 3 && EXPRESSIONS.includes(face[0])
        && EXPRESSIONS.includes(face[1]) && typeof face[2] === 'boolean';
    })) return false;
    if (layers != null && (typeof layers !== 'object' || Array.isArray(layers)
        || !['shima', 'adachi'].every(who => layers[who] == null || isRows(layers[who], width, height, colours)))) return false;
    return true;
  }
  if (!isArt(ART)) return { figure: () => null };
  const COLOURS = ART.colours, PICTURE = ART.picture, W = ART.width, H = ART.height;
  const SPLIT = ART.split, SKIN = ART.skin, EYES = ART.eyes, LIDS = ART.lids, SHY = ART.shy, FACES = ART.faces;
  const LAYERS = ART.layers;
  const TICK = 1000 / 12, FRAMES = 24;   // the loop: 24 frames, 2 s

  const SQUARE = 1.3;   // CSS px a square: the same on every screen, the art is scaled to it
  const BORDER = 2;     // squares of clear canvas round the art: one to bob into, one for the rim
  const PW = W + 2 * BORDER, PH = H + 2 * BORDER;
  const PIC_W = PW * SQUARE, PIC_H = PH * SQUARE;
  const PAD = 18;       // CSS px of canvas up and left of the point (the glyphs reach out round it)
  const ROOM = 6;       // CSS px of clear canvas past the pointer's farthest reach
  const FRAME = 3;      // CSS px between the two and the lock's corners
  const RIM = 0.55;     // the dark rim round the two, so that they hold on a bright picture
  const ACCENT = '#1c8ad7', FLASH = '#59bff7', WHITE = '#ffffff', EDGE = 'rgba(11, 21, 38, 0.72)';
  const T_LOCK = 130, T_PRESS = 90, T_FLASH = 240;   // ms
  const GLYPH = { text: 'text', resize: 'resize', grab: 'grab', grabbing: 'grab' };
  // Where the picture's canvas goes from the point (CSS px) for each glyph: its clear border is two
  // squares, so it is set a square nearer than the art used to be.
  const AT = {
    corner: [7 - SQUARE, 7 - SQUARE], text: [7 - SQUARE, 12 - SQUARE],
    resize: [6 - SQUARE, 10 - SQUARE], grab: [7 - SQUARE, 10 - SQUARE],
  };
  // The canvas round the point: PAD up and left, and as far right and down as the pointer reaches.
  const LEFT = PAD, TOP = PAD;
  const RIGHT = Math.ceil(Math.max(...Object.values(AT).map(([x]) => x)) + PIC_W + FRAME) + ROOM;
  const BOTTOM = Math.ceil(Math.max(...Object.values(AT).map(([, y]) => y)) + PIC_H + FRAME) + ROOM;

  // Where each of them is (squares across and down) and whether she blinks, at frame f of the loop:
  // a square up and back in turn, a blink each; quicker, one after the other, over what can be
  // clicked; a square down while pressed; swaying with the divider's arrows.
  function motion(state, f) {
    const p = f % 12;
    let s = [0, p >= 3 && p < 6 ? -1 : 0, f === 9 || f === 10];
    let a = [0, p >= 6 && p < 9 ? -1 : 0, f === 21 || f === 22];
    if (state === 'click') {
      const q = f % 6;
      s = [0, q < 2 ? -1 : 0, false];
      a = [0, q >= 3 && q < 5 ? -1 : 0, false];
    } else if (state === 'press' || state === 'grabbing') {
      s = [0, 1, false];
      a = [0, 1, false];
    } else if (state === 'resize') {
      const d = p < 6 ? -1 : 1;
      s = [d, 0, s[2]];
      a = [d, 0, a[2]];
    }
    return [s, a];
  }

  // One of them as rows of squares ('.' clear): her side of the split, with her eyes as asked.
  function layer(who, eyes) {
    const base = LAYERS && LAYERS[who];
    const rows = base ? base.map(line => [...line]) : PICTURE.map((line, y) => {
      const row = [...line], cut = SPLIT[y];
      if (who === 'shima') for (let x = cut; x < W; x++) row[x] = x < cut + 2 ? row[cut - 1] : '.';
      else row.fill('.', 0, cut);
      return row;
    });
    if (eyes !== 'open') {
      EYES[who].forEach(([ex, ey], side) => LIDS[eyes].forEach((line, y) => {
        [...line].forEach((ch, x) => { rows[ey + y][ex + (side ? 4 - x : x)] = ch === '.' ? SKIN : ch; });
      }));
    }
    return rows;
  }

  // The picture at a frame, a square to a pixel: the two with a clear square round them to bob into,
  // and a faint dark rim in the square outside that, where it touches them (kept: there are a few
  // dozen different ones).
  const pictures = new Map();
  function picture(state, f) {
    const [s, a] = motion(state, f), [shimaEyes, adachiEyes, shy] = FACES[state] || ['open', 'open', false];
    const eyes = [s[2] && shimaEyes === 'open' ? 'shut' : shimaEyes, a[2] && adachiEyes === 'open' ? 'shut' : adachiEyes];
    const key = [...s, ...a, ...eyes, shy].join();
    let canvas = pictures.get(key);
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.width = PW;
      canvas.height = PH;
      const g = canvas.getContext('2d');
      const solid = new Uint8Array(PW * PH);
      const paint = (rows, colours, dx, dy) => rows.forEach((row, y) => row.forEach((ch, x) => {
        if (ch === '.') return;
        const X = BORDER + dx + x, Y = BORDER + dy + y;
        solid[Y * PW + X] = 1;
        g.fillStyle = colours[ch];
        g.fillRect(X, Y, 1, 1);
      }));
      paint(layer('shima', eyes[0]), COLOURS, s[0], s[1]);
      paint(layer('adachi', eyes[1]), shy ? { ...COLOURS, G: SHY } : COLOURS, a[0], a[1]);
      const at = (x, y) => x >= 0 && y >= 0 && x < PW && y < PH && solid[y * PW + x];
      g.fillStyle = `rgba(11, 21, 38, ${RIM})`;
      for (let y = 0; y < PH; y++) for (let x = 0; x < PW; x++) {
        if (at(x, y)) continue;
        if (at(x - 1, y) || at(x + 1, y) || at(x, y - 1) || at(x, y + 1)) g.fillRect(x, y, 1, 1);
      }
      pictures.set(key, canvas);
    }
    return canvas;
  }

  // The glyphs, in CSS px from the point and drawn on device pixels (s of them to a CSS px): rects
  // [x, y, w, h] each snapped to them, the edge a device pixel round, then the fill; or a closed shape
  // with the edge stroked round it.
  function rects(g, s, list, fill) {
    const px = v => Math.round(v * s);
    for (const [colour, grow] of [[EDGE, 1], [fill, 0]]) {
      g.fillStyle = colour;
      for (const [x, y, w, h] of list) {
        const x0 = px(x), y0 = px(y);
        g.fillRect(x0 - grow, y0 - grow, px(x + w) - x0 + 2 * grow, px(y + h) - y0 + 2 * grow);
      }
    }
  }
  function shape(g, s, outline, fill, edge = 1.25) {
    g.save();
    g.scale(s, s);
    g.beginPath();
    outline(g);
    g.lineJoin = 'round';
    g.lineWidth = 2 * edge;
    g.strokeStyle = EDGE;
    g.stroke();
    g.fillStyle = fill;
    g.fill();
    g.restore();
  }
  const polygon = points => g => {
    points.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
    g.closePath();
  };
  // a rounded rectangle, on browsers that have not the canvas' roundRect yet
  function rounded(c, x, y, w, h, r) {
    if (c.roundRect) { c.roundRect(x, y, w, h, r); return; }
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }
  // a viewfinder corner, its outer corner at (x, y) and its arms going (sx, sy): (1, 1) right and down
  function corner(g, s, x, y, sx, sy, arm, t, fill) {
    rects(g, s, [[arm, t], [t, arm]].map(([w, h]) => [sx > 0 ? x : x - w, sy > 0 ? y : y - h, w, h]), fill);
  }
  // the corner's colour: white at rest, blue over what can be clicked, a lighter blue as a click
  // flashes it (lock and flash 0..1)
  const rgbOf = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  function colour(lock, flash) {
    const a = rgbOf(ACCENT), f = rgbOf(FLASH);
    let r = 255 + (a[0] - 255) * lock, g2 = 255 + (a[1] - 255) * lock, b = 255 + (a[2] - 255) * lock;
    if (flash > 0) {
      r += (f[0] - r) * flash;
      g2 += (f[1] - g2) * flash;
      b += (f[2] - b) * flash;
    }
    return `rgb(${Math.round(r)}, ${Math.round(g2)}, ${Math.round(b)})`;
  }
  // box: the art's, [left, top, right, bottom] from the point; the lock's corners sit FRAME outside it
  const GLYPHS = {
    corner(g, s, state, box, lock, press, flash) {
      const inset = 2 * press, arm = 19 - 5 * press, t = 3.5 - 0.5 * press;
      const fill = colour(lock, flash);
      corner(g, s, inset, inset, 1, 1, arm, t, fill);
      if (lock > 0.01) {   // the other three, round the two of them, closing in as it locks
        const [left, top, right, bottom] = box;
        const fl = left - FRAME, ft = top - FRAME, fr = right + FRAME, fb = bottom + FRAME;
        const out = (1 - lock) * 5, a = (13 - 4 * press) * (0.55 + 0.45 * lock);
        g.save();
        g.globalAlpha = lock;
        for (const [cx, cy, ax, ay, ox, oy] of [
          [fl, ft, 1, 1, -1, -1], [fr, ft, -1, 1, 1, -1],
          [fl, fb, 1, -1, -1, 1], [fr, fb, -1, -1, 1, 1],
        ]) {
          if (cx === fl && cy === ft) continue;   // the main corner is at the point
          corner(g, s, cx + ox * out, cy + oy * out, ax, ay, a, 3, fill);
        }
        g.restore();
      }
      if (state === 'help') {   // a question tile like the index's squares, by the corner
        shape(g, s, c => rounded(c, 23, -5, 12, 12, 3), ACCENT, 0.9);
        g.save();
        g.scale(s, s);
        g.fillStyle = WHITE;
        g.font = '9.5px "Archivo Black", Inter, system-ui, sans-serif';
        g.textAlign = 'center';
        g.textBaseline = 'middle';
        g.fillText('?', 29, 1.5);
        g.restore();
      }
    },
    text(g, s) {
      rects(g, s, [[-1, -9, 2, 18], [-4, -10, 8, 2], [-4, 8, 8, 2]], WHITE);
    },
    resize(g, s) {
      shape(g, s, polygon([[-11.5, 0], [-6.5, -5], [-6.5, -1.75], [6.5, -1.75], [6.5, -5], [11.5, 0], [6.5, 5], [6.5, 1.75], [-6.5, 1.75], [-6.5, 5]]), WHITE);
      rects(g, s, [[-1, -8, 2, 16]], WHITE);
    },
    grab(g, s, state) {
      const held = state === 'grabbing', o = held ? 3.5 : 6;
      for (const d of [-1, 1]) {
        shape(g, s, polygon([[d * o, -5.25], [d * (o + 4.4), 0], [d * o, 5.25], [d * (o + 2.1), 5.25], [d * (o + 6.5), 0], [d * (o + 2.1), -5.25]]), WHITE);
      }
      rects(g, s, [[-1.75, -1.75, 3.5, 3.5]], held ? ACCENT : WHITE);
    },
  };

  const root = document.documentElement;
  const forced = matchMedia('(forced-colors: active)');
  const still = matchMedia('(prefers-reduced-motion: reduce)');
  const view = document.createElement('canvas');
  view.className = 'pointer';
  view.hidden = true;
  view.setAttribute('aria-hidden', 'true');
  document.body.append(view);
  const g = view.getContext('2d');

  // dpr: device px a CSS px; O: device px from the canvas' corner to the point, up and left of it
  let dpr = 0, O = [0, 0];
  let on = false, inside = false, x = 0, y = 0, over = null, moved = false, drawn = '', placed = '', frame = 0, timer = 0;
  // what is under the pointer, kept while it is held still (see stateAt)
  let hit = { el: null, kind: 'rest', stamp: 0 };
  // the lock, the press and a click's flash, eased (see draw)
  const anim = {
    lock: { v: 0, from: 0, to: 0, t0: 0 },
    press: { v: 0, from: 0, to: 0, t0: 0 },
    flash: { v: 0, t0: 0 },
  };
  // where the two of them were last drawn from the point (figure); the corner's place until the first draw
  let figX = AT.corner[0] + PIC_W / 2, figY = AT.corner[1] + PIC_H / 2;

  function fit() {
    dpr = devicePixelRatio || 1;
    view.width = Math.round((LEFT + RIGHT) * dpr);
    view.height = Math.round((TOP + BOTTOM) * dpr);
    view.style.width = `${view.width / dpr}px`;
    view.style.height = `${view.height / dpr}px`;
    O = [Math.round(LEFT * dpr), Math.round(TOP * dpr)];
    drawn = '';
  }

  // On a ruler's handle: a 12px square whose centre runs from 6px in at either end (styles.css).
  function onHandle(ruler) {
    const r = ruler.getBoundingClientRect(), min = Number(ruler.min || 0), max = Number(ruler.max || 100);
    const centre = r.left + 6 + (r.width - 12) * ((ruler.valueAsNumber - min) / (max - min));
    return Math.abs(x - centre) <= 6 && y >= r.top + 6 && y <= r.top + 18;
  }

  // What the pointer is over: what the last move was over, or, held still, what is there now (a
  // section may have opened under it). Held still, it looks every 200 ms rather than every frame.
  function stateAt(now) {
    const went = moved;
    moved = false;
    if (went || !hit.el || now - hit.stamp > 200) {
      const el = (went && over) || document.elementFromPoint(x, y);
      const kind = el ? getComputedStyle(el).getPropertyValue('--pointer').trim() || 'rest' : 'rest';
      hit = { el, kind, stamp: now };
    }
    const { el, kind } = hit;
    return kind === 'click' && el && el.classList.contains('ruler') && onHandle(el) ? 'grab' : kind;
  }

  const ease = t => 1 - (1 - t) ** 3;
  // Move a value towards `to` over `dur` ms, eased out; true while it is still moving.
  function step(a, to, dur, now) {
    if (to !== a.to) { a.from = a.v; a.to = to; a.t0 = now; }
    if (!a.t0) return false;
    const p = dur <= 0 ? 1 : Math.min(1, (now - a.t0) / dur);
    a.v = a.from + (a.to - a.from) * ease(p);
    if (p >= 1) { a.v = a.to; a.t0 = 0; }
    return p < 1;
  }

  function draw(now) {
    frame = 0;
    if (!on) return;
    if ((devicePixelRatio || 1) !== dpr) fit();
    const state = stateAt(now);
    const locked = state === 'click' || state === 'press';
    let busy = step(anim.lock, locked ? 1 : 0, still.matches ? 0 : T_LOCK, now);
    busy = step(anim.press, state === 'press' ? 1 : 0, still.matches ? 0 : T_PRESS, now) || busy;
    if (anim.flash.t0) {
      const p = (now - anim.flash.t0) / T_FLASH;
      if (p >= 1) { anim.flash.v = 0; anim.flash.t0 = 0; }
      else { anim.flash.v = p < 0.35 ? 1 : 1 - ease((p - 0.35) / 0.65); busy = true; }
    }
    const f = still.matches ? 0 : Math.floor(now / TICK) % FRAMES;
    const pic = picture(state, f);
    const glyph = GLYPH[state] || 'corner';
    const [px, py] = AT[glyph];
    const key = `${state}|${f}|${Math.round(anim.lock.v * 60)}|${Math.round(anim.press.v * 60)}|${Math.round(anim.flash.v * 60)}|${glyph}`;
    if (key !== drawn) {
      drawn = key;
      g.clearRect(0, 0, view.width, view.height);
      g.imageSmoothingEnabled = false;
      g.drawImage(pic, O[0] + Math.round(px * dpr), O[1] + Math.round(py * dpr), Math.round(PIC_W * dpr), Math.round(PIC_H * dpr));
      g.save();
      g.translate(O[0], O[1]);
      const box = [px + BORDER * SQUARE, py + BORDER * SQUARE, px + (BORDER + W) * SQUARE, py + (BORDER + H) * SQUARE];
      GLYPHS[glyph](g, dpr, state, box, anim.lock.v, anim.press.v, anim.flash.v);
      g.restore();
      figX = px + PIC_W / 2;
      figY = py + PIC_H / 2;
    }
    const at = `translate(${(Math.round(x * dpr) - O[0]) / dpr}px, ${(Math.round(y * dpr) - O[1]) / dpr}px)`;
    if (at !== placed) view.style.transform = placed = at;
    if (busy) soon();
  }
  const soon = () => { frame ||= requestAnimationFrame(draw); };
  // the next frame of the loop, and the one after, while it is shown
  function loop() {
    clearTimeout(timer);
    if (on && !still.matches) timer = setTimeout(() => { soon(); loop(); }, TICK - (performance.now() % TICK) + 1);
  }

  function show() {
    if (on) return;
    on = true;
    view.hidden = false;
    root.classList.add('pointer-drawn');
    soon();
    loop();
  }
  function hide(system) {
    on = false;
    view.hidden = true;
    clearTimeout(timer);
    if (system) root.classList.remove('pointer-drawn');
  }
  function follow(event) {
    if (event.pointerType !== 'mouse' || forced.matches) { hide(true); return; }
    x = event.clientX;
    y = event.clientY;
    over = event.target instanceof Element ? event.target : null;
    inside = true;
    moved = true;
    show();
    if (event.type === 'pointerup' && event.button === 0 && !still.matches) {
      const state = stateAt(performance.now());
      if (state === 'click' || state === 'press') { anim.flash.v = 1; anim.flash.t0 = performance.now(); }
    }
    soon();
  }
  for (const type of ['pointermove', 'pointerdown', 'pointerup']) addEventListener(type, follow, { capture: true, passive: true });
  // back into the page without a move (out of the window, back from another tab, after a drag)
  addEventListener('pointerover', event => {
    if (event.pointerType !== 'mouse' || forced.matches || on) return;
    x = event.clientX;
    y = event.clientY;
    over = event.target instanceof Element ? event.target : null;
    inside = true;
    moved = true;
    show();
  }, { capture: true, passive: true });
  document.addEventListener('pointerout', event => {
    if (!event.relatedTarget && event.pointerType === 'mouse') { inside = false; hide(false); }
  });
  // a picture dragged away: the system's drag pointer shows until the drag is done
  addEventListener('dragstart', () => hide(true), true);
  addEventListener('dragend', () => { if (inside) show(); }, true);
  document.addEventListener('visibilitychange', () => { if (document.hidden) hide(false); else if (inside) show(); });
  forced.addEventListener('change', () => { if (forced.matches) hide(true); });
  still.addEventListener('change', () => { loop(); soon(); });
  addEventListener('resize', () => { fit(); soon(); });
  fit();

  // The middle of the two of them from the point (CSS px) while the pointer is drawn; null while not.
  function figure() {
    return on ? [figX, figY] : null;
  }
  return { figure };
})();
