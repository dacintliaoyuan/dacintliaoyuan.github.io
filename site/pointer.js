// The mouse pointer (CONTEXT: 鼠标指针): Shimamura and Adachi in their summer chibi (the official
// picture put into squares, 46 across, the eyes and mouths drawn again by hand) beside a viewfinder
// corner in the HUD's own hand, white on a faint dark edge, the point at its corner. It is drawn on a
// canvas over the page that follows the mouse, and the system's pointer is hidden meanwhile
// (html.pointer-drawn, styles.css). The two of them bob in turn and blink, two seconds round. Over what
// can be clicked the corner turns blue and three more close round the two of them (focus locked;
// Shimamura smiles, Adachi blushes), drawn in while it is pressed; over what says something when
// pointed at, a blue question tile sits by the corner. Written text, the divider and a ruler's handle
// have an I-beam, arrows and grip chevrons in the same hand instead, the two beside them.
// What it is over comes from styles.css: each rule that sets a cursor sets --pointer with it, so the two
// cannot disagree (a ruler's handle, a pseudo-element, is found by where it is). Only for a mouse: a
// pen, a finger and forced colours keep the system's pointers (styles.css). With less motion asked for,
// the two hold still. main.js asks where the two of them are, for the fill's soft light (figure).
window.HOME_POINTER = (() => {
  'use strict';

  const COLOURS = {
    a: '#fff0e0', b: '#606a90', c: '#000000', d: '#f9bc9f', e: '#617aa4', f: '#9f6a64', g: '#bf8c83',
    h: '#535679', i: '#384367', j: '#fdd7c7', k: '#b17c75', l: '#855f5c', m: '#e4d0c6', n: '#a4b9df',
    o: '#e4a599', p: '#8296bf', q: '#020100', r: '#0d0808', s: '#22171a', v: '#eb7974', x: '#a0cc9f',
    z: '#c28e86', E: '#bc6a68', G: '#f9d6cd', M: '#c45c60', R: '#60222a', S: '#9e3e44', T: '#d4766e',
    U: '#f2b296', V: '#123a4e', W: '#ffffff', X: '#247680', Y: '#58a8a0', Z: '#acdeac',
  };
  const PICTURE = [
    'ccccc.ccaaaaaaaaamdcc..........ccccc..........',
    'dddvvcmmmmmaaaaaaddddc.....cccceeeeeccc.......',
    'dddddaaammmmmmmaadddddccccceeeeeeeeeeecc......',
    'dddddddaaammmmmmmxxddddoonneeeeeeeeeebbnc.....',
    'dddddcfffaaammmmmmxsddoonneeeeeeeeeeebbnec....',
    'ddddcfffffaaaammccddddrniieeeeeeheennhbbbcc...',
    'dddclfffffffaaaaccddddniieeeeeeeehnnnbbbbbc...',
    'ddcllffffffffaaajddddrnineeeeennnphbbbbbbbbc..',
    'ddlllffffffffffjjddddeennnnnnnnnpbbbbbbbbbbc..',
    'ddllllfffffffffffddddeeeeeinneebbbbbbbbbbbbhc.',
    'dllllllffffffmfffldddebbbbibbbbbbbbbbbbbhhhhc.',
    'dlllllljjrjodmojjjjjbbbbbijbbbbbbbbbbbbhhhhhc.',
    'dllggoojjjjddadjjjoobbbbbijbbbbibbbbbbhhihhic.',
    'lggsgggooooaaaaooooobbbbbjjbbbbjbbbbbhhhriiiic',
    'ggsgggdccoaaaaaaooggbbbbbjaabbbiaaibbhhhiiiiic',
    'gggsaaaaaaaaaaaaagggbbbbbiaabbjiaaabhhhiiiiiic',
    'ggzcccccaaacccccaggghhhqcccccaqacccccahiaiiiic',
    'ggzcRWRRaaaWRRRcaggghhhocVWVVaaaWVVVcahiaaiiic',
    'ggzaRRSRaaaRSRRaagggghqoaVVXVaaaVXVVaahhariiic',
    'ggzaSUUSaaaSUUSaaggggrrraXZZXaaaXZZXaahhqpiiic',
    'ggzaaTTaaaaaTTaaaagggghqaaYYaaaaaYYaaahhppiiic',
    'gggGGGaaaaaaaGGGaagggrhraaaaaaaaaaaaalhhppiiic',
    'gggsaaaaaaaaaaaaaakkkshraGGGaaaaaaGGGlhhppiiic',
    'gggsaaaaaMMaaaaaakkkkshhqaaaaaEEaaaaalhhcpirhc',
    'ckkkaaaaavvaaaaakkkkkkbbqaaaaavvaaaaalhiqcscbc',
    'ckkckkavqaaaaaaffkkkkfbbbpppaaaaaapppicqc.c.c.',
    'ckkckkvvqaaaooffffkkkfsbbqspspcaaacccqcc......',
  ];
  const W = PICTURE[0].length, H = PICTURE.length;
  // Where Adachi begins on each row: she is in front, a layer of her own (on the two top rows, from the
  // gap between the hat and her head). Shimamura's runs on two squares under her, so that neither leaves
  // a hole when the other bobs.
  const SPLIT = [31, 27, 22, 25, 24, 22, 22, 21, 21, 21, 21, 20, 20, 20, 20, 20, 20, 20, 21, 21, 22, 21, 21, 21, 22, 22, 22];
  const SKIN = 'a';
  const EYES = { shima: [[3, 16], [11, 16]], adachi: [[24, 16], [32, 16]] };   // each eye's top left
  // eyes other than open, as the one on the viewer's left (the other is its mirror): a line ('c') on skin
  const LIDS = {
    shut: ['.....', '.....', '.cccc', 'c....', '.....'],
    happy: ['.....', '.ccc.', 'c...c', '.....', '.....'],
    squint: ['.....', 'cc...', '..cc.', 'cc...', '.....'],
  };
  const SHY = '#ecb1a5';   // Adachi's blush (G), deeper
  // [Shimamura's eyes, Adachi's, whether Adachi blushes deeper] where they are not both open and calm
  const FACES = {
    click: ['happy', 'open', true], press: ['happy', 'squint', true], grabbing: ['squint', 'squint', true],
  };
  const TICK = 1000 / 12, FRAMES = 24;   // the loop: 24 frames, 2 s
  const SQUARE = 1.3;   // CSS px a square, about (a whole number of device px, so they stay sharp)
  const PAD = 18;       // CSS px of canvas up and left of the point
  const ACCENT = '#1c8ad7', WHITE = '#fff', EDGE = 'rgba(11, 21, 38, 0.72)';
  // the glyph for each state, and where the picture's top left goes from the point (CSS px)
  const GLYPH = { text: 'text', resize: 'resize', grab: 'grab', grabbing: 'grab' };
  const AT = { corner: [7, 7], text: [7, 12], resize: [6, 10], grab: [7, 10] };

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
    const rows = PICTURE.map((line, y) => {
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

  // The picture at a frame, a square to a pixel with a clear square round it to bob into (kept: there
  // are a few dozen different ones).
  const pictures = new Map();
  function picture(state, f) {
    const [s, a] = motion(state, f), [shimaEyes, adachiEyes, shy] = FACES[state] || ['open', 'open', false];
    const eyes = [s[2] && shimaEyes === 'open' ? 'shut' : shimaEyes, a[2] && adachiEyes === 'open' ? 'shut' : adachiEyes];
    const key = [...s, ...a, ...eyes, shy].join();
    let canvas = pictures.get(key);
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.width = W + 2;
      canvas.height = H + 2;
      const g = canvas.getContext('2d');
      const paint = (rows, colours, dx, dy) => rows.forEach((row, y) => row.forEach((ch, x) => {
        if (ch === '.') return;
        g.fillStyle = colours[ch];
        g.fillRect(1 + dx + x, 1 + dy + y, 1, 1);
      }));
      paint(layer('shima', eyes[0]), COLOURS, s[0], s[1]);
      paint(layer('adachi', eyes[1]), shy ? { ...COLOURS, G: SHY } : COLOURS, a[0], a[1]);
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
  // a viewfinder corner, its outer corner at (x, y) and its arms going (sx, sy): (1, 1) right and down
  function corner(g, s, x, y, sx, sy, arm, t, fill) {
    rects(g, s, [[arm, t], [t, arm]].map(([w, h]) => [sx > 0 ? x : x - w, sy > 0 ? y : y - h, w, h]), fill);
  }
  // box: the picture's, [left, top, right, bottom] from the point
  const GLYPHS = {
    corner(g, s, state, box) {
      const locked = state === 'click' || state === 'press', pressed = state === 'press';
      const arm = pressed ? 14 : 19, inset = pressed ? 2 : 0, fill = locked ? ACCENT : WHITE;
      corner(g, s, inset, inset, 1, 1, arm, 3.5, fill);
      if (locked) {   // the other three, round the two of them
        const [, top, right, bottom] = box, x1 = right + 3 - inset, y0 = top - 1 + inset, y1 = bottom + 3 - inset;
        corner(g, s, x1, y0, -1, 1, arm - 6, 3, fill);
        corner(g, s, box[0] - 1 + inset, y1, 1, -1, arm - 6, 3, fill);
        corner(g, s, x1, y1, -1, -1, arm - 6, 3, fill);
      }
      if (state === 'help') {   // a question tile like the index's squares
        shape(g, s, c => c.roundRect(23, -5, 12, 12, 3), ACCENT, 0.9);
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

  // dpr: device px a CSS px; k: device px a square; O: device px up and left of the point
  let dpr = 0, k = 1, O = 0;
  let on = false, x = 0, y = 0, over = null, moved = false, drawn = null, placed = '', frame = 0, timer = 0;

  function fit() {
    dpr = devicePixelRatio || 1;
    k = Math.max(1, Math.round(dpr * SQUARE));
    O = Math.round(PAD * dpr);
    view.width = O + Math.round(12 * dpr) + (W + 2) * k + Math.round(10 * dpr);
    view.height = O + Math.round(14 * dpr) + (H + 2) * k + Math.round(10 * dpr);
    view.style.width = `${view.width / dpr}px`;
    view.style.height = `${view.height / dpr}px`;
    drawn = null;
  }

  // On a ruler's handle: a 12px square whose centre runs from 6px in at either end (styles.css).
  function onHandle(ruler) {
    const r = ruler.getBoundingClientRect(), min = Number(ruler.min || 0), max = Number(ruler.max || 100);
    const centre = r.left + 6 + (r.width - 12) * ((ruler.valueAsNumber - min) / (max - min));
    return Math.abs(x - centre) <= 6 && y >= r.top + 6 && y <= r.top + 18;
  }

  // What the pointer is over: what the last move was over, or, held still, what is there now (a
  // section may have opened under it).
  function stateAt() {
    if (!moved) over = document.elementFromPoint(x, y);
    moved = false;
    if (!over) return 'rest';
    const kind = getComputedStyle(over).getPropertyValue('--pointer').trim() || 'rest';
    return kind === 'click' && over.classList.contains('ruler') && onHandle(over) ? 'grab' : kind;
  }

  function draw() {
    frame = 0;
    if (!on) return;
    if ((devicePixelRatio || 1) !== dpr) fit();
    const state = stateAt(), pic = picture(state, still.matches ? 0 : Math.floor(performance.now() / TICK) % FRAMES);
    if (!drawn || drawn[0] !== state || drawn[1] !== pic) {
      drawn = [state, pic];
      const glyph = GLYPH[state] || 'corner', [px, py] = AT[glyph];
      g.clearRect(0, 0, view.width, view.height);
      g.imageSmoothingEnabled = false;
      g.drawImage(pic, O + Math.round(px * dpr), O + Math.round(py * dpr), pic.width * k, pic.height * k);
      g.save();
      g.translate(O, O);
      GLYPHS[glyph](g, dpr, state, [px, py, px + (pic.width * k) / dpr, py + (pic.height * k) / dpr]);
      g.restore();
    }
    const at = `translate(${(Math.round(x * dpr) - O) / dpr}px, ${(Math.round(y * dpr) - O) / dpr}px)`;
    if (at !== placed) view.style.transform = placed = at;
  }
  const soon = () => { frame ||= requestAnimationFrame(draw); };
  // the next frame of the loop, and the one after, while it is shown
  function loop() {
    clearTimeout(timer);
    if (on && !still.matches) timer = setTimeout(() => { soon(); loop(); }, TICK - (performance.now() % TICK) + 1);
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
    moved = true;
    if (!on) {
      on = true;
      view.hidden = false;
      root.classList.add('pointer-drawn');
      loop();
    }
    soon();
  }
  for (const type of ['pointermove', 'pointerdown', 'pointerup']) addEventListener(type, follow, { capture: true, passive: true });
  document.addEventListener('pointerout', event => { if (!event.relatedTarget && event.pointerType === 'mouse') hide(false); });
  // a picture dragged away: the system's drag pointer shows until the mouse moves after the drop
  addEventListener('dragstart', () => hide(false), true);
  document.addEventListener('visibilitychange', () => { if (document.hidden) hide(false); });
  forced.addEventListener('change', () => { if (forced.matches) hide(true); });
  still.addEventListener('change', () => { loop(); soon(); });
  fit();

  // The middle of the two of them from the point (CSS px) while the pointer is drawn; null while not.
  function figure() {
    if (!on) return null;
    const [px, py] = AT[GLYPH[drawn?.[0]] || 'corner'];
    return [px + (W + 2) * k / dpr / 2, py + (H + 2) * k / dpr / 2];
  }
  return { figure };
})();
