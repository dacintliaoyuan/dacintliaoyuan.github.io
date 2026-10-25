// Opening of dacint_liaoyuan's homepage, shot like a camera on graph paper.
//   1. Construction lines are drawn on the paper while viewfinder marks come up round the screen
//      edge. A flock of distant bluebird silhouettes darts in and tracking squares lock on.
//   2. The viewfinder closes onto a window, the shutter fires and the sky develops square by square;
//      ornaments are drawn in the paper margins.
//   3. The birds fly off and break into pixels. A strip of semiconductor equations, there only as
//      decoration, is drawn across the sky; the light floods in and washes it out, and sakura
//      petals ride in on it.
//   4. HELLO is built out of hairlines and rings in the open sky while the petals slow down;
//      butterflies and blue-bird feathers are drawn on the paper with it and come alive, calmly
//      (a few wingbeats, then a glide; a falling leaf's swing). HELLO blows away as dust, and the
//      ring it sends out blows them away (the pinned specimen only trembles) and nudges the petals.
//   5. The camera drops fast. The sky, its clouds and the petals run up the window, and the sky comes
//      in like the tide on a beach, in cloud and blue sky rather than water, the window's top edge
//      being the shore: line after line forms at the bottom edge and runs up towards the top edge in
//      layers, the hardest throwing up spray on it, and the deck of cloud lying on the picture comes
//      in from the bottom as the high tide, pushing them all up into the edge. The camera catches the
//      two characters only just before landing, with a hand-held jolt.
//   6. The window opens out to the whole screen, focus is pulled onto the pair and the name comes up
//      over the picture; the ornament is drawn on the fill round it in the order the light goes, and
//      blue birds take to the orbit round the picture.
// Wherever the window is, the picture is all of it in there, as big as it fits, and the rest of the
// window is a wash of its own colours (the fill).
// The sky in the window follows the time of day (time.js; CONTEXT: 时段), at dusk with the evening star
// and at night with stars and today's moon, its clouds and its surf with it, until the camera goes into
// the picture's own time at the cloud sea; the paper follows it too (styles.css).
// The final screen is the opening screen (00) of a section index on the right edge: opening a
// section docks the window aside, framed afresh, and the section's panel fills the paper beside it.
// On a wide screen the divider between them sets how much of the width the picture keeps, and the
// picture can be folded away behind the section: it takes the whole screen again and the section
// comes back in a wide column across the middle, laid out across it and lettered in white on a
// frosted block straight on the picture (it covers the picture on purpose; docked, the two are side
// by side). The
// index's last square opens the settings (04): how strongly that block and the picture itself are
// blurred, which picture is shown, and a map of the keys. Single keys work the page (none with Ctrl,
// Alt or Cmd, which stay the browser's).
// Only the name, HELLO and the index (its titles and chapter numbers) are lettered: the
// margins hold ornaments, never text or pictures, and the final screen has no equations.
// render(t) is a pure function of time (and of how far the window is docked, folded away and how
// wide it is docked): skipping is render(END), and a replay restarts the clock with another picture.
(() => {
  'use strict';

  // Beats of the opening (ms). Tuning the feel is mostly a matter of these numbers.
  const BEAT = {
    snap: 420, snapLen: 260,      // the flock darts in from the left and stops dead
    track: 760,                   // tracking squares lock on, each with a ping ring and a callout
    frame: 1500,                  // construction lines clear, the viewfinder closes onto the window...
    shutter: 1600,                // ...the shutter fires...
    reveal: 1660,                 // ...and the sky develops square by square
    leave: 2300,                  // the birds fly off up and to the right and break into pixels
    strip: 2450,                  // the equation strip is drawn across the sky...
    flood: 3500,                  // ...and the light floods in and washes it out
    hello: 3950, dust: 5050,      // HELLO is built in the open sky, then blows away as dust
    fall: 5250,                   // the camera drops fast, the sky coming up the window like the tide...
    land: 6300,                   // ...and lands on the pair with a hand-held jolt
    open: 6340, openLen: 700,     // the window opens out to the whole screen, the picture with it
    grid: 6640,                   // the fill's grid is drawn out from the picture's edges
    af: 6600, focus: 6800, focusLen: 700,
    name: 7450, button: 8200,
    afOut: 8150,                  // the focus brackets leave; the viewfinder marks stay
  };
  const END = 9300;   // (the ornament on the fill comes in last, MEET)
  const PUSH = 1.04;          // push-in scale reached with the focus pull
  const BREATH = 1.025;       // the idle breathing's push-in at its deepest (styles.css takes it as --breath)
  const FADE_BAND = 0.32;     // window-height share over which the picture's top fades into the sky
  const OVERSHOOT = 0.1;      // window-height share of ground below the window, for the landing to overshoot into
  const SKY_SPAN = 2.2;       // window-heights of sky above the picture, so HELLO hangs in open sky
  const DRIFT = 0.16;         // share of the way down covered while HELLO is built (still all sky)
  // The window's sky by the time of day (time.js: sky, 0 by day, 1 at dusk, 2 at night), as stops of
  // [window-heights down from the top of the sky, colour]: by day the Liz palette; at dusk a deep blue
  // going over to rose and apricot low down; at night deep blues. Between two of them it is the two
  // mixed. Its bottom is the picture's own sky colour, whatever the time.
  const SKIES = [
    [[0.1, '#8fd0f0'], [1.75, '#bfe3f4']],
    [[0.1, '#33437c'], [0.85, '#6f63a3'], [1.45, '#d996aa'], [1.95, '#f4bd8f']],
    [[0.1, '#040a1e'], [0.9, '#0a1a40'], [1.8, '#173263']],
  ];
  const PERIODS = ['day', 'dusk', 'night'];   // what pictures are tagged with, as the sky's phases (0 to 2)
  // How the clouds are tinted by the time of day, as CSS filter functions in this order: brightness,
  // sepia, hue-rotate (degrees) and saturate; by day as they are, at dusk warmer, at night a moonlit
  // steel blue (fitted to the night cloud the sea over a night picture had before there was a night
  // sky); between two of them the two mixed. The cloud sea and the surf's puffs, made from the same
  // photos, are tinted the same way.
  const TINTS = [[1, 0, 0, 1], [1.02, 0.32, -46, 1.9], [0.48, 1, -178, 1.9]];
  // The night sky in the window (window shares): a few bright stars with a small glint [x, y, size px],
  // the moon (x, y and its radius as a share of the window's height, at least `least` px) and at dusk
  // the evening star [x, y, size px]. The rest of the stars are scattered over it, one to `per` px²,
  // thinning out towards the horizon.
  const STARS = {
    per: 3800, bright: [[0.12, 0.16, 7], [0.36, 0.08, 5], [0.58, 0.3, 6], [0.9, 0.52, 5], [0.24, 0.44, 4]],
    moon: [0.8, 0.2, 0.026], least: 14, evening: [0.6, 0.1, 6],
  };

  // Cloud layers of the opening sky inside the window: width (window-width share), left and top
  // from the top of the sky (window shares), parallax factor and opacity. The near bank sits low,
  // so it sweeps past in the fall.
  const CLOUDS = {
    landscape: { far: [1.15, -0.08, 0.0, 0.55, 0.8], tower: [0.55, -0.16, 0.5, 0.8, 0.9],
                 mid: [0.62, 0.5, 0.42, 0.9, 0.9], near: [1.15, -0.08, 1.65, 1.35, 0.95] },
    portrait: { far: [1.9, -0.45, 0.0, 0.55, 0.8], tower: [1.15, -0.38, 0.5, 0.8, 0.9],
                mid: [1.2, 0.25, 0.42, 0.9, 0.9], near: [2.4, -0.7, 1.65, 1.35, 0.95] },
  };
  // The flock around the window's centre, using distant bluebird silhouettes: a near row above a far
  // row. [row (0 near, 1 far), x and y offset (window-size shares), size, wing pose (0 raised,
  // 1 calm glide), tilt in degrees (negative: nose up)]. Poses stay frozen: the camera holds the frame.
  const FLOCK = [
    [0, -0.26, 0.02, 1.0, 0.15, -14], [0, -0.13, -0.04, 1.08, 0.55, -10], [0, 0.0, 0.0, 1.0, 0.1, -16],
    [0, 0.13, -0.07, 1.12, 0.7, -9], [0, 0.26, -0.03, 0.98, 0.3, -13],
    [1, -0.2, 0.16, 0.66, 0.85, -8], [1, -0.07, 0.13, 0.7, 0.2, -12], [1, 0.06, 0.18, 0.62, 0.6, -10],
    [1, 0.19, 0.12, 0.68, 0.4, -14],
  ];
  const TRACKED = [1, 3, 6, 8];   // birds that get a tracking square, in locking order
  const PIXELS = 12;              // squares a bird breaks into when it leaves
  const STREAKS = 16;             // speed lines inside the window during the fall
  const RINGS = 3;                // rings bursting behind HELLO
  const DUST = 1400;              // most specks HELLO breaks into
  const PETALS = 60;              // sakura petals riding in on the light
  // Where the surf's puffs take their texture from in the cloud photos: layer, centre (shares of its
  // width and height) and radius (share of its width), each well inside a cloud.
  const PUFFS = [
    ['tower', 0.361, 0.151, 0.055], ['tower', 0.343, 0.258, 0.055], ['tower', 0.253, 0.408, 0.055],
    ['tower', 0.235, 0.687, 0.055], ['mid', 0.676, 0.384, 0.05], ['mid', 0.775, 0.169, 0.05], ['mid', 0.577, 0.408, 0.05],
  ];
  const SEA = 0.6;                // the cloud sea's depth over the picture, as a window-height share
  const FLAP_HZ = 1.5;            // a butterfly's wingbeats a second, a few at a time between glides
  const SWING = 4;                // seconds for a feather's swing there and back, like a falling leaf
  // Viewfinder marks: the paper's ink and this pale blue on the paper, white over the opened picture (RGB).
  const TONE = { pale: [124, 191, 235] };
  // Ornament clusters in the margins, after the blue-sky film, in units round the middle square:
  // offset outline squares [left, top, side], long diagonals [x1, y1, x2, y2], cross marks [x, y]
  // and pixel squares [left, top, side] breaking away to the right.
  const CLUSTER = {
    squares: [[-1, -1, 2], [-1.6, -1.6, 1], [0.5, 0.5, 1.4]],
    diagonals: [[-1.8, -1.8, -0.6, -0.6], [1.25, 1.25, 2.6, 2.6]],
    crosses: [[-1.95, -1.05], [-1.1, 1.4], [1.5, -0.95]],
    pixels: [[0.55, -0.8, 0.28], [0.9, -0.55, 0.2], [1.15, -0.3, 0.13], [0.62, -0.38, 0.16], [1.32, -0.02, 0.09],
      [0.86, -0.08, 0.12], [1.5, 0.22, 0.06], [0.3, -1.05, 0.12], [1.06, 0.3, 0.08]],
  };
  // Butterflies and blue-bird feathers on the paper, in unit shapes: a butterfly seen from above
  // (wingspan about 2, head towards -y) and a flight feather about 2 long (tip towards -y), its vane
  // narrower on the leading edge and notched where the barbs split.
  const BUTTERFLY = {
    // A light swallowtail-like contour: broad forewing, gently scalloped hindwing and small tail.
    fore: 'M0.04 -0.18C0.29 -0.65 0.77 -0.88 0.98 -0.67C1.11 -0.49 0.94 -0.19 0.73 -0.09C0.48 0.04 0.20 0.01 0.04 -0.02Z',
    hind: 'M0.05 0.01C0.30 -0.03 0.66 0.13 0.75 0.37C0.79 0.51 0.67 0.67 0.54 0.70L0.60 0.94L0.43 0.74C0.19 0.70 0.06 0.42 0.05 0.01Z',
    antenna: 'M-0.02 -0.44C-0.06 -0.64 -0.15 -0.76 -0.22 -0.81',
    vein: 'M0.10 -0.11Q0.42 -0.43 0.84 -0.61M0.13 0.06Q0.45 0.33 0.62 0.48',
  };
  // The pinned specimen's wings are the Lorenz attractor (sigma 10, rho 28, beta 8/3), the butterfly
  // of the butterfly effect, seen along its two lobes: (x + y) / sqrt 2 across and z up (squashed to
  // 0.95), in its own units round the middle of its two fixed points, which sit `wing` either side of
  // it at z = 27. The orbit is followed for `span` time units in RK4 steps of `step` from `from`, a
  // point just under that middle where it crosses into a wing and then switches within a loop or two.
  const LORENZ = { from: [-1.332, 1.4, 24.525], span: 20, step: 0.005, wing: 12 };
  // Two gently asymmetric feather silhouettes, with a curved quill and sparse down.
  const FEATHER = {
    vane: 'M0 -1C0.12 -0.91 0.28 -0.67 0.26 -0.40C0.25 -0.19 0.24 0.10 0.16 0.31C0.10 0.47 0.03 0.58 -0.02 0.65C-0.16 0.51 -0.23 0.29 -0.20 0.08C-0.22 -0.15 -0.14 -0.51 -0.09 -0.74C-0.05 -0.89 -0.02 -0.96 0 -1Z',
    shaft: 'M0.01 0.98C-0.02 0.48 0.10 -0.18 0 -0.97',
    down: 'M-0.02 0.64Q-0.12 0.73 -0.19 0.81M-0.01 0.70Q0.08 0.78 0.13 0.85',
  };
  const FEATHER_WIDTH = 1.2;
  // A sakura petal about 2 long: the base towards +y, the notched tip towards -y.
  const PETAL = new Path2D('M0 1C-0.55 0.62 -0.74 -0.16 -0.42 -0.86L0 -0.62L0.42 -0.86C0.74 -0.16 0.55 0.62 0 1Z');
  const GUST_LEN = 700;   // the ring HELLO sends out as it breaks up, sweeping past the screen edges
  // Sections in index order ('home' is the opening screen, 00, and 'settings' always the last; the
  // digit keys follow this order). The opening plays once per visit.
  const TABS = ['home', 'about', 'projects', 'contact', 'settings'];
  const SEEN_KEY = 'home:opening-seen';   // in sessionStorage
  const FILL_KEY = 'home:fill';   // the fill's mean colour, for a refresh to wait on (index.html)
  // The picture's share of the screen width while docked aside for a section (wide screens): 54%
  // unless the divider is dragged, anywhere from 30% to 70% as long as the panel keeps `pane` px; the
  // arrow keys move it by `step`. Dragged more than `snap` px past the narrowest and let go, the
  // picture folds away.
  const SPLIT = { normal: 0.54, min: 0.3, max: 0.7, pane: 380, step: 0.02, snap: 12 };
  const FOLD_MS = 500;   // folding the picture away behind a section, or bringing it back aside
  const FOLD_FADE = 0.35;   // the share of a fold over which the section fades out, and again in at its new place
  // The picture folded away behind a section is blurred as much as the visitor sets in the settings
  // (0 to 1, none by default) up to `max` px, pushed in a little (a share per px) to keep the blur's
  // soft edge off the screen. (The frosted block behind the section's text is in styles.css.)
  const PICTURE_BLUR = { max: 20, zoom: 0.003 };
  // The fill round the picture: its thumbnail painted `size` px across, blurred there by `blur` px
  // (stretched over a screen, some 7% of its height), its colours a little richer (`saturate`) and
  // dimmed (`dim`) so that the picture stands out against them.
  const WASH = { size: 64, blur: 3, saturate: 1.2, dim: 0.86 };
  // The picture's own deep colour, for the shades behind the white lettering over it (styles.css,
  // --tone): the mean of the lower part of its thumbnail (that share of its height), in the same hue,
  // a little more saturated (capped) and at this lightness.
  const DEEP = { part: 0.45, saturate: 1.2, saturation: 0.55, lightness: 0.17 };
  // The fill's grid (styles.css) is drawn out from the picture's edges over len ms, fading in over
  // soft px behind a brighter pen that glows pen px either side.
  const GRID = { len: 1000, soft: 28, pen: 42 };
  // The soft light on the opening screen's fill. It follows the pointer some 1/`follow` s behind it
  // (round the two of them beside a drawn one, pointer.js), comes up and dies away at `rise` and `fall`
  // a second, and is `reach` px in radius, a little bigger than they are: a warm `core`
  // in a cool `halo` half as wide again ([r, g, b, alpha at the heart]), which breathe at rest by
  // `breath` [share, rad/s]. Under it the grid's lines light up (`grid`, their alpha at its heart) and
  // stay lit a moment where it has been: every `trail.every` px it leaves a patch of `trail.size` its
  // radius and `trail.strength` as bright, fading in `trail.fade` s. Crossings shine past `pin` of its
  // light. The dust, a mote to `dust.area` px², wanders (`drift`, px/s a √s), rises (`rise`, px/s²),
  // settles (`calm`, a second) and is carried along by the light (`stir`). While the pointer is still
  // or off the fill, now and then (`pass.every`, ms) a weaker light (`pass.strength`) makes a pass of
  // its own `pass.length` ms long along a gentle curve `pass.path` px long.
  const SOFT_LIGHT = {
    reach: 80, follow: 10, rise: 4, fall: 1.4, breath: [0.04, 1.7],
    core: [255, 249, 236, 0.5], halo: [205, 228, 255, 0.25], grid: 0.7,
    trail: { every: 14, size: 0.8, strength: 0.55, fade: 0.5 }, pin: 0.45,
    dust: { area: 1800, drift: 6.7, rise: 3, calm: 1.5, stir: 0.9 },
    pass: { every: [4000, 7000], length: 2400, path: [200, 320], strength: 0.6 },
  };
  // The opening screen's ornament on the fill, after the 相遇主旨 (CONTEXT: 开场屏装饰, 大圆, 圆面, 成像面).
  // The moon (Shimamura) sits high in the left fill and the sakura (Adachi) low in the right one; rays
  // from the moon go in behind the picture, the lens they pass through, and come out on to her; a large
  // faint orbit runs round the picture through both, a new moon growing up it from the moon. On her side
  // the light lands on planes: a deep disc round her (rings, worlds and glints on it, a light clear spot
  // in the middle) over a light hatched image plane tucked in behind the picture's edge, a strip of
  // film. Blue birds glide
  // round the orbit. It is drawn only on a wide screen, beside a picture with `min` px of fill or more on
  // each side. Its lines are white on a dark fill and the picture's deep colour on a light one, going
  // over between the lumas `light` of what is under them, planes included. The planes' colours are the
  // fill's own on her side: the disc `deep` darker (OKLCH lightness, never under `floor`) and a little
  // richer, the image plane and the clear spot `lighter`. The disc is `disc.r` of the screen's height in
  // radius and keeps `disc.clear` of the grid's cells clear of the index (smaller where there is not the
  // room; where it would be less than `disc.least` times the clear spot, there is no ornament), the clear
  // spot `disc.spot`. On the disc, sized for a disc `disc.unit` px in radius: rings of its own, unequal
  // like orbits (`tracks`: radius as a share of the disc's, weight, and for an arc where it runs [from,
  // to], in degrees clockwise from the right), each with a world on it, a point `worlds` px in radius;
  // at its edge three fine lines close together, `rim` px in from it; and glints, like the starbursts
  // round lights at night ([angle, radius share, size px]): the big one on the side the light comes
  // from, the small ones somewhere between two angles for each picture. The image plane, sized for the
  // same disc: down its right edge a clear band `film.band` px wide punched with perforations (`hole`:
  // width, height and corner radius) every `pitch` px, `inset` px in from the edge and from `top` px down;
  // its hatching starts `top` px down as well and breaks between two frames about `gap` of the way down
  // from there to the disc, across the space between two perforations. Its entrance takes `len` ms from
  // `start`, in the order the light goes (drawMeetMarks). The birds sit evenly round the orbit some
  // `bird.step` degrees apart and `bird.off` px outside it, `bird.size` px long at its top and its bottom
  // (an orbit seen tilted), and glide round it clockwise at `bird.speed` degrees a second. After the
  // entrance the disc turns (`spin`, drawDisc): each world goes round its ring clockwise in `turn` s
  // (the outer ring's first), the arc or the dots of its ring with it, getting up to speed over `up` ms;
  // two worlds passing each other swell to `pass[0]` times their size and back in `pass[1]` ms; the
  // glints twinkle in turn, `twinkle.at` s into every `twinkle.every` s of turning, for `twinkle.len` ms.
  const MEET = {
    min: 300, start: 6900, len: 2400, light: [150, 180],
    disc: { r: 0.19, spot: 0.055, clear: 2, least: 2.5, unit: 205 }, deep: 0.17, floor: 0.38, lighter: 0.09,
    tracks: [[0.86, 'mid', 150, 352], [0.73, 'fine'], [0.6, 'dots'], [0.47, 'fine', 196, 468]], worlds: [2.2, 2.6, 1.8, 2.1],
    rim: [1.5, 5, 8.5], glints: { big: [236, 0.8, 23], small: [[[0, 70], 0.88, 10], [[280, 320], 0.68, 6]] },
    film: { band: 17, hole: [9, 6, 1.6], pitch: 15, inset: 4, top: 7, gap: 0.6 },
    bird: { count: 14, mobile: 8, off: 16, size: [8, 20], speed: 7 },
    spin: { turn: [120, 80, 55, 40], up: 2000, pass: [1.6, 800], twinkle: { at: [4, 10.5, 18.5], every: 21.5, len: 600 } },
  };
  // How far in from the right-hand meter's line the section index stands on a wide screen, for the
  // focus scale that takes the meter's place (drawScale).
  const INDEX_IN = 20;
  // The settings' starting values: the frosted block's strength and the picture's blur (0 to 1).
  const LOOKS = { glass: 0.5, blur: 0 };
  // Another picture put up from the settings: a rack focus, in ms from when the new picture is in
  // ([start, length] pairs). The picture on screen goes out of focus (by `blur` px) and melts away
  // over the new one, which comes into focus as far as its far layer goes (its background, or with a
  // picture focused whole, all of it still soft); then the focus moves on to its near layer, as at
  // the end of the opening. The viewfinder corners close in by `close` px while the lens works;
  // as it locks on they spring back out and light up blue a moment.
  const SWAP = {
    blur: 12, defocus: [0, 240], melt: [150, 300], refocus: [380, 380], pull: [720, 520],
    close: 8, closing: 300, lock: 1240, spring: 320, flash: 480,
  };
  // The visitor's choices, kept for the visit in sessionStorage: the split, whether the picture is
  // folded away, the blurs, the time of day and the picture chosen in the settings. (time.js reads the
  // time of day there too, for the first paint.)
  const PREFS_KEY = 'home:prefs';
  // How often the time of day is worked out again while the page is open (ms): the paper darkens a
  // little at a time through the hour round sunset.
  const TICK = 15000;
  // The settings' map of the keys: a 75% keyboard (ANSI), row by row, each key [legend, code (as in
  // KeyboardEvent.code), width in keys (one if not given)]; no legend is a gap.
  const BOARD = (() => {
    const run = (chars, prefix) => [...chars].map(c => [c, prefix + c]);
    const fn = Array.from({ length: 12 }, (_, i) => [`F${i + 1}`, `F${i + 1}`]);
    return [
      [['Esc', 'Escape'], ...fn, ['PrtSc', 'PrintScreen'], ['Del', 'Delete'], ['Home', 'Home']],
      [['`', 'Backquote'], ...run('1234567890', 'Digit'), ['-', 'Minus'], ['=', 'Equal'], ['Bksp', 'Backspace', 2], ['PgUp', 'PageUp']],
      [['Tab', 'Tab', 1.5], ...run('QWERTYUIOP', 'Key'), ['[', 'BracketLeft'], [']', 'BracketRight'], ['\\', 'Backslash', 1.5], ['PgDn', 'PageDown']],
      [['Caps', 'CapsLock', 1.75], ...run('ASDFGHJKL', 'Key'), [';', 'Semicolon'], ["'", 'Quote'], ['Enter', 'Enter', 2.25], ['End', 'End']],
      [['Shift', 'ShiftLeft', 2.25], ...run('ZXCVBNM', 'Key'), [',', 'Comma'], ['.', 'Period'], ['/', 'Slash'], ['Shift', 'ShiftRight', 1.75],
        ['\u2191', 'ArrowUp'], [null]],
      [['Ctrl', 'ControlLeft', 1.25], ['Win', 'MetaLeft', 1.25], ['Alt', 'AltLeft', 1.25], ['', 'Space', 6.25], ['Alt', 'AltRight'],
        ['Fn', 'Fn'], ['Ctrl', 'ControlRight'], ['\u2190', 'ArrowLeft'], ['\u2193', 'ArrowDown'], ['\u2192', 'ArrowRight']],
    ];
  })();
  // The page's own keys, lit on the map: [code, the key's name read out, what it does] (B's depends on
  // whether the picture is folded away; the scrolling keys are left out).
  const SHORTCUTS = [
    ['Escape', 'Esc', 'Back to home'], ['Digit0', '0', 'Home'], ['Digit1', '1', 'About'], ['Digit2', '2', 'Projects'],
    ['Digit3', '3', 'Contact'], ['Digit4', '4', 'Settings'], ['ArrowLeft', 'Left arrow', 'Previous section'],
    ['ArrowRight', 'Right arrow', 'Next section'], ['KeyB', 'B', null], ['KeyR', 'R', 'Replay intro'],
  ];
  const FOLD_SAYS = { folded: 'Picture back to the side', aside: 'Picture behind the text', both: 'Picture behind the text, or back to the side' };

  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const stage = $('#stage'), windowEl = $('#window');
  const world = $('.world'), sky = $('#sky'), starCanvas = $('#stars');
  const scene = $('#scene'), sceneFill = $('#sceneFill'), wash = $('#sceneFill canvas'), lightCanvas = $('#sceneLight');
  const meetSvg = $('#meet'), meetPlanes = $('#meetPlanes');
  const scenePic = $('#scenePic'), scenePush = $('#scenePush');
  const sceneFar = $('#sceneFar'), sceneNear = $('#sceneNear');
  const lens = $('#lens'), tiles = $('#tiles'), windowFlash = $('#windowFlash'), glow = $('#glow');
  const surfCanvas = $('#surf'), seaCanvas = $('#sea'), petalCanvas = $('#petals'), dustCanvas = $('#dust');
  const strip = $('#strip'), stripItems = $$('.strip math, .strip .tail');
  const guides = $('#guides'), flock = $('#flock'), helloSvg = $('#hello'), shutter = $('#shutter');
  const hud = $('#hud'), ruler = $('#ruler'), rec = $('.hud .rec');
  const meters = $('#meters'), meterTicks = $('#meterTicks'), meterTicksRight = $('#meterTicksRight'), meterLevel = $('#meterLevel');
  const corners = $$('.hud .corner'), marks = $$('.hud .marks i'), dashes = $$('.hud .dashes i');
  const nameEl = $('.name');
  const deco = Object.fromEntries($$('.deco [data-part]').map(el => [el.dataset.part, el]));
  const replayButton = $('#replay');
  const identity = $('#identity'), indexNav = $('#index'), indexLinks = $$('#index a'), brackets = $('#index .brackets');
  const indexShade = $('#indexShade'), panel = $('#panel'), panes = $$('.pane'), divider = $('#divider');
  const sliders = { glass: $('#glass'), blur: $('#blur') }, picks = $('#picks'), times = $('#times'), timeNow = $('#timeNow');
  const mail = $('#mail'), mailSaid = $('#mailSaid');
  const kb = $('#kb'), kbSay = $('#kbSay'), kbList = $('#kbList'), keyEls = new Map();   // the keyboard map's keys by code
  const clouds = Object.fromEntries($$('.cloud').map(el => [el.dataset.sky, el]));
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  // The page's own scrollbars (makeScrollbar): the panel's, and the settings' pictures' for when they
  // scroll on their own (spread across the middle of the screen; white there, like the lettering), kept
  // down their right edge (the bar is 12px wide, styles.css).
  const panelBar = makeScrollbar(panel, panes);
  const picksBar = makeScrollbar(picks, [], bar => {
    bar.style.left = `${picks.offsetLeft + picks.offsetWidth - 12}px`;
    bar.style.top = `${picks.offsetTop}px`;
    bar.style.height = `${picks.offsetHeight}px`;
  });
  picksBar.bar.classList.add('over');
  // The time of day (time.js), or where that could not be had, always day.
  const clock = window.HOME_TIME || {
    MODES: ['auto'], paper() {},
    at: () => ({ mode: 'auto', period: 'day', real: 'day', sky: 0, dark: 0, light: 0, sun: {}, moon: { lit: 0, right: true } }),
  };
  // The drawn pointer (pointer.js): where the two of them are beside it, or where that could not be had,
  // nowhere (the soft light then follows the point itself).
  const drawnPointer = window.HOME_POINTER || { figure: () => null };
  const SVG_NS = 'http://www.w3.org/2000/svg';
  stage.style.setProperty('--breath', String(BREATH));   // the idle breathing's depth (styles.css)

  const DEG = Math.PI / 180;
  const clamp01 = v => Math.min(1, Math.max(0, v));
  const seg = (t, start, length) => clamp01((t - start) / length);
  const smooth = (a, b, x) => { const p = clamp01((x - a) / (b - a)); return p * p * (3 - 2 * p); };
  const ease = {
    in: p => p * p * p,
    out: p => 1 - Math.pow(1 - p, 3),
    inOut: p => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
    expoOut: p => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
    back: p => 1 + 2.7 * Math.pow(p - 1, 3) + 1.7 * Math.pow(p - 1, 2),
    // a hard quartic start, then a back-out stop that overshoots by ~2.5% and settles
    drop: p => (p < 0.5 ? 8 * p ** 4 : 0.5 + 0.5 * (1 + 2.2 * (2 * p - 2) ** 3 + 1.2 * (2 * p - 2) ** 2)),
  };
  const svg = (tag, attrs, parent) => {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    parent.appendChild(el);
    return el;
  };
  const show = (el, visible) => { el.style.display = visible ? '' : 'none'; };
  const fixed = v => v.toFixed(1);
  const lerp = (a, b, p) => a + (b - a) * p;
  const mix = (a, b, p) => a.map((v, i) => Math.round(lerp(v, b[i], p))).join(', ');   // two RGB colours, as 'r, g, b'
  const attrs = (el, values) => {
    for (const [key, value] of Object.entries(values)) el.setAttribute(key, typeof value === 'number' ? fixed(value) : value);
  };
  // Sets a custom property only when it changes, so a held frame restyles nothing.
  const setVar = (el, name, value) => { if (el.style.getPropertyValue(name) !== value) el.style.setProperty(name, value); };
  // Small deterministic noise, so a replayed frame always looks the same.
  const noise = n => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));   // '#rrggbb'
  const hex = colour => `#${colour.map(v => Math.round(v).toString(16).padStart(2, '0')).join('')}`;   // and back
  const ready = img => img.complete && img.naturalWidth > 0;

  const state = {
    manifest: { scenes: [], sky: {} }, scene: null, sceneIndex: -1, layout: null, birds: [],
    start: 0, running: false, raf: 0, playToken: 0, debugT: null, size: null,
    windowBox: '', sceneSize: '',   // what the window and the picture were last placed and sized to
    washes: 0,   // the fill painted afresh (or cleared) so many times; the ornament's colours follow it
    washFrom: null,   // the thumbnail the fill is painted from (none while it is cleared)
    time: null,   // the time of day as last worked out (time.js, tick)
    at: null,   // a moment the time of day is worked out for instead of now (for inspection)
  };
  // The window docked aside for a section: value runs from 0 (the opening screen) to 1 (docked), and
  // tab is the section shown or on its way. With a section open the picture can be folded away behind
  // it (fold, 0 to 1; touched once the visitor has folded it away or brought it back in the settings
  // this time), and while it is not it keeps a share of the width (split). They are eased to their
  // targets by tweens, which share one frame; prefs are the visitor's choices, kept for the visit
  // (scene: the picture chosen in the settings, by its file; null for a random one each time). drag
  // follows a drag of the divider: the pointer, where it was pressed and how far off the line, the
  // split before it, and whether it has moved yet. swap counts the pictures chosen, so only the last
  // one is put up, and holds the one being put up: the still of the picture going (layer) and the
  // animations of the rack focus (anims: the pictures', marks: the viewfinder corners'). gridPen is
  // the fill grid's pen going over it again (value 0 to 1, 1 put away): due once the opening screen is
  // back after the picture was changed (stale), after timer.
  const dock = { value: 0, tab: 'home', reveal: 0 };
  const gridPen = { value: 1, stale: false, timer: 0 };
  // The opening screen's ornament (MEET): G is where it goes for this screen and picture (null where it
  // has none, id telling one layout from the next), ink what its colours were last worked out from (the
  // fill as painted, for that layout) and drawn the frame its marks were last drawn for. Its birds have
  // glided round the orbit for lap s, and its disc has turned for spin s since its entrance (counted at
  // full speed; up, 0 to 1, is how far it has got up to speed); while the opening screen is up they go
  // on a frame at a time (raf, last), unless held still for inspection (held). meetPen is the ornament
  // coming in again after the picture has been changed (value 0 to 1, 1 when in), once the grid's pen
  // has gone over the new picture: due until it starts (stale), after timer.
  const meet = { G: null, id: 0, ink: '', drawn: '', lap: 0, spin: 0, up: 0, raf: 0, last: 0, held: false };
  const meetPen = { value: 1, stale: false, timer: 0 };
  // The fill's soft light (SOFT_LIGHT): the pointer's light (hand) and the one making a pass of its
  // own (roam), each where it is (fill px), how fast it goes (px/s), how far it is up (amp, 0 to 1), how
  // bright it is meant to be (str) and how far it has gone since it last left a patch of the trail
  // (run); the trail's patches; the dust. pointer is where the pointer is (client px; null while it is
  // away or, on a touch screen, no finger is down), nudged whether it has moved since the last frame,
  // and still when the pointer's light last moved; path is the pass under way. The light at the grid's
  // crossings goes in lines (for the lit grid) and glow (for the shining crossings and the dust); map
  // is lines as a small image, a pixel to a crossing (pixels), stretched over the grid when drawn. size
  // is what the canvas was sized for, box the area drawn last frame, keepOff the picture's rect (at its
  // biggest, fill px; worked out when first needed), timer the wait for the next pass, fading the
  // canvas fading out.
  const softLight = {
    g: null, size: '', W: 0, H: 0, C: 28, cols: 0, rows: 0, lines: null, glow: null, shone: null, frame: 0,
    map: null, mapG: null, pixels: null, pin: null, speck: null,
    hand: { x: 0, y: 0, vx: 0, vy: 0, amp: 0, str: 1, run: 0 }, roam: { x: 0, y: 0, vx: 0, vy: 0, amp: 0, str: 1, run: 0 },
    trail: [], motes: [], pointer: null, nudged: false, still: 0, path: null, resting: false,
    t: 0, last: 0, drawn: 0, raf: 0, timer: 0, box: null, keepOff: null, fading: null,
  };
  const fold = { value: 0, touched: false };
  const split = { value: SPLIT.normal };
  // The replay button is there (1) on the opening screen and in the settings, and away (0) in the other
  // sections; it fades between as the section changes.
  const replayShown = { value: 1 };
  const prefs = { split: SPLIT.normal, folded: false, glass: LOOKS.glass, blur: LOOKS.blur, time: 'auto', scene: null };
  const swap = { count: 0, layer: null, anims: [], marks: [] };
  const tweens = new Map();   // value holder -> { from, to, began, length, curve }
  let tweenFrame = 0;
  const drag = { id: null, x0: 0, x: 0, grab: 0, from: 0, moved: false };
  // The surf's puffs of cloud and their shadows by day, at dusk and at night, cut from the cloud photos
  // once they are in (puffSprites), and two of them mixed for a time between (toneSprites); they do not
  // depend on the layout, so every layout shares them.
  const sprites = { puffs: null, shades: null, between: null };

  // ---------- birds ----------

  // Distant bluebirds inspired by Liz and the Blue Bird: silhouettes only.
  // Two paths share the same 22-point topology: raised wings and a calm glide.
  // There are no face, feather or beak details at this scale.
  const RAISED = [
    0.76, -0.02, 0.69, -0.12, 0.58, -0.17, 0.45, -0.12,
    0.37, -0.46, 0.09, -0.80, -0.42, -0.84,
    -0.23, -0.59, -0.06, -0.34, 0.06, -0.12,
    -0.03, -0.08, -0.16, -0.07, -0.25, -0.07,
    -0.79, 0.19, -0.73, 0.29, -0.29, 0.12, -0.20, 0.13,
    -0.05, 0.22, 0.29, 0.17, 0.49, 0.09,
    0.62, 0.06, 0.70, 0.03
  ];
  const GLIDE = [
    0.76, -0.02, 0.69, -0.12, 0.58, -0.17, 0.45, -0.12,
    0.18, -0.30, -0.13, -0.37, -0.65, -0.32,
    -0.42, -0.21, -0.15, -0.12, 0.06, -0.09,
    -0.03, -0.08, -0.16, -0.07, -0.25, -0.07,
    -0.79, 0.19, -0.73, 0.29, -0.29, 0.12, -0.20, 0.13,
    -0.05, 0.22, 0.29, 0.17, 0.49, 0.09,
    0.62, 0.06, 0.70, 0.03
  ];

  function bluebirdPath(pose) {
    const v = RAISED.map((a, i) => a + (GLIDE[i] - a) * clamp01(pose));
    const p = i => `${v[2 * i].toFixed(3)} ${v[2 * i + 1].toFixed(3)}`;
    return `M${p(0)}C${p(1)} ${p(2)} ${p(3)}C${p(4)} ${p(5)} ${p(6)}C${p(7)} ${p(8)} ${p(9)}C${p(10)} ${p(11)} ${p(12)}`
      + `L${p(13)}L${p(14)}L${p(15)}L${p(16)}C${p(17)} ${p(18)} ${p(19)}C${p(20)} ${p(21)} ${p(0)}Z`;
  }

  function makeBird(index) {
    const streak = svg('line', { class: 'streak' }, flock);
    const g = svg('g', {}, flock);
    const body = svg('path', { class: index >= 5 ? 'bird far' : 'bird' }, g);
    const pixels = Array.from({ length: PIXELS }, (_, i) => {
      const n = index * 31 + i * 7;
      // squares spread over the wings and body, flying off forward and up
      return { el: svg('rect', { class: 'px' }, flock), x: (noise(n) - 0.5) * 1.4, y: (noise(n + 1) - 0.7) * 1.0,
               side: 0.12 + noise(n + 2) * 0.16, fly: 0.5 + noise(n + 3), rise: 0.2 + noise(n + 4) * 0.5,
               delay: noise(n + 5) * 160 };
    });
    [g, streak, ...pixels.map(p => p.el)].forEach(el => show(el, false));
    return { g, body, streak, pixels, drawn: -1 };
  }

  // Draws one bird at screen (x, y), tilted by `tilt` degrees.
  function poseBird(bird, x, y, size, pose, tilt, opacity = 1) {
    if (bird.drawn !== pose) { bird.body.setAttribute('d', bluebirdPath(pose)); bird.drawn = pose; }
    bird.g.setAttribute('transform', `translate(${fixed(x)} ${fixed(y)}) rotate(${fixed(tilt)}) scale(${size.toFixed(2)})`);
    bird.g.style.opacity = opacity;
    show(bird.g, true);
  }

  function hideBird(bird) {
    show(bird.g, false);
    show(bird.streak, false);
    bird.pixels.forEach(p => show(p.el, false));
  }

  // ---------- static marks, built once ----------

  function makeGuides() {
    const line = cls => svg('line', { class: cls || '' }, guides);
    return {
      lines: [line(), line(), line(), line()],        // from the shot's centre to the four screen edges
      ticks: svg('path', { class: 'tick' }, guides),
      scale: line('bar'),                             // a heavy scale bar on the horizontal guide
      ring: svg('circle', { class: 'ring', pathLength: 1 }, guides),
      arc: svg('circle', { class: 'arc', pathLength: 1, 'stroke-dasharray': '0.12 0.88' }, guides),
      dot: svg('circle', { r: 5 }, guides),
      outline: svg('rect', { class: 'outline', pathLength: 1 }, guides),
    };
  }

  function makeTracking() {
    const track = TRACKED.map((_, i) => {
      const g = svg('g', { class: 'track' }, flock);
      return {
        g, box: svg('rect', {}, g), corners: svg('path', { class: 'corners' }, g),
        rings: [svg('circle', {}, g), svg('circle', {}, g)], callout: svg('polyline', {}, g),
        tag: svg('rect', { class: 'tag' }, g), index: i,
      };
    });
    return { track, link: svg('polyline', { class: 'link' }, flock) };
  }

  function makeLens() {
    return {
      streaks: Array.from({ length: STREAKS }, () => svg('line', { class: 'speed' }, lens)),
      // measurement marks pinned in the sky during the fall: three dots and two small squares
      dots: Array.from({ length: 3 }, () => svg('circle', { class: 'mark', r: 2.5 }, lens)),
      boxes: Array.from({ length: 2 }, () => svg('rect', { class: 'mark-box', width: 9, height: 9 }, lens)),
      cross: [svg('line', { class: 'cross' }, lens), svg('line', { class: 'cross' }, lens)],
      af: svg('path', { class: 'af' }, lens),
    };
  }

  function makeHello() {
    const g = svg('g', {}, helloSvg);
    const rings = Array.from({ length: RINGS }, (_, i) => svg('circle', { class: i === 1 ? 'heavy' : '' }, g));
    const rules = [svg('line', { class: 'rule' }, g), svg('line', { class: 'rule' }, g)];
    const bars = [svg('line', { class: 'bar' }, g), svg('line', { class: 'bar' }, g)];
    const letters = [...'HELLO'].map(ch => {
      const guide = svg('line', { class: 'rule' }, g);
      const echo = svg('text', { class: 'echo' }, g);
      const letter = svg('text', { class: 'letter' }, g);
      echo.textContent = letter.textContent = ch;
      return { guide, echo, letter };
    });
    const dimension = svg('path', {}, g);
    const gust = svg('circle', { class: 'heavy' }, g);   // sent out as the word breaks up
    return { g, rings, rules, bars, letters, dimension, gust };
  }

  // A butterfly's body: its two antennae, then the abdomen and the head (unit space).
  function makeBody(g) {
    const body = [1, -1].map(side => svg('path', { class: 'antenna', d: BUTTERFLY.antenna, transform: `scale(${side} 1)` }, g));
    body.push(svg('ellipse', { class: 'body', cx: 0, cy: 0.04, rx: 0.05, ry: 0.42 }, g),
      svg('circle', { class: 'body', cx: 0, cy: -0.43, r: 0.065 }, g));
    return body;
  }

  // A butterfly: each wing pair is flapped by squeezing it towards the body. `lines` are the wing
  // outlines that are drawn on before the colour fills in.
  function makeButterfly(parent, cls) {
    const g = svg('g', { class: `butterfly ${cls}` }, parent);
    const wings = [1, -1].map(side => {
      const flap = svg('g', {}, g);
      const half = svg('g', { transform: `scale(${side} 1)` }, flap);
      return {
        flap,
        fore: svg('path', { class: 'wing fore', d: BUTTERFLY.fore, pathLength: 1 }, half),
        hind: svg('path', { class: 'wing hind', d: BUTTERFLY.hind, pathLength: 1 }, half),
      };
    });
    const body = makeBody(g);
    const veins = wings.flatMap(w => [svg('path', { class: 'veins', d: BUTTERFLY.vein }, w.fore.parentNode)]);
    show(g, false);
    return { g, wings, body, veins, lines: wings.flatMap(w => [w.fore, w.hind]) };
  }

  // The specimen's orbit (see LORENZ): its points two RK4 steps apart, in Lorenz units with y down
  // (rounded as the path has them), the length of the orbit up to each, and how far it reaches
  // either side.
  function lorenzOrbit() {
    const { from, span, step: h } = LORENZ;
    const f = ([x, y, z]) => [10 * (y - x), x * (28 - z) - y, x * y - 8 / 3 * z];
    const seen = ([x, y, z]) => [+((x + y) / Math.SQRT2).toFixed(2), +(-0.95 * (z - 27)).toFixed(2)];
    let p = from;
    const points = [seen(p)], run = [0];
    for (let i = 1; i * h <= span + 1e-9; i++) {
      const k1 = f(p), k2 = f(p.map((v, j) => v + h / 2 * k1[j]));
      const k3 = f(p.map((v, j) => v + h / 2 * k2[j])), k4 = f(p.map((v, j) => v + h * k3[j]));
      p = p.map((v, j) => v + h / 6 * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j]));
      if (i % 2) continue;
      const q = seen(p), [x, y] = points[points.length - 1];
      run.push(run[run.length - 1] + Math.hypot(q[0] - x, q[1] - y));
      points.push(q);
    }
    const across = points.map(([x]) => x);
    return { points, run, dt: 2 * h, left: Math.min(...across), right: Math.max(...across) };
  }

  // Where the trace of the orbit has got to after `time` Lorenz time units: its head, and the share
  // of the orbit's length drawn behind it.
  function orbitAt(orbit, time) {
    const { points, run, dt } = orbit, last = points.length - 1;
    const at = Math.min(last, time / dt), i = Math.min(last - 1, Math.floor(at)), f = at - i;
    const [x0, y0] = points[i], [x1, y1] = points[i + 1];
    return { x: lerp(x0, x1, f), y: lerp(y0, y1, f), drawn: lerp(run[i], run[i + 1], f) / run[last] };
  }

  // The pinned specimen: its wings are the orbit (in Lorenz units, see LORENZ), traced by a small
  // square round the crosses on the two fixed points, with a butterfly's body laid over it, a
  // dimension line without numbers under it and a pin. The orbit is squeezed towards the body when
  // the specimen trembles.
  function makeSpecimen(parent) {
    const orbit = lorenzOrbit();
    const g = svg('g', {}, parent), wings = svg('g', {}, g);
    const path = svg('path', { class: 'orbit', d: `M${orbit.points.map(([x, y]) => `${x} ${y}`).join('L')}`, pathLength: 1 }, wings);
    const crosses = [0, 1].map(() => svg('path', { class: 'cross fine' }, parent));
    const torso = svg('g', {}, parent);
    [g, torso].forEach(el => show(el, false));
    return {
      g, wings, path, orbit, crosses, torso, body: makeBody(torso),
      tracer: svg('rect', { class: 'tracer' }, parent),
      dim: svg('path', { class: 'dim' }, parent), pin: svg('circle', { class: 'pin', r: 0 }, parent),
    };
  }

  function makeFeather(parent) {
    const g = svg('g', { class: 'feather' }, parent);
    show(g, false);
    // every other number in the paths is an x (all their commands are absolute)
    const wide = d => { let i = 0; return d.replace(/-?\d*\.?\d+/g, n => (i++ % 2 ? n : String(+(n * FEATHER_WIDTH).toFixed(3)))); };
    return {
      g,
      vane: svg('path', { class: 'vane', d: wide(FEATHER.vane), pathLength: 1 }, g),
      down: svg('path', { class: 'down', d: wide(FEATHER.down) }, g),
      shaft: svg('path', { class: 'shaft', d: wide(FEATHER.shaft) }, g),
    };
  }

  // Butterflies and blue-bird feathers on the paper, under the cluster lines (so the cluster's
  // pixel squares break up the pinned specimen's wing).
  function makeMotifs() {
    const g = svg('g', {}, guides);
    return {
      specimen: makeSpecimen(g),
      butterflies: [makeButterfly(g, ''), makeButterfly(g, 'pale')],
      feathers: [makeFeather(g), makeFeather(g)],
    };
  }

  // Ornaments in the paper margins (no text): two clusters after the blue-sky film and a bar group
  // in each bottom corner. The window covers them when it opens out.
  function makeOrnaments() {
    const cluster = () => {
      const g = svg('g', {}, guides);
      return {
        squares: CLUSTER.squares.map(() => svg('rect', { class: 'frame', pathLength: 1 }, g)),
        diagonals: CLUSTER.diagonals.map(() => svg('line', { class: 'frame', pathLength: 1 }, g)),
        crosses: CLUSTER.crosses.map(() => svg('path', { class: 'cross' }, g)),
        pixels: CLUSTER.pixels.map((_, i) => svg('rect', { class: `pixel p${i % 3}` }, g)),
      };
    };
    const g = svg('g', { class: 'corner-bars' }, guides);
    return {
      clusters: [cluster(), cluster()],
      left: { rule: svg('line', { class: 'rule' }, g), bar: svg('rect', { class: 'fade-bar' }, g) },
      right: { bar: svg('rect', { class: 'ink-bar' }, g), rule: svg('line', { class: 'rule' }, g), blinds: svg('rect', { class: 'blinds' }, g) },
    };
  }

  // Four L-shaped corners around a box: focus brackets and the heavy corners of tracking squares.
  function bracketPath(x0, y0, x1, y1, arm) {
    return `M${x0} ${y0 + arm}V${y0}H${x0 + arm}M${x1 - arm} ${y0}H${x1}V${y0 + arm}`
      + `M${x1} ${y1 - arm}V${y1}H${x1 - arm}M${x0 + arm} ${y1}H${x0}V${y1 - arm}`;
  }

  // The opening screen's ornament (MEET), built once. The planes lie under the fill's grid; over it the
  // line work is one group drawn twice, each through a mask: white where what lies under it is dark,
  // ink where it is light (the fill's own lightness, from its thumbnail, and over it the planes', shape
  // by shape). Then the AF brackets on her and the bar group in the bottom-right corner, in their own
  // colours, and the birds, blue and, over a dark plane, white.
  function makeMeet() {
    const defs = svg('defs', {}, meetSvg);
    const mask = id => svg('mask', { id, maskUnits: 'userSpaceOnUse' }, defs);
    // The masks for the line work and the birds are laid first with a ground over their whole region
    // (black where nothing shows but the shapes put over it, white where all does), and the line work
    // and each flock start with a clear rect as big (extent): Chromium keeps a group drawn through a mask
    // in the layer under it only while all of it merges into one, and it merges small parts far apart
    // only into a part that already spans them. Left to its parts the ornament splits into some twenty
    // layers, most as big as the screen, while it comes in; the page runs out of GPU memory for them, and
    // whole layers drop out for a frame. (The orbit and the moon each start with a shape spanning the rest.)
    const cover = (parent, look) => svg('rect', { x: '-10%', y: '-10%', width: '120%', height: '120%', ...look }, parent);
    const chalk = mask('meetChalk'), ink = mask('meetInk'), onDark = mask('meetOnDark'), offDark = mask('meetOffDark');
    [chalk, ink, onDark].forEach(m => cover(m, { fill: '#000' }));
    cover(offDark, { fill: '#fff' });
    const thumbs = [chalk, ink].map(m => svg('image', { preserveAspectRatio: 'none' }, m));
    // the planes in the order they lie: the image plane (its perforations holes in it), the disc over it,
    // the clear spot on the disc
    const planes = [['path', { 'fill-rule': 'evenodd' }], ['circle', {}], ['circle', {}]].map(([tag, a]) => ({
      fill: svg(tag, a, meetPlanes), chalk: svg(tag, a, chalk), ink: svg(tag, a, ink), on: svg(tag, a, onDark), off: svg(tag, a, offDark),
    }));
    // the orbit broken round the two of them; the moon's dark side
    const gap = mask('meetGap');
    cover(gap, { fill: '#fff' });
    const gaps = [svg('circle', { fill: '#000' }, gap), svg('circle', { fill: '#000' }, gap)];
    const moonMask = mask('meetMoon');
    const moonBox = svg('rect', { fill: '#fff' }, moonMask), moonDark = svg('circle', { fill: '#000' }, moonMask);
    const blinds = svg('pattern', { id: 'meetBlinds', width: 4.5, height: 8, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(42)' }, defs);
    svg('rect', { width: 2, height: 8, fill: '#fff' }, blinds);
    // the line work, bottom up (styles.css gives each its weight)
    const lines = svg('g', { id: 'meetLines' }, defs);
    cover(lines, { class: 'extent' });
    const hatch = svg('path', { class: 'hatch' }, lines);
    // on the disc: its rim, its rings with a world on each, its glints (each drawn at a size of one, about
    // its middle: a soft halo, four spikes and, on the big one, four shorter ones between them, a core;
    // the spikes run out thin, each side between two tips a curve keeping close to both axes)
    const rim = svg('path', { class: 'rim' }, lines);
    const tracks = MEET.tracks.map(([, weight]) => svg('path', { class: `track ${weight}` }, lines));
    const worlds = MEET.tracks.map(() => svg('circle', { class: 'world' }, lines));
    const star = (h, a) => `M0 -1C.035 -.18 ${a} -.035 ${h} 0C${a} .035 .035 .18 0 1C-.035 .18 ${-a} .035 ${-h} 0C${-a} -.035 -.035 -.18 0 -1Z`;
    const glints = [0, 1, 2].map(i => {
      const g = svg('g', { class: 'glint' }, lines);
      svg('circle', { class: 'halo', r: 0.5 }, g);
      svg('circle', { class: 'halo in', r: 0.22 }, g);
      svg('path', { class: 'spikes', d: star(0.74, 0.15) }, g);
      if (!i) svg('path', { class: 'spikes between', d: star(1, 0.18), transform: 'rotate(45) scale(0.42)' }, g);
      return { g, core: svg('circle', { class: 'core' }, g) };
    });
    const rays = [0, 1, 2].map(i => [0, 1].map(() => svg('line', { class: i === 1 ? 'ray' : 'ray side' }, lines)));
    const orbitG = svg('g', { mask: 'url(#meetGap)' }, lines);   // (on the group: the orbit itself is turned)
    const orbit = svg('circle', { class: 'orbit' }, orbitG), lune = svg('path', { class: 'lune' }, orbitG);
    const points = [0, 1, 2].map(() => svg('circle', { class: 'point', r: 2.2 }, lines));
    const moonG = svg('g', {}, lines);
    const moon = svg('circle', { class: 'moon' }, moonG), moonLit = svg('circle', { class: 'moon-lit', mask: 'url(#meetMoon)' }, moonG);
    const bezel = [svg('path', { class: 'bezel' }, lines), svg('path', { class: 'bezel long' }, lines)];
    const herG = svg('g', {}, lines);
    const her = [svg('polygon', { class: 'her' }, herG), svg('polygon', { class: 'her inner' }, herG)];
    const petals = [0, 1, 2].map(() => svg('rect', { class: 'petal' }, lines));
    svg('use', { href: '#meetLines', class: 'chalk', mask: 'url(#meetChalk)' }, meetSvg);
    svg('use', { href: '#meetLines', class: 'ink', mask: 'url(#meetInk)' }, meetSvg);
    const af = svg('path', { class: 'af' }, meetSvg);
    const barsG = svg('g', { class: 'bars' }, meetSvg);
    const bars = [svg('rect', { class: 'blinds' }, barsG), svg('line', {}, barsG), svg('rect', {}, barsG)];
    // the birds: the flock twice, blue off the dark planes and white on them; gliding, each with its
    // wings swept back a little differently
    const flocks = [svg('g', { class: 'birds', mask: 'url(#meetOffDark)' }, meetSvg), svg('g', { class: 'birds white', mask: 'url(#meetOnDark)' }, meetSvg)];
    flocks.forEach(g => cover(g, { class: 'extent' }));
    const birds = Array.from({ length: MEET.bird.count }, (_, i) => {
      const d = bluebirdPath(0.65 + 0.3 * noise(91 + i));
      return { els: flocks.map(g => svg('path', { d }, g)), seen: true };
    });
    return { thumbs, planes, gaps, moonBox, moonDark, hatch, rim, tracks, worlds, glints, rays, orbit, lune, points, moonG, moon, moonLit, bezel, herG, her, petals, af, barsG, bars, birds };
  }

  // The section index's focus scale (drawScale): a hairline beside the squares, fine ticks along it,
  // a long one at each square and the current one's blue.
  function makeScale() {
    const g = svg('svg', { class: 'scale', 'aria-hidden': 'true' }, indexNav);
    return { fine: svg('path', { class: 'fine' }, g), long: svg('path', { class: 'long' }, g), lit: svg('path', { class: 'lit' }, g) };
  }

  const paper = makeGuides();
  const tracking = makeTracking();
  const lensMarks = makeLens();
  const hello = makeHello();
  const motifs = makeMotifs();
  const ornaments = makeOrnaments();
  const meetMarks = makeMeet();
  const indexScale = makeScale();

  // ---------- layout ----------

  function layout() {
    // a page opened in a hidden frame reports no size; lay it out at a pixel until it is resized
    const [W, H] = state.size || [Math.max(1, innerWidth), Math.max(1, innerHeight)];
    const portrait = W < H;
    stage.classList.toggle('portrait', portrait);
    // The shot's window sits in the middle with white paper round it; it opens out to the whole
    // screen when the camera lands.
    const win = portrait ? { x: 0.06 * W, y: 0.15 * H, w: 0.88 * W, h: 0.55 * H }
      : { x: 0.18 * W, y: 0.1 * H, w: 0.64 * W, h: 0.66 * H };
    const m = Math.min(48, Math.max(18, 0.026 * W));   // how far in from the screen edge the viewfinder marks sit
    for (const [key, value] of Object.entries({ wx: win.x, wy: win.y, ww: win.w, wh: win.h, m })) {
      stage.style.setProperty(`--${key}`, `${fixed(value)}px`);
    }
    for (const el of [guides, flock, helloSvg, meters]) el.setAttribute('viewBox', `0 0 ${W} ${H}`);
    state.windowBox = state.sceneSize = state.picSize = '';   // placed and sized again on the next frame
    dropLight();   // (drawn for the old layout)
    const tone = state.time.sky;   // (the window's sky, by the time of day)
    const L = {
      W, H, portrait, win, m, screen: { x: 0, y: 0, w: W, h: H },
      cell: parseFloat(getComputedStyle(stage).getPropertyValue('--cell')) || 28,
      cx: win.x + win.w / 2, cy: win.y + win.h / 2, camStart: -SKY_SPAN * win.h,
      birdUnit: portrait ? Math.max(14, 0.05 * W) : Math.min(40, Math.max(20, 0.02 * W)),
    };
    const s = state.scene;
    if (s) {
      // The picture as framed in the shot's window. The camera comes to rest with the ground filling
      // the window, so the faded seam runs no lower than just above the heads.
      const shot = frameFor(win, s);
      const band = Math.min(FADE_BAND * win.h, 0.8 * shot.head);
      Object.assign(L, { shot, camEnd: 0, band, bandShare: band / ((1 + OVERSHOOT) * win.h), top: s.top });
      // the push-in and the idle breathing scale around the faces, so the faces stay where framed
      const [fx, fy] = focusOf(s), origin = `${fixed(fx * 100)}% ${fixed(fy * 100)}%`;
      scenePush.style.transformOrigin = origin;
      scene.style.setProperty('--focus', origin);
    } else {
      Object.assign(L, { shot: null, camEnd: L.camStart, band: 0, bandShare: 0, top: hex(skyAt(tone, SKY_SPAN)) });
    }
    // The time of day's sky above the picture (SKIES); it turns to the picture's own sky colour only just
    // above and under the faded seam, and runs on a window-height below it, so the seam always has sky
    // behind. Its clouds are tinted for the time of day; in a night sky HELLO is printed in a brighter
    // blue (styles.css, .night-sky), and the flood of light is the moon's, fainter (flood: its strength).
    L.skyTop = L.camStart - 0.1 * win.h;
    L.skyHeight = L.band + win.h - L.skyTop;
    const seam = -L.skyTop + 0.5 * L.band, k = Math.min(1, Math.floor(tone)), between = tone - k;
    const palettes = between <= 0 ? [SKIES[k]] : between >= 1 ? [SKIES[k + 1]] : [SKIES[k], SKIES[k + 1]];
    const heights = [...new Set(palettes.flat().map(([y]) => y))].sort((a, b) => a - b);
    L.skyStops = heights.map(y => [y * win.h, hex(skyAt(tone, y))]).filter(([at]) => at < seam - 0.1 * win.h).concat([[seam, L.top]]);
    sky.style.height = `${L.skyHeight}px`;
    sky.style.background = `linear-gradient(${L.skyStops.map(([at, color]) => `${color} ${fixed(at)}px`).join(', ')})`;
    stage.classList.toggle('night-sky', tone > 1.5);
    L.flood = 1 - 0.45 * smooth(1, 2, tone);
    const sizes = CLOUDS[portrait ? 'portrait' : 'landscape'], tint = tintFilter(tintAt(tone));
    L.clouds = Object.entries(clouds).map(([name, el]) => {
      const [width, left, top, parallax, opacity] = sizes[name];
      const info = state.manifest.sky[name];
      el.style.width = `${width * win.w}px`;
      el.style.filter = tint;
      const height = info ? width * win.w * info.h / info.w : 0;
      return { el, x: left * win.w, y: top * win.h, width: width * win.w, height, parallax, opacity };
    });
    // Speed lines: fixed columns and lengths, so every frame of the fall is reproducible.
    L.streaks = lensMarks.streaks.map((line, i) => ({
      line, x: ((i * 0.618034) % 1) * win.w, length: (0.25 + ((i * 0.381966) % 1) * 0.45) * win.h, phase: (i * 0.7548) % 1,
    }));
    layoutTiles(L);
    layoutStars(L);
    layoutSurf(L);
    layoutHello(L);
    layoutOrnaments(L);
    layoutMeters(L);
    layoutMotifs(L);
    layoutPetals(L);
    layoutSections(L);
    layoutPicks(L);
    layoutMeet(L);
    state.layout = L;
    prepareFlock();
  }

  // The sky's colour (RGB) y window-heights down from its top at a time of day (0 to 2, SKIES).
  function skyAt(tone, y) {
    const along = stops => {
      const i = stops.findIndex(([at]) => at > y);
      if (i <= 0) return rgb(stops[i < 0 ? stops.length - 1 : 0][1]);
      const [a, from] = stops[i - 1], [b, to] = stops[i], end = rgb(to);
      return rgb(from).map((v, j) => lerp(v, end[j], (y - a) / (b - a)));
    };
    const k = Math.min(1, Math.floor(tone)), lo = along(SKIES[k]), hi = along(SKIES[k + 1]);
    return lo.map((v, j) => Math.round(lerp(v, hi[j], tone - k)));
  }

  // Where the push-in and the breathing are centred, as shares of the picture: the faces (the top of
  // the box round the two of them, a little way down).
  function focusOf(s) {
    return [s.cx, s.box[1] + 0.12 * (s.box[3] - s.box[1])];
  }

  // How the picture sits in a window (rect): all of it, as big as the window holds it, in the
  // middle; the rest of the window is the fill. It is laid out a little smaller than that, so that
  // pushed in and breathing at its deepest (both round the faces) it comes to just that size and no
  // part of it leaves the window. Returns its scale and its top-left corner (window-relative) as laid
  // out, the most of the window it takes (fit, window-relative), how far down the window the tops of
  // the heads come (window px) and where the box round the two heads ends up (screen space).
  function frameFor(rect, s) {
    const fit = Math.min(rect.w / s.w, rect.h / s.h), grow = PUSH * BREATH;
    const w = s.w * fit, h = s.h * fit, x = (rect.w - w) / 2, y = (rect.h - h) / 2;
    const [fx, fy] = focusOf(s), head = y + s.box[1] * h;
    const spanX = (s.box[2] - s.box[0]) * w, spanY = (s.box[3] - s.box[1]) * h;
    return {
      k: fit / grow, left: x + fx * w * (1 - 1 / grow), top: y + fy * h * (1 - 1 / grow), head, fit: { x, y, w, h },
      faces: {
        x0: rect.x + Math.max(0.04 * rect.w, x + s.box[0] * w + 0.08 * spanX),
        x1: rect.x + Math.min(0.96 * rect.w, x + s.box[2] * w - 0.08 * spanX),
        y0: rect.y + Math.max(0.04 * rect.h, head - 0.03 * rect.h),
        y1: rect.y + Math.min(0.9 * rect.h, head + Math.min(0.32 * spanY, 0.42 * rect.h)),
      },
    };
  }

  // Ornament clusters in the margins (the second one turned half round) and the bar groups in the
  // bottom corners, inside where the viewfinder corners start.
  function layoutOrnaments(L) {
    const { W, H, win, m, portrait } = L;
    const unit = (share, lo, hi) => Math.min(hi, Math.max(lo, share * W));
    const spots = portrait
      ? [[0.3 * W, win.y + win.h + 0.42 * (H - win.y - win.h), unit(0.06, 18, 30), 1],
        [0.74 * W, 0.55 * win.y, unit(0.05, 16, 24), -1]]
      : [[0.45 * win.x, win.y + win.h - 0.02 * H, unit(0.028, 26, 54), 1],
        [W - 0.45 * win.x, win.y + 0.2 * win.h, unit(0.028, 26, 54), -1]];
    L.clusters = spots;   // the pinned butterfly sits in the first one
    ornaments.clusters.forEach((c, i) => {
      const [cx, cy, a, dir] = spots[i];
      const at = (x, y) => [cx + dir * x * a, cy + dir * y * a];
      const box = ([x, y, side], el) => {
        const [px, py] = dir > 0 ? at(x, y) : at(x + side, y + side);   // top-left corner after the turn
        attrs(el, { x: px, y: py, width: side * a, height: side * a });
      };
      CLUSTER.squares.forEach((square, j) => box(square, c.squares[j]));
      CLUSTER.pixels.forEach((pixel, j) => box(pixel, c.pixels[j]));
      CLUSTER.diagonals.forEach(([x1, y1, x2, y2], j) => {
        const [ax, ay] = at(x1, y1), [bx, by] = at(x2, y2);
        attrs(c.diagonals[j], { x1: ax, y1: ay, x2: bx, y2: by });
      });
      const arm = Math.max(4, 0.13 * a);
      CLUSTER.crosses.forEach(([x, y], j) => {
        const [px, py] = at(x, y);
        c.crosses[j].setAttribute('d', `M${fixed(px - arm)} ${fixed(py)}H${fixed(px + arm)}M${fixed(px)} ${fixed(py - arm)}V${fixed(py + arm)}`);
      });
    });
    // lengths in the bar groups: a hairline over a fading bar on the left; a bar, a hairline and
    // blinds on the right (shorter on a phone, where the dash group sits close between them)
    const size = portrait ? { lead: 36, fade: 70, bar: 24, rule: 20, blinds: 24, gap: 6 }
      : { lead: 56, fade: 118, bar: 52, rule: 64, blinds: 30, gap: 8 };
    const y = H - m - 18, { left, right } = ornaments;
    attrs(left.rule, { x1: m + 14, y1: y - 8, x2: m + 14 + size.lead, y2: y - 8 });
    attrs(left.bar, { x: m + 14, y: y - 3, width: size.fade, height: 9 });
    let x = W - m - 14 - size.blinds;
    attrs(right.blinds, { x, y: y - 3, width: size.blinds, height: 8 });
    x -= size.gap;
    attrs(right.rule, { x1: x - size.rule, y1: y + 1, x2: x, y2: y + 1 });
    x -= size.rule + size.gap;
    attrs(right.bar, { x: x - size.bar, y: y - 1.5, width: size.bar, height: 5 });
  }

  // Tick meters down both sides of the screen, with irregular tick lengths after the blue-sky film.
  // The right one is a path of its own: the section index takes its place at the end.
  function layoutMeters(L) {
    const y0 = 0.38 * L.H, y1 = 0.62 * L.H, step = 6;
    [[meterTicks, L.m + 3, 1, 0], [meterTicksRight, L.W - L.m - 3, -1, 40]].forEach(([path, x, dir, seed]) => {
      let d = `M${fixed(x)} ${fixed(y0)}V${fixed(y1)}`;
      for (let i = 0, y = y0; y <= y1 + 0.1; i++, y += step) {
        const len = i % 5 ? 2 + 7 * noise(seed + i) ** 2 : 10;
        d += `M${fixed(x)} ${fixed(y)}h${fixed(dir * len)}`;
      }
      path.setAttribute('d', d);
    });
    L.meter = { x: L.m + 3, y0, y1 };
  }

  // Where the window docks for a section, and the panel beside it. On a wide screen the picture
  // keeps the left part (its share of the width, the split, is where the divider sits) and the panel
  // takes the paper between it and the index on the right edge, never narrower than SPLIT.pane where
  // the screen allows; folded away, the picture takes the whole screen again behind the panel, which
  // moves to a wide column in the middle of the screen, its full height, as wide as it can be clear
  // of the index with as much room on its left (the section is laid out across it there, styles.css
  // .spread). On a phone the picture keeps the top third, the index a strip under it and the panel
  // the rest. The index is anchored by its own size: on the right edge (INDEX_IN in from the meter's
  // line, where its scale is), centred (on a phone at the top of the picture, then centred in the strip).
  function layoutSections(L) {
    const { W, H, m, portrait } = L;
    const box = { w: indexNav.offsetWidth, h: indexNav.offsetHeight };
    const strip = Math.max(84, box.h + 28);
    const right = W - m - (portrait ? 0 : INDEX_IN);
    const room = right - box.w - 12;   // the paper from the screen's left edge to the index
    const max = Math.max(SPLIT.min, Math.min(SPLIT.max, (room - SPLIT.pane) / W));
    const edge = { x: right, y: H / 2, ax: 1, ay: 0.5 };
    let column = null;
    if (!portrait) {
      const w = Math.max(0, 2 * room - W);
      column = { x: (W - w) / 2, y: 0, w, h: H };
    }
    L.dock = {
      box, strip, room, min: SPLIT.min, max, column, at: null,
      home: portrait ? { x: W / 2, y: m + 44, ax: 0.5, ay: 0 } : edge,
      docked: portrait ? { x: W / 2, y: 0.34 * H + strip / 2, ax: 0.5, ay: 0.5 } : edge,
    };
    placeBrackets(false);
  }

  // Where the ornament goes (MEET) for this screen and picture: none on a phone, beside a picture with
  // too little fill, or where her disc would have too little room. The picture's box is taken at its
  // biggest (breathing at its deepest), so what goes in behind it stays behind it; on her side it keeps
  // clear of the index (its squares, and the titles that come up beside them). Each picture is a world of its own: the moon's phase, the point on its
  // bezel, the turn of her pentagon, and on the disc where the worlds ride and the small glints lie come
  // from it. What does not change in the entrance is set here.
  function layoutMeet(L) {
    const { W, H, m } = L, s = state.scene, M = meetMarks;
    for (const el of [meetSvg, meetPlanes]) {
      el.setAttribute('viewBox', `0 0 ${W} ${H}`);
      el.style.width = `${W}px`;
      el.style.height = `${H}px`;
    }
    meet.G = null;
    meet.drawn = '';
    if (!s || L.portrait) return;
    const fit = frameFor(L.screen, s).fit, px = fit.x, pr = fit.x + fit.w;
    if (px < MEET.min) return;
    const D = L.dock, squares = D.home.x - indexLinks[0].querySelector('b').offsetWidth;
    const l0 = m + 44, l1 = px - 26, r0 = pr + 30, r1 = D.home.x - D.box.w - 18;
    // her halfway across her side's fill, but in far enough for the disc round her to keep its cells
    // clear of the index, and not so far that her clear spot goes behind the picture; the disc made
    // smaller where that leaves it too little room, and no ornament where too little of it would be left
    const room = squares - MEET.disc.clear * L.cell, discR = MEET.disc.r * H, spotR = MEET.disc.spot * H;
    const Sa = { x: Math.max(pr + spotR + 12, Math.min(lerp(r0, r1, 0.5), room - discR)), y: 0.69 * H };
    if (room - Sa.x < MEET.disc.least * spotR) return;
    const Mo = { x: lerp(l0, l1, 0.36), y: 0.31 * H };
    const rm = Math.max(16, 0.028 * H), rp = Math.max(12, 0.019 * H);
    const seed = k => noise(31 * (state.sceneIndex + 2) + k);
    // the orbit: the circle round the middle of the screen's width through the two of them
    const cx = W / 2, cy = ((Sa.x - cx) ** 2 + Sa.y ** 2 - (Mo.x - cx) ** 2 - Mo.y ** 2) / (2 * (Sa.y - Mo.y));
    const R = Math.hypot(Mo.x - cx, Mo.y - cy), from = Math.atan2(Mo.y - cy, Mo.x - cx), toHer = Math.atan2(Sa.y - cy, Sa.x - cx);
    // the rays: from the moon to points on the picture's middle line (behind it) and on to her
    const toward = (a, b, d) => { const k = d / Math.hypot(b.x - a.x, b.y - a.y); return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k }; };
    const atX = (a, b, x) => ({ x, y: a.y + (b.y - a.y) * (x - a.x) / (b.x - a.x) });
    const rays = [-1, 0, 1].map(f => {
      const P = { x: W / 2, y: (Mo.y + Sa.y) / 2 + f * 0.11 * H };
      return { inL: toward(Mo, P, rm + 6), outL: atX(Mo, P, px), inR: atX(P, Sa, pr), outR: toward(Sa, P, rp + 7) };
    });
    const spot = { cx: Sa.x, cy: Sa.y, r: spotR };
    const B = MEET.bird, round = (a, at, wide, need) => {
      const d = Math.abs((((a - at) % (2 * Math.PI)) + 3 * Math.PI) % (2 * Math.PI) - Math.PI);
      return d < wide ? Math.max(0, need - B.off) * Math.cos(Math.PI * d / (2 * wide)) ** 2 : 0;
    };
    meet.G = {
      id: ++meet.id, W, H, px, pr, squares, Mo, Sa, rm, rp, cx, cy, R, from, rays, spot,
      full: seed(1), bezelAt: 140 + 5 * Math.round(22 * seed(2)),
      disc: { cx: Sa.x, cy: Sa.y, r: Math.min(discR, room - Sa.x) },
      plane: { x0: pr - 40, y0: 0.17 * H, x1: Sa.x + 0.12 * (r1 - r0), y1: 0.7 * H },
      at: (a, r) => ({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }),
      // how far out of their way the birds go at angle a on the orbit: round the moon's bezel and her
      // clear spot
      swerve: a => Math.max(round(a, from, 15 * DEG, 1.7 * rm + 14), round(a, toHer, 13 * DEG, Math.max(spot.r, rp + 14) + 10)),
    };
    const G = meet.G, phase = 0.34 + 0.3 * G.full, turn = 2 * Math.PI / 5 * seed(3) - Math.PI / 2;
    // on the disc: the big glint, turned up towards the top as far as it must be to come out from behind
    // the picture, and the small ones somewhere in their ranges; a world on each ring, well in from an
    // arc's ends and clear of the picture, the rays, the glints and the other worlds (the first place
    // tried that is)
    const u = G.u = G.disc.r / MEET.disc.unit, onDisc = (a, rf) => [Sa.x + rf * G.disc.r * Math.cos(a * DEG), Sa.y + rf * G.disc.r * Math.sin(a * DEG)];
    const [bigAt, bigR, bigSize] = MEET.glints.big;
    let big = bigAt;
    while (big < 270 && onDisc(big, bigR)[0] - 0.74 * bigSize * u < pr + 8) big += 2;
    G.glints = [[big, bigR, bigSize], ...MEET.glints.small.map(([[lo, hi], rf, size], i) => [lerp(lo, hi, seed(4 + i)), rf, size])];
    const away = (a, b) => Math.abs((((a - b) % 360) + 540) % 360 - 180);
    const rayAt = rays.map(ray => Math.atan2(ray.outR.y - Sa.y, ray.outR.x - Sa.x) / DEG);
    G.worlds = MEET.tracks.map(() => 0);
    MEET.tracks.forEach(([rf, , from = 0, to = 360], i) => {
      const end = to - from < 360 ? 15 : 0;
      for (let j = 0; j < 8; j++) {
        const a = G.worlds[i] = lerp(from + end, to - end, seed(10 + 4 * j + i)), [x, y] = onDisc(a, rf);
        const clear = ([b, gr, size]) => { const [gx, gy] = onDisc(b, gr); return Math.hypot(x - gx, y - gy) > size * u + 6; };
        if (x > pr + 8 && rayAt.every(b => away(a, b) > 10) && G.worlds.every((b, k) => k >= i || away(a, b) > 30) && G.glints.every(clear)) break;
      }
    });
    // the image plane's film: the gap in its hatching between the first frame and the next, across the
    // space between the two of its perforations nearest the place (from the bottom of one to the top of
    // the next), the disc's top taken over its clear band
    const F = MEET.film, plane = G.plane, pitch = F.pitch * u, first = plane.y0 + F.top * u;
    const below = G.disc.cy - Math.sqrt(Math.max(0, G.disc.r ** 2 - (plane.x1 - F.band * u / 2 - G.disc.cx) ** 2));
    const n = Math.max(1, Math.round((lerp(first, below, F.gap) - first) / pitch));
    plane.gap = [first + (n - 1) * pitch + F.hole[1] * u, first + n * pitch];
    attrs(M.gaps[0], { cx: Mo.x, cy: Mo.y, r: rm + 7 });
    attrs(M.gaps[1], { cx: Sa.x, cy: Sa.y, r: rp + 14 });
    attrs(M.orbit, { cx, cy, r: R, transform: `rotate(${fixed(from / DEG)} ${fixed(cx)} ${fixed(cy)})` });
    // the moon: a hairline disc, its lit part a crescent opening towards the picture (the dark disc
    // pushed off by the phase)
    attrs(M.moonBox, { x: Mo.x - 2 * rm, y: Mo.y - 2 * rm, width: 4 * rm, height: 4 * rm });
    attrs(M.moonDark, { cx: Mo.x + phase * rm, cy: Mo.y - 0.12 * rm, r: 0.93 * rm });
    for (const el of [M.moon, M.moonLit]) attrs(el, { cx: Mo.x, cy: Mo.y, r: rm });
    // her: the pentagon, a smaller one turned inside it, and the petals drifting off up and to the right
    const pentagon = (r, a0) => Array.from({ length: 5 }, (_, i) => `${fixed(Sa.x + r * Math.cos(a0 + i * 0.4 * Math.PI))},${fixed(Sa.y + r * Math.sin(a0 + i * 0.4 * Math.PI))}`).join(' ');
    M.her[0].setAttribute('points', pentagon(rp, turn));
    M.her[1].setAttribute('points', pentagon(0.44 * rp, turn + Math.PI / 5));
    [[rp + 14, -rp - 6, 4], [rp + 27, -rp - 17, 3], [rp + 36, -rp - 3, 2]].forEach(([dx, dy, side], i) => {
      attrs(M.petals[i], { x: Sa.x + dx, y: Sa.y + dy, width: side, height: side });
    });
    // the bar group in the bottom-right corner, on the HUD's bottom line, flush with the index's squares
    const right = W - m - INDEX_IN, y = H - m - 18;
    show(M.barsG, right - 160 >= pr + 30);
    attrs(M.bars[0], { x: right - 30, y: y - 4, width: 30, height: 8 });
    attrs(M.bars[1], { x1: right - 98, y1: y + 0.5, x2: right - 38, y2: y + 0.5 });
    attrs(M.bars[2], { x: right - 152, y: y - 2, width: 46, height: 4 });
  }

  // The settings' picture tiles have the screen's shape, so that each shows its picture as it is put
  // up on this screen (all of it in the middle, styles.css).
  function layoutPicks(L) {
    picks.style.setProperty('--screen', `${fixed(L.W)} / ${fixed(L.H)}`);
  }

  // The docked picture's window (rect) and the panel beside it, at the split (worked out again only
  // when that changes).
  function dockedAt(L) {
    const D = L.dock, share = L.portrait ? 0 : Math.min(D.max, Math.max(D.min, split.value));
    if (D.at && D.at.share === share) return D.at;
    const { W, H } = L;
    const rect = L.portrait ? { x: 0, y: 0, w: W, h: 0.34 * H } : { x: 0, y: 0, w: share * W, h: H };
    const pane = L.portrait ? { x: 0, y: rect.h + D.strip, w: W, h: H - rect.h - D.strip }
      : { x: rect.w, y: 0, w: Math.max(0, D.room - rect.w), h: H };
    D.at = { share, rect, pane };
    return D.at;
  }

  // Where HELLO hangs, as an offset from the middle of the screen (px): it rises into the middle,
  // then drifts up a little. Its rings burst from there.
  function helloLift(L, t) {
    const T = BEAT.hello;
    return t < T + 400 ? 0.75 * L.H * (1 - ease.out(seg(t, T, 400))) : -0.05 * L.H * seg(t, T + 400, BEAT.dust - T - 400);
  }

  // The rings HELLO bursts out with: the i-th grows round the word over 900 ms.
  function helloRing(L, i, t) {
    const k = seg(t, BEAT.hello + 150 + i * 180, 900);
    return { k, r: L.W * (0.05 + 0.55 * ease.out(k)) };
  }

  // When each of HELLO's first rings passes over something moving along at(t) (screen px), and which
  // way it pushes it (the heavy second ring counts half again). The rings' centre moves with HELLO,
  // so this is found by stepping through time.
  function ringPasses(L, at) {
    const passes = [];
    for (let i = 0; i < RINGS; i++) {
      for (let t = BEAT.hello; ; t += 4) {
        const { k, r } = helloRing(L, i, t);
        if (k >= 1) break;
        const p = at(t), cy = L.H / 2 + helloLift(L, t), d = Math.hypot(p.x - L.W / 2, p.y - cy) || 1;
        if (k > 0 && d <= r) {
          passes.push({ at: t, weight: i === 1 ? 1.5 : 1, away: [(p.x - L.W / 2) / d, (p.y - cy) / d] });
          break;
        }
      }
    }
    return passes;
  }

  // When the ring HELLO sends out as it breaks up (growing as reach * (0.06 + 0.94 * ease.out(k)),
  // past every corner of the screen) reaches something moving along at(t), and which way it blows
  // it: straight out from the ring's centre.
  function gustHit(gust, at) {
    let t = BEAT.dust, p = at(t);
    for (; t < BEAT.dust + GUST_LEN; t += 4) {
      p = at(t);
      if (Math.hypot(p.x - gust.x, p.y - gust.y) <= gust.reach * (0.06 + 0.94 * ease.out(seg(t, BEAT.dust, GUST_LEN)))) break;
    }
    const d = Math.hypot(p.x - gust.x, p.y - gust.y) || 1;
    return { at: t, away: [(p.x - gust.x) / d, (p.y - gust.y) / d] };
  }

  // Where the butterflies and feathers sit. On a wide screen a butterfly over a feather in the left
  // margin (the pinned specimen is in the cluster below them) and a butterfly over a feather in
  // the right one, under the upper cluster; on a phone a butterfly and a feather above the window
  // and another butterfly and feather below it. Each goes its own calm way (butterflyAt, featherAt);
  // HELLO's first rings nudge the ones they pass over (on a phone they stay round the window and
  // miss most), and the ring it sends out as it breaks up blows them away.
  function layoutMotifs(L) {
    const { W, H, win, portrait } = L, u = L.birdUnit;
    const gust = { x: W / 2, y: 0.45 * H, reach: 1.05 * Math.hypot(W / 2, 0.55 * H) };
    const below = win.y + win.h, right = win.x + win.w;
    // butterflies: [x, y, the way they drift in degrees]; feathers: [x, y]
    const spots = portrait
      ? { butterflies: [[0.2 * W, 0.55 * win.y, 190], [0.6 * W, below + 0.55 * (H - below), -20]],
          feathers: [[0.42 * W, 0.6 * win.y], [0.8 * W, below + 0.35 * (H - below)]] }
      : { butterflies: [[0.52 * win.x, win.y + 0.2 * win.h, -110], [right + 0.45 * (W - right), win.y + 0.47 * win.h, 75]],
          feathers: [[0.42 * win.x, win.y + 0.56 * win.h], [right + 0.52 * (W - right), win.y + 0.72 * win.h]] };
    // the specimen about two cluster units across (u px to a Lorenz unit), its fixed points a little
    // over the cluster's middle (at y mid) and its body (bodyK across a unit) on them
    const [cx, cy, a] = L.clusters[0], mid = cy - 0.1 * a;
    const specimen = { x: cx, y: cy, a, u: 0.041 * a, mid, bodyY: mid + 0.05 * a, bodyK: 0.62 * a, tracer: Math.max(3, 0.1 * a) };
    specimen.rings = ringPasses(L, () => specimen);
    specimen.blow = gustHit(gust, () => specimen);
    const M = {
      gust, specimen,
      fly: 1.125 * u, quill: 1.69 * u,   // butterfly wingspan 2.25, feather length 3.4 bird units
      butterflies: spots.butterflies.map(([x, y, course], i) => {
        const rad = course * Math.PI / 180, drawn = BEAT.hello + 40 + 90 * i;
        // the first starts with its wingbeats, the second with a glide
        const b = {
          x, y, dir: [Math.cos(rad), Math.sin(rad)], speed: 0.8 * u, meander: 0.35 * u, weave: 1.6, phase: 0.5 + 1.9 * i,
          bob: 0.15 * u, flaps: 2 + i, glide: 0.9, offset: i ? (2 + i) / FLAP_HZ + 0.35 : 0, drawn, alive: drawn + 340,
        };
        b.rings = ringPasses(L, t => butterflyAt(b, t));
        b.blow = gustHit(gust, t => butterflyAt(b, t));
        return b;
      }),
    };
    M.feathers = spots.feathers.map(([x, y], i) => {
      const drawn = BEAT.hello + 120 + 110 * i;
      const f = {
        x, y, tilt: [-22, 28][i], phase: [0.3, 2.2][i], spin: i % 2 ? 1 : -1, drawn, alive: drawn + 360,
        swing: 0.6 * M.quill, dip: 0.12 * M.quill, fall: 0.035 * H,
      };
      f.rings = ringPasses(L, t => featherAt(f, t));
      f.blow = gustHit(gust, t => featherAt(f, t));
      return f;
    });
    L.motifs = M;
    // The shapes are drawn in unit space: the specimen is placed once, and every outline gets a
    // hairline width for its scale.
    const hairline = (els, px, scale) => els.forEach(el => { el.style.strokeWidth = (px / scale).toFixed(4); });
    const s = motifs.specimen;
    s.g.setAttribute('transform', `translate(${fixed(cx)} ${fixed(mid)}) scale(${specimen.u.toFixed(3)})`);
    s.torso.setAttribute('transform', `translate(${fixed(cx)} ${fixed(specimen.bodyY)}) scale(${specimen.bodyK.toFixed(2)})`);
    hairline([s.path], 0.5, specimen.u);
    hairline(s.body.slice(0, 2), 0.9, specimen.bodyK);
    for (const b of motifs.butterflies) {
      hairline(b.lines, 0.85, M.fly);
      hairline(b.veins, 0.6, M.fly);
      hairline(b.body.slice(0, 2), 1, M.fly);
    }
    for (const f of motifs.feathers) {
      hairline([f.vane], 0.9, M.quill);
      hairline([f.shaft], 1.2, M.quill);
      hairline([f.down], 0.8, M.quill);
    }
  }

  // Paper tiles over the window; the ones nearest the middle clear first.
  function layoutTiles(L) {
    const { win } = L;
    const cols = L.portrait ? 6 : 10, side = win.w / cols, rows = Math.ceil(win.h / side);
    tiles.textContent = '';
    L.tiles = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const el = document.createElement('i');
        el.style.left = `${c * side}px`;
        el.style.top = `${r * side}px`;
        el.style.width = el.style.height = `${side + 0.5}px`;
        tiles.appendChild(el);
        const dist = Math.hypot((c + 0.5) / cols - 0.5, ((r + 0.5) * side / win.h - 0.5) * win.h / win.w);
        L.tiles.push({ el, delay: dist * 520 + noise(r * 17 + c) * 120 });
      }
    }
  }

  // The night sky's stars and moon, and the evening star at dusk (STARS), drawn once for the window: as
  // far away as can be, they stay put in it while the sky goes by, fading out as the camera goes down
  // (drawWindow). They come out as the sky darkens; the evening star is gone again in the night.
  function layoutStars(L) {
    const { win } = L, tone = state.time.sky, dpr = Math.min(2, window.devicePixelRatio || 1);
    const stars = smooth(1.2, 1.9, tone), evening = smooth(0.55, 0.95, tone) * (1 - smooth(1.5, 1.9, tone));
    L.stars = stars > 0 || evening > 0;
    show(starCanvas, false);
    if (!L.stars) {
      starCanvas.width = starCanvas.height = 0;
      return;
    }
    const w = win.w, h = win.h;
    starCanvas.width = Math.max(1, Math.round(w * dpr));
    starCanvas.height = Math.max(1, Math.round(h * dpr));
    starCanvas.style.width = `${fixed(w)}px`;
    starCanvas.style.height = `${fixed(h)}px`;
    const g = starCanvas.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const dot = (x, y, r) => {
      g.beginPath();
      g.arc(x, y, r, 0, 2 * Math.PI);
      g.fill();
    };
    const halo = (x, y, r, colour, alpha) => {
      const light = g.createRadialGradient(x, y, 0, x, y, r);
      light.addColorStop(0, `rgba(${colour}, ${alpha})`);
      light.addColorStop(1, `rgba(${colour}, 0)`);
      g.fillStyle = light;
      dot(x, y, r);
    };
    if (stars > 0) {
      g.globalAlpha = stars;
      for (let i = 0, n = Math.round(w * h / STARS.per); i < n; i++) {
        const q = k => noise(17.3 * i + k), y = h * q(2) ** 1.35;
        g.fillStyle = `rgba(235, 242, 255, ${((0.3 + 0.7 * q(4)) * (1 - 0.75 * y / h)).toFixed(3)})`;
        dot(q(1) * w, y, 0.45 + 1.1 * q(3) ** 3);
      }
      for (const [fx, fy, s] of STARS.bright) {
        const x = fx * w, y = fy * h;
        halo(x, y, 2.4 * s, '225, 236, 255', 0.5);
        g.strokeStyle = 'rgba(240, 246, 255, 0.75)';
        g.lineWidth = 0.75;
        g.beginPath();
        g.moveTo(x - 1.6 * s, y);
        g.lineTo(x + 1.6 * s, y);
        g.moveTo(x, y - 1.6 * s);
        g.lineTo(x, y + 1.6 * s);
        g.stroke();
        g.fillStyle = '#fff';
        dot(x, y, 1.4);
      }
      // Today's moon (time.js): a faint dark disc, the part of it that is lit, on the side the sun is,
      // and a soft glow round it. A new moon is not drawn.
      const { lit, right } = state.time.moon, [fx, fy, size] = STARS.moon;
      if (lit >= 0.03) {
        const x = fx * w, y = fy * h, r = Math.max(STARS.least, size * h);
        const glow = g.createRadialGradient(x, y, r, x, y, 4.5 * r);
        glow.addColorStop(0, `rgba(255, 244, 214, ${(0.28 * (0.4 + 0.6 * lit)).toFixed(3)})`);
        glow.addColorStop(1, 'rgba(255, 244, 214, 0)');
        g.fillStyle = glow;
        dot(x, y, 4.5 * r);
        g.fillStyle = 'rgba(60, 78, 128, 0.55)';
        dot(x, y, r);
        g.save();
        g.translate(x, y);
        if (!right) g.scale(-1, 1);
        g.fillStyle = '#fff6df';
        g.beginPath();
        g.moveTo(0, -r);
        g.arc(0, 0, r, -Math.PI / 2, Math.PI / 2);   // the lit limb, round the right
        g.ellipse(0, 0, r * Math.abs(1 - 2 * lit), r, 0, Math.PI / 2, -Math.PI / 2, lit < 0.5);   // back up the terminator
        g.fill();
        g.restore();
      }
    }
    if (evening > 0) {
      const [fx, fy, s] = STARS.evening, x = fx * w, y = fy * h;
      g.globalAlpha = evening;
      halo(x, y, 3 * s, '255, 246, 228', 0.55);
      g.fillStyle = '#fff';
      dot(x, y, 1.8);
    }
    g.globalAlpha = 1;
  }

  // The surf: in the fall the sky comes into the window like the tide on a beach, the window's top
  // edge being the shore (window px, y down from that edge); it is made of cloud and blue sky, not
  // water. Tide lines (broken lines of small cloud, each trailing a pale sheet of sky) form one after
  // another at the window's bottom edge and run up towards the top edge, slowing and crowding as they
  // go, thin and faint where they form and thicker and whiter the higher they get, so that several are
  // up at once in layers from bottom to top. The first, faintest ones stop short of the edge, hang a
  // moment and wash back a little, fraying into lace and leaving the sky a little deeper blue for a
  // moment, like wet sand; the harder ones reach the edge and throw up a row of cloud spray on it. The
  // cloud sea lying on the picture comes in at the bottom edge as the last and biggest line, the high
  // tide: it pushes the lines before it up into the edge (new ones still form just over it), hits the
  // edge with the biggest spray and, once the sky has run out, washes back down over the top of the
  // picture in layers, gone by the landing.
  // Everything is laid out here from the camera's fall, sampled every STEP ms, so a frame is a pure
  // function of time.
  const STEP = 5;
  const FRONT = 0.12;   // how far into the cloud sea the high tide rides, just over its billows (share of its depth)
  // The surf's colours (RGB) by day, at dusk and at night: its sheets of sky, the sky where a line has
  // washed back and the shadows under its lace. (Not the clouds' tint, which would turn these blues
  // teal at dusk and brown at night.)
  const TIDE = {
    sheet: [[238, 247, 255], [255, 236, 234], [150, 170, 214]],
    wet: [[26, 96, 180], [122, 76, 146], [14, 26, 70]],
    shade: [[58, 104, 168], [118, 90, 140], [8, 14, 40]],
  };
  // One of them at a time of day (0 to 2), as 'r, g, b'.
  const tideColour = (colours, tone) => {
    const k = Math.min(1, Math.floor(tone));
    return mix(colours[k], colours[k + 1], tone - k);
  };

  function layoutSurf(L) {
    const { win } = L, h = win.h, dpr = Math.min(2, window.devicePixelRatio || 1);
    surfCanvas.width = Math.max(1, Math.round(win.w * dpr));
    surfCanvas.height = Math.max(1, Math.round(h * dpr));
    surfCanvas.style.width = `${fixed(win.w)}px`;
    surfCanvas.style.height = `${fixed(h)}px`;
    layoutSea(L);
    puffSprites();   // cut and painted as soon as the cloud photos are in, so the fall never waits on them
    paintSea(L);
    L.surf = null;
    if (!L.shot) return;
    const camAt = t => L.camStart + (L.camEnd - L.camStart) * dropAt(t);
    const count = Math.ceil((BEAT.land - BEAT.fall) / STEP) + 1, at = k => BEAT.fall + k * STEP;
    // Where the cloud sea's front is, as the hand-held camera shows it (its slight zoom-in moves the
    // front a little away from the window's middle), and when the sky runs out: as the picture's top
    // reaches the edge.
    const front = new Float32Array(count);
    let end = -1;
    for (let k = 0; k < count; k++) {
      const t = at(k), y = -camAt(t) - (1 - FRONT) * L.sea.height;
      front[k] = h / 2 + (1 + AIM.zoom * aimOff(t)) * (y - h / 2);
      if (end < 0 && camAt(t) >= 0) end = k;
    }
    if (end < 0) end = count - 1;
    const fu = Math.min(16, Math.max(7, 0.011 * (win.w + h)));   // the surf's unit: a small puff's radius
    const S = { dpr, ctx: surfCanvas.getContext('2d'), fu, h, front, lines: [], spots: [] };
    // How far down the high tide may veil the picture as it washes back: its top third, but no lower
    // than just past the top of the pair's heads (on a phone they sit high), so the faces stay clear.
    S.veil = Math.min(0.34 * h, L.shot.faces.y0 - win.y + 0.08 * h);
    // The high tide comes in as the sea's front comes in at the bottom edge, hits the top edge as the
    // front gets there and is held there until the sky has run out. The surf is in the sky's time of day
    // (from), and as the sea fills the window, just before the hit, the camera goes into the picture's
    // (to, the sea's; drawSurf).
    const rise = front.findIndex(y => y < 1.05 * h);
    const hit = rise < 0 ? -1 : Math.max(rise + 12, front.findIndex(y => y <= 0)), stay = at(Math.max(end, hit + 6));
    S.from = state.time.sky;
    S.to = L.sea.tone;
    S.into = S.from !== S.to && rise >= 0 ? at(hit) - 80 : null;
    // The tide lines before it, one after another, sooner and sooner (80 ms apart at first, 50 later),
    // until the sea's front is too high for one to form under those already up. Each comes harder than
    // the one before: the first are faint, run up quickly and stop short of the edge, the later ones
    // take longer and run all the way to the edge, and the weaker a line, the less of the window's width
    // it runs along.
    for (let j = 0, t0 = BEAT.fall + 15; ; j++, t0 += lerp(80, 50, smooth(0, 6, j))) {
      const k = Math.round((t0 - BEAT.fall) / STEP);
      if (k >= count || front[k] < 0.7 * h) break;
      const n = q => noise(23.1 * j + q), s = lerp(0.4, 1.3, smooth(0, 5, j)) * (0.9 + 0.2 * n(5)), hard = Math.min(1, s);
      const yTop = h * (1 - lerp(0.84, 1.03, smooth(0, 3, j)) * (0.97 + 0.06 * n(3))), short = 0.3 * (1 - hard);
      S.lines.push(tideLine(n, win, {
        t0, up: lerp(280, 380, smooth(0, 4, j)) * (0.92 + 0.16 * n(1)), hang: 40, back: lerp(320, 260, hard) * (0.85 + 0.3 * n(4)),
        y0: 1.04 * h, yTop, backTo: yTop + 0.16 * h, s, sheet: h * (0.1 + 0.08 * hard),
        xa: win.w * (-0.1 + short * n(6)), xb: win.w * (1.1 - short * n(7)),
      }));
    }
    // The high tide: the sea's front comes in as the biggest line of all, tilted like the sea under the
    // hand-held camera, and rides up with it; it hits the edge and is held there while the sea runs in,
    // then washes back down over the top of the picture once the sky has run out, two thinner lines
    // peeling off it on the way, all gone by the landing.
    if (rise >= 0) {
      const t0 = at(rise), ebb = BEAT.land - 40 - stay, y0 = Math.min(0.34 * h, S.veil);
      // each: when it peels off once the sky has run out (ms), how far back it washes (share of y0), how hard
      [[0, 0.9, 2.4], [20, 0.3, 1.3], [45, 0.58, 1]].forEach(([delay, depth, s], j) => {
        const n = q => noise(23.1 * (40 + j) + q), peel = j > 0;
        const run = peel
          ? { t0: stay + delay, up: 0, hang: 0, back: ebb - delay, yTop: 0.005 * h, sheet: 0.04 * h }
          : { t0, up: at(hit) - t0, hang: stay - at(hit) + 30, back: ebb - 30, ride: true, yTop: -0.012 * h, sheet: 0.16 * h,
            size: 1.4, tilt: win.w * Math.sin(AIM.r * Math.PI / 180) };
        S.lines.push(tideLine(n, win, { ...run, y0: 0, backTo: depth * y0, s, high: true, peel, xa: -0.1 * win.w, xb: 1.1 * win.w }));
      });
    }
    // Where a line first reaches the edge with its highest crest (unless it is pushed into the edge
    // there), it throws up a burst of spray on it; the high tide throws up burst after burst while the
    // sea runs into the edge, bigger and bigger until the sky runs out (drawSpray).
    const touches = 0.012 * h;
    S.sprays = [];
    for (const line of S.lines) {
      if (line.peel) continue;
      for (let t = line.t0; t < line.t0 + line.up + line.hang + line.back; t += STEP) {
        const q = tideAt(S, line, t);
        if (q.y - 1.6 * line.amp - Math.abs(line.tilt) / 2 > touches) continue;
        const y = (tideAt(S, line, t + 40) || q).y;
        if (line.ride) {
          for (let i = 0, a = t; a <= stay + 10; i++, a += 45) {
            S.sprays.push({ line, at: a, y, s: lerp(1.4, 2.6, clamp01((a - t) / Math.max(1, stay - t))), seed: line.seed + 7.3 * i });
          }
        } else if (q.squeeze > 0.12) {
          S.sprays.push({ line, at: t, y, s: line.s, seed: line.seed });
        }
        break;
      }
    }
    // Spots along the edge where the spray goes up.
    for (let i = 0, x = -fu; x < win.w + 2 * fu; i++, x += 1.2 * fu) S.spots.push({ x, seed: 5.3 * i });
    L.surf = S;
  }

  // A tide line laid out by layoutSurf: its run (o, see tideAt) and, from n, its shape: how wavy and
  // tilted it lies and where it breaks, and how big its lace is (o may set the tilt and the size).
  function tideLine(n, win, o) {
    return {
      amp: win.h * (0.012 + 0.014 * n(8)) * (1 + 0.3 * Math.min(1.5, o.s)), f1: 0.5 + 0.9 * n(9), f2: 2 + 1.5 * n(10),
      f3: 6 + 4 * n(17), p1: n(11), p2: n(12), p3: n(18), tilt: (n(13) - 0.5) * 0.03 * win.h, g1: n(14), g2: n(15),
      seed: 97 * n(16), size: 1, ...o,
    };
  }

  // Where the cloud sea's front is at time t (window px under the edge).
  function frontAt(S, t) {
    const i = Math.min(S.front.length - 1, Math.max(0, (t - BEAT.fall) / STEP)), j = Math.min(S.front.length - 2, Math.floor(i));
    return lerp(S.front[j], S.front[j + 1], i - j);
  }

  // Where a tide line is at time t: how far under the edge (window px, before its waviness), how much of
  // it is left (alpha), how far it has frayed into lace and how far it has washed back (0 to 1), and how
  // far the cloud sea has pushed it up into the edge (squeeze: 1 until the sea comes into the window, 0
  // at the edge); null before it forms and once it is gone. It runs up slowing (the high tide rides on
  // the sea's front instead), hangs a moment and washes back. The sea pushes the lines before it into
  // the edge keeping their order, so they crowd ever closer under it, and they are gone into the high
  // tide by the time it gets there.
  function tideAt(S, line, t) {
    const s = t - line.t0;
    if (s < 0 || s >= line.up + line.hang + line.back) return null;
    let q;
    if (s < line.up && line.ride) {
      q = { y: Math.max(line.yTop, frontAt(S, t)), alpha: 1, fray: 0, washed: 0, riding: true };
    } else if (s < line.up) {
      const p = s / line.up;
      q = { y: lerp(line.y0, line.yTop, 1 - (1 - p) ** 2), alpha: ease.out(clamp01(p / 0.2)), fray: 0, washed: 0 };
    } else {
      const p = clamp01((s - line.up - line.hang) / line.back);
      q = { y: lerp(line.yTop, line.backTo, smooth(0, 1, p)), alpha: 1 - smooth(0.45, 1, p), fray: smooth(0, 0.8, p), washed: p };
    }
    q.squeeze = line.high ? 1 : clamp01(frontAt(S, t) / S.h);
    q.y *= q.squeeze;
    q.kept = smooth(0.05, 0.32, q.squeeze);
    q.alpha *= q.kept;
    return q;
  }

  // How far a line has grown when it is y under the edge (0 where it forms at the bottom edge, 1 at the
  // top edge): it is thin and faint where it forms and thick and white near the top edge.
  function growth(S, y) {
    return (1 - clamp01(y / S.h)) ** 1.2;
  }

  // A tide line's waviness at x (window px, added to how far under the edge it is).
  function tideOffset(line, x, w) {
    const u = x / w;
    return line.amp * (Math.sin(2 * Math.PI * (line.f1 * u + line.p1)) + 0.45 * Math.sin(2 * Math.PI * (line.f2 * u + line.p2))
      + 0.15 * Math.sin(2 * Math.PI * (line.f3 * u + line.p3))) + line.tilt * (u - 0.5);
  }

  // How much is left of a tide line towards its ends (0 to 1).
  function tideEnds(line, x, w) {
    return smooth(line.xa, line.xa + 0.1 * w, x) * (1 - smooth(line.xb - 0.1 * w, line.xb, x));
  }

  // How much of a tide line there is at x (0 to 1): it breaks here and there, the more the weaker it is
  // and the further it has frayed.
  function tideHere(line, x, w, fray) {
    const u = x / w, gaps = 0.5 + 0.3 * Math.sin(2 * Math.PI * (3.1 * u + line.g1)) + 0.2 * Math.sin(2 * Math.PI * (7.7 * u + line.g2));
    const level = 0.12 + 0.25 * (1 - Math.min(1, line.s)) + 0.45 * fray;
    return smooth(level - 0.08, level + 0.08, gaps) * tideEnds(line, x, w);
  }

  // The cloud sea: a deck of low cloud lying on the picture's top edge, the last of the sky the camera
  // falls through (window px, placed like the clouds). It is painted from the cloud photos once they
  // are in (paintSea) and tinted like the clouds for the time of day it lies in (tone): a picture's own
  // if it is tagged with one, which the camera goes into as the sea comes in; else the sky's, which
  // then stays.
  function layoutSea(L) {
    const { win } = L, dpr = Math.min(2, window.devicePixelRatio || 1);
    const sea = { x: -0.1 * win.w, width: 1.2 * win.w, height: SEA * win.h, parallax: 1, opacity: 1, dpr, painted: false };
    seaCanvas.width = Math.max(1, Math.round(sea.width * dpr));
    seaCanvas.height = Math.max(1, Math.round(sea.height * dpr));
    seaCanvas.style.width = `${fixed(sea.width)}px`;
    seaCanvas.style.height = `${fixed(sea.height)}px`;
    const s = state.scene;
    sea.tone = s && PERIODS.includes(s.time) ? PERIODS.indexOf(s.time) : state.time.sky;
    seaCanvas.style.filter = tintFilter(tintAt(sea.tone));
    L.sea = sea;
  }

  // Sakura petals riding in on the light, inside the window (window px): each comes in past the
  // window's top-right corner at its own moment and drifts down to the left, turning and flipping
  // over. They slow down while HELLO is built (petalClock), and HELLO's rings, the one it sends out
  // as it breaks up included, only nudge them. When the camera drops they rise with the sky, faster
  // than the clouds (they are nearer, the bigger ones nearest), into the surf on the top edge.
  function layoutPetals(L) {
    const { win } = L, dpr = Math.min(2, window.devicePixelRatio || 1);
    petalCanvas.width = Math.max(1, Math.round(win.w * dpr));
    petalCanvas.height = Math.max(1, Math.round(win.h * dpr));
    petalCanvas.style.width = `${fixed(win.w)}px`;
    petalCanvas.style.height = `${fixed(win.h)}px`;
    const g = petalCanvas.getContext('2d');
    // the lit and the shaded face, in the petal's own units: deeper pink at the base, paler to the tip
    const face = (base, tip) => {
      const gradient = g.createLinearGradient(0, 1, 0, -0.9);
      gradient.addColorStop(0, base);
      gradient.addColorStop(1, tip);
      return gradient;
    };
    const unit = Math.min(5.5, Math.max(2.8, 0.0037 * (win.w + win.h)));   // half a petal's length, give or take
    const air = Math.min(11, Math.max(5.5, 0.0075 * (win.w + win.h)));     // how far the air sways them
    const onScreen = p => t => { const a = petalAt(p, t); return { x: win.x + a.x, y: win.y + a.y }; };
    const petals = Array.from({ length: PETALS }, (_, i) => {
      const n = k => noise(31.7 * i + k);
      const s = n(1), top = s < 0.62;   // in over the top edge's right part, or the right edge's top part
      const p = {
        t0: BEAT.flood + 1100 * n(2), size: unit * (0.7 + 0.6 * n(3)), near: 1.6 + 0.8 * n(3),
        x: top ? win.w * (0.4 + 0.7 * s / 0.62) : win.w + 2 * unit, y: top ? -2 * unit : 0.55 * win.h * (s - 0.62) / 0.38,
        vx: -win.w * (0.26 + 0.24 * n(4)), vy: win.h * (0.2 + 0.25 * n(5)),
        sway: air * (1 + 1.2 * n(6)), weave: 2.4 + 2.2 * n(7), phase: 2 * Math.PI * n(8),
        rot: 2 * Math.PI * n(9), spin: (n(10) < 0.5 ? -1 : 1) * (1 + 1.6 * n(11)),
        flip: 2 * Math.PI * n(12), flipRate: 2.2 + 2.8 * n(13),
      };
      // the ring HELLO sends out as it breaks up nudges them twice as hard as its first rings
      const gust = gustHit(L.motifs.gust, onScreen(p));
      p.rings = [...ringPasses(L, onScreen(p)), { at: gust.at, weight: 2, away: gust.away }];
      return p;
    });
    L.petals = { petals, dpr, ctx: g, lit: face('#f5a9c0', '#fff1f6'), shaded: face('#e796ae', '#fbd9e4') };
  }

  // The petals' clock (s): full speed as they ride in, easing down to 30% over half a second once
  // HELLO starts, so they hang in the sky round it.
  function petalClock(t) {
    const x = clamp01((t - BEAT.hello) / 500);
    const slowed = 500 * (x ** 3 - x ** 4 / 2) + Math.max(0, t - BEAT.hello - 500);   // the smoothstep's integral (ms)
    return (t - 0.7 * slowed) / 1000;
  }

  // A petal's own course (window px) and its turn and flip (radians), before any ring touches it.
  function petalAt(p, t) {
    const u = Math.max(0, petalClock(t) - petalClock(p.t0));
    return {
      x: p.x + p.vx * u + p.sway * Math.sin(p.weave * u + p.phase),
      y: p.y + p.vy * u + 0.4 * p.sway * Math.cos(1.3 * p.weave * u + p.phase),
      rot: p.rot + p.spin * u, flip: p.flip + p.flipRate * u,
    };
  }

  // HELLO letters are measured in the loaded display font and centred on the screen; the same
  // glyphs are rasterised once to seed the dust they break into.
  function layoutHello(L) {
    const size = L.portrait ? 0.185 * L.W : Math.min(260, Math.max(72, 0.15 * L.W));
    const hidden = helloSvg.style.display === 'none';
    show(helloSvg, true);   // text can only be measured while it is rendered
    const widths = hello.letters.map(({ letter, echo }) => {
      letter.setAttribute('font-size', size);
      echo.setAttribute('font-size', size);
      return letter.getComputedTextLength() || size * 0.8;
    });
    show(helloSvg, !hidden);
    const gap = -0.02 * size;
    const total = widths.reduce((a, b) => a + b, 0) + gap * (widths.length - 1);
    let x = (L.W - total) / 2;
    L.hello = { size, total, x0: x, base: L.H / 2 + 0.36 * size, cap: L.H / 2 - 0.36 * size, xs: [] };
    hello.letters.forEach(({ letter, echo }, i) => {
      L.hello.xs.push(x);
      letter.setAttribute('x', fixed(x));
      letter.setAttribute('y', fixed(L.hello.base));
      echo.setAttribute('x', fixed(x));
      echo.setAttribute('y', fixed(L.hello.base));
      x += widths[i] + gap;
    });
    L.hello.dust = seedDust(L, widths, gap);
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    dustCanvas.width = Math.round(L.W * dpr);
    dustCanvas.height = Math.round(L.H * dpr);
    L.dustScale = dpr;
  }

  function seedDust(L, widths, gap) {
    const h = L.hello, pad = Math.ceil(0.1 * h.size);
    const bw = Math.ceil(h.total + 2 * pad), bh = Math.ceil(h.base - h.cap + 2 * pad + 0.1 * h.size);
    const canvas = document.createElement('canvas');
    canvas.width = bw;
    canvas.height = bh;
    const g = canvas.getContext('2d');
    g.font = `${h.size}px "Archivo Black", system-ui, sans-serif`;
    g.fillStyle = '#000';
    let x = pad;
    widths.forEach((w, i) => { g.fillText('HELLO'[i], x, h.base - h.cap + pad); x += w + gap; });
    const data = g.getImageData(0, 0, bw, bh).data;
    const step = Math.max(3, Math.round(h.size / 42));
    const specks = [];
    for (let y = 0; y < bh; y += step) {
      for (let x = 0; x < bw; x += step) {
        if (data[(y * bw + x) * 4 + 3] > 128) specks.push([h.x0 - pad + x, h.cap - pad + y]);
      }
    }
    // keep an even sample when the word is very large
    const keep = Math.min(1, DUST / Math.max(1, specks.length));
    return specks.filter((_, i) => noise(i * 3.1) < keep).map(([x, y], i) => ({
      x, y, size: step * (0.55 + 0.5 * noise(i + 2)),
      dx: (noise(i + 5) - 0.25) * 0.22 * L.W, dy: -(0.04 + 0.22 * noise(i + 9)) * L.H,
      delay: ((x - h.x0) / h.total) * 320 + noise(i + 11) * 160, life: 650 + noise(i + 13) * 450,
      tint: noise(i + 17) < 0.3 ? '#59bff7' : noise(i + 17) < 0.6 ? '#1871c2' : '#1c8ad7',
    }));
  }

  function prepareFlock() {
    const L = state.layout;
    state.birds.forEach((bird, i) => {
      const [row, dx, dy, size, pose, tilt] = FLOCK[i];
      const rad = tilt * Math.PI / 180;
      Object.assign(bird, {
        row, pose, tilt, size: size * L.birdUnit,
        holdX: L.cx + dx * L.win.w * (L.portrait ? 1.1 : 1), holdY: L.cy + dy * L.win.h,
        dirX: Math.cos(rad), dirY: Math.sin(rad),   // unit vector along the flight
        delay: (row ? 50 : 0) + i * 9,
        leave: BEAT.leave + (row ? 110 : 0) + noise(i) * 180,
      });
    });
  }

  // ---------- camera ----------

  // Camera drop as a share of the way down: a slow sink through open sky while HELLO is built, then
  // one fast fall all the way to the ground that overshoots a little and settles.
  function dropAt(t) {
    return DRIFT * ease.inOut(seg(t, BEAT.hello - 200, BEAT.fall - BEAT.hello + 200))
      + (1 - DRIFT) * ease.drop(seg(t, BEAT.fall, BEAT.land - BEAT.fall));
  }

  function cameraAt(t) {
    const L = state.layout;
    return L.camStart + (L.camEnd - L.camStart) * dropAt(t);
  }

  // The camera falls a little off target (shifted and tilted) and is aimed at the pair only just
  // before landing; the landing itself jolts it like a hand-held camera, then it settles. Nothing
  // shakes before that. How far off target: shifted (window-width share), tilted (degrees) and
  // zoomed in (share; a slight zoom-in keeps the window edges covered).
  const AIM = { x: 0.035, r: 0.8, zoom: 0.075 };

  // How far off target the camera is (0 to 1): off as soon as it falls, on target just before landing.
  function aimOff(t) {
    return ease.out(seg(t, BEAT.fall, 300)) * (1 - ease.inOut(seg(t, BEAT.land - 380, 330)));
  }

  function handheld(t) {
    const L = state.layout, off = aimOff(t);
    const jolt = t > BEAT.land - 60 ? 5 * Math.exp(-(t - BEAT.land + 60) / 150) : 0;
    const wobble = (a, b, pa, pb) => 0.6 * Math.sin(t * a + pa) + 0.4 * Math.sin(t * b + pb);
    return {
      x: off * AIM.x * L.win.w + jolt * wobble(0.05, 0.08, 1.3, 4.1),
      y: jolt * wobble(0.045, 0.085, 2.7, 0.4),
      r: off * AIM.r + jolt * 0.06 * wobble(0.04, 0.07, 5.2, 2.2),
      zoom: 1 + AIM.zoom * off + 0.005 * jolt,
    };
  }

  // The window and the picture in it. The window is the framed shot until the camera lands, then
  // opens out to the whole screen. With a section open the opened window docks aside in the same way
  // (dock). Folding the picture away behind the section (fold) takes it back to the whole screen, so
  // the picture stands aside as far as the dock less the fold (aside); veil is how far it is folded
  // away behind a section that is open. Whatever the window's size on the way, the picture is framed
  // for it (frame): all of it in the middle, on the fill. In the fall the ground lies that far down
  // the sky (y, window-relative), and comes up the window as the camera drops onto it.
  function shotAt(t, camY) {
    const L = state.layout, e = L.shot ? ease.out(seg(t, BEAT.open, BEAT.openLen)) : 0;
    const d = e >= 1 || !L.shot ? ease.inOut(dock.value) : 0;
    const f = L.portrait ? 0 : ease.inOut(fold.value), aside = d * (1 - f);
    const at = dockedAt(L), R = at.rect;
    const open = { x: lerp(L.win.x, 0, e), y: lerp(L.win.y, 0, e), w: lerp(L.win.w, L.W, e), h: lerp(L.win.h, L.H, e) };
    const rect = { x: lerp(open.x, R.x, aside), y: lerp(open.y, R.y, aside), w: lerp(open.w, R.w, aside), h: lerp(open.h, R.h, aside) };
    const shot = { e, rect, at, dock: d, fold: f, aside, veil: d * f, faces: null };
    if (!L.shot) return shot;
    const frame = frameFor(rect, state.scene), y = (L.camEnd - camY) * (1 - e);
    const faces = { ...frame.faces, y0: frame.faces.y0 + y, y1: frame.faces.y1 + y };
    return Object.assign(shot, { frame, faces, y });
  }

  // ---------- rendering ----------

  // Where a bird is (screen space): it darts in along its heading, keeps gliding a little while the
  // frame is held, and accelerates away when it leaves.
  function birdPos(bird, t) {
    const L = state.layout;
    const arrive = ease.expoOut(seg(t, BEAT.snap + bird.delay, BEAT.snapLen));
    const along = -0.85 * L.W * (1 - arrive) + 0.012 * L.W * Math.max(0, t - BEAT.snap) / 1000
      + 0.9 * L.W * ease.in(seg(t, bird.leave, 700));
    return { x: bird.holdX + bird.dirX * along, y: bird.holdY + bird.dirY * along };
  }

  function drawFlock(t) {
    const L = state.layout;
    for (const bird of state.birds) {
      if (t < BEAT.snap + bird.delay) { hideBird(bird); continue; }
      const { x, y } = birdPos(bird, t);
      const gone = seg(t, bird.leave + 260, 160);
      const enter = ease.out(seg(t, BEAT.snap + bird.delay, BEAT.snapLen));
      const exit = ease.inOut(seg(t, bird.leave, 460));
      const pose = lerp(lerp(0.2, bird.pose, enter), 0.15, exit);
      if (gone < 1) poseBird(bird, x, y, bird.size, pose, bird.tilt, 1 - gone);
      else show(bird.g, false);
      // a speed streak trails each bird while it darts in or away
      const prev = birdPos(bird, t - 45);
      const run = Math.hypot(x - prev.x, y - prev.y);
      if (run > 3 && gone < 1) {
        const tail = 0.6 * bird.size, len = Math.min(run * 1.6, 0.4 * L.W);
        bird.streak.setAttribute('x1', fixed(x - bird.dirX * (tail + len)));
        bird.streak.setAttribute('y1', fixed(y - bird.dirY * (tail + len)));
        bird.streak.setAttribute('x2', fixed(x - bird.dirX * tail));
        bird.streak.setAttribute('y2', fixed(y - bird.dirY * tail));
        show(bird.streak, true);
      } else {
        show(bird.streak, false);
      }
      // leaving: the bird breaks into squares that fly on and up (as in the blue-sky film)
      for (const p of bird.pixels) {
        const k = seg(t, bird.leave + 240 + p.delay * 0.4, 560 + p.delay);
        if (k <= 0 || k >= 1) { show(p.el, false); continue; }
        const s = bird.size, side = p.side * s * (1 - 0.4 * k);
        const px = x + p.x * s + bird.dirX * p.fly * 0.12 * L.W * ease.out(k);
        const py = y + p.y * s + bird.dirY * p.fly * 0.12 * L.W * ease.out(k) - p.rise * 0.18 * L.H * ease.out(k);
        p.el.setAttribute('x', fixed(px - side / 2));
        p.el.setAttribute('y', fixed(py - side / 2));
        p.el.setAttribute('width', fixed(side));
        p.el.setAttribute('height', fixed(side));
        p.el.style.opacity = (1 - k).toFixed(3);
        show(p.el, true);
      }
    }
  }

  function drawTracking(t) {
    const visible = t >= BEAT.track && t < BEAT.frame + 120;
    const fade = 1 - seg(t, BEAT.frame, 120);
    const points = [];
    tracking.track.forEach(mark => {
      const bird = state.birds[TRACKED[mark.index]];
      const lockAt = BEAT.track + mark.index * 100;
      const p = ease.out(seg(t, lockAt, 160));
      if (!visible || p <= 0) { show(mark.g, false); return; }
      const side = bird.size * 2.1 * (1 + 0.8 * (1 - p));
      const { x, y } = birdPos(bird, t);
      const x0 = x - side / 2, y0 = y - side / 2;
      mark.box.setAttribute('x', fixed(x0));
      mark.box.setAttribute('y', fixed(y0));
      mark.box.setAttribute('width', fixed(side));
      mark.box.setAttribute('height', fixed(side));
      mark.corners.setAttribute('d', bracketPath(x0, y0, x0 + side, y0 + side, Math.max(4, side * 0.18)));
      // two rings ping outwards from the locked bird
      mark.rings.forEach((ring, j) => {
        const k = seg(t, lockAt + 120 + j * 160, 520);
        ring.setAttribute('cx', fixed(x));
        ring.setAttribute('cy', fixed(y));
        ring.setAttribute('r', fixed(side * (0.5 + 1.1 * ease.out(k))));
        ring.style.opacity = k > 0 && k < 1 ? (0.9 * (1 - k)).toFixed(3) : 0;
      });
      // a callout: a leader line up and to the right, ending in a small square
      const c = ease.out(seg(t, lockAt + 140, 220));
      const lx = x0 + side, ly = y0, run = 14 * c, reach = 34 * c;
      mark.callout.setAttribute('points', `${fixed(lx)},${fixed(ly)} ${fixed(lx + run)},${fixed(ly - run)} ${fixed(lx + run + reach)},${fixed(ly - run)}`);
      const tag = Math.max(0, 6 * ease.back(seg(t, lockAt + 300, 200)));
      attrs(mark.tag, { x: lx + run + reach, y: ly - run - tag / 2, width: tag, height: tag });
      mark.g.style.opacity = (p * fade).toFixed(3);
      show(mark.g, true);
      points.push(`${fixed(x)},${fixed(y)}`);
    });
    // a dashed line strings the tracked birds together, like the windows of the blue-sky network
    const linkIn = seg(t, BEAT.track + 520, 260) * fade;
    tracking.link.setAttribute('points', points.join(' '));
    show(tracking.link, visible && points.length > 1 && linkIn > 0);
    tracking.link.style.opacity = linkIn.toFixed(3);
  }

  function drawGuides(t) {
    const L = state.layout, g = paper, w = L.win;
    const fade = 1 - seg(t, BEAT.frame, 260);
    const visible = fade > 0;
    // hairlines from the shot's centre to the four screen edges, with ticks along the horizontal one
    const reach = ease.out(seg(t, 0, 520));
    const ends = [[0, L.cy], [L.W, L.cy], [L.cx, 0], [L.cx, L.H]];
    g.lines.forEach((line, i) => {
      const [ex, ey] = ends[i];
      line.setAttribute('x1', fixed(L.cx));
      line.setAttribute('y1', fixed(L.cy));
      line.setAttribute('x2', fixed(L.cx + (ex - L.cx) * reach));
      line.setAttribute('y2', fixed(L.cy + (ey - L.cy) * reach));
      line.style.opacity = fade.toFixed(3);
      show(line, visible);
    });
    let ticks = '';
    for (let i = 1, step = 32; i * step < w.w / 2 * reach; i++) {
      const len = i % 5 ? 4 : 9;
      for (const sign of [-1, 1]) ticks += `M${fixed(L.cx + sign * i * step)} ${fixed(L.cy - len)}v${2 * len}`;
    }
    g.ticks.setAttribute('d', ticks);
    g.ticks.style.opacity = fade.toFixed(3);
    show(g.ticks, visible);
    const sx = L.cx + 0.12 * w.w, scaleIn = ease.out(seg(t, 380, 260));
    g.scale.setAttribute('x1', fixed(sx));
    g.scale.setAttribute('x2', fixed(sx + 64 * scaleIn));
    g.scale.setAttribute('y1', fixed(L.cy - 6));
    g.scale.setAttribute('y2', fixed(L.cy - 6));
    g.scale.style.opacity = fade.toFixed(3);
    show(g.scale, visible && scaleIn > 0);
    // a ring drawn round the shot with a heavy arc running round it, and a small target at its centre
    const r = 0.42 * Math.min(w.w, w.h);
    for (const ring of [g.ring, g.arc]) {
      ring.setAttribute('cx', fixed(L.cx));
      ring.setAttribute('cy', fixed(L.cy));
      ring.setAttribute('r', fixed(r));
      ring.setAttribute('transform', `rotate(-90 ${fixed(L.cx)} ${fixed(L.cy)})`);
      ring.style.opacity = fade.toFixed(3);
      show(ring, visible);
    }
    g.ring.style.strokeDashoffset = (1 - ease.inOut(seg(t, 180, 760))).toFixed(3);
    g.arc.style.strokeDashoffset = (-t / 2600).toFixed(4);
    g.arc.style.opacity = (ease.out(seg(t, 600, 300)) * fade).toFixed(3);
    g.dot.setAttribute('cx', fixed(L.cx));
    g.dot.setAttribute('cy', fixed(L.cy));
    g.dot.style.opacity = (ease.out(seg(t, 260, 200)) * fade).toFixed(3);
    show(g.dot, visible);
    // the window's outline is drawn first, then handed over to the viewfinder corners
    g.outline.setAttribute('x', fixed(w.x));
    g.outline.setAttribute('y', fixed(w.y));
    g.outline.setAttribute('width', fixed(w.w));
    g.outline.setAttribute('height', fixed(w.h));
    g.outline.style.strokeDashoffset = (1 - ease.inOut(seg(t, 300, 800))).toFixed(3);
    const outlineFade = 1 - seg(t, BEAT.shutter + 60, 200);
    g.outline.style.opacity = (0.8 * outlineFade).toFixed(3);
    show(g.outline, outlineFade > 0);
  }

  // The margin ornaments come in once the shot is framed: the outline squares and diagonals are
  // drawn, the cross marks show and the pixel squares switch on one by one. The bar groups in the
  // bottom corners grow in at the start.
  function drawOrnaments(t) {
    ornaments.clusters.forEach((c, i) => {
      const t0 = BEAT.frame + 140 + i * 180;
      c.squares.forEach((el, j) => { el.style.strokeDashoffset = (1 - ease.inOut(seg(t, t0 + j * 90, 420))).toFixed(3); });
      c.diagonals.forEach((el, j) => { el.style.strokeDashoffset = (1 - ease.out(seg(t, t0 + 220 + j * 140, 380))).toFixed(3); });
      c.crosses.forEach((el, j) => { el.style.opacity = ease.out(seg(t, t0 + 320 + j * 70, 160)).toFixed(3); });
      c.pixels.forEach((el, j) => { el.style.opacity = t >= t0 + 420 + j * 45 ? '1' : '0'; });
    });
    const grow = (el, delay, origin) => {
      el.style.transformOrigin = origin;
      el.style.transform = `scaleX(${ease.out(seg(t, 200 + delay, 380)).toFixed(3)})`;
    };
    const { left, right } = ornaments;
    grow(left.rule, 0, 'left center');
    grow(left.bar, 80, 'left center');
    grow(right.bar, 40, 'right center');
    grow(right.rule, 120, 'right center');
    grow(right.blinds, 200, 'right center');
  }

  // Butterflies and feathers come with HELLO: each is drawn where it sits (outline, then colour),
  // comes alive, calmly (a few wingbeats and a glide, or a falling leaf's swing), and is blown off
  // the screen when HELLO's ring reaches it. The pinned specimen is drawn like a plate and only
  // trembles as the ring passes.
  function drawMotifs(t) {
    const M = state.layout.motifs;
    drawSpecimen(t, M.specimen);
    motifs.butterflies.forEach((node, i) => drawButterfly(t, node, M.butterflies[i], M.fly));
    motifs.feathers.forEach((node, i) => drawFeather(t, node, M.feathers[i], M.quill));
  }

  // Outlines drawn on, then the colour fills in.
  function drawIn(lines, t, start, length) {
    const line = (1 - ease.inOut(seg(t, start, length))).toFixed(3);
    const fill = ease.out(seg(t, start + 0.75 * length, 0.6 * length)).toFixed(3);
    for (const el of lines) {
      el.style.strokeDashoffset = line;
      el.style.fillOpacity = fill;
    }
  }

  // How far HELLO's ring has blown something since it reached it (px), and how long ago that was (s).
  function blown(t, hit) {
    const since = Math.max(0, t - hit) / 1000;
    return { since, push: 300 * since + 2200 * since * since };
  }

  // How far the rings HELLO bursts out with have nudged something: each pass pushes it gently out
  // from the word and lets it drift back (furthest 0.3 s after the ring), without any shaking. Unit
  // amounts; the heavy ring counts half again.
  function nudged(t, rings) {
    const n = { x: 0, y: 0 };
    for (const ring of rings) {
      const s = (t - ring.at) / 1000;
      if (s <= 0) continue;
      const push = ring.weight * (s / 0.3) * Math.exp(1 - s / 0.3);
      n.x += ring.away[0] * push;
      n.y += ring.away[1] * push;
    }
    return n;
  }

  // The signed turn (degrees) from heading a to heading b, the short way round.
  const turnTo = (a, b) => ((((b - a) % 360) + 540) % 360) - 180;

  // A butterfly's own course (screen px), before any ring touches it: from its spot it drifts slowly
  // along dir, weaving a little from side to side and heading the way it goes. Its wings beat a few
  // times (FLAP_HZ, eased in once it is coloured in), then it glides with them open, and again;
  // each beat bobs it on a little.
  function butterflyAt(b, t) {
    const tau = Math.max(0, t - b.alive) / 1000, [dx, dy] = b.dir;
    const beating = b.flaps / FLAP_HZ, c = (tau + b.offset) % (beating + b.glide);
    const beat = c < beating ? Math.sin(Math.PI * FLAP_HZ * c) ** 2 * ease.inOut(seg(t, b.alive, 400)) : 0;
    const along = b.speed * tau + b.bob * beat;
    const across = b.meander * (Math.sin(b.weave * tau + b.phase) - Math.sin(b.phase));
    const side = b.meander * b.weave * Math.cos(b.weave * tau + b.phase);   // d(across)/d(tau)
    return {
      x: b.x + dx * along - dy * across, y: b.y + dy * along + dx * across, open: 1 - 0.85 * beat,
      heading: Math.atan2(dy * b.speed + dx * side, dx * b.speed - dy * side) * 180 / Math.PI + 90,
    };
  }

  // A feather's own course: it swings from side to side as it sinks, like a falling leaf (a swing
  // every SWING / 2 seconds), lowest in the middle of each swing, tilted the way it swings and
  // slowly turning over; eased in from where it was drawn.
  function featherAt(f, t) {
    const tau = Math.max(0, t - f.alive) / 1000, life = ease.inOut(seg(t, f.alive, 500));
    const phi = 2 * Math.PI * tau / SWING + f.phase;
    return {
      x: f.x + life * f.swing * (Math.sin(phi) - Math.sin(f.phase)),
      y: f.y + life * (f.fall * tau + f.dip * (Math.cos(2 * phi) - Math.cos(2 * f.phase))),
      tilt: f.tilt + life * 24 * (Math.cos(phi) - Math.cos(f.phase)),
      turn: 1 - life * 0.25 * (0.5 - 0.5 * Math.cos(1.2 * tau)),
    };
  }

  function offscreen(x, y) {
    const L = state.layout;
    return x < -80 || y < -80 || x > L.W + 80 || y > L.H + 80;
  }

  // The pinned specimen is drawn like a plate: the crosses on the two fixed points first, then a
  // small square runs the orbit from just under their middle, faster and faster, leaving it drawn
  // behind it (a loop or two round each wing slowly enough to follow, then the rest of the wings);
  // the body comes in over it with the dimension line under it, and the pin goes in last.
  function drawSpecimen(t, p) {
    const node = motifs.specimen, T = BEAT.hello, { orbit } = node;
    // pinned, so the rings only flex its wings: a little as HELLO's first rings pass, a quick
    // tremble when the last one blows the others away
    const { since } = blown(t, p.blow.at), n = nudged(t, p.rings);
    const gust = since > 0 ? 0.45 * Math.exp(-since / 0.15) * Math.abs(Math.sin(2 * Math.PI * 8 * since)) : 0;
    const squeeze = 1 - Math.min(0.6, gust + 0.1 * Math.hypot(n.x, n.y));
    node.crosses.forEach((el, i) => {
      const arm = 3 * ease.out(seg(t, T + 60 * i, 150)), x = p.x + (2 * i - 1) * LORENZ.wing * p.u * squeeze;
      el.setAttribute('d', `M${fixed(x - arm)} ${fixed(p.mid)}h${fixed(2 * arm)}M${fixed(x)} ${fixed(p.mid - arm)}v${fixed(2 * arm)}`);
      show(el, arm > 0);
    });
    const run = seg(t, T + 50, 650), head = orbitAt(orbit, LORENZ.span * Math.expm1(3 * run) / Math.expm1(3));
    show(node.g, run > 0);
    // the orbit is a long path: restyled only when its trace or its squeeze has moved on
    const drawn = (1 - head.drawn).toFixed(4), wings = `scale(${squeeze.toFixed(3)} 1)`;
    if (node.drawn !== drawn) { node.path.style.strokeDashoffset = drawn; node.drawn = drawn; }
    if (node.squeezed !== wings) { node.wings.setAttribute('transform', wings); node.squeezed = wings; }
    const tracer = 1 - seg(t, T + 700, 100), side = p.tracer;
    show(node.tracer, run > 0 && tracer > 0);
    attrs(node.tracer, { x: p.x + head.x * p.u * squeeze - side / 2, y: p.mid + head.y * p.u - side / 2, width: side, height: side });
    node.tracer.style.opacity = tracer.toFixed(3);
    const body = ease.out(seg(t, T + 650, 150));
    show(node.torso, body > 0);
    node.torso.style.opacity = body.toFixed(3);
    // the dimension line measures the orbit from wing tip to wing tip
    const dim = ease.out(seg(t, T + 650, 160)), y = p.y + 1.15 * p.a;
    const x0 = p.x + orbit.left * p.u * dim, x1 = p.x + orbit.right * p.u * dim;
    node.dim.setAttribute('d', `M${fixed(x0)} ${fixed(y - 4)}v8M${fixed(x0)} ${fixed(y)}H${fixed(x1)}M${fixed(x1)} ${fixed(y - 4)}v8`);
    show(node.dim, dim > 0);
    attrs(node.pin, { cx: p.x, cy: p.bodyY - 0.12 * p.bodyK, r: Math.max(0, 1.9 * ease.back(seg(t, T + 800, 100))) });
  }

  function drawButterfly(t, node, b, size) {
    if (t < b.drawn) { show(node.g, false); return; }
    drawIn(node.lines, t, b.drawn, 240);
    node.body.forEach(el => { el.style.opacity = ease.out(seg(t, b.drawn + 120, 160)).toFixed(3); });
    node.veins.forEach(el => { el.style.opacity = (0.38 * ease.out(seg(t, b.drawn + 150, 200))).toFixed(3); });
    // HELLO's first rings nudge it (about 10 px); the last one carries it off, and it turns to run
    // before the wind, its wings beating
    const at = butterflyAt(b, t), n = nudged(t, b.rings), { since, push } = blown(t, b.blow.at);
    const x = at.x + 10 * n.x + b.blow.away[0] * push, y = at.y + 10 * n.y + b.blow.away[1] * push;
    show(node.g, !offscreen(x, y));
    if (offscreen(x, y)) return;
    const wind = Math.atan2(b.blow.away[1], b.blow.away[0]) * 180 / Math.PI + 90;
    const heading = at.heading + turnTo(at.heading, wind) * ease.inOut(clamp01(since / 0.4));
    const open = lerp(at.open, 1 - 0.8 * Math.sin(Math.PI * 2.5 * since) ** 2, clamp01(since / 0.2));
    node.wings.forEach(w => w.flap.setAttribute('transform', `scale(${open.toFixed(3)} 1)`));
    node.g.setAttribute('transform', `translate(${fixed(x)} ${fixed(y)}) rotate(${fixed(heading)}) scale(${size.toFixed(2)})`);
  }

  function drawFeather(t, node, f, size) {
    if (t < f.drawn) { show(node.g, false); return; }
    drawIn([node.vane], t, f.drawn, 260);
    node.shaft.style.opacity = node.down.style.opacity = ease.out(seg(t, f.drawn + 160, 180)).toFixed(3);
    // HELLO's first rings nudge it (about 8 px); the last one carries it off, slowly turning and
    // rolling over
    const at = featherAt(f, t), n = nudged(t, f.rings), { since, push } = blown(t, f.blow.at);
    const x = at.x + 8 * n.x + f.blow.away[0] * push, y = at.y + 8 * n.y + f.blow.away[1] * push;
    show(node.g, !offscreen(x, y));
    if (offscreen(x, y)) return;
    const tilt = at.tilt + f.spin * 150 * since, roll = at.turn * Math.cos(2.2 * since);
    node.g.setAttribute('transform', `translate(${fixed(x)} ${fixed(y)}) rotate(${fixed(tilt)}) scale(${(size * roll).toFixed(3)} ${size.toFixed(2)})`);
  }

  function drawWindow(t, camY, shot) {
    const L = state.layout;
    const taken = t >= BEAT.shutter + 30;   // the picture exists once the shutter has fired
    world.style.visibility = taken ? 'visible' : 'hidden';
    tiles.style.visibility = taken ? 'visible' : 'hidden';
    if (taken) {
      for (const tile of L.tiles) {
        const k = ease.in(seg(t, BEAT.reveal + tile.delay, 180));
        tile.el.style.transform = k >= 1 ? 'scale(0)' : `scale(${(1 - k).toFixed(3)})`;
      }
    }
    windowFlash.style.opacity = (taken ? 0.7 * (1 - ease.out(seg(t, BEAT.shutter + 30, 520))) : 0).toFixed(3);
    const blink = t < BEAT.shutter + 30 ? seg(t, BEAT.shutter, 30) : 1 - seg(t, BEAT.shutter + 30, 70);
    shutter.style.opacity = (0.72 * blink).toFixed(3);

    // the equation strip: its frame is drawn left to right, the equations come up one after
    // another, and the flood of light washes it all out
    const washed = 1 - seg(t, BEAT.flood + 80, 380), stripShown = t >= BEAT.strip && washed > 0;
    strip.style.opacity = stripShown ? washed.toFixed(3) : 0;
    // (washed out, it is put away: unseen, a layer still keeps its tiles in the GPU memory the page's
    // layers share, which runs short at the end of the opening; makeMeet)
    strip.style.visibility = stripShown ? '' : 'hidden';
    strip.style.setProperty('--open', ease.inOut(seg(t, BEAT.strip, 320)).toFixed(3));
    stripItems.forEach((item, i) => item.style.setProperty('--in', ease.out(seg(t, BEAT.strip + 220 + i * 80, 300)).toFixed(3)));
    const flood = t < BEAT.hello ? ease.out(seg(t, BEAT.flood, 300)) : 1 - ease.inOut(seg(t, BEAT.hello, 600));
    glow.style.opacity = (flood * L.flood).toFixed(3);
    glow.style.visibility = flood > 0 ? '' : 'hidden';   // (out, it is put away as the strip is)
    glow.style.transform = `scale(${(0.85 + 0.5 * seg(t, BEAT.flood, 850)).toFixed(3)})`;

    // the window: the framed shot, opening out to the whole screen after the landing
    placeWindow(shot.rect);
    stage.classList.toggle('full', shot.e > 0.5);
    // folded away behind a section, the picture is blurred (below) as much as the visitor set, and
    // pushed in to match
    stage.classList.toggle('folded', shot.veil > 0);
    const blur = PICTURE_BLUR.max * prefs.blur * shot.veil;

    // the whole world moves with the hand-held camera; the window's frame stays put
    const hand = handheld(t), zoom = hand.zoom * (1 + PICTURE_BLUR.zoom * blur);
    world.style.transform = `translate(${fixed(hand.x)}px, ${fixed(hand.y)}px) rotate(${hand.r.toFixed(3)}deg) scale(${zoom.toFixed(4)})`;

    const dropped = camY - L.camStart;
    sky.style.transform = `translate3d(0, ${fixed(L.skyTop - camY)}px, 0)`;
    // once the window has opened out, the picture and the fill round it cover the sky (unless blurred,
    // which softens their edges, or until the fill is painted); it is put away meanwhile, its layer
    // (taller than the screen) with it (as the strip, above)
    const covered = Boolean(L.shot && state.washFrom) && t >= BEAT.open + BEAT.openLen && blur === 0;
    sky.style.visibility = covered ? 'hidden' : '';
    // the stars stay where they are in the window, fading as the camera goes down, gone before it lands
    const starsLeft = L.stars ? 1 - smooth(0.05, 0.75, dropped / (L.camEnd - L.camStart || 1)) : 0;
    show(starCanvas, starsLeft > 0);
    if (starsLeft > 0) starCanvas.style.opacity = starsLeft.toFixed(3);
    for (const c of L.clouds) {
      const y = c.y - c.parallax * dropped;
      c.el.style.opacity = y + c.height < 0 ? 0 : c.opacity;
      c.el.style.transform = `translate3d(${fixed(c.x)}px, ${fixed(y)}px, 0)`;
    }
    // the cloud sea lies on the picture's top edge; it is only seen in the fall (afterwards the
    // opened-out picture would run under it)
    const seaShown = Boolean(state.scene) && t >= BEAT.fall && t < BEAT.land;
    show(seaCanvas, seaShown);
    if (seaShown) {
      paintSea(L);
      seaCanvas.style.transform = `translate3d(${fixed(L.sea.x)}px, ${fixed(-camY - L.sea.height)}px, 0)`;
    }
    if (shot.frame) {
      // The ground is the window's size (and a little more below it); the picture on it is laid out
      // at the size it is shown rather than scaled, so it stays sharp once the window is open.
      const s = state.scene, r = shot.rect, fr = shot.frame;
      const ground = `${fixed(r.w)} ${fixed((1 + OVERSHOOT) * r.h)}`, pic = `${fixed(s.w * fr.k)} ${fixed(s.h * fr.k)}`;
      if (state.sceneSize !== ground) {
        state.sceneSize = ground;
        [scene.style.width, scene.style.height] = ground.split(' ').map(v => `${v}px`);
      }
      if (state.picSize !== pic) {
        state.picSize = pic;
        [scenePic.style.width, scenePic.style.height] = pic.split(' ').map(v => `${v}px`);
        setVar(identity, '--pic-w', `${fixed(s.w * fr.k * PUSH)}px`);   // the shade behind the name keeps to it
      }
      scene.style.transform = `translate3d(0, ${fixed(shot.y)}px, 0)`;
      scenePic.style.transform = `translate3d(${fixed(fr.left)}px, ${fixed(fr.top)}px, 0)`;
      scene.style.filter = blur > 0 ? `blur(${blur.toFixed(2)}px)` : '';
      setVar(scene, '--band', `${(100 * L.bandShare * (1 - shot.e)).toFixed(2)}%`);
      // the fill fades into the sky a whole band down (the picture's colours spread round it are no
      // sky colour), until the window opens
      const fade = shot.e < 1 ? `linear-gradient(transparent, #000 ${(100 * FADE_BAND / (1 + OVERSHOOT) * (1 - shot.e)).toFixed(2)}%)` : '';
      if (state.fillFade !== fade) {
        state.fillFade = fade;
        sceneFill.style.webkitMaskImage = sceneFill.style.maskImage = fade;
      }
      sceneNear.style.opacity = ease.inOut(seg(t, BEAT.focus, BEAT.focusLen)).toFixed(3);
      scenePush.style.transform = `scale(${(1 + (PUSH - 1) * ease.out(seg(t, BEAT.focus, 1000))).toFixed(4)})`;
      // the fill's grid, drawn out from the picture's edges by the pen as the window opens (and gone
      // over again by it after a change of picture)
      const drawn = ease.out(seg(t, BEAT.grid, GRID.len)), at = drawn < 1 ? drawn : gridPen.value;
      const [gridMask, penMask] = gridMasks(fr.fit, r, drawn, at);
      setVar(sceneFill, '--fill-grid-mask', gridMask);
      setVar(sceneFill, '--fill-pen-mask', penMask);
      setVar(sceneFill, '--fill-pen', penMask ? (1 - seg(at, 0.7, 0.3)).toFixed(3) : '');
    }
  }

  // The masks of the fill's grid (GRID): what is drawn of it, out from the picture's edges to the
  // pen (drawn, 0 to 1; none once it is all drawn), and the pen's glow (at, 0 to 1; none while the pen
  // is put away). They run across the window where the fill is beside the picture, down it where the
  // fill is above and below it.
  function gridMasks(fit, r, drawn, at) {
    const across = r.w - fit.w >= r.h - fit.h, S = GRID.soft, P = GRID.pen;
    const [lo, size, span] = across ? [fit.x, fit.w, r.w] : [fit.y, fit.h, (1 + OVERSHOOT) * r.h];
    const far = Math.max(lo, span - lo - size) + S, dir = across ? '90deg' : '180deg';
    const px = v => `${fixed(v)}px`;
    // the pen's way out from the picture's edges: at 0 just inside them, at 1 past the far one
    const edges = p => [lo - p * far, lo + size + p * far];
    let gridMask = '', penMask = '';
    if (drawn < 1) {
      const [a, b] = edges(drawn);
      gridMask = `linear-gradient(${dir}, transparent ${px(a)}, #000 ${px(a + S)}, #000 ${px(b - S)}, transparent ${px(b)})`;
    }
    if (at > 0 && at < 1) {
      const [a, b] = edges(at).map((v, i) => v + (i ? -S : S) / 2);
      penMask = `linear-gradient(${dir}, transparent ${px(a - P)}, #000 ${px(a)}, transparent ${px(a + P)}, transparent ${px(b - P)}, #000 ${px(b)}, transparent ${px(b + P)})`;
    }
    return [gridMask, penMask];
  }

  function placeWindow(rect) {
    const box = [rect.x, rect.y, rect.w, rect.h].map(fixed).join(' ');
    if (box === state.windowBox) return;
    state.windowBox = box;
    windowEl.style.left = `${fixed(rect.x)}px`;
    windowEl.style.top = `${fixed(rect.y)}px`;
    windowEl.style.width = `${fixed(rect.w)}px`;
    windowEl.style.height = `${fixed(rect.h)}px`;
    lens.setAttribute('viewBox', `0 0 ${fixed(rect.w)} ${fixed(rect.h)}`);
  }

  // The ornament (MEET) on the fill in frame t: its entrance, or on the opening screen its coming in
  // again after a change of picture (meetPen), and the birds where they have glided to. It fades out
  // quickly as the window docks for a section, and back in as the window returns. (By the time it
  // comes in the window has all but opened, so the fill is the screen.)
  function drawMeet(t) {
    const G = meet.G, T = Math.min(seg(t, MEET.start, MEET.len), meetPen.value);
    // (left out of the painting until it has something to show; its colours are got ready before)
    const seen = G && T > 0 ? 1 - seg(dock.value, 0, 0.3) : 0, opacity = seen < 1 ? seen.toFixed(3) : '';
    for (const el of [meetSvg, meetPlanes]) {
      if (el.style.opacity !== opacity) el.style.opacity = opacity;
      show(el, seen > 0);
    }
    if (G && meet.ink !== `${state.washes} ${G.id}`) inkMeet(G);
    if (!seen) return;
    const playing = state.running || state.debugT != null;
    if (playing) {
      meet.lap = Math.max(0, t - MEET.start - 0.1 * MEET.len) / 1000;   // (the birds take off with the orbit)
      meet.spin = meet.up = 0;   // (and the disc turns once it is all in)
    }
    const key = `${T} ${G.id} ${meet.ink}`;
    if (meet.drawn !== key) {
      meet.drawn = key;
      drawMeetMarks(G, T);
    }
    drawBirds(G, T);
    if (!playing) flyBirds();
  }

  // The ornament as far as its entrance has got (T, 0 to 1; 1 on the opening screen), in the order the
  // light goes, point, line, plane: the moon lights; the new moon grows up the orbit out of it, waxing,
  // as the orbit is drawn round from it (and the birds come up on it, drawBirds); the bezel's ticks
  // light; the rays reach for the picture, go in behind it and come out the other side; where they land
  // the image plane spreads out from behind the picture's edge as if exposed, a film coming out with its
  // perforations, and the disc opens out from her like a ripple, its rim with it, leaving its rings
  // behind; the arc on its outer ring is
  // drawn round from the lower left and the worlds on the rings light from the inside out; last her
  // pentagon comes up in the clear spot as the AF brackets close on it, and the petals drift off, a
  // glint on the disc coming up in a flash with each.
  function drawMeetMarks(G, T) {
    const M = meetMarks, span = (a, b) => ease.out(seg(T, a, b - a));
    const pMoon = span(0, 0.18), pLune = span(0.1, 0.42), pRing = span(0.1, 0.55), pTicks = span(0.25, 0.5);
    const pRayL = span(0.4, 0.62), pRayR = span(0.62, 0.78), pPlane = span(0.64, 0.84), pDisc = span(0.74, 0.92), pHer = span(0.82, 1);
    // the planes (and, in the masks, what they make of the lines and the birds over them); the image
    // plane's edge carries its perforations out with it as it spreads
    const p = G.plane, disc = { ...G.disc, r: G.disc.r * pDisc }, spot = { ...G.spot, r: G.spot.r * pHer };
    const edge = lerp(p.x0, p.x1, pPlane), plane = { d: planePath(G, edge, disc) };
    M.planes.forEach((marks, i) => {
      const shape = i ? (i === 1 ? disc : spot) : plane;
      for (const el of Object.values(marks)) attrs(el, shape);
    });
    M.hatch.setAttribute('d', hatchPath(G, edge, disc));
    // on the disc: the rim at its edge; its rings, worlds and glints
    M.rim.setAttribute('d', MEET.rim.map(e => disc.r - e * G.u).filter(r => r > 1).map(r => ringPath(disc, r)).join(''));
    drawDisc(G, T, disc);
    // the rays, and small points where the middle one goes in behind the picture and comes out
    const part = (a, b, k) => ({ x: lerp(a.x, b.x, k), y: lerp(a.y, b.y, k) });
    G.rays.forEach((ray, i) => {
      const [left, right] = M.rays[i], a = part(ray.inL, ray.outL, pRayL), b = part(ray.inR, ray.outR, pRayR);
      show(left, pRayL > 0);
      show(right, pRayR > 0);
      attrs(left, { x1: ray.inL.x, y1: ray.inL.y, x2: a.x, y2: a.y });
      attrs(right, { x1: ray.inR.x, y1: ray.inR.y, x2: b.x, y2: b.y });
    });
    const mid = G.rays[1];
    show(M.points[0], pRayL >= 1);
    show(M.points[1], pRayR > 0);
    attrs(M.points[0], { cx: mid.outL.x, cy: mid.outL.y });
    attrs(M.points[1], { cx: mid.inR.x, cy: mid.inR.y });
    // the orbit, drawn round from the moon; the new moon lying on it, growing up it out of the moon and
    // waxing as it goes: the orbit is its outer edge, it swells soon after the moon and runs out to a
    // point, longer the fuller this world's moon
    const around = 2 * Math.PI * G.R;
    show(M.orbit, pRing > 0);
    M.orbit.setAttribute('stroke-dasharray', pRing < 1 ? `${fixed(around * pRing)} ${fixed(around)}` : 'none');
    show(M.lune, pLune > 0);
    if (pLune > 0) {
      const arc = (44 + 26 * G.full) * DEG * pLune, thick = 5 * Math.sqrt(pLune), a0 = G.from + 7 * DEG, n = 72, edge = [];
      for (let i = 0; i <= n; i++) edge.push(G.at(a0 + arc * i / n, G.R));
      for (let i = n; i >= 0; i--) edge.push(G.at(a0 + arc * i / n, G.R - thick * Math.sin(Math.PI * (1 - i / n) ** 2)));
      M.lune.setAttribute('d', `M${edge.map(q => `${fixed(q.x)} ${fixed(q.y)}`).join('L')}Z`);
    }
    // the moon, and its bezel of fine ticks on the side away from the picture, lighting one by one,
    // a point where this world's moon is on it
    M.moonG.setAttribute('opacity', pMoon.toFixed(3));
    show(M.moonG, pMoon > 0);
    const rb = 1.7 * G.rm, ticks = ['', ''];
    for (let i = 0, n = Math.ceil(23 * pTicks); i < n; i++) {
      const deg = 250 - 5 * i, long = (deg - 140) % 25 === 0, len = long ? 6 : 2.5, c = Math.cos(deg * DEG), s = Math.sin(deg * DEG);
      ticks[long ? 1 : 0] += `M${fixed(G.Mo.x + c * rb)} ${fixed(G.Mo.y + s * rb)}L${fixed(G.Mo.x + c * (rb + len))} ${fixed(G.Mo.y + s * (rb + len))}`;
    }
    M.bezel.forEach((path, i) => path.setAttribute('d', ticks[i]));
    show(M.points[2], pTicks >= 1);
    attrs(M.points[2], { cx: G.Mo.x + Math.cos(G.bezelAt * DEG) * (rb - 5), cy: G.Mo.y + Math.sin(G.bezelAt * DEG) * (rb - 5) });
    // her, the AF brackets closing on her, the petals; and the bar group in the corner
    M.herG.setAttribute('opacity', pHer.toFixed(3));
    show(M.herG, pHer > 0);
    M.petals.forEach((petal, i) => show(petal, pHer > 0.55 + 0.15 * i));
    const half = (G.rp + 9) * (1 + 0.9 * (1 - pHer)), at = v => Math.round(10 * v) / 10;
    M.af.setAttribute('d', bracketPath(at(G.Sa.x - half), at(G.Sa.y - half), at(G.Sa.x + half), at(G.Sa.y + half), 5));
    M.af.style.opacity = pHer.toFixed(3);
    M.barsG.style.opacity = pHer.toFixed(3);
  }

  // The disc's rings, the worlds on them and its glints, as far as its entrance has got (T; disc, the
  // disc as far as it has rippled out) and, once it is all in, as far as it has turned (meet.spin,
  // MEET.spin). Each ring comes up once the rim has passed it, the arc on the outer one then drawn round,
  // and the world on each lights in its turn, from the inside out, once the ring has got to it; then
  // each world goes round clockwise with the arc or the dots of its ring, and two passing each other
  // swell a moment. The glints come up with the petals in a flash (up at once, swelling and brighter for
  // a moment, and settling), and then twinkle in turn, half as much. (On the opening screen this is
  // every frame: only what has changed is written.)
  function drawDisc(G, T, disc = G.disc) {
    const M = meetMarks, S = MEET.spin, u = G.u, R = G.disc.r, spin = T < 1 ? 0 : meet.spin;
    const put = (el, name, value) => { if (el.getAttribute(name) !== value) el.setAttribute(name, value); };
    const seen = (el, visible) => { if ((el.style.display !== 'none') !== visible) show(el, visible); };
    const xy = (a, r) => `${fixed(disc.cx + r * Math.cos(a * DEG))} ${fixed(disc.cy + r * Math.sin(a * DEG))}`;
    const when = (p, a, b) => a + (b - a) * (1 - Math.cbrt(1 - p));   // (when easing out from a to b gets to p)
    const passed = disc.r - MEET.rim[MEET.rim.length - 1] * u, pArc = ease.out(seg(T, 0.84, 0.12));
    // how far round each world has gone, and how much it swells: as far from lining up with another as
    // the angle between them takes to close at their paces, the whole swell taking `pass[1]` ms
    const turned = S.turn.map(s => 360 * spin / s), at = G.worlds.map((a, i) => a + turned[i]);
    const apart = (a, b) => Math.abs((((a - b) % 360) + 540) % 360 - 180);
    const swell = at.map((a, i) => 1 + (S.pass[0] - 1) * Math.max(...at.map((b, j) => {
      const s = j === i ? 1 : apart(a, b) / Math.abs(360 / S.turn[i] - 360 / S.turn[j]) / (S.pass[1] / 2000);
      return s < 1 ? Math.cos(Math.PI * s / 2) ** 2 : 0;
    })));
    MEET.tracks.forEach(([rf, , from = 0, to = 360], i) => {
      const r = rf * R, got = passed < r ? from : i ? to : lerp(from, to, pArc), inside = MEET.tracks.filter(([q]) => q < rf).length;
      const track = M.tracks[i], whole = got - from >= 360;
      put(track, 'd', got <= from ? '' : whole ? ringPath(disc, r)
        : `M${xy(from + turned[i], r)}A${fixed(r)} ${fixed(r)} 0 ${got - from > 180 ? 1 : 0} 1 ${xy(got + turned[i], r)}`);
      if (whole) {   // (a whole number of dots round it, so that they can flow round with its world)
        const length = 4 * Math.round(Math.PI * r / 2);
        put(track, 'pathLength', String(length));
        put(track, 'stroke-dashoffset', fixed(length * (turned[i] % 360) / 360));
      }
      const k = got >= G.worlds[i] ? ease.out(seg(T, 0.85 + 0.02 * inside, 0.02)) : 0, [cx, cy] = xy(at[i], r).split(' ');
      seen(M.worlds[i], k > 0);
      put(M.worlds[i], 'cx', cx);
      put(M.worlds[i], 'cy', cy);
      put(M.worlds[i], 'r', fixed(MEET.worlds[i] * u * k * swell[i]));
    });
    G.glints.forEach(([a, rf, size], i) => {
      const { g, core } = M.glints[i], k = seg(T, when(0.55 + 0.15 * i, 0.82, 1), 0.08), flash = Math.sin(Math.PI * k) ** 2;
      const tw = S.twinkle, since = spin - tw.at[i], q = since < 0 ? 1 : (since % tw.every) * 1000 / tw.len;
      const twinkle = q < 1 ? Math.sin(Math.PI * q) ** 2 : 0;
      seen(g, k > 0);
      if (!k) return;
      const v = size * u * ease.out(Math.min(1, 3 * k)) * (1 + 0.6 * flash + 0.3 * twinkle);
      put(g, 'transform', `translate(${xy(a, rf * R)}) scale(${v.toFixed(2)})`);
      setVar(g, '--flash', (1 + 2 * flash + twinkle).toFixed(2));
      put(core, 'r', (Math.max(1, 0.07 * v) / v).toFixed(3));
    });
  }

  // A circle round c as a path: two half arcs from its left, anticlockwise (the way its dashes run).
  function ringPath(c, r) {
    return `M${fixed(c.cx - r)} ${fixed(c.cy)}a${fixed(r)} ${fixed(r)} 0 1 0 ${fixed(2 * r)} 0a${fixed(r)} ${fixed(r)} 0 1 0 ${fixed(-2 * r)} 0`;
  }

  // The image plane as far as it has spread (to x1), a strip of film (MEET.film): down its edge the clear
  // band punched with perforations, but not where the disc lies over it (which covers them, though not
  // quite: it is a little see-through). The holes are holes in its shape, so that in the masks too what
  // is over them is over the fill.
  function planePath(G, x1, disc) {
    const p = G.plane, F = MEET.film, u = G.u, [w, h, rx] = F.hole.map(v => v * u), x = x1 - F.inset * u - w, r = fixed(rx);
    let d = `M${fixed(p.x0)} ${fixed(p.y0)}H${fixed(x1)}V${fixed(p.y1)}H${fixed(p.x0)}Z`;
    if (x < p.x0) return d;
    const X = [x, x + rx, x + w - rx, x + w].map(fixed);
    for (let y = p.y0 + F.top * u; y + h <= p.y1 - F.top * u; y += F.pitch * u) {
      const nx = Math.min(Math.max(disc.cx, x), x + w) - disc.cx, ny = Math.min(Math.max(disc.cy, y), y + h) - disc.cy;
      if (nx * nx + ny * ny < (disc.r + 3) ** 2) continue;
      const Y = [y, y + rx, y + h - rx, y + h].map(fixed);
      d += `M${X[1]} ${Y[0]}H${X[2]}A${r} ${r} 0 0 1 ${X[3]} ${Y[1]}V${Y[2]}A${r} ${r} 0 0 1 ${X[2]} ${Y[3]}`
        + `H${X[1]}A${r} ${r} 0 0 1 ${X[0]} ${Y[2]}V${Y[1]}A${r} ${r} 0 0 1 ${X[1]} ${Y[0]}Z`;
    }
    return d;
  }

  // The image plane's hatching, 45 degrees up to the right like the petals' way, as far as the plane
  // has spread (to x1), short of the film's clear band and its top, and broken between two frames and
  // where the disc lies over it. (Cut line by line rather than clipped: in Chromium the whole of a <use>
  // of the line work can drop out while a clip inside it goes from empty to not.)
  function hatchPath(G, x1, disc) {
    const p = G.plane, top = p.y0 + MEET.film.top * G.u, right = x1 - MEET.film.band * G.u;
    let d = '';
    for (let s = p.x0 + p.y0 + 4; s < right + p.y1; s += 4) {
      // the line x + y = s across the plane, less the gap (y = s - x) and where it crosses the disc's
      // edge (2x² - 2qx + cx² + (s - cy)² - r² = 0)
      let parts = [[Math.max(p.x0, s - p.y1), Math.min(right, s - top)]];
      const cut = (a, b) => { parts = parts.flatMap(([c, e]) => [[c, Math.min(e, a)], [Math.max(c, b), e]]); };
      cut(s - p.gap[1], s - p.gap[0]);
      const q = disc.cx + s - disc.cy, D = q * q - 2 * (disc.cx ** 2 + (s - disc.cy) ** 2 - disc.r ** 2);
      if (D > 0) cut((q - Math.sqrt(D)) / 2, (q + Math.sqrt(D)) / 2);
      for (const [a, b] of parts) if (b - a > 0.5) d += `M${fixed(a)} ${fixed(s - a)}L${fixed(b)} ${fixed(s - b)}`;
    }
    return d;
  }

  // The birds (MEET.bird) where they have glided to (meet.lap s): evenly round the orbit, each as big
  // as it is low on it, swerving out round the moon and her. In the entrance each comes up (fading in
  // and growing to its size) as the orbit is drawn past it, the last just as it closes. Those behind
  // the picture are not drawn (it would hide them), nor those off the screen.
  function drawBirds(G, T) {
    const B = MEET.bird, birds = meetMarks.birds, n = state.layout.portrait ? B.mobile : B.count, rise = 12 * DEG;
    const drawn = 2 * Math.PI * ease.out(seg(T, 0.1, 0.45)), turned = B.speed * DEG * meet.lap;
    birds.forEach((bird, i) => {
      const at = 4 * DEG + 2 * Math.PI * i / n, up = clamp01((drawn - at * (1 - rise / (2 * Math.PI))) / rise);
      const a = G.from + at + turned, r = G.R + B.off + G.swerve(a), x = G.cx + r * Math.cos(a), y = G.cy + r * Math.sin(a);
      const seen = i < n && up > 0 && x > -24 && x < G.squares - 8 && y > -24 && y < G.H + 24 && !(x > G.px + 10 && x < G.pr - 10);
      if (seen !== bird.seen) {
        bird.seen = seen;
        for (const el of bird.els) show(el, seen);
      }
      if (!seen) return;
      // heading along their way, which bends where they swerve
      const b = a + 0.01, rb = G.R + B.off + G.swerve(b);
      const dx = G.cx + rb * Math.cos(b) - x, dy = G.cy + rb * Math.sin(b) - y;
      const left = dx < 0;
      // Small side-view silhouettes must never turn upside down as they orbit.
      const pitch = Math.max(-18, Math.min(18, Math.atan2(dy, Math.abs(dx)) / DEG));
      const size = lerp(B.size[0], B.size[1], (1 + Math.sin(a)) / 2) * (0.6 + 0.4 * up);
      const transform = `translate(${fixed(x)} ${fixed(y)}) rotate(${fixed(left ? -pitch : pitch)}) scale(${(left ? -size : size).toFixed(2)} ${size.toFixed(2)})`;
      const opacity = up < 1 ? up.toFixed(3) : '';
      for (const el of bird.els) {
        el.setAttribute('transform', transform);
        if (el.style.opacity !== opacity) el.style.opacity = opacity;
      }
    });
  }

  // While the opening screen is up and settled the birds glide on and the disc turns, a frame at a time:
  // not with reduced motion, in a background tab or while a section is open (they wait where they are).
  function birdsWanted() {
    return !reduceMotion && !document.hidden && !state.running && state.debugT == null && !meet.held && Boolean(meet.G)
      && dock.tab === 'home' && dock.value === 0;
  }

  function flyBirds() {
    if (meet.raf || !birdsWanted()) return;
    meet.last = performance.now();
    meet.raf = requestAnimationFrame(birdFrame);
  }

  function birdFrame(now) {
    meet.raf = 0;
    const wanted = birdsWanted();
    // (gliding once the ornament is all in, the birds are drawn on layers of their own: styles.css)
    meetSvg.classList.toggle('gliding', wanted && meetPen.value >= 1);
    if (!wanted) return;
    const dt = Math.min(0.05, (now - meet.last) / 1000);
    meet.lap = (meet.lap + dt) % (360 / MEET.bird.speed);
    meet.last = now;
    drawBirds(meet.G, meetPen.value);
    turnDisc(dt);
    meet.raf = requestAnimationFrame(birdFrame);
  }

  // The disc turning on by dt s (MEET.spin) once it is all in, getting up to speed at first; while the
  // ornament comes in again for another picture, it waits to start again from where that puts it.
  function turnDisc(dt) {
    if (meetPen.value < 1) {
      meet.spin = meet.up = 0;
      return;
    }
    meet.up = Math.min(1, meet.up + 1000 * dt / MEET.spin.up);
    meet.spin += dt * ease.inOut(meet.up);
    drawDisc(meet.G, 1);
  }

  // sRGB (0 to 255) to linear light, linear light to OKLCH, and OKLCH back to sRGB (its chroma brought in
  // until it fits), for the planes' colours
  const toLinear = v => ((v /= 255) <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  function oklch([r, g, b]) {
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s, B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
    return { L: 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, C: Math.hypot(A, B), h: Math.atan2(B, A) };
  }
  function fromOklch(L, C, h) {
    const encode = v => Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055));
    for (let c = C; ; c *= 0.94) {
      const a = c * Math.cos(h), b = c * Math.sin(h);
      const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
      const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
      const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
      if (c < 0.002 || rgb.every(v => v >= -0.001 && v <= 1.001)) return rgb.map(v => encode(clamp01(v)));
    }
  }

  // What the ornament's colours come from (MEET): the fill as painted, its thumbnail cover-fitted to 116%
  // of the fill (styles.css), read back. Its luma makes the masks that turn the line work white or ink,
  // laid over the fill where the thumbnail is; the mean of the fill on her side, in OKLCH, makes the
  // planes' colours, and their lumas what the lines and the birds over them do. (Where the fill cannot
  // be read back, as on a page opened from a local file, the lines are white and the planes a quiet
  // grey-blue.)
  function inkMeet(G) {
    const M = meetMarks, { W, H } = G, [lo, hi] = MEET.light, luma = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
    meet.ink = `${state.washes} ${G.id}`;
    let px = null, w = 1, h = 1;
    if (state.washFrom) {
      // (painted again on a canvas kept for reading, as deepOf reads, rather than read back from the
      // fill's own: that waits on the GPU, on a cold start for a good part of a second)
      const copy = document.createElement('canvas'), g = copy.getContext('2d', { willReadFrequently: true });
      paintWash(copy, state.washFrom);
      try {
        px = g.getImageData(0, 0, copy.width, copy.height).data;
        [w, h] = [copy.width, copy.height];
      } catch { px = null; }
    }
    const inked = new Float32Array(w * h), sum = [0, 0, 0];
    const bw = 1.16 * W, bh = 1.16 * (1 + OVERSHOOT) * H, k = Math.max(bw / w, bh / h);
    const ox = -0.08 * W + (bw - w * k) / 2, oy = -0.08 * (1 + OVERSHOOT) * H + (bh - h * k) / 2;
    let count = 0;
    for (let q = 0; px && q < w * h; q++) {
      const rgb = [px[4 * q], px[4 * q + 1], px[4 * q + 2]], x = ox + (q % w + 0.5) * k, y = oy + (Math.floor(q / w) + 0.5) * k;
      inked[q] = smooth(lo, hi, luma(...rgb));
      if (x >= G.pr && x <= W && y >= 0 && y <= H) {
        rgb.forEach((v, c) => { sum[c] += toLinear(v); });
        count++;
      }
    }
    const canvas = document.createElement('canvas');
    [canvas.width, canvas.height] = [w, h];
    // (kept off the GPU too: encoding it would wait on the GPU as reading the fill back would)
    const g = canvas.getContext('2d', { willReadFrequently: true }), image = g.createImageData(w, h);
    [v => 1 - v, v => v].forEach((f, i) => {
      for (let q = 0; q < w * h; q++) image.data.set(Array(3).fill(Math.round(255 * f(inked[q]))).concat(255), 4 * q);
      g.putImageData(image, 0, 0);
      attrs(M.thumbs[i], { href: canvas.toDataURL(), x: ox, y: oy, width: w * k, height: h * k });
    });
    const fill = count ? oklch(sum.map(v => v / count)) : { L: 0.62, C: 0.02, h: -1.9 };
    const deep = fromOklch(Math.max(MEET.floor, fill.L - MEET.deep), Math.min(0.12, 1.4 * fill.C + 0.015), fill.h);
    const light = fromOklch(Math.min(0.9, fill.L + MEET.lighter), Math.min(0.1, 1.1 * fill.C), fill.h);
    const grey = v => `rgb(${Array(3).fill(Math.round(255 * v)).join(' ')})`;
    [light, deep, light].forEach((rgb, i) => {
      const marks = M.planes[i], l = smooth(lo, hi, luma(...rgb)), dark = l < 0.5;
      marks.fill.setAttribute('fill', `rgb(${rgb.join(' ')})`);
      marks.chalk.setAttribute('fill', grey(1 - l));
      marks.ink.setAttribute('fill', grey(l));
      marks.on.setAttribute('fill', dark ? '#fff' : '#000');
      marks.off.setAttribute('fill', dark ? '#000' : '#fff');
    });
  }

  // The cloud sea, painted once the cloud photos are in: the near layer's deck under a soft white body,
  // cumulus heads from the photos along its back, billows of every size (the surf's puffs) in front,
  // and its underside fading out onto the picture. (Painted as by day: layoutSea tints it for the time.)
  function paintSea(L) {
    const sea = L.sea, day = puffSprites()?.[0];
    if (!sea || sea.painted || !day || ![clouds.near, clouds.mid, clouds.tower].every(ready)) return;
    const W = sea.width, H = sea.height, g = seaCanvas.getContext('2d');
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, seaCanvas.width, seaCanvas.height);
    g.setTransform(sea.dpr, 0, 0, sea.dpr, 0, 0);
    for (let i = 0; i < 2; i++) {
      g.save();
      g.translate(i ? W : 0, 0);
      g.scale(i ? -1 : 1, 1);
      g.drawImage(clouds.near, -0.05 * W, 0.4 * H, 0.62 * W, 0.5 * H);
      g.restore();
    }
    const body = g.createLinearGradient(0, 0.3 * H, 0, 0.9 * H);
    body.addColorStop(0, 'rgba(240, 245, 251, 0)');
    body.addColorStop(0.3, 'rgba(240, 245, 251, 0.9)');
    body.addColorStop(0.7, 'rgba(232, 239, 248, 0.85)');
    body.addColorStop(1, 'rgba(232, 239, 248, 0)');
    g.fillStyle = body;
    g.fillRect(0, 0.3 * H, W, 0.6 * H);
    // the heads: the middle layer (every third one the tower), every other one mirrored
    for (let i = 0, x = -0.2 * W; x < W; i++) {
      const img = i % 3 === 2 ? clouds.tower : clouds.mid, ch = H * (0.42 + 0.18 * noise(i + 41));
      const cw = ch * img.naturalWidth / img.naturalHeight;
      g.save();
      g.translate(x + (i % 2 ? cw : 0), 0.62 * H - 0.92 * ch);
      g.scale(i % 2 ? -1 : 1, 1);
      g.drawImage(img, 0, 0, cw, ch);
      g.restore();
      x += cw * (0.55 + 0.3 * noise(i + 43));
    }
    // each row of billows: how low it sits, their radius (shares of H) and their spacing (share of a
    // width); now and then a gap
    [[0.42, 0.13, 0.84], [0.52, 0.09, 0.72]].forEach(([y, size, step], row) => {
      for (let j = 0, x = -0.1 * H; x < W + 0.2 * H; j++) {
        const n = q => noise(13.7 * j + 71 * row + q), r = H * size * (0.5 + n(1)), gap = n(5) < 0.25;
        if (!gap) {
          g.save();
          g.translate(x, H * (y + 0.08 * (n(2) - 0.5)));
          g.rotate((n(3) - 0.5) * 0.5);
          g.drawImage(day[(j + 5 * row) % day.length][0], -r, -r, 2 * r, 2 * r);
          g.restore();
        }
        x += 2 * r * (gap ? 1 : step * (0.6 + 0.8 * n(4)));
      }
    });
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = 'destination-in';
    const fade = g.createLinearGradient(0, 0, 0, seaCanvas.height);
    fade.addColorStop(0.62, '#000');
    fade.addColorStop(1, 'rgba(0, 0, 0, 0)');
    g.fillStyle = fade;
    g.fillRect(0, 0, seaCanvas.width, seaCanvas.height);
    g.globalCompositeOperation = 'source-over';
    sea.painted = true;
  }

  // A tint (TINTS) at a time of day (0 to 2): the two nearest mixed.
  function tintAt(tone) {
    const k = Math.min(1, Math.floor(tone));
    return TINTS[k].map((v, i) => lerp(v, TINTS[k + 1][i], tone - k));
  }

  // A tint as a CSS filter ('' for none).
  function tintFilter([bright, sepia, hue, saturate]) {
    if (bright === 1 && !sepia && !hue && saturate === 1) return '';
    return `brightness(${bright.toFixed(3)}) sepia(${sepia.toFixed(3)}) hue-rotate(${hue.toFixed(1)}deg) saturate(${saturate.toFixed(3)})`;
  }

  // A tint as one colour matrix (rows) for sRGB values, as the browser works the filter functions out
  // (Filter Effects): brightness, then sepia, hue-rotate and saturate.
  function tintMatrix([bright, sepia, hue, saturate]) {
    const times = (a, b) => a.map(row => [0, 1, 2].map(j => row[0] * b[0][j] + row[1] * b[1][j] + row[2] * b[2][j]));
    const s = 1 - sepia, c = Math.cos(hue * DEG), n = Math.sin(hue * DEG), v = saturate;
    const toSepia = [
      [0.393 + 0.607 * s, 0.769 - 0.769 * s, 0.189 - 0.189 * s],
      [0.349 - 0.349 * s, 0.686 + 0.314 * s, 0.168 - 0.168 * s],
      [0.272 - 0.272 * s, 0.534 - 0.534 * s, 0.131 + 0.869 * s],
    ];
    const turn = [
      [0.213 + 0.787 * c - 0.213 * n, 0.715 - 0.715 * c - 0.715 * n, 0.072 - 0.072 * c + 0.928 * n],
      [0.213 - 0.213 * c + 0.143 * n, 0.715 + 0.285 * c + 0.14 * n, 0.072 - 0.072 * c - 0.283 * n],
      [0.213 - 0.213 * c - 0.787 * n, 0.715 - 0.715 * c + 0.715 * n, 0.072 + 0.928 * c + 0.072 * n],
    ];
    const saturated = [
      [0.213 + 0.787 * v, 0.715 - 0.715 * v, 0.072 - 0.072 * v],
      [0.213 - 0.213 * v, 0.715 + 0.285 * v, 0.072 - 0.072 * v],
      [0.213 - 0.213 * v, 0.715 - 0.715 * v, 0.072 + 0.928 * v],
    ];
    return times(saturated, times(turn, toSepia)).map(row => row.map(x => x * bright));
  }

  // A copy of a small canvas tinted for a time of day (0, 1 or 2): its pixels worked through the tint's
  // matrix, on the CPU (the source is read back, so it should be a canvas kept there too).
  function tinted(source, tone) {
    const canvas = document.createElement('canvas');
    canvas.width = source.width;
    canvas.height = source.height;
    const g = canvas.getContext('2d', { willReadFrequently: true }), m = tintMatrix(TINTS[tone]);
    g.drawImage(source, 0, 0);
    const image = g.getImageData(0, 0, canvas.width, canvas.height), px = image.data;
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i], gr = px[i + 1], b = px[i + 2];
      for (let k = 0; k < 3; k++) px[i + k] = m[k][0] * r + m[k][1] * gr + m[k][2] * b;   // (clamped and rounded by the array)
    }
    g.putImageData(image, 0, 0);
    return canvas;
  }

  // Cuts a billowing outline into a square canvas: a body with a ring of smaller lobes round it, each
  // with a soft edge (soft is where its fade starts, as a share of its radius: low for a puff frayed
  // into wisps), so a patch of cloud becomes a puff.
  function billow(g, size, seed, soft) {
    const mask = document.createElement('canvas');
    mask.width = mask.height = size;
    const m = mask.getContext('2d'), n = q => noise(7.7 * seed + q);
    const lobes = [[0.5, 0.55, 0.22 + 0.04 * n(0.3)]], count = 7 + Math.floor(5 * n(0.5));
    for (let j = 0; j < count; j++) {
      const a = 2 * Math.PI * (j + 0.7 * n(j + 1)) / count, d = 0.15 + 0.13 * n(j + 11), r = 0.07 + 0.11 * n(j + 21);
      const k = Math.min(1, (0.47 - r) / d);   // keeps the lobe inside the square
      lobes.push([0.5 + k * d * Math.cos(a), 0.53 + 0.85 * k * d * Math.sin(a), r]);
    }
    for (const [x, y, r] of lobes) {
      const disc = m.createRadialGradient(x * size, y * size, 0, x * size, y * size, r * size);
      disc.addColorStop(0, '#000');
      disc.addColorStop(soft, '#000');
      disc.addColorStop(1, 'rgba(0, 0, 0, 0)');
      m.fillStyle = disc;
      m.fillRect(0, 0, size, size);
    }
    g.save();
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = 'destination-in';
    g.drawImage(mask, 0, 0);
    g.restore();
  }

  // Light from the top right, as on the window's clouds: a little whiter overall (lift), brightest
  // towards the top right and shaded blue-grey low on the left.
  function topLight(g, size, lift) {
    g.save();
    g.globalCompositeOperation = 'source-atop';
    g.fillStyle = `rgba(255, 255, 255, ${lift})`;
    g.fillRect(0, 0, size, size);
    const bright = g.createRadialGradient(0.7 * size, 0.25 * size, 0, 0.7 * size, 0.25 * size, 0.65 * size);
    bright.addColorStop(0, 'rgba(255, 255, 255, 0.6)');
    bright.addColorStop(1, 'rgba(255, 255, 255, 0)');
    g.fillStyle = bright;
    g.fillRect(0, 0, size, size);
    const shade = g.createLinearGradient(0.8 * size, 0.15 * size, 0.2 * size, 0.95 * size);
    shade.addColorStop(0.35, 'rgba(118, 150, 196, 0)');
    shade.addColorStop(1, 'rgba(118, 150, 196, 0.4)');
    g.fillStyle = shade;
    g.fillRect(0, 0, size, size);
    g.restore();
  }

  // The surf's puffs (sprites.puffs), made once the cloud photos are in: patches of the photos cut into
  // billowing outlines and lit from the top right, each as a compact puff and frayed into wisps, by day
  // and tinted like the clouds for dusk and for night; and each compact puff's shadow at each time of
  // day (sprites.shades). (Small canvases kept on the CPU, so that they can be read back for the tints.)
  function puffSprites() {
    if (sprites.puffs || ![clouds.tower, clouds.mid].every(ready)) return sprites.puffs;
    const size = 128, blank = () => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = size;
      return [canvas, canvas.getContext('2d', { willReadFrequently: true })];
    };
    const day = Array.from({ length: 2 * PUFFS.length }, (_, i) => [0.62, 0.15].map((soft, frayed) => {
      const [layer, u, v, r] = PUFFS[i % PUFFS.length], img = clouds[layer], R = 1.25 * r * img.naturalWidth;
      const [canvas, g] = blank();
      g.drawImage(img, u * img.naturalWidth - R, v * img.naturalHeight - R, 2 * R, 2 * R, 0, 0, size, size);
      topLight(g, size, frayed ? 0.35 : 0.22);
      billow(g, size, i + 1, soft);
      return canvas;
    }));
    sprites.puffs = [day, ...[1, 2].map(tone => day.map(pair => pair.map(canvas => tinted(canvas, tone))))];
    sprites.shades = [0, 1, 2].map(tone => day.map(([solid]) => {
      const [canvas, g] = blank();
      g.drawImage(solid, 0, 0);
      g.globalCompositeOperation = 'source-in';
      g.fillStyle = `rgb(${tideColour(TIDE.shade, tone)})`;
      g.fillRect(0, 0, size, size);
      return canvas;
    }));
    return sprites.puffs;
  }

  // The puffs and their shadows at a time of day (0 day, 1 dusk, 2 night): those of one of them or,
  // between two, the two mixed, painted again whenever the time moves, so that each puff is still drawn
  // once. They share their outlines, so mixing them colour by colour ('copy', then 'lighter') keeps each
  // puff as solid as either.
  function toneSprites(tone) {
    const k = Math.min(1, Math.floor(tone)), p = tone - k;
    if (p <= 0 || p >= 1) return { puffs: sprites.puffs[k + (p > 0)], shades: sprites.shades[k + (p > 0)] };
    const like = source => {
      const canvas = document.createElement('canvas');
      canvas.width = source.width;
      canvas.height = source.height;
      return canvas;
    };
    if (!sprites.between) sprites.between = { tone: null, puffs: sprites.puffs[0].map(pair => pair.map(like)), shades: sprites.shades[0].map(like) };
    const mixed = sprites.between;
    if (mixed.tone !== tone) {
      const paint = (canvas, from, to) => {
        const g = canvas.getContext('2d');
        g.globalCompositeOperation = 'copy';
        g.globalAlpha = 1 - p;
        g.drawImage(from, 0, 0);
        g.globalCompositeOperation = 'lighter';
        g.globalAlpha = p;
        g.drawImage(to, 0, 0);
      };
      mixed.puffs.forEach((pair, i) => pair.forEach((canvas, j) => paint(canvas, sprites.puffs[k][i][j], sprites.puffs[k + 1][i][j])));
      mixed.shades.forEach((canvas, i) => paint(canvas, sprites.shades[k][i], sprites.shades[k + 1][i]));
      mixed.tone = tone;
    }
    return mixed;
  }

  // Sets the canvas to draw a sprite centred on (x, y) (window px), turned and stretched.
  function place(g, dpr, x, y, angle, sx, sy) {
    const c = Math.cos(angle) * dpr, s = Math.sin(angle) * dpr;
    g.setTransform(c * sx, s * sx, -s * sy, c * sy, dpr * x, dpr * y);
  }

  // Draws a puff of radius r where place has set the canvas: its solid sprite, giving way to its wisp
  // as it frays.
  function drawPuff(g, [solid, wisp], alpha, fray, r) {
    if (alpha <= 0) return;
    if (fray < 1) {
      g.globalAlpha = alpha * (1 - fray);
      g.drawImage(solid, -r, -r, 2 * r, 2 * r);
    }
    if (fray > 0) {
      g.globalAlpha = alpha * fray;
      g.drawImage(wisp, -r, -r, 2 * r, 2 * r);
    }
  }

  // Adds a tide line's curve to the path, from x0 to x1 (either way), depth(x) under the edge plus its
  // waviness.
  function traceTide(g, line, w, x0, x1, depth) {
    const n = Math.max(1, Math.ceil(Math.abs(x1 - x0) / 8));
    for (let i = 0; i <= n; i++) {
      const x = lerp(x0, x1, i / n);
      g.lineTo(x, depth(x) + tideOffset(line, x, w));
    }
  }

  // Where a line has washed back from, the sky is left a little deeper blue for a moment, like wet sand.
  function drawWet(g, line, q, w, tone, gone) {
    const a = 0.32 * (0.6 + 0.4 * Math.min(1, line.s)) * (1 - q.washed) * q.kept * gone;
    if (q.washed <= 0 || a <= 0.005) return;
    const x0 = Math.max(0, line.xa + 0.05 * w), x1 = Math.min(w, line.xb - 0.05 * w), top = line.yTop * q.squeeze;
    g.beginPath();
    traceTide(g, line, w, x0, x1, () => top);
    traceTide(g, line, w, x1, x0, () => q.y);
    g.closePath();
    g.globalAlpha = a;
    g.fillStyle = `rgb(${tideColour(TIDE.wet, tone)})`;
    g.fill();
  }

  // The pale sheet of sky a line trails, from under its lace down to its foot, draining as it washes
  // back and tapering off towards its ends; it grows with the line, and the cloud sea pushes it up with
  // the line. The high tide's runs down over the sea as it comes in, and veils the picture no lower
  // than S.veil as it washes back.
  function drawSheet(g, S, line, q, w, tone, gone) {
    const grow = line.high ? 1 : lerp(0.4, 1, growth(S, q.y));
    let depth = line.sheet * grow * q.squeeze * (1 - 0.6 * q.washed);
    if (line.high && !q.riding) depth = Math.min(line.peel ? depth : Infinity, S.veil - q.y);
    const a = (line.high ? 0.5 : 0.42 + 0.2 * Math.min(1, line.s)) * grow * q.alpha * gone;
    if (depth < 2 || a <= 0.005) return;
    const colour = tideColour(TIDE.sheet, tone), sheet = g.createLinearGradient(0, q.y, 0, q.y + depth);
    sheet.addColorStop(0, `rgba(${colour}, ${a.toFixed(3)})`);
    sheet.addColorStop(0.35, `rgba(${colour}, ${(0.55 * a).toFixed(3)})`);
    sheet.addColorStop(1, `rgba(${colour}, 0)`);
    const x0 = Math.max(0, line.xa), x1 = Math.min(w, line.xb);
    g.beginPath();
    traceTide(g, line, w, x0, x1, () => q.y);
    traceTide(g, line, w, x1, x0, x => q.y + depth * tideEnds(line, x, w));
    g.closePath();
    g.globalAlpha = 1;
    g.fillStyle = sheet;
    g.fill();
  }

  // A line's lace: small puffs of cloud overlapping along it into one line, stretched along it and
  // jittered so its edges are scalloped, thinning into its breaks, with now and then a wisp of lace
  // off either edge; over a soft shadow, which keeps it showing where it runs over a white cloud. It
  // is thin and faint where it forms and grows thicker and whiter the higher it runs (the first,
  // weakest lines stay faint all the way), and thins as it washes back.
  function drawLace(g, S, line, q, w, tone, gone) {
    const step = 0.65 * S.fu, { puffs, shades } = toneSprites(tone);
    const grow = line.high ? 1 : growth(S, q.y), faint = lerp(0.6, 1, smooth(0.4, 0.9, line.s));
    if (q.alpha * faint * gone < 0.01) return;
    const thin = line.size * (line.peel ? 0.7 : line.high ? 1 : lerp(0.4, 1.1, grow)) * (1 - 0.35 * q.fray);
    const j0 = Math.ceil(Math.max(-step, line.xa) / step), j1 = Math.floor(Math.min(w + step, line.xb) / step);
    for (let pass = 0; pass < 2; pass++) {   // the shadow first, then the puffs over it
      for (let j = j0; j <= j1; j++) {
        const x = j * step, here = tideHere(line, x, w, q.fray);
        if (here <= 0.02) continue;
        const n = k => noise(line.seed + 3.7 * j + k);
        const r = S.fu * (0.6 + 0.27 * Math.min(2, line.s)) * thin * (0.45 + 0.55 * here) * (0.75 + 0.5 * n(1));
        const y = q.y + tideOffset(line, x, w) + (n(2) - 0.5) * 0.5 * r;
        if (y < -2 * r || y > S.h + 2 * r) continue;
        const alpha = Math.min(1, q.alpha * here) * faint * lerp(0.45, 1, grow) * gone, i = Math.floor(n(3) * puffs.length);
        const cx = x + (n(4) - 0.5) * step, angle = (n(5) - 0.5) * 0.3, sx = (n(6) < 0.5 ? -1 : 1) * (1.8 + 0.8 * n(7));
        if (pass === 0) {
          const dark = (line.high ? 0.25 : 0.2) * alpha * (1 - 0.6 * q.fray);
          if (dark < 0.01) continue;
          place(g, S.dpr, cx, y + 0.4 * r, angle, 1.1 * sx, 0.8);
          g.globalAlpha = dark;
          g.drawImage(shades[i], -r, -r, 2 * r, 2 * r);
          continue;
        }
        place(g, S.dpr, cx, y, angle, sx, 0.7);
        drawPuff(g, puffs[i], alpha, q.fray, r);
        if (n(8) < 0.25) {
          const rl = r * (0.35 + 0.25 * n(9)), k = Math.floor(n(10) * puffs.length);
          place(g, S.dpr, cx + (n(11) - 0.5) * 2 * step, y + (n(12) < 0.5 ? -1 : 1) * (0.7 + 0.5 * n(13)) * r, angle, sx, 0.8);
          drawPuff(g, puffs[k], 0.8 * alpha, 1, rl);
        }
      }
    }
  }

  // A burst of spray (see layoutSurf): a row of cloud puffs where the line reaches the edge, which swell
  // and are drawn up into the edge within a quarter of a second, over soft shadows that keep them
  // showing over white cloud; the high tide's are the biggest.
  function drawSpray(g, S, t, w, tone, gone) {
    const h = S.h, touches = 0.012 * h;
    for (let pass = 0; pass < 2; pass++) {   // the shadows first, then the puffs over them
      for (const burst of S.sprays) {
        const s = t - burst.at, line = burst.line;   // since the burst
        if (s < 0 || s > 260) continue;
        const env = (1 - Math.exp(-s / 20)) * (1 - smooth(80, 260, s)) * Math.min(1, 0.5 + 0.5 * burst.s) * gone;
        const { puffs, shades } = toneSprites(tone(line));
        for (const spot of S.spots) {
          const touch = clamp01((touches - burst.y - tideOffset(line, spot.x, w)) / (0.03 * h)) * tideHere(line, spot.x, w, 0);
          if (touch <= 0.02) continue;
          const n = k => noise(spot.seed + burst.seed + k), i = Math.floor(n(5) * puffs.length), a = env * touch;
          const r = 1.2 * S.fu * (0.4 + 0.7 * Math.min(2.6, burst.s)) * (0.5 + 0.5 * touch) * (0.8 + 0.4 * n(1)) * (0.7 + 0.4 * ease.out(clamp01(s / 120)));
          const x = spot.x + (n(2) - 0.5) * S.fu, y = r * (0.45 + 0.4 * n(6) - 1.1 * ease.out(clamp01(s / 260)));
          const angle = (n(3) - 0.5) * 0.8, flip = n(4) < 0.5 ? -1 : 1;
          if (pass === 0) {
            place(g, S.dpr, x, y + 0.3 * r, angle, 1.1 * flip, 0.9);
            g.globalAlpha = 0.22 * a;
            g.drawImage(shades[i], -r, -r, 2 * r, 2 * r);
            continue;
          }
          place(g, S.dpr, x, y, angle, flip, 1);
          drawPuff(g, puffs[i], a, 0, r);
        }
      }
    }
  }

  // The surf (see layoutSurf): where lines have washed back, the sheets they trail, the lines
  // themselves (each over the ones before it, the high tide over them all) and the spray on the top
  // edge. All of it has gone by the landing.
  function drawSurf(t) {
    const L = state.layout, S = L.surf;
    const active = Boolean(S) && t >= BEAT.fall && t < BEAT.land;
    show(surfCanvas, active);
    if (!active) return;
    const g = S.ctx, w = L.win.w, gone = 1 - smooth(BEAT.land - 240, BEAT.land - 30, t);
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, surfCanvas.width, surfCanvas.height);
    if (!puffSprites()) return;
    // The surf is in the sky's time of day; the high tide is in the picture's from the start, like the
    // cloud sea, and as the sea fills the window the camera goes into it: what is left of the other
    // lines turns to it too.
    const sky = S.into == null ? S.from : lerp(S.from, S.to, smooth(S.into, S.into + 70, t));
    const tone = line => (line.high ? S.to : sky);
    const live = [];
    for (const line of S.lines) {
      const q = tideAt(S, line, t);
      if (q) live.push([line, q, tone(line)]);
    }
    g.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
    for (const [line, q, d] of live) drawWet(g, line, q, w, d, gone);
    for (const [line, q, d] of live) drawSheet(g, S, line, q, w, d, gone);
    for (const [line, q, d] of live) drawLace(g, S, line, q, w, d, gone);
    drawSpray(g, S, t, w, tone, gone);
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalAlpha = 1;
  }

  // Speed lines through the whole window while the camera drops; they run up under the surf.
  function drawStreaks(t, camY) {
    const L = state.layout;
    const speed = Math.abs(camY - cameraAt(t - 16)) / 16 / (L.win.h / 400);   // windows per 400 ms
    const alpha = clamp01((speed - 0.25) / 0.9) * 0.75;
    for (const s of L.streaks) {
      if (alpha <= 0.01) { show(s.line, false); continue; }
      const period = L.win.h + s.length;
      const y = ((s.phase * period - 1.7 * (camY - L.camStart)) % period + period) % period - s.length;
      s.line.setAttribute('x1', fixed(s.x));
      s.line.setAttribute('x2', fixed(s.x));
      s.line.setAttribute('y1', fixed(y));
      s.line.setAttribute('y2', fixed(y + s.length));
      s.line.style.opacity = alpha.toFixed(3);
      show(s.line, true);
    }
  }

  // Measurement marks pinned in the sky during the fall, as over the surf shot in the Adachi video:
  // three dots and two small squares, [x, y] where they are when it begins (window shares), some low
  // in the window and some still below it. They rise with the sky and dissolve into the surf under
  // the top edge.
  const MARKS = [[0.14, 0.72], [0.5, 1.08], [0.83, 0.9], [0.3, 1.3], [0.68, 1.55]];

  function drawSkyMarks(t, camY) {
    const L = state.layout, rose = camY - cameraAt(BEAT.fall);
    const on = L.surf ? seg(t, BEAT.fall + 80, 150) : 0;
    [...lensMarks.dots, ...lensMarks.boxes].forEach((el, i) => {
      const x = MARKS[i][0] * L.win.w, y = MARKS[i][1] * L.win.h - rose;
      const visible = on > 0 && t < BEAT.land && y > -10 && y < L.win.h + 10;
      show(el, visible);
      if (!visible) return;
      if (el.tagName === 'circle') attrs(el, { cx: x, cy: y });
      else attrs(el, { x: x - 4.5, y: y - 4.5 });
      el.style.opacity = (on * smooth(0.02 * L.win.h, 0.16 * L.win.h, y)).toFixed(3);
    });
  }

  // The petals, inside the window (window px): a light pink face towards the light and a deeper
  // pink back, a white sheen down the middle, and the edge catching the light whenever a petal
  // turns to face it. In the fall they rise with the sky (p.near times as fast) into the surf,
  // dissolving as they near the top edge.
  function drawPetals(t, camY) {
    const L = state.layout, P = L.petals, w = L.win.w, h = L.win.h;
    const active = t >= BEAT.flood && t < BEAT.land;
    show(petalCanvas, active);
    if (!active) return;
    const g = P.ctx, rose = Math.max(0, camY - cameraAt(BEAT.fall));
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, petalCanvas.width, petalCanvas.height);
    for (const p of P.petals) {
      if (t < p.t0) continue;
      const at = petalAt(p, t), n = nudged(t, p.rings);
      const x = at.x + 6 * n.x, y = at.y + 6 * n.y - p.near * rose;
      const into = lerp(1, smooth(0.02 * h, 0.16 * h, y), seg(t, BEAT.fall, 200));   // dissolving into the surf
      const alpha = ease.out(seg(t, p.t0, 200)) * into, reach = 3 * p.size;
      if (x < -reach || y < -reach || x > w + reach || y > h + reach) continue;
      const c = Math.cos(at.flip);
      g.setTransform(P.dpr, 0, 0, P.dpr, 0, 0);
      g.translate(x, y);
      g.rotate(at.rot);
      g.scale(p.size * Math.max(0.1, Math.abs(c)), p.size);
      g.globalAlpha = alpha;
      g.fillStyle = c >= 0 ? P.lit : P.shaded;
      g.fill(PETAL);
      if (c > 0) {
        g.globalAlpha = alpha * 0.5 * c;
        g.fillStyle = '#fff';
        g.beginPath();
        g.ellipse(0.1, 0, 0.12, 0.5, 0, 0, 2 * Math.PI);
        g.fill();
      }
      const glint = clamp01((c - 0.8) / 0.2) ** 2;
      if (glint > 0) {
        g.globalAlpha = alpha * glint;
        g.strokeStyle = '#fff';
        g.lineWidth = 1.2 / p.size;
        g.stroke(PETAL);
      }
    }
    g.globalAlpha = 1;
  }

  function drawHello(t) {
    const L = state.layout, h = L.hello, T = BEAT.hello;
    const shown = t >= T && t < BEAT.dust + GUST_LEN + 50;
    show(helloSvg, shown);
    if (shown) {
      hello.g.setAttribute('transform', `translate(0 ${fixed(helloLift(L, t))})`);
      const midX = L.W / 2, midY = L.H / 2;
      // rings burst from the middle (the second one heavy)
      hello.rings.forEach((ring, i) => {
        const { k, r } = helloRing(L, i, t);
        ring.setAttribute('cx', fixed(midX));
        ring.setAttribute('cy', fixed(midY));
        ring.setAttribute('r', fixed(r));
        ring.style.opacity = k > 0 && k < 1 ? (0.7 * (1 - k)).toFixed(3) : 0;
      });
      // cap-height and baseline rules sweep out to the screen edges, with heavy bars at the baseline's ends
      const sweep = ease.out(seg(t, T, 240)), rulesFade = 1 - seg(t, T + 900, 300);
      hello.rules.forEach((rule, i) => {
        const ry = i ? h.base : h.cap;
        rule.setAttribute('x1', fixed(midX - midX * sweep));
        rule.setAttribute('x2', fixed(midX + midX * sweep));
        rule.setAttribute('y1', fixed(ry));
        rule.setAttribute('y2', fixed(ry));
        rule.style.opacity = (0.55 * rulesFade).toFixed(3);
      });
      const barIn = ease.out(seg(t, T + 200, 220));
      hello.bars.forEach((bar, i) => {
        const x = i ? h.x0 + h.total + 10 : h.x0 - 10, dir = i ? 1 : -1;
        bar.setAttribute('x1', fixed(x));
        bar.setAttribute('x2', fixed(x + dir * 26 * barIn));
        bar.setAttribute('y1', fixed(h.base));
        bar.setAttribute('y2', fixed(h.base));
        bar.style.opacity = (barIn * (1 - seg(t, BEAT.dust, 150))).toFixed(3);
      });
      hello.letters.forEach(({ guide, echo, letter }, i) => {
        // a vertical guide snaps in at each letter...
        const gIn = ease.out(seg(t, T + 120 + i * 50, 160));
        const gx = h.xs[i], extra = 0.25 * h.size;
        guide.setAttribute('x1', fixed(gx));
        guide.setAttribute('x2', fixed(gx));
        guide.setAttribute('y1', fixed(midY - (midY - h.cap + extra) * gIn));
        guide.setAttribute('y2', fixed(midY + (h.base - midY + extra) * gIn));
        guide.style.opacity = (0.55 * rulesFade).toFixed(3);
        // ...the letter's outline is drawn, an offset echo closes in, then the ink fills with a punch;
        // when the word blows away, each letter fades as its dust lifts off
        const draw = ease.inOut(seg(t, T + 200 + i * 70, 380));
        const fill = ease.out(seg(t, T + 480 + i * 70, 160));
        const punch = seg(t, T + 480 + i * 70, 260);
        const gone = seg(t, BEAT.dust + ((h.xs[i] - h.x0) / h.total) * 320, 180);
        letter.style.strokeDashoffset = fixed(2600 * (1 - draw));
        letter.style.fillOpacity = fill.toFixed(3);
        letter.style.opacity = draw > 0 ? (1 - gone).toFixed(3) : 0;
        letter.style.transform = `scale(${(1 + 0.16 * (1 - ease.back(punch))).toFixed(4)})`;
        const off = 10 * (1 - ease.out(seg(t, T + 260 + i * 70, 420)));
        echo.setAttribute('transform', `translate(${fixed(off)} ${fixed(off)})`);
        echo.style.opacity = draw > 0 ? (0.5 * (1 - fill)).toFixed(3) : 0;
      });
      // a dimension line under the word
      const dim = ease.out(seg(t, T + 560, 300)), dimFade = 1 - seg(t, BEAT.dust, 200);
      const dy = h.base + 0.16 * h.size, half = h.total / 2 * dim;
      hello.dimension.setAttribute('d', `M${fixed(midX - half)} ${fixed(dy - 8)}v16M${fixed(midX - half)} ${fixed(dy)}H${fixed(midX + half)}M${fixed(midX + half)} ${fixed(dy - 8)}v16`);
      hello.dimension.style.opacity = dim > 0 ? (0.8 * dimFade).toFixed(3) : 0;
      // as the word breaks up it sends out one heavy ring, which blows the butterflies and feathers
      // off the paper (layoutMotifs times each of them by when this ring reaches it)
      const gust = seg(t, BEAT.dust, GUST_LEN);
      hello.gust.setAttribute('cx', fixed(midX));
      hello.gust.setAttribute('cy', fixed(midY));
      hello.gust.setAttribute('r', fixed(L.motifs.gust.reach * (0.06 + 0.94 * ease.out(gust))));
      hello.gust.style.opacity = gust > 0 && gust < 1 ? (0.8 * (1 - gust)).toFixed(3) : 0;
    }
    drawDust(t);
  }

  // HELLO blows away as dust: each speck starts where its piece of a letter was and drifts up
  // and to the right, fading.
  function drawDust(t) {
    const L = state.layout, h = L.hello;
    const active = t >= BEAT.dust && t < BEAT.dust + 1500;
    show(dustCanvas, active);
    if (!active) return;
    const g = dustCanvas.getContext('2d'), s = L.dustScale;
    g.setTransform(s, 0, 0, s, 0, 0);
    g.clearRect(0, 0, L.W, L.H);
    const lift = -0.05 * L.H;   // where the word hung when it broke up
    for (const p of h.dust) {
      const k = seg(t, BEAT.dust + p.delay, p.life);
      if (k <= 0 || k >= 1) continue;
      const e = ease.out(k);
      g.globalAlpha = (1 - k) * 0.95;
      g.fillStyle = p.tint;
      const size = p.size * (1 - 0.5 * k);
      g.fillRect(p.x + p.dx * e + 6 * Math.sin(k * 9 + p.delay), p.y + lift + p.dy * e, size, size);
    }
    g.globalAlpha = 1;
  }

  function drawFocus(t, shot) {
    const f = shot.faces;
    const p = seg(t, BEAT.af, 220);
    const out = seg(t, BEAT.afOut, 400);
    const active = Boolean(f) && p > 0 && out < 1;
    show(lensMarks.af, active);
    lensMarks.cross.forEach(line => show(line, active));
    if (!active) return;
    // the brackets close round the faces, which move with the opening window (window-relative here)
    const { rect } = shot;
    const grow = 1 + 0.5 * (1 - ease.out(p));
    const cx = (f.x0 + f.x1) / 2 - rect.x, cy = (f.y0 + f.y1) / 2 - rect.y;
    const hw = (f.x1 - f.x0) / 2 * grow, hh = (f.y1 - f.y0) / 2 * grow;
    const arm = Math.min(hw, hh) * 0.35;
    lensMarks.af.setAttribute('d', bracketPath(cx - hw, cy - hh, cx + hw, cy + hh, arm));
    // two quick blinks, then the brackets turn blue: focus locked
    const blink = t > BEAT.af + 250 && t < BEAT.af + 310 || t > BEAT.af + 360 && t < BEAT.af + 420;
    lensMarks.af.classList.toggle('locked', t >= BEAT.af + 420);
    lensMarks.af.style.opacity = (blink ? 0.15 : (1 - out)).toFixed(3);
    // dashed cross-hairs run from the brackets to the window edges while the focus is found
    const reach = ease.out(seg(t, BEAT.af + 60, 260)), crossFade = 1 - seg(t, BEAT.focus + 500, 300);
    const [h, v] = lensMarks.cross;
    attrs(h, { x1: cx - cx * reach, x2: cx + (rect.w - cx) * reach, y1: cy, y2: cy });
    attrs(v, { x1: cx, x2: cx, y1: cy - cy * reach, y2: cy + (rect.h - cy) * reach });
    lensMarks.cross.forEach(line => { line.style.opacity = crossFade.toFixed(3); });
  }

  function drawHud(t, camY, shot) {
    const L = state.layout, w = L.win, m = L.m, e = shot.e;
    // The viewfinder corners start round the screen edge, close onto the window for the shot and go
    // back out to the screen edge as the window opens. With the window docked aside for a section
    // they frame the picture in it (outset px out from its edges, kept inside the window), so they
    // follow it as the divider is dragged; with the picture folded away behind the section, the
    // screen again.
    const close = ease.back(seg(t, BEAT.frame, 160)) * (1 - e);
    const draw = ease.out(seg(t, 40, 260));
    const size = 26, outset = 10, F = shot.dock > 0 ? shot.rect : L.screen;
    let box = { x0: F.x + m, y0: F.y + m, x1: F.x + F.w - m, y1: F.y + F.h - m };
    if (shot.aside > 0 && shot.frame) {
      const fit = shot.frame.fit, keep = 8;   // (how far inside the window's edges they stay)
      const pic = {
        x0: Math.max(F.x + keep, F.x + fit.x - outset), y0: Math.max(F.y + keep, F.y + fit.y - outset),
        x1: Math.min(F.x + F.w - keep, F.x + fit.x + fit.w + outset), y1: Math.min(F.y + F.h - keep, F.y + fit.y + fit.h + outset),
      };
      for (const key of Object.keys(box)) box[key] = lerp(box[key], pic[key], shot.aside);
    }
    const x0 = lerp(box.x0, w.x - outset, close), y0 = lerp(box.y0, w.y - outset, close);
    const x1 = lerp(box.x1, w.x + w.w + outset, close), y1 = lerp(box.y1, w.y + w.h + outset, close);
    const at = [[x0, y0], [x1 - size, y0], [x0, y1 - size], [x1 - size, y1 - size]];
    corners.forEach((c, i) => {
      c.style.transform = `translate(${fixed(at[i][0])}px, ${fixed(at[i][1])}px) scale(${draw.toFixed(3)})`;
      c.style.transformOrigin = `${i % 2 ? 100 : 0}% ${i < 2 ? 0 : 100}%`;
    });
    // over the opened picture the marks turn white, with a faint shadow to hold them on bright skies (on
    // the paper they are its ink, which follows the time of day)
    const white = `${(100 * e).toFixed(1)}%`;
    setVar(hud, '--hud', `color-mix(in srgb, var(--ink), #fff ${white})`);
    setVar(hud, '--hud-soft', `color-mix(in srgb, rgb(${TONE.pale.join(' ')}), #fff ${white})`);
    hud.style.filter = e > 0 ? `drop-shadow(0 0 1.5px rgba(8, 22, 44, ${(0.5 * e).toFixed(2)}))` : '';
    marks.forEach((mark, i) => setVar(mark, '--pop', ease.back(seg(t, 120 + i * 60, 220)).toFixed(3)));
    dashes.forEach((dash, i) => setVar(dash, '--grow', ease.out(seg(t, 160 + (i % 4) * 60, 260)).toFixed(3)));
    // the record light and the ruler beside the window leave as the window opens
    const extras = ease.out(seg(t, 100, 300)) * (1 - Math.max(e, seg(t, BEAT.afOut, 400)));
    rec.style.opacity = extras.toFixed(3);
    ruler.style.opacity = (extras * ease.out(seg(t, BEAT.frame, 300))).toFixed(3);
    ruler.style.backgroundPositionY = `${fixed(-camY * 0.9)}px`;
    // the side meters come in at the start; a level mark slides down the left one as the camera
    // sinks and falls. The section index takes the right one's place as it comes in (on a phone,
    // where there are no meters, the top dashes' place).
    const metersIn = 0.7 * ease.out(seg(t, 200, 400)), indexIn = seg(t, BEAT.button - 150, 400);
    meterTicks.style.opacity = metersIn.toFixed(3);
    meterTicksRight.style.opacity = (metersIn * (1 - indexIn)).toFixed(3);
    setVar(stage, '--index-in', indexIn.toFixed(3));
    const level = lerp(L.meter.y0, L.meter.y1, dropAt(t));
    attrs(meterLevel, { x1: L.meter.x, x2: L.meter.x + 16, y1: level, y2: level });
    meterLevel.style.opacity = (ease.out(seg(t, BEAT.hello - 200, 300)) * (1 - e)).toFixed(3);
    setVar(stage, '--grid-in', ease.out(seg(t, 0, 400)).toFixed(3));
  }

  function drawIdentity(t, shot) {
    const nameIn = ease.out(seg(t, BEAT.name, 700));
    // The text group grows from 85% while rising into place (as in the Bocchi template).
    nameEl.style.opacity = nameIn.toFixed(3);
    nameEl.style.transform = `translateY(${fixed((1 - nameIn) * 16)}px) scale(${(0.85 + 0.15 * nameIn).toFixed(4)})`;
    const grow = (part, delay, length) => deco[part].style.setProperty('--grow', ease.out(seg(t, BEAT.name + delay, length)).toFixed(3));
    grow('thick', 60, 300);
    grow('thin', 120, 600);
    grow('dash', 320, 500);
    grow('dot', 380, 200);
    grow('square', 460, 220);
    // (the blinds close up; on a wide screen they are the legend's hatched block, styles.css)
    const blinds = seg(t, BEAT.name + 480, 700);
    deco.blinds.style.setProperty('--grow', ease.out(blinds).toFixed(3));
    deco.blinds.style.setProperty('--gap', `${(7 - 4.92 * ease.out(blinds)).toFixed(2)}px`);
    // a soft shade behind the name, only once it sits on the picture
    setVar(identity, '--shade', (shot.e * ease.out(seg(t, BEAT.name - 250, 700)) * (1 - shot.veil)).toFixed(3));
    // On a wide screen the opened picture's name sits at its bottom left (styles.css), where the window
    // docking aside leaves it; on a phone, and until the window has opened, it stays centred on the
    // picture. On a phone the docked picture is too small for it, so it steps out before the picture's
    // edge passes it. It steps out too while the picture folds away behind a section. Stepped out, it
    // no longer takes the pointer (it would sit over the panel).
    const centred = state.layout.portrait || shot.e <= 0.5;
    const left = centred ? `${fixed(shot.rect.x)}px` : '', width = centred ? `${fixed(shot.rect.w)}px` : '';
    if (identity.style.left !== left) identity.style.left = left;
    if (identity.style.width !== width) identity.style.width = width;
    const away = state.layout.portrait ? clamp01(shot.dock / 0.2) : clamp01(shot.veil / 0.6);
    identity.style.opacity = away > 0 ? (1 - away).toFixed(3) : '';
    identity.style.visibility = away >= 1 ? 'hidden' : '';
  }

  // The section index comes in with the replay button, and the focus brackets lock onto the
  // current square. It is white over the picture (with a shade behind it) and ink once the picture
  // has moved out from under it (white again over the picture folded away); the colour fades in CSS.
  function drawIndex(t, shot) {
    const D = state.layout.dock, d = shot.dock, shown = ease.out(seg(t, BEAT.button, 400));
    const at = key => lerp(D.home[key], D.docked[key], d);
    const x = at('x'), y = at('y'), ax = at('ax'), ay = at('ay');
    indexNav.style.transform = `translate(${fixed(x)}px, ${fixed(y)}px) translate(${fixed(-100 * ax)}%, ${fixed(-100 * ay)}%)`;
    const left = x - ax * D.box.w, top = y - ay * D.box.h, r = shot.rect;
    const over = left < r.x + r.w && left + D.box.w > r.x && top < r.y + r.h && top + D.box.h > r.y;
    indexNav.classList.toggle('on-paper', !over);
    indexNav.style.opacity = shown.toFixed(3);
    indexNav.style.pointerEvents = shown < 1 ? 'none' : '';
    const lock = ease.out(seg(t, BEAT.button + 150, 450));
    setVar(brackets, '--zoom', (1 + 0.7 * (1 - lock)).toFixed(3));
    setVar(brackets, '--seen', lock.toFixed(3));
    indexShade.style.opacity = (shown * (1 - shot.aside)).toFixed(3);
    setVar(stage, '--dock', d.toFixed(3));
  }

  // The panel: beside the docked picture (under it on a phone), or with the picture folded away the
  // wide column in the middle of the screen, the section laid out across it (.spread) and lettered
  // in white (.over). It does not travel with the fold: the section fades out where it is as the
  // picture sets off, changes places unseen halfway and fades in at the other place as the picture
  // settles, so it is never laid out again or recoloured on the way. (The section itself fades, not
  // the panel: a panel seen through would leave its frosted block nothing behind it to blur.)
  function drawPanel(shot) {
    const p = state.layout.portrait ? 0 : fold.value, spread = p >= 0.5;
    const box = spread ? state.layout.dock.column : shot.at.pane;
    for (const [name, key] of [['px', 'x'], ['py', 'y'], ['pw', 'w'], ['ph', 'h']]) {
      for (const el of [panel, panelBar.bar]) setVar(el, `--${name}`, `${fixed(box[key])}px`);   // (its scrollbar with it)
    }
    setVar(panel, '--fold', spread ? '1' : '0');
    panel.classList.toggle('over', spread);
    panel.classList.toggle('spread', spread);
    panelBar.bar.classList.toggle('over', spread);
    const seen = spread ? seg(p, 1 - FOLD_FADE, FOLD_FADE) : 1 - seg(p, 0, FOLD_FADE);
    const opacity = seen < 1 ? seen.toFixed(3) : '';
    for (const el of [...panes, panelBar.bar]) if (el.style.opacity !== opacity) el.style.opacity = opacity;
  }

  // The divider, with a section open on a wide screen: on the docked picture's right edge, moving to
  // the screen's left edge as the picture folds away (it is 12px wide, centred on the line where
  // there is room). It takes the pointer only once the window has docked.
  function drawDivider(shot) {
    const on = !state.layout.portrait && dock.tab !== 'home' && dock.value >= 1;
    if (divider.hidden === on) divider.hidden = !on;
    if (!on) return;
    const x = (1 - shot.fold) * shot.at.rect.w;
    divider.style.transform = `translateX(${fixed(Math.max(0, x - 6))}px)`;
    divider.classList.toggle('edge', x < 6);
    const folded = foldWanted(), value = folded ? '0' : String(Math.round(100 * shot.at.share));
    if (divider.getAttribute('aria-valuenow') !== value) {
      divider.setAttribute('aria-valuenow', value);
      divider.setAttribute('aria-valuetext', folded ? 'folded away' : `${value}% of the screen`);
    }
  }

  function render(t) {
    const camY = cameraAt(t), shot = shotAt(t, camY);
    drawGuides(t);
    drawOrnaments(t);
    drawMotifs(t);
    drawWindow(t, camY, shot);
    drawMeet(t);
    drawPetals(t, camY);
    drawSurf(t);
    drawSkyMarks(t, camY);
    drawFlock(t);
    drawTracking(t);
    drawStreaks(t, camY);
    drawHello(t);
    drawFocus(t, shot);
    drawHud(t, camY, shot);
    drawIdentity(t, shot);
    drawIndex(t, shot);
    drawPanel(shot);
    drawDivider(shot);
    // the replay button comes in last; on a phone it would sit on a section's text, so it steps out
    // as soon as the window starts to dock. Gone, it cannot be reached by the keyboard either.
    const there = replayShown.value * (state.layout.portrait ? 1 - clamp01(shot.dock / 0.15) : 1);
    replayButton.style.opacity = (ease.out(seg(t, BEAT.button, 400)) * there).toFixed(3);
    replayButton.style.pointerEvents = there < 0.5 ? 'none' : '';
    replayButton.style.visibility = there > 0 ? '' : 'hidden';
  }

  // ---------- sections ----------

  const tabFromHash = () => (TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home');
  const homeUrl = () => location.pathname + location.search;

  // Marks the current section in the index and puts the focus brackets on its square, with the
  // lock-on when the section has changed (they are placed afresh after every layout).
  function placeBrackets(lock) {
    const active = indexLinks.find(link => link.dataset.tab === dock.tab);
    indexLinks.forEach(link => {
      link.classList.toggle('active', link === active);
      if (link === active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    const tile = active.querySelector('b');
    brackets.style.setProperty('--x', `${active.offsetLeft + tile.offsetLeft}px`);
    brackets.style.setProperty('--y', `${active.offsetTop + tile.offsetTop}px`);
    brackets.style.setProperty('--s', `${tile.offsetWidth}px`);
    drawScale();
    if (!lock) return;
    brackets.classList.remove('lock');
    void brackets.offsetWidth;   // restart the lock-on
    brackets.classList.add('lock');
  }

  // The index's focus scale, like the one on a lens (CONTEXT 板块索引): a hairline beside the squares,
  // on a wide screen on the right-hand meter's line, whose place it takes (the squares stand INDEX_IN
  // in from it), on a phone just over them. A long tick points at each square's middle, the current
  // one's blue and a little longer; fine ticks run between, six to a square's pitch, a little past the
  // end squares.
  function drawScale() {
    const portrait = stage.classList.contains('portrait');
    const tiles = indexLinks.map(link => {
      const b = link.querySelector('b');
      return { at: (portrait ? link.offsetLeft + b.offsetLeft : link.offsetTop + b.offsetTop) + b.offsetWidth / 2, side: b.offsetWidth, on: link.classList.contains('active') };
    });
    const step = (tiles[1].at - tiles[0].at) / 6, first = tiles[0].at - (portrait ? 2 : 3) * step, last = tiles[tiles.length - 1].at + (portrait ? 2 : 3) * step;
    // the line (nav px) and which way the ticks point from it, towards the squares
    const line = portrait ? indexLinks[0].offsetTop + indexLinks[0].querySelector('b').offsetTop - 13 : indexNav.offsetWidth + INDEX_IN - 3;
    const dir = portrait ? 1 : -1, reach = portrait ? 6 : INDEX_IN - 7;
    const tick = (along, length) => (portrait ? `M${fixed(along)} ${fixed(line)}V${fixed(line + dir * length)}` : `M${fixed(line)} ${fixed(along)}H${fixed(line + dir * length)}`);
    let fine = portrait ? `M${fixed(first)} ${fixed(line)}H${fixed(last)}` : `M${fixed(line)} ${fixed(first)}V${fixed(last)}`;
    for (let k = -(portrait ? 2 : 3); first + (k + (portrait ? 2 : 3)) * step <= last + 0.1; k++) {
      if (k % 6) fine += tick(tiles[0].at + k * step, k % 3 ? 3 : 5);
    }
    indexScale.fine.setAttribute('d', fine);
    indexScale.long.setAttribute('d', tiles.filter(q => !q.on).map(q => tick(q.at, reach)).join(''));
    indexScale.lit.setAttribute('d', tiles.filter(q => q.on).map(q => tick(q.at, reach + 2)).join(''));
  }

  const drawFinal = () => render(state.debugT ?? END);
  const drawSoon = () => { if (!tweenFrame) tweenFrame = requestAnimationFrame(stepTweens); };

  // Eases a value of the final screen (dock, fold, split or the replay button's being there) to target
  // over ms along curve (at once with reduced motion), drawing the final screen as it goes.
  function moveTo(holder, target, ms, curve = p => p) {
    tweens.delete(holder);
    if (reduceMotion || ms <= 0) {
      holder.value = target;
      drawFinal();
      return;
    }
    tweens.set(holder, { from: holder.value, to: target, began: performance.now(), length: ms, curve });
    drawSoon();
  }

  function stepTweens(now) {
    tweenFrame = 0;
    for (const [holder, m] of tweens) {
      const p = clamp01((now - m.began) / m.length);
      holder.value = p < 1 ? lerp(m.from, m.to, m.curve(p)) : m.to;
      if (p >= 1) tweens.delete(holder);
    }
    drawFinal();
    if (tweens.size) drawSoon();
  }

  // Ends every tween where it was going (the opening is about to play, or a frame is held).
  function settle() {
    cancelAnimationFrame(tweenFrame);
    tweenFrame = 0;
    for (const [holder, m] of tweens) holder.value = m.to;
    tweens.clear();
  }

  // Shows a section ('home': the opening screen). From the opening screen the window docks aside
  // first and the panel comes up as it settles; between sections only the panel's content changes
  // (and the picture folds away or comes back if the section wants it otherwise). The section shown
  // takes the keyboard's focus, so the keys scroll it.
  function go(tab, instant) {
    if (!state.layout || tab === dock.tab && !instant) return;   // (before the first layout the boot reads the hash)
    if (state.running) enterIdle();   // asked for during the opening: skip to its end first
    endSwap();
    const fromHome = dock.tab === 'home';
    if (tab === 'settings' && dock.tab !== 'settings') fold.touched = false;   // they fold the picture away afresh
    dock.tab = tab;
    placeBrackets(true);
    moveTo(replayShown, tab === 'home' || tab === 'settings' ? 1 : 0, instant ? 0 : 300, ease.inOut);
    clearTimeout(dock.reveal);
    panes.forEach(pane => { pane.hidden = true; });
    if (tab === 'home') {
      endDrag();
      tweens.delete(fold);   // the fold holds while the window opens out, which hides it anyway
      panel.classList.remove('open');
      panel.inert = true;
      moveTo(dock, 0, instant ? 0 : 650);
      waitForPass();
      if (gridPen.stale || meetPen.stale) penAgain(instant ? 0 : 650);
      return;
    }
    // nothing on the fill moves while a section is open (an ornament coming in again is put in place;
    // one still due comes in once the opening screen is back)
    dropLight(true, true);
    clearTimeout(gridPen.timer);
    tweens.delete(gridPen);
    gridPen.value = 1;
    clearTimeout(meetPen.timer);
    tweens.delete(meetPen);
    if (!meetPen.stale) meetPen.value = 1;
    // on the opening screen the fold is not seen: the section starts as it wants the picture
    if (instant || dock.value === 0) {
      tweens.delete(fold);
      fold.value = foldWanted() ? 1 : 0;
    } else {
      applyFold();
    }
    const reveal = () => {
      const shown = panes.find(pane => pane.dataset.tab === tab);
      panel.classList.add('open');
      panel.inert = false;
      panes.forEach(pane => { pane.hidden = pane !== shown; });
      panel.scrollTop = 0;
      picks.scrollTop = 0;   // (the settings' pictures scroll on their own when spread across the middle)
      if (tab === 'settings') loadPicks();
      if (!shown.contains(document.activeElement)) shown.focus({ preventScroll: true });
    };
    if (fromHome || instant) moveTo(dock, 1, instant ? 0 : 700);
    if (instant) reveal();
    else dock.reveal = setTimeout(reveal, fromHome ? 380 : 140);
  }

  // After a change of picture the pen goes over the fill's grid again (GRID), once the window has
  // opened out on the opening screen (after delay ms), and then the ornament comes in again for the
  // new picture (MEET). (Only the ornament is due where the opening screen came up before its picture
  // was in: it comes in without the pen.)
  function penAgain(delay) {
    const grid = gridPen.stale;
    gridPen.stale = false;
    clearTimeout(gridPen.timer);
    clearTimeout(meetPen.timer);
    if (reduceMotion) { meetAgain(); return; }
    gridPen.timer = setTimeout(() => {
      if (dock.tab !== 'home' || state.running) return;
      if (!grid) { meetAgain(); return; }
      gridPen.value = 0;
      moveTo(gridPen, 1, GRID.len, ease.out);
      meetPen.timer = setTimeout(meetAgain, GRID.len);
    }, delay);
  }

  // The ornament comes in again, if it is still due, its picture and the fill round it are in (it takes
  // its colours from the fill) and the opening screen is up (at once with reduced motion).
  function meetAgain() {
    if (!meetPen.stale || !sceneIn() || dock.tab !== 'home' || state.running) return;
    meetPen.stale = false;
    meetPen.value = 0;
    moveTo(meetPen, 1, MEET.len);
  }

  // Whether the picture is folded away behind the section: as the visitor chose, except that the
  // settings fold it away by themselves (so its blur can be seen) until the visitor folds it away or
  // brings it back there; leaving them, it is as the visitor chose.
  function foldWanted() {
    return prefs.folded || dock.tab === 'settings' && !fold.touched;
  }

  function applyFold() {
    const to = foldWanted() ? 1 : 0;
    endSwap();
    moveTo(fold, to, FOLD_MS * Math.abs(to - fold.value));
    if (kbSay.dataset.code === 'KeyB') describeKey(keyEls.get('KeyB'));   // B does the other thing now
  }

  // Folds the docked picture away behind the section, or brings it back aside (B, Enter on the
  // divider, a click on the screen's left edge, the divider dragged past the narrowest). The choice
  // holds for the visit, in every section.
  function setFold(on) {
    prefs.folded = on;
    fold.touched = true;
    keepPrefs();
    applyFold();
  }

  function toggleFold() {
    if (state.layout.portrait || dock.tab === 'home' || drag.moved) return;
    setFold(!foldWanted());
  }

  // Gives the docked picture this share of the width, over ms. The share is the visitor's choice
  // and is kept as it is; a screen too narrow for it shows the nearest it allows.
  function setSplit(share, ms) {
    const D = state.layout.dock;
    split.value = Math.min(D.max, Math.max(D.min, split.value));   // ease from where it is seen
    prefs.split = share;
    keepPrefs();
    endSwap();
    moveTo(split, share, ms, ease.out);
  }

  // The share of the width for the divider's line at x (px), within the split's limits.
  function splitAt(x) {
    const L = state.layout;
    return Math.min(L.dock.max, Math.max(L.dock.min, x / L.W));
  }

  // Where the divider's line is now (px from the screen's left edge).
  function dividerX() {
    const L = state.layout;
    return (1 - ease.inOut(fold.value)) * dockedAt(L).rect.w;
  }

  // Lets go of the divider (forgetting the drag first: letting go of the pointer reports back).
  function endDrag() {
    const id = drag.id;
    if (id == null) return;
    drag.id = null;
    drag.moved = false;
    if (divider.hasPointerCapture(id)) divider.releasePointerCapture(id);
    divider.classList.remove('dragging');
    stage.classList.remove('resizing');
  }

  // A drag of the divider let go at the pointer's x: past the narrowest the picture folds away
  // (and will come back as wide as before the drag); otherwise the split it reached is kept. A click
  // without a drag brings back a picture folded away.
  function dropDivider() {
    const { moved, from } = drag, x = drag.x - drag.grab, L = state.layout;
    endDrag();
    if (!moved) {
      if (foldWanted()) setFold(false);
    } else if (x < L.dock.min * L.W - SPLIT.snap) {
      prefs.split = from;
      moveTo(split, from, FOLD_MS, ease.out);
      setFold(true);
    } else {
      prefs.split = split.value;
      keepPrefs();
    }
  }

  // What scrolls: the section, except in the settings spread across the middle of the screen, where
  // only the pictures do (the rest stays put; on a window too narrow to spread them, the section).
  const scroller = () => (dock.tab === 'settings' && getComputedStyle(picks).overflowY !== 'visible' ? picks : panel);

  // A scrollbar of the page's own for box (styles.css: .scrollbar; where the pointer is not a mouse it is
  // never shown): a thumb down its right edge, as long as the share of it in view, there only while the
  // box scrolls and has more to see than it shows. Dragged, it scrolls the box; a click beside it pages
  // it, the wheel over it scrolls it. It follows the box's size and what is in it (watch); place puts
  // the bar beside it where nothing else keeps it there (the panel's goes with the panel: drawPanel).
  function makeScrollbar(box, watch, place) {
    const INSET = 6, LEAST = 24;   // px: the thumb's travel short of either end, its shortest
    const bar = document.createElement('div'), thumb = document.createElement('i'), held = { id: null, y: 0, top: 0 };
    bar.className = 'scrollbar';
    bar.setAttribute('aria-hidden', 'true');
    bar.append(thumb);
    box.after(bar);
    const sizes = () => {
      const view = box.clientHeight, all = box.scrollHeight, track = view - 2 * INSET;
      return { view, all, track, length: Math.max(LEAST, track * view / all) };
    };
    function update() {
      const { view, all, track, length } = sizes(), on = all > view + 1 && getComputedStyle(box).overflowY !== 'visible';
      bar.classList.toggle('on', on);
      if (!on) return;
      place?.(bar);
      thumb.style.height = `${fixed(length)}px`;
      thumb.style.transform = `translateY(${fixed(INSET + (track - length) * box.scrollTop / (all - view))}px)`;
    }
    box.addEventListener('scroll', update, { passive: true });
    const sized = new ResizeObserver(update);
    for (const el of [box, ...watch]) sized.observe(el);
    thumb.addEventListener('pointerdown', event => {
      if (event.button !== 0 || held.id != null) return;
      event.preventDefault();
      Object.assign(held, { id: event.pointerId, y: event.clientY, top: box.scrollTop });
      thumb.setPointerCapture(event.pointerId);
      bar.classList.add('held');
      stage.classList.add('grabbing');
    });
    thumb.addEventListener('pointermove', event => {
      if (event.pointerId !== held.id) return;
      const { view, all, track, length } = sizes();
      box.scrollTop = held.top + (event.clientY - held.y) * (all - view) / Math.max(1, track - length);
    });
    const letGo = event => {
      if (event.pointerId !== held.id) return;
      held.id = null;
      bar.classList.remove('held');
      stage.classList.remove('grabbing');
    };
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) thumb.addEventListener(type, letGo);
    bar.addEventListener('pointerdown', event => {
      if (event.button !== 0 || event.target === thumb) return;
      event.preventDefault();
      const down = event.clientY > thumb.getBoundingClientRect().top;
      box.scrollBy({ top: (down ? 1 : -1) * Math.max(40, 0.875 * box.clientHeight), behavior: reduceMotion ? 'auto' : 'smooth' });
    });
    bar.addEventListener('wheel', event => {
      event.preventDefault();
      box.scrollBy({ top: event.deltaY * (event.deltaMode === 1 ? 40 : event.deltaMode === 2 ? box.clientHeight : 1) });
    }, { passive: false });
    return { bar, update };
  }

  // The scrolling keys, when the keyboard's focus is outside what scrolls (the page itself does not
  // scroll): the browser's own steps, smooth unless the key is held or motion is reduced.
  function scrollPanel(key, back, held) {
    const box = scroller(), page = Math.max(40, 0.875 * box.clientHeight), end = box.scrollHeight - box.clientHeight;
    const by = { ArrowUp: -40, ArrowDown: 40, PageUp: -page, PageDown: page, ' ': back ? -page : page }[key];
    const top = key === 'Home' ? 0 : key === 'End' ? end : box.scrollTop + by;
    box.scrollTo({ top, behavior: held || reduceMotion ? 'auto' : 'smooth' });
  }

  // Replays the opening (the replay button, R). It ends on the opening screen, so it starts from there.
  function replay() {
    if (dock.tab !== 'home') {
      history.replaceState(null, '', homeUrl());
      go('home', true);
    }
    play();
  }

  // The visitor's choices last for the visit (browsing session), like the opening. (A picture chosen
  // that is no longer in the pool is dropped once the pool is in.)
  function recallPrefs() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(PREFS_KEY) || 'null');
      if (saved && Number.isFinite(saved.split)) prefs.split = Math.min(SPLIT.max, Math.max(SPLIT.min, saved.split));
      if (saved && typeof saved.folded === 'boolean') prefs.folded = saved.folded;
      if (saved && Number.isFinite(saved.glass)) prefs.glass = clamp01(saved.glass);
      if (saved && Number.isFinite(saved.blur)) prefs.blur = clamp01(saved.blur);
      if (saved && clock.MODES.includes(saved.time)) prefs.time = saved.time;
      if (saved && typeof saved.scene === 'string') prefs.scene = saved.scene;
    } catch { /* no storage (blocked site data), or a damaged entry: the defaults */ }
    split.value = prefs.split;
    fold.value = prefs.folded ? 1 : 0;
    for (const name of Object.keys(sliders)) showLook(name);
  }

  function keepPrefs() {
    try {
      sessionStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    } catch { /* no storage: the choices last until the page is left */ }
  }

  // A section asked for on the page (the index, Esc) gets a history entry of its own, so the back
  // button (a phone's back gesture) returns to where the visitor was.
  function navigate(tab) {
    if (tab === dock.tab) return;
    history.pushState(null, '', tab === 'home' ? homeUrl() : `#${tab}`);
    go(tab);
  }

  // The opening plays once per visit (browsing session); a refresh opens on its final screen.
  function firstOpening() {
    try {
      if (sessionStorage.getItem(SEEN_KEY)) return false;
      sessionStorage.setItem(SEEN_KEY, '1');
    } catch { /* no storage (blocked site data): it plays every time */ }
    return true;
  }

  // ---------- settings ----------

  // A blur setting ('glass': the frosted block's strength, 'blur': the picture's own; 0 to 1) shown
  // on its ruler and on the page: the block's strength goes to styles.css, the picture's blur is
  // drawn with the next frame.
  function showLook(name) {
    const value = prefs[name], slider = sliders[name];
    slider.value = String(value);
    slider.setAttribute('aria-valuetext', value ? `${Math.round(100 * value)}%` : 'none');
    if (name === 'glass') stage.style.setProperty('--glass', String(value));
  }

  function setLook(name, value) {
    prefs[name] = clamp01(value);
    keepPrefs();
    showLook(name);
    if (name === 'blur' && state.layout && !state.running) drawFinal();
  }

  // The time of day worked out again (every TICK ms while the page is seen, and as soon as it is seen
  // again): the paper follows it, eased over, but not while the opening plays (it does once that is
  // over); the window's sky and the pictures follow it with the next opening.
  function tick() {
    state.time = clock.at(state.at ?? new Date(), prefs.time);
    if (!state.running) clock.paper(state.time, true);
    sayTime();
  }

  // The time of day chosen in the settings ('auto': the visitor's own).
  function setTime(mode) {
    if (mode === prefs.time || !clock.MODES.includes(mode)) return;
    prefs.time = mode;
    keepPrefs();
    tick();
  }

  // The settings' time of day: the tile chosen, and under them what the time is now and the sun's last
  // and next rising or setting (where it rises and sets at all), in the visitor's own time.
  function sayTime() {
    for (const tile of times.children) {
      const pressed = String(tile.dataset.time === prefs.time);
      if (tile.getAttribute('aria-pressed') !== pressed) tile.setAttribute('aria-pressed', pressed);
    }
    const { real, sun } = state.time, hm = date => [date.getHours(), date.getMinutes()].map(v => String(v).padStart(2, '0')).join(':');
    const events = sun.last && sun.next ? [sun.last, sun.next].map(e => `${e.rise ? 'sunrise' : 'sunset'} ${hm(e.at)}`) : [];
    const said = [`Now ${real.toUpperCase()}`, ...events].join(' · ');
    if (timeNow.textContent !== said) timeNow.textContent = said;
  }

  // The settings' pictures: a tile for each in the pool after the random one, the picture over its
  // own fill (its thumbnail twice). Their pictures load only once the settings are first shown.
  function makePicks() {
    state.manifest.scenes.forEach((s, i) => {
      const pick = document.createElement('button'), fill = document.createElement('img'), img = document.createElement('img');
      pick.className = 'pick';
      pick.type = 'button';
      pick.dataset.scene = String(i);
      pick.setAttribute('aria-label', `${s.title || `Picture ${i + 1}`}${s.artist ? `, art by ${s.artist}` : ''}`);
      fill.className = 'pick-fill';
      for (const el of [fill, img]) {
        el.alt = '';
        el.decoding = 'async';
        el.dataset.src = `assets/${s.thumb || s.far}`;
      }
      pick.append(fill, img);
      picks.append(pick);
    });
    markPicks();
    picksBar.update();
  }

  function loadPicks() {
    for (const img of picks.querySelectorAll('img[data-src]')) {
      img.src = img.dataset.src;
      delete img.dataset.src;
    }
  }

  // The chosen picture's tile shows as pressed (the random one's while none is chosen).
  function markPicks() {
    for (const pick of picks.children) {
      const s = state.manifest.scenes[pick.dataset.scene];
      pick.setAttribute('aria-pressed', String((s ? s.far : null) === prefs.scene));
    }
  }

  // A tile chosen: that picture for the rest of the visit (a refresh and a replay keep it), put up at
  // once with a rack focus (unless it is up already); the random tile only lets the next replay or
  // visit draw one again. A picture that cannot be had leaves the choice as it was.
  async function choosePicture(pick) {
    const index = pick.dataset.scene == null ? -1 : Number(pick.dataset.scene);
    const s = state.manifest.scenes[index] || null, file = s ? s.far : null;
    if (file === prefs.scene) return;
    const before = prefs.scene, count = ++swap.count, token = state.playToken;
    prefs.scene = file;
    keepPrefs();
    markPicks();
    if (!s || index === state.sceneIndex) return;
    // (a later choice, a replay or another opening takes over from this one)
    const current = () => count === swap.count && token === state.playToken && !state.running;
    try {
      // fetched and decoded first, so that the new picture is in at once
      await Promise.all([s.far, sharpOf(s)].map(name => {
        const img = new Image();
        img.src = `assets/${name}`;
        return img.decode();
      }));
    } catch {
      if (count === swap.count) {
        prefs.scene = before;
        keepPrefs();
        markPicks();
      }
      return;
    }
    if (!current()) return;
    // The picture as it is seen stays over the new one until it is in. While the picture moves (it
    // folds, docks or is resized) it is only swapped, as with reduced motion.
    let still = null;
    if (!reduceMotion && !tweens.size) {
      still = coverScene();
      await still.ready;
      if (!current()) return;
      if (swap.layer !== still.layer) still = null;   // the picture has started to move since
    }
    state.sceneIndex = index;
    gridPen.stale = true;   // (the pen goes over the new picture's grid when the opening screen is back)
    meetPen.stale = true;   // (and then the ornament comes in again for it; until then it is not seen)
    meetPen.value = 0;
    const shown = Promise.all([showScene(s), loaded(sceneNear)]);
    layout();
    drawFinal();
    if (!still) return;
    // (and painted under it a couple of frames, the slow ones while the new picture first goes up)
    await shown.catch(() => {});
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (current() && swap.layer === still.layer) rackFocus(still.layer);
  }

  // Lays a still of the picture as it is seen now over it, for the next picture to be put in under it:
  // a copy of the picture, its breathing stopped where it is and its focus as it stands (a swap may be
  // under way), and over that what such a swap is melting away. Their animations end there. Returns
  // the layer and when it can be seen.
  function coverScene() {
    // (read before the animations end)
    const breath = getComputedStyle(scene.querySelector('.scene-breath')), going = swap.layer && getComputedStyle(swap.layer);
    const look = {
      breath: { animation: 'none', transform: breath.transform, transformOrigin: breath.transformOrigin },
      push: getComputedStyle(scenePush).filter, near: getComputedStyle(sceneNear).opacity,
      going: going && { filter: going.filter, opacity: going.opacity },
    };
    for (const a of swap.anims) a.cancel();
    swap.anims = [];
    const layer = document.createElement('div'), copy = scene.cloneNode(true);
    layer.className = 'scene-gone';
    layer.setAttribute('aria-hidden', 'true');
    // (with its own deep colour in its shadow, not the next picture's)
    const deep = stage.style.getPropertyValue('--tone');
    if (deep) layer.style.setProperty('--tone', deep);
    copy.removeAttribute('id');
    for (const el of copy.querySelectorAll('[id]')) el.removeAttribute('id');
    copy.querySelectorAll('.meet, .meet-planes').forEach(el => el.remove());   // (not seen with a section open)
    Object.assign(copy.querySelector('.scene-breath').style, look.breath);
    copy.querySelector('.scene-push').style.filter = look.push;
    const fill = copy.querySelector('.scene-fill canvas'), far = copy.querySelector('img.far'), near = copy.querySelector('img.near');
    far.alt = '';
    near.style.opacity = look.near;
    // (a copied canvas comes blank: the fill is painted into it again; the soft light, out in the
    // settings anyway, is not copied)
    [fill.width, fill.height] = [wash.width, wash.height];
    if (wash.width) fill.getContext('2d').drawImage(wash, 0, 0);
    copy.querySelector('.scene-light').remove();
    layer.append(copy);
    if (swap.layer) {
      Object.assign(swap.layer.style, look.going);
      layer.append(swap.layer);
    }
    scene.after(layer);
    swap.layer = layer;
    return { layer, ready: Promise.all([far, near].map(img => img.decode().catch(() => {}))) };
  }

  // The rack focus (SWAP) to the picture just put in under the still of the old one.
  function rackFocus(layer) {
    const S = SWAP, blur = px => `blur(${px}px)`;
    const run = (el, frames, [delay, duration], easing, fill) => el.animate(frames, { delay, duration, easing, fill });
    swap.anims = [
      run(layer, { filter: [blur(0), blur(S.blur)] }, S.defocus, 'ease-in', 'forwards'),
      run(layer, { opacity: [1, 0] }, S.melt, 'ease-in-out', 'forwards'),
      run(scenePush, { filter: [blur(S.blur), blur(0)] }, S.refocus, 'cubic-bezier(0.25, 0.6, 0.3, 1)', 'backwards'),
      run(sceneNear, { opacity: [0, 1] }, S.pull, 'ease-in-out', 'backwards'),
    ];
    // the still goes once it has melted away
    swap.anims[1].finished.then(() => {
      if (swap.layer !== layer) return;
      layer.remove();
      swap.layer = null;
    }, () => {});
    // the corners close in from where they are (a swap under way may have closed them in already)
    const length = S.lock + S.spring;
    const from = corners.map(c => getComputedStyle(c).translate);
    for (const a of swap.marks) a.cancel();
    swap.marks = corners.flatMap((c, i) => {
      const at = `${i % 2 ? -S.close : S.close}px ${i < 2 ? S.close : -S.close}px`;
      return [
        c.animate([
          { translate: from[i], easing: 'cubic-bezier(0.2, 0.8, 0.3, 1)' },
          { translate: at, offset: S.closing / length },
          { translate: at, offset: S.lock / length, easing: 'cubic-bezier(0.3, 1.7, 0.5, 1)' },
          { translate: '0px 0px' },
        ], length),
        c.animate([
          { borderColor: 'var(--accent)' },
          { borderColor: 'var(--accent)', offset: 0.25, easing: 'ease-out' },
          { borderColor: 'currentcolor' },
        ], { delay: S.lock, duration: S.flash }),
      ];
    });
  }

  // Ends a swap under way at once, as it ends (the picture is about to move, or the opening to play).
  function endSwap() {
    for (const a of [...swap.anims, ...swap.marks]) a.cancel();
    swap.anims = [];
    swap.marks = [];
    if (swap.layer) swap.layer.remove();
    swap.layer = null;
  }

  // The settings' keyboard map, drawn once: each key on the board's grid of quarter keys (the first
  // row stands a little apart), the page's own keys lit; and the same keys as a list read out.
  function makeKeyboard() {
    const lit = new Set(SHORTCUTS.map(([code]) => code));
    BOARD.forEach((row, r) => {
      let column = 1;
      for (const [legend, code, width = 1] of row) {
        const span = Math.round(4 * width);
        if (legend != null) {
          const key = document.createElement('i');
          key.className = lit.has(code) ? 'k on' : 'k';
          key.classList.toggle('small', width === 1 && legend.length > 3);   // set smaller on a small board
          key.dataset.code = code;
          key.textContent = legend;
          key.style.gridArea = `${r ? r + 2 : 1} / ${column} / span 1 / span ${span}`;
          keyEls.set(code, key);
          kb.append(key);
        }
        column += span;
      }
    });
    for (const [, name, does] of SHORTCUTS) {
      const item = document.createElement('li');
      item.textContent = `${name}: ${does || FOLD_SAYS.both}`;
      kbList.append(item);
    }
  }

  // The line under the map says what the key pointed at does; a key that is not lit says nothing (the
  // line fades out, keeping its words until the next lit key).
  function describeKey(key) {
    if (!key || !key.classList.contains('on')) {
      kbSay.classList.remove('on');
      delete kbSay.dataset.code;
      return;
    }
    const code = key.dataset.code, cap = document.createElement('kbd');
    cap.textContent = key.textContent;
    kbSay.replaceChildren(cap, SHORTCUTS.find(([c]) => c === code)[2] || (foldWanted() ? FOLD_SAYS.folded : FOLD_SAYS.aside));
    kbSay.dataset.code = code;
    kbSay.classList.add('on');
  }

  // A key pressed lights up on the map a moment (held down, it stays lit).
  function flashKey(code) {
    const key = keyEls.get(code);
    if (!key) return;
    key.classList.remove('hit');
    void key.offsetWidth;   // restart the light
    key.classList.add('hit');
  }

  // ---------- playback ----------

  // The picture chosen in the settings if there is one, else a random one (not the last one again,
  // so that a replay changes it): about half the time one of the time of day's own pictures, else one
  // that fits any time (not tagged with one); another time's pictures only when chosen. (Where there is
  // none of the one kind, the other; where there are neither, any.)
  function pickScene() {
    const scenes = state.manifest.scenes;
    if (!scenes.length) return null;
    let index = scenes.findIndex(s => s.far === prefs.scene);
    if (index < 0) {
      const all = scenes.map((_, i) => i), fresh = pool => pool.filter(i => i !== state.sceneIndex);
      const own = all.filter(i => scenes[i].time === state.time.period), free = all.filter(i => !scenes[i].time);
      const pools = (Math.random() < 0.5 ? [own, free] : [free, own]).map(fresh);
      const pool = [...pools, fresh(all), all].find(p => p.length);
      index = pool[Math.floor(Math.random() * pool.length)];
    }
    state.sceneIndex = index;
    return scenes[index];
  }

  // Resolves once the picture has loaded (and is decoded where the browser can say so); a failed
  // decode() alone does not count as a failed picture.
  function loaded(img) {
    return new Promise((resolve, reject) => {
      if (img.complete && img.naturalWidth) { resolve(); return; }
      img.addEventListener('load', () => resolve(), { once: true });
      img.addEventListener('error', () => reject(new Error(`cannot load ${img.src}`)), { once: true });
    }).then(() => img.decode().catch(() => {}));
  }

  // The picture's sharp layer: the one sized for a screen, or where this screen shows the picture with
  // more pixels than that one has (a 5K screen, a tablet held upright), the one at its full size (the
  // manifest has it, and the other's height, for a picture taller than that). The picture is at its
  // biggest whole on the screen.
  function sharpOf(s) {
    const [W, H] = state.size || [Math.max(1, innerWidth), Math.max(1, innerHeight)];
    const shown = s.h * Math.min(W / s.w, H / s.h) * (window.devicePixelRatio || 1);
    return s.full && shown > s.nearH ? s.full : s.near;
  }

  // Puts the picture up: resolves once it can be seen, with the fill round it (from its thumbnail;
  // one that cannot be had leaves the picture on the sky and fails nothing).
  function showScene(s) {
    state.scene = s;
    if (!s) return Promise.resolve();
    sceneFar.alt = s.artist ? `Adachi and Shimamura, art by ${s.artist}` : 'Adachi and Shimamura';
    sceneFar.src = `assets/${s.far}`;
    sceneNear.src = `assets/${sharpOf(s)}`;
    // decoded as soon as it is in, not the moment the focus is pulled onto it (a big picture would
    // hold that frame up)
    sceneNear.decode().catch(() => {});
    const thumb = new Image();
    thumb.src = `assets/${s.thumb || s.far}`;
    wash.width = 0;   // (no fill until it is painted)
    state.washFrom = null;
    state.washes++;
    stage.style.removeProperty('--tone');   // (nor the picture's own deep colour)
    dropLight();   // (it was kept off the old picture)
    const fill = loaded(thumb).then(() => {
      if (state.scene !== s) return;
      paintWash(wash, thumb);
      keepFill(thumb);
      state.washFrom = thumb;
      state.washes++;   // (the ornament takes its colours from it, on the next frame drawn)
      const deep = deepOf(thumb);
      if (deep) stage.style.setProperty('--tone', deep);
      if (state.layout && !state.running) drawFinal();
    }, () => {});
    const shown = Promise.all([loaded(sceneFar), fill]);
    // (an ornament the opening screen came up without comes in now)
    shown.then(() => { if (state.scene === s) meetAgain(); }, () => {});
    return shown;
  }

  // The fill's mean colour, kept for the visit (FILL_KEY): a refresh shows it while it waits to be shown
  // whole (index.html), rather than the bare paper. (Worked out on a fill painted again on a canvas kept
  // for reading, as inkMeet does: reading the fill's own back would wait on the GPU.)
  function keepFill(img) {
    const copy = document.createElement('canvas'), g = copy.getContext('2d', { willReadFrequently: true });
    paintWash(copy, img);
    let px;
    try { px = g.getImageData(0, 0, copy.width, copy.height).data; } catch { return; }
    const sum = [0, 0, 0];
    for (let i = 0; i < px.length; i += 4) for (let c = 0; c < 3; c++) sum[c] += px[i + c];
    try {
      sessionStorage.setItem(FILL_KEY, `rgb(${sum.map(v => Math.round(4 * v / px.length)).join(' ')})`);
    } catch { /* no storage: the paper */ }
  }

  // Whether the picture is in and the fill round it painted.
  function sceneIn() {
    return Boolean(state.washFrom) && sceneFar.complete && sceneFar.naturalWidth > 0;
  }

  // The picture's own deep colour (DEEP) as 'r g b', or null where the picture cannot be read back
  // (a page opened from a local file), which keeps the stylesheet's neutral one.
  function deepOf(img) {
    const canvas = document.createElement('canvas'), w = 16, h = 8;
    canvas.width = w;
    canvas.height = h;
    const g = canvas.getContext('2d', { willReadFrequently: true });
    g.imageSmoothingQuality = 'high';
    const top = img.naturalHeight * (1 - DEEP.part);
    g.drawImage(img, 0, top, img.naturalWidth, img.naturalHeight - top, 0, 0, w, h);
    let px;
    try { px = g.getImageData(0, 0, w, h).data; } catch { return null; }
    let [r, gr, b] = [0, 1, 2].map(c => { let sum = 0; for (let i = c; i < px.length; i += 4) sum += px[i]; return sum / (w * h) / 255; });
    // to hue (in sixths), saturation and lightness, and back with the saturation and lightness set
    const max = Math.max(r, gr, b), min = Math.min(r, gr, b), d = max - min, l0 = (max + min) / 2;
    const hue = d === 0 ? 0 : max === r ? ((gr - b) / d + 6) % 6 : max === gr ? (b - r) / d + 2 : (r - gr) / d + 4;
    const sat = d === 0 ? 0 : d / (1 - Math.abs(2 * l0 - 1));
    const s = Math.min(DEEP.saturation, DEEP.saturate * sat), l = DEEP.lightness;
    const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(hue % 2 - 1)), m = l - c / 2;
    [r, gr, b] = [[c, x, 0], [x, c, 0], [0, c, x], [0, x, c], [x, 0, c], [c, 0, x]][Math.floor(hue) % 6];
    return [r, gr, b].map(v => Math.round(255 * (v + m))).join(' ');
  }

  // Paints the fill (WASH) from the picture's thumbnail, once a picture: small, so that stretched
  // over the ground it is a smooth wash that costs nothing to move or resize. (Where the canvas
  // cannot blur, as in Safari, the same blur is worked out on its pixels, blurWash; where they cannot
  // be read back either, as on a page opened from disk, painting it smaller still and then up to size
  // blurs it about as much, without the richer colours.)
  function paintWash(canvas, img) {
    const w = WASH.size, h = Math.max(1, Math.round(w * img.naturalHeight / img.naturalWidth));
    canvas.width = w;
    canvas.height = h;
    const g = canvas.getContext('2d');
    g.drawImage(img, 0, 0, w, h);   // (under the blurred one, whose edges thin out)
    const worked = 'filter' in g ? null : blurWash(img, w, h);
    if ('filter' in g) {
      g.filter = `blur(${WASH.blur}px) saturate(${WASH.saturate})`;
      g.drawImage(img, 0, 0, w, h);
      g.filter = 'none';
    } else if (worked) {
      g.drawImage(worked, 0, 0);
    } else {
      const tiny = document.createElement('canvas'), k = 1 / (2 * WASH.blur);
      tiny.width = Math.max(1, Math.round(w * k));
      tiny.height = Math.max(1, Math.round(h * k));
      tiny.getContext('2d').drawImage(img, 0, 0, tiny.width, tiny.height);
      g.imageSmoothingQuality = 'high';
      g.drawImage(tiny, 0, 0, w, h);
    }
    const grey = Math.round(255 * WASH.dim);
    g.globalCompositeOperation = 'multiply';
    g.fillStyle = `rgb(${grey}, ${grey}, ${grey})`;
    g.fillRect(0, 0, w, h);
  }

  // The thumbnail as the canvas's filter would leave it (WASH), for a canvas without one, worked out on a
  // copy kept for reading: a Gaussian blur of the filter's width, beyond whose edges all is clear (so
  // the picture under it shows through there, as it does with the filter), its colours made richer by
  // the filter's own matrix. Null where the pixels cannot be read back.
  function blurWash(img, w, h) {
    const canvas = document.createElement('canvas');
    [canvas.width, canvas.height] = [w, h];
    const g = canvas.getContext('2d', { willReadFrequently: true });
    g.drawImage(img, 0, 0, w, h);
    let image;
    try { image = g.getImageData(0, 0, w, h); } catch { return null; }
    const px = image.data, s = WASH.blur, r = Math.ceil(3 * s);
    const kernel = Array.from({ length: 2 * r + 1 }, (_, i) => Math.exp(-((i - r) ** 2) / (2 * s * s)));
    const total = kernel.reduce((a, b) => a + b);
    // premultiplied, across and then down
    let from = new Float32Array(4 * w * h), to = new Float32Array(4 * w * h);
    for (let q = 0; q < w * h; q++) {
      const alpha = px[4 * q + 3] / 255;
      for (let c = 0; c < 3; c++) from[4 * q + c] = px[4 * q + c] * alpha;
      from[4 * q + 3] = alpha;
    }
    for (const [dx, dy] of [[1, 0], [0, 1]]) {
      to.fill(0);
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
          for (let k = -r; k <= r; k++) {
            const sx = x + k * dx, sy = y + k * dy;
            if (sx < 0 || sy < 0 || sx >= w || sy >= h) continue;
            const f = kernel[k + r] / total, i = 4 * (sy * w + sx), o = 4 * (y * w + x);
            for (let c = 0; c < 4; c++) to[o + c] += from[i + c] * f;
          }
        }
      }
      [from, to] = [to, from];
    }
    const t = WASH.saturate, matrix = [
      [0.213 + 0.787 * t, 0.715 - 0.715 * t, 0.072 - 0.072 * t],
      [0.213 - 0.213 * t, 0.715 + 0.285 * t, 0.072 - 0.072 * t],
      [0.213 - 0.213 * t, 0.715 - 0.715 * t, 0.072 + 0.928 * t],
    ];
    for (let q = 0; q < w * h; q++) {
      const alpha = from[4 * q + 3];
      if (alpha <= 0) continue;
      const rgb = [0, 1, 2].map(c => from[4 * q + c] / alpha);
      for (let c = 0; c < 3; c++) {
        const v = Math.min(255, Math.max(0, matrix[c][0] * rgb[0] + matrix[c][1] * rgb[1] + matrix[c][2] * rgb[2]));
        px[4 * q + c] = Math.round(v * alpha + px[4 * q + c] * (1 - alpha));
      }
    }
    g.putImageData(image, 0, 0);
    return canvas;
  }

  // ---------- the fill's soft light ----------

  // The soft light (SOFT_LIGHT, softLight) on the opening screen's fill: a light that follows the
  // pointer (on a touch screen, a finger while it is down), and, while the pointer is still or off the
  // fill, now and then a weaker one making a pass of its own somewhere on it, as if an unseen pointer
  // went by. Under them the fill's grid lights up and stays lit a moment where they have been, the
  // crossings nearest them shine, and fine dust drifts in their light, carried along as they go by. It
  // is drawn on a canvas in the fill, under the picture, and keeps off the picture: the pointer over it
  // counts as away, and the passes go round it. Not while the opening plays or a section is open,
  // with reduced motion or in a background tab; frames are drawn only while something is lit (at
  // rest, every other one).

  // whether the light may shine: the opening screen, settled, in sight
  function lightWanted() {
    return !reduceMotion && !document.hidden && !state.running && state.debugT == null && Boolean(state.scene)
      && Boolean(state.layout) && dock.tab === 'home' && dock.value === 0;
  }

  // Sizes the canvas to the screen, and what the light is worked out and drawn with to the grid on it,
  // when the light is first wanted after a layout.
  function sizeLight() {
    const L = softLight, { W, H, cell: C } = state.layout, dpr = Math.min(2, devicePixelRatio || 1);
    const size = `${W} ${H} ${C} ${dpr}`;
    if (L.size === size) return;
    L.size = size;
    Object.assign(L, { W, H, C, cols: Math.floor(W / C) + 2, rows: Math.floor(H / C) + 2 });
    lightCanvas.width = Math.round(W * dpr);
    lightCanvas.height = Math.round(H * dpr);
    lightCanvas.style.width = `${W}px`;
    lightCanvas.style.height = `${H}px`;
    L.g = lightCanvas.getContext('2d');
    L.g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = L.cols * L.rows;
    L.lines = new Float32Array(n);
    L.glow = new Float32Array(n);
    L.shone = new Uint32Array(n);
    L.map = document.createElement('canvas');
    [L.map.width, L.map.height] = [L.cols, L.rows];
    L.mapG = L.map.getContext('2d');
    L.pixels = L.mapG.createImageData(L.cols, L.rows);
    L.pixels.data.fill(255);   // white; the light goes in the alpha
    // a soft white dot r px in radius: the shine on a crossing, and the glow round a bigger mote
    const dot = r => {
      const c = document.createElement('canvas'), side = Math.ceil(2 * r * dpr);
      [c.width, c.height] = [side, side];
      const g = c.getContext('2d'), grad = g.createRadialGradient(side / 2, side / 2, 0, side / 2, side / 2, side / 2);
      grad.addColorStop(0, '#fff');
      grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
      g.fillStyle = grad;
      g.fillRect(0, 0, side, side);
      return c;
    };
    L.pin = dot(4);
    L.speck = dot(8);
    L.motes = Array.from({ length: Math.round(W * H / SOFT_LIGHT.dust.area) }, () => ({
      x: W * Math.random(), y: H * Math.random(), vx: 0, vy: 0,
      s: Math.random() < 0.3 ? 1.7 + 0.9 * Math.random() : 1 + 0.5 * Math.random(),   // its size
      ph: 2 * Math.PI * Math.random(), f: 1 + 2 * Math.random(),   // how it twinkles
    }));
  }

  // whether a point of the fill (px) is on the picture at its biggest, or within margin px of it
  function onPicture(x, y, margin = 0) {
    const L = softLight;
    L.keepOff ??= frameFor(state.layout.screen, state.scene).fit;
    const r = L.keepOff;
    return x > r.x - margin && x < r.x + r.w + margin && y > r.y - margin && y < r.y + r.h + margin;
  }

  // Starts drawing the light if it may shine and is not drawn already (the pointer has moved, or a pass
  // is due).
  function wakeLight() {
    const L = softLight;
    L.nudged = true;
    if (L.raf || !lightWanted()) return;
    if (L.fading) {
      L.fading.cancel();
      L.fading = null;
    }
    L.last = performance.now();
    L.raf = requestAnimationFrame(lightFrame);
  }

  function lightFrame(now) {
    const L = softLight;
    L.raf = 0;
    if (!lightWanted()) { dropLight(); return; }
    sizeLight();
    // at rest (only the pointer's light up, under a pointer that does not move) every other frame does
    if (L.resting && !L.nudged && now - L.drawn < 30) {
      L.raf = requestAnimationFrame(lightFrame);
      return;
    }
    L.nudged = false;
    const dt = Math.min(0.05, Math.max(0.001, (now - L.last) / 1000));
    L.last = L.drawn = now;
    stepLight(dt);
    if (drawLight() || L.path) L.raf = requestAnimationFrame(lightFrame);
  }

  // The light a frame (dt s) on: the pointer's light and the pass's move, the trail fades, the dust
  // drifts.
  function stepLight(dt) {
    const L = softLight, S = SOFT_LIGHT, D = S.dust;
    L.t += dt;
    // the pointer's light goes after the pointer (in the fill's px), unless it is over the picture: round
    // the two of them beside a drawn pointer
    let aim = null;
    if (L.pointer) {
      const r = sceneFill.getBoundingClientRect(), x = L.pointer.x - r.left, y = L.pointer.y - r.top;
      const [fx, fy] = drawnPointer.figure() || [0, 0];
      if (x >= 0 && y >= 0 && x <= L.W && y <= L.H && !onPicture(x, y)) aim = [x + fx, y + fy];
    }
    const moved = moveLight(L.hand, aim, dt, 1);
    if (moved) L.still = performance.now();
    let way = null;
    if (L.path) {
      L.path.t += 1000 * dt;
      if (L.path.t < S.pass.length) way = onPath(L.path, L.path.t / S.pass.length);
      else L.path = null;
    }
    moveLight(L.roam, way, dt, S.pass.strength);
    const fade = Math.exp(-dt / S.trail.fade);
    let kept = 0;
    for (const patch of L.trail) {
      patch.a *= fade;
      if (patch.a >= 0.02) L.trail[kept++] = patch;
    }
    L.trail.length = kept;
    L.resting = L.hand.amp >= 1 && !moved && !L.path && L.roam.amp === 0 && kept === 0;
    // the dust wanders, rising a little and settling; a light going by carries it along
    const calm = Math.exp(-D.calm * dt), kick = D.drift * Math.sqrt(dt);
    const lit = [L.hand, L.roam].filter(o => o.amp > 0);
    for (const m of L.motes) {
      m.vx += (Math.random() - 0.5) * kick;
      m.vy += (Math.random() - 0.5) * kick - D.rise * dt;
      for (const o of lit) {
        const d = Math.hypot(m.x - o.x, m.y - o.y);
        if (d < S.reach) {
          const k = (1 - d / S.reach) * D.stir * dt * o.amp;
          m.vx += o.vx * k;
          m.vy += o.vy * k;
        }
      }
      m.vx *= calm;
      m.vy *= calm;
      m.x = (m.x + m.vx * dt + L.W) % L.W;
      m.y = (m.y + m.vy * dt + L.H) % L.H;
    }
  }

  // Moves a light a frame (dt s) on after aim (fill px), as bright as str; with no aim it dies away
  // where it is. It leaves the trail behind it. Returns whether it moved (by half a px or more).
  function moveLight(o, aim, dt, str) {
    const S = SOFT_LIGHT;
    if (!aim) {
      o.amp = Math.max(0, o.amp - S.fall * dt);
      const calm = Math.exp(-2 * dt);
      o.vx *= calm;
      o.vy *= calm;
      return false;
    }
    if (o.amp < 0.02) [o.x, o.y] = aim;   // (it comes up where it is wanted, not on its way there)
    const k = 1 - Math.exp(-S.follow * dt), x = lerp(o.x, aim[0], k), y = lerp(o.y, aim[1], k);
    const step = Math.hypot(x - o.x, y - o.y);
    [o.vx, o.vy, o.x, o.y] = [(x - o.x) / dt, (y - o.y) / dt, x, y];
    o.amp = Math.min(1, o.amp + S.rise * dt);
    o.str = str;
    o.run += step;
    if (o.run > S.trail.every) {
      o.run = 0;
      softLight.trail.push({ x, y, r: S.trail.size * S.reach, a: S.trail.strength * str });
    }
    return step >= 0.5;
  }

  // Draws the light as it is now; returns whether anything is lit.
  function drawLight() {
    const L = softLight, S = SOFT_LIGHT, R = S.reach, { g, C, cols, rows, lines, glow } = L;
    const lights = [L.hand, L.roam].filter(o => o.amp > 0);
    // The light at the grid's crossings, from the lights and the trail: in lines as the canvas would
    // add up their radial gradients (falling straight off to nothing at their edge), in glow falling
    // off softly. box is what is drawn round them, out to the halos and the dust's glow.
    lines.fill(0);
    glow.fill(0);
    let box = null;
    const add = (x, y, r, a, round) => {
      const far = 1.3 * r, r2 = r * r, far2 = far * far, spread = 0.45 * r2;
      const i0 = Math.max(0, Math.ceil((x - far) / C)), i1 = Math.min(cols - 1, Math.floor((x + far) / C));
      const j0 = Math.max(0, Math.ceil((y - far) / C)), j1 = Math.min(rows - 1, Math.floor((y + far) / C));
      for (let j = j0; j <= j1; j++) {
        const dy = j * C - y;
        for (let i = i0; i <= i1; i++) {
          const dx = i * C - x, d2 = dx * dx + dy * dy;
          if (d2 >= far2) continue;
          const k = j * cols + i;
          glow[k] += a * Math.exp(-d2 / spread);
          if (d2 < r2) lines[k] += a * (1 - Math.sqrt(d2) / r);
        }
      }
      const e = Math.max(far, round) + 10;
      box = box ? { x0: Math.min(box.x0, x - e), y0: Math.min(box.y0, y - e), x1: Math.max(box.x1, x + e), y1: Math.max(box.y1, y + e) }
        : { x0: x - e, y0: y - e, x1: x + e, y1: y + e };
    };
    for (const o of lights) add(o.x, o.y, R, o.amp * o.str, 1.6 * R);
    for (const patch of L.trail) add(patch.x, patch.y, patch.r, patch.a, 0);
    if (box) {
      box = { x0: Math.max(0, Math.floor(box.x0)), y0: Math.max(0, Math.floor(box.y0)), x1: Math.min(L.W, Math.ceil(box.x1)), y1: Math.min(L.H, Math.ceil(box.y1)) };
      if (box.x0 >= box.x1 || box.y0 >= box.y1) box = null;
    }
    // what was drawn last frame goes
    for (const b of [L.box, box]) if (b) g.clearRect(b.x0 - 1, b.y0 - 1, b.x1 - b.x0 + 2, b.y1 - b.y0 + 2);
    L.box = box;
    if (!box) return false;
    const { x0, y0, x1, y1 } = box;
    g.save();
    g.beginPath();
    g.rect(x0, y0, x1 - x0, y1 - y0);
    g.clip();
    // the lit grid: the light at the crossings stretched over the grid (so it runs smoothly along the
    // lines between them), kept only on its lines
    const px = L.pixels.data;
    for (let k = 0; k < lines.length; k++) px[4 * k + 3] = 255 * lines[k];
    L.mapG.putImageData(L.pixels, 0, 0);
    g.drawImage(L.map, -C / 2, -C / 2, cols * C, rows * C);
    g.globalCompositeOperation = 'destination-in';
    g.fillStyle = `rgba(255, 255, 255, ${S.grid})`;
    g.beginPath();
    for (let x = Math.ceil(x0 / C) * C; x < x1; x += C) g.rect(x, y0, 1, y1 - y0);
    for (let y = Math.ceil(y0 / C) * C; y < y1; y += C) g.rect(x0, y, x1 - x0, 1);
    g.fill();
    // the lights themselves, behind the lit lines: a warm core in a cool halo, breathing a little
    g.globalCompositeOperation = 'destination-over';
    const breath = 1 + S.breath[0] * Math.sin(S.breath[1] * L.t);
    const blot = (o, r, [red, green, blue, alpha], stops) => {
      const grad = g.createRadialGradient(o.x, o.y, 0, o.x, o.y, r);
      for (const [at, share] of stops) grad.addColorStop(at, `rgba(${red}, ${green}, ${blue}, ${(alpha * share * o.amp * o.str).toFixed(3)})`);
      g.fillStyle = grad;
      g.fillRect(o.x - r, o.y - r, 2 * r, 2 * r);
    };
    for (const o of lights) {
      blot(o, 0.65 * R * breath, S.core, [[0, 1], [0.5, 0.32], [1, 0]]);
      blot(o, 1.5 * R * breath, S.halo, [[0, 1], [1, 0]]);
    }
    // the crossings nearest a light shine, like pins in the paper
    g.globalCompositeOperation = 'source-over';
    L.frame++;
    for (const o of lights) {
      const i0 = Math.max(0, Math.ceil((o.x - R) / C)), i1 = Math.min(cols - 1, Math.floor((o.x + R) / C));
      const j0 = Math.max(0, Math.ceil((o.y - R) / C)), j1 = Math.min(rows - 1, Math.floor((o.y + R) / C));
      for (let j = j0; j <= j1; j++) {
        for (let i = i0; i <= i1; i++) {
          const k = j * cols + i, over = Math.min(1.2, glow[k]) - S.pin;
          if (L.shone[k] === L.frame || over <= 0) continue;
          L.shone[k] = L.frame;
          g.globalAlpha = 0.85 * Math.min(1, 1.8 * over);
          g.drawImage(L.pin, i * C - 3.5, j * C - 3.5, 8, 8);
        }
      }
    }
    // the dust shows only in the light, twinkling as it turns
    const glowAt = (x, y) => {
      const fx = x / C, fy = y / C, i = Math.min(cols - 2, Math.floor(fx)), j = Math.min(rows - 2, Math.floor(fy));
      const u = fx - i, k = j * cols + i;
      return lerp(lerp(glow[k], glow[k + 1], u), lerp(glow[k + cols], glow[k + cols + 1], u), fy - j);
    };
    g.fillStyle = '#fff';
    for (const m of L.motes) {
      if (m.x < x0 || m.x > x1 || m.y < y0 || m.y > y1) continue;
      const l = Math.min(1.2, glowAt(m.x, m.y));
      if (l < 0.03) continue;
      const a = Math.min(1, 1.3 * l * (0.55 + 0.45 * Math.sin(2 * m.f * L.t + m.ph)));
      if (m.s > 1.6) {
        const h = 3.2 * m.s;
        g.globalAlpha = 0.6 * a;
        g.drawImage(L.speck, m.x - h, m.y - h, 2 * h, 2 * h);
      }
      g.globalAlpha = a;
      g.beginPath();
      g.arc(m.x, m.y, 0.7 * m.s, 0, 2 * Math.PI);
      g.fill();
    }
    g.restore();
    return true;
  }

  // A pass's way (a gentle curve, SOFT_LIGHT.pass) all on the fill: clear of the screen's edges, off the
  // picture (well off it if it can be) and well away from the pointer's light if that is up. Null if
  // none is found.
  function passPath() {
    sizeLight();
    const L = softLight, P = SOFT_LIGHT.pass, R = SOFT_LIGHT.reach;
    for (let tries = 0; tries < 60; tries++) {
      const loose = tries >= 30, len = lerp(P.path[0], P.path[1], Math.random()) * (loose ? 0.5 : 1);
      const turn = 2 * Math.PI * Math.random(), bend = (Math.random() - 0.5) * 0.5 * len;
      const x0 = L.W * Math.random(), y0 = L.H * Math.random();
      const x1 = x0 + len * Math.cos(turn), y1 = y0 + len * Math.sin(turn);
      const path = { x0, y0, x1, y1, cx: (x0 + x1) / 2 - bend * Math.sin(turn), cy: (y0 + y1) / 2 + bend * Math.cos(turn), t: 0 };
      let fits = true;
      for (let k = 0; k <= 12 && fits; k++) {
        const [x, y] = onPath(path, k / 12);
        fits = x > 12 && x < L.W - 12 && y > 12 && y < L.H - 12 && !onPicture(x, y, loose ? 12 : 40)
          && !(L.hand.amp > 0 && Math.hypot(x - L.hand.x, y - L.hand.y) < 2 * R);
      }
      if (fits) return path;
    }
    return null;
  }

  // the point of a pass's curve (a quadratic Bézier) at share s of its time, easing in and out
  function onPath(p, s) {
    const e = s * s * (3 - 2 * s), u = 1 - e;
    return [u * u * p.x0 + 2 * u * e * p.cx + e * e * p.x1, u * u * p.y0 + 2 * u * e * p.cy + e * e * p.y1];
  }

  // The wait for the next pass (SOFT_LIGHT.pass); not off the opening screen, with reduced motion or in
  // a background tab.
  function waitForPass(delay = lerp(SOFT_LIGHT.pass.every[0], SOFT_LIGHT.pass.every[1], Math.random())) {
    clearTimeout(softLight.timer);
    const wanted = !reduceMotion && dock.tab === 'home' && !document.hidden;
    softLight.timer = wanted ? setTimeout(passDue, delay) : 0;
  }

  // A pass, once the pointer has been still (or off the fill) as long as the shortest wait, if it is
  // still the opening screen, settled, and a way is found; either way the next wait begins.
  function passDue() {
    const L = softLight, P = SOFT_LIGHT.pass, quiet = performance.now() - L.still;
    if (quiet < P.every[0]) { waitForPass(P.every[0] - quiet + 200); return; }
    if (lightWanted() && !L.path) {
      L.path = passPath();
      if (L.path) wakeLight();
    }
    waitForPass(P.length + lerp(P.every[0], P.every[1], Math.random()));
  }

  // Puts the light out: at once (a new layout or picture) or fading quickly (the opening screen is
  // left), and with stop the next pass too.
  function dropLight(fade, stop) {
    const L = softLight;
    cancelAnimationFrame(L.raf);
    L.raf = 0;
    if (stop) {
      clearTimeout(L.timer);
      L.timer = 0;
    }
    if (fade && L.fading) return;   // (going out already)
    if (L.fading) {
      L.fading.cancel();
      L.fading = null;
    }
    const out = () => {
      if (L.box) L.g.clearRect(L.box.x0 - 1, L.box.y0 - 1, L.box.x1 - L.box.x0 + 2, L.box.y1 - L.box.y0 + 2);
      L.box = L.path = L.keepOff = null;
      L.trail.length = 0;
      L.hand.amp = L.roam.amp = 0;
      L.resting = false;
    };
    if (!fade || !L.box) { out(); return; }
    const fading = lightCanvas.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, fill: 'forwards' });
    L.fading = fading;
    fading.finished.then(() => {
      out();
      fading.cancel();
      L.fading = null;
    }, () => {});
  }

  function enterIdle() {
    state.running = false;
    cancelAnimationFrame(state.raf);
    tick();   // (the paper, held while the opening played)
    // come up before the picture was in (shown at once, late or skipped early), the ornament waits for
    // it and the fill round it, and then comes in (showScene)
    if (!sceneIn() && !meetPen.stale) {
      meetPen.stale = true;
      meetPen.value = 0;
    }
    render(END);
    stage.classList.remove('playing');
    stage.classList.add('idle');
    waitForPass();
    if (softLight.pointer) wakeLight();   // (under a pointer already on the fill)
  }

  function stopAll() {
    state.running = false;
    cancelAnimationFrame(state.raf);
    settle();
    endDrag();
    endSwap();
    dropLight(false, true);
    clearTimeout(gridPen.timer);
    gridPen.stale = false;
    cancelAnimationFrame(meet.raf);
    meet.raf = 0;
    meetSvg.classList.remove('gliding');
    clearTimeout(meetPen.timer);
    meetPen.stale = false;
    meetPen.value = 1;
    stage.classList.remove('idle');
  }

  function play() {
    stopAll();
    const token = ++state.playToken;
    tick();   // (the sky and the picture by the time of day now)
    const ready = showScene(pickScene());
    layout();
    if (reduceMotion || !state.scene) { enterIdle(); return; }
    stage.classList.add('playing');
    state.running = true;
    render(0);
    // Wait for the picture before the birds fly; after two seconds show the final screen instead,
    // where the picture simply appears once it arrives.
    const timeout = new Promise(resolve => setTimeout(resolve, 2000, 'late'));
    Promise.race([ready.then(() => 'ready', () => 'late'), timeout]).then(result => {
      if (token !== state.playToken || !state.running) return;
      if (result === 'late') { enterIdle(); return; }
      state.start = 0;   // the clock starts on the first painted frame (background tabs wait)
      const loop = now => {
        if (!state.running) return;
        if (!state.start) state.start = now;
        const t = now - state.start;
        if (t >= END) { enterIdle(); return; }
        render(t);
        state.raf = requestAnimationFrame(loop);
      };
      state.raf = requestAnimationFrame(loop);
    });
  }

  function skip() {
    if (state.running) enterIdle();
  }

  // The final screen without the opening: it has been seen in this visit, or a section was asked
  // for. The picture paints in place whenever it arrives.
  function showFinal() {
    stopAll();
    state.playToken++;
    tick();
    const shown = showScene(pickScene());
    shown.catch(() => {});
    layout();
    enterIdle();
    arrive(shown);
  }

  // A visit opening straight on the final screen has come up hidden (index.html: arriving): it is shown
  // at once when it can be seen whole, the picture in with its sharp layer decoded, the fill round it
  // painted and the lettering in its own fonts, not in the states it goes through on the way (the white
  // paper, the window still empty, the picture on bare paper).
  function arrive(shown) {
    const root = document.documentElement, done = () => root.classList.remove('arriving');
    if (!root.classList.contains('arriving')) return;
    Promise.all([shown, sceneNear.decode(), document.fonts?.ready]).then(done, done);
  }

  // ?debug exposes seek hooks so each beat of the opening can be inspected frame by frame;
  // ?debug&scene=1&t=3200 opens straight on that frame, and &size=375x812 pins the stage to a
  // screen size (headless screenshots cannot always match the viewport to the window); &time=night
  // sets the time of day as the settings do (not kept), &at=2026-10-21T17:30 works it out for then.
  const params = new URLSearchParams(location.search);
  if (params.has('debug')) {
    const pinned = (params.get('size') || '').match(/^(\d+)x(\d+)$/);
    if (pinned) {
      state.size = [Number(pinned[1]), Number(pinned[2])];
      stage.style.width = `${state.size[0]}px`;
      stage.style.height = `${state.size[1]}px`;
    }
    window.homeDebug = {
      state, BEAT,
      seek(t) {
        state.debugT = t;   // a resize while inspecting re-renders this frame instead of skipping
        stopAll();
        stage.classList.add('playing');
        render(t);
      },
      async scene(index) {
        stopAll();
        state.sceneIndex = index;
        const ready = showScene(state.manifest.scenes[index]);
        layout();
        render(state.debugT ?? END);
        await ready.catch(() => {});
      },
      go: tab => go(tab, true),   // a section at once, without the docking move
      // the picture folded away or brought back, and the split, at once (not kept for the visit)
      setFold: on => { prefs.folded = Boolean(on); moveTo(fold, foldWanted() ? 1 : 0, 0); },
      setSplit: share => { prefs.split = share; moveTo(split, share, 0); },
      // a pass of the fill's soft light now (if it may shine and a way is found)
      pass() {
        softLight.path = lightWanted() ? passPath() : null;
        if (softLight.path) wakeLight();
        return Boolean(softLight.path);
      },
      // the time of day worked out for a moment (a date or a string such as '2026-10-21T17:30'; null:
      // now) and as chosen ('auto', 'day', 'dusk' or 'night'; not kept), and the frame drawn again for it
      time(at, mode) {
        state.at = at == null ? null : new Date(at);
        if (mode) prefs.time = mode;
        tick();
        layout();
        render(state.debugT ?? END);
        return state.time;
      },
      // the ornament's birds held where they are after lap s of gliding (null: gliding on)
      birds(lap) {
        meet.held = lap != null;
        if (meet.held) meet.lap = lap;
        if (meet.G) drawBirds(meet.G, meetPen.value);
        flyBirds();
      },
      // the disc as it is after s of turning (at full speed): held there with the birds, or turning on
      spin(s) {
        meet.spin = s;
        meet.up = 1;
        if (meet.G && meetPen.value === 1) drawDisc(meet.G, 1);
      },
      dock, fold, split, prefs, softLight, meet, meetPen,
    };
  }

  makeKeyboard();
  recallPrefs();
  if (window.homeDebug) {
    if (clock.MODES.includes(params.get('time'))) prefs.time = params.get('time');
    if (params.has('at')) state.at = new Date(params.get('at'));
  }
  tick();
  setInterval(() => { if (!document.hidden) tick(); }, TICK);
  state.birds = FLOCK.map((_, i) => makeBird(i));
  ['pointerdown', 'wheel', 'touchstart'].forEach(type => addEventListener(type, skip, { passive: true }));
  // The pointer, for the fill's soft light: followed wherever it is over the page (the light keeps to
  // the fill), a finger only while it is down.
  const pointAt = event => {
    softLight.pointer = { x: event.clientX, y: event.clientY };
    wakeLight();
  };
  const pointAway = () => {
    softLight.pointer = null;
    wakeLight();
  };
  addEventListener('pointermove', pointAt, { passive: true });
  addEventListener('pointerdown', pointAt, { passive: true });
  addEventListener('pointerup', event => { if (event.pointerType === 'touch') pointAway(); }, { passive: true });
  addEventListener('pointercancel', pointAway, { passive: true });
  addEventListener('pointerout', event => { if (!event.relatedTarget) pointAway(); }, { passive: true });
  replayButton.addEventListener('click', event => {
    event.stopPropagation();
    replay();
  });
  indexNav.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    // the current section's square leads back to the opening screen
    navigate(link.dataset.tab === dock.tab ? 'home' : link.dataset.tab);
  });
  addEventListener('popstate', () => go(tabFromHash()));
  addEventListener('hashchange', () => go(tabFromHash()));

  // The settings: a ruler moved (a double-click puts it back to the usual; while it is dragged the
  // whole page shows the closed hand), a picture or a time of day chosen, a key on the map pointed at
  // (the gaps between keys keep what was said; tapped, a key stays said), a key pressed while they are
  // shown.
  const LET_GO = ['pointerup', 'pointercancel', 'blur'];
  const letGo = () => {
    stage.classList.remove('grabbing');
    LET_GO.forEach(type => removeEventListener(type, letGo));
  };
  for (const [name, slider] of Object.entries(sliders)) {
    slider.addEventListener('input', () => setLook(name, Number(slider.value)));
    slider.addEventListener('dblclick', () => setLook(name, LOOKS[name]));
    slider.addEventListener('pointerdown', event => {
      if (event.button !== 0 || event.pointerType === 'touch') return;
      stage.classList.add('grabbing');
      LET_GO.forEach(type => addEventListener(type, letGo));
    });
  }
  picks.addEventListener('click', event => {
    const pick = event.target.closest('.pick');
    if (pick) choosePicture(pick);
  });
  times.addEventListener('click', event => {
    const tile = event.target.closest('.time');
    if (tile) setTime(tile.dataset.time);
  });

  // The e-mail address in CONTACT is put together here rather than written out in the page (for the
  // harvesters that read pages without running them). A click copies it, and the entry says so for a
  // moment (COPIED by its label, and read out); where the clipboard cannot be had, the click opens a
  // mail app with it instead.
  const address = `${mail.dataset.user}@${mail.dataset.host}`;
  mail.querySelector('.reach-id').textContent = address;
  mail.setAttribute('aria-label', `Copy the e-mail address ${address}`);
  let mailTimer = 0;
  const writeMail = () => { location.href = `mailto:${address}`; };
  mail.addEventListener('click', () => {
    if (!navigator.clipboard || !window.isSecureContext) {
      writeMail();
      return;
    }
    navigator.clipboard.writeText(address).then(() => {
      mail.classList.add('copied');
      mailSaid.textContent = 'Copied';
      clearTimeout(mailTimer);
      mailTimer = setTimeout(() => {
        mail.classList.remove('copied');
        mailSaid.textContent = '';
      }, 1600);
    }, writeMail);
  });
  kb.addEventListener('pointerover', event => {
    const key = event.target.closest('.k');
    if (key) describeKey(key);
  });
  kb.addEventListener('pointerleave', event => { if (event.pointerType !== 'touch') describeKey(null); });
  addEventListener('keydown', event => { if (dock.tab === 'settings') flashKey(event.code); });

  // The keyboard. Single keys only: with Ctrl, Alt or Cmd held they stay the browser's. 0-4 open
  // 00-04 (the current one's key does nothing), the left and right arrows step round the index, B
  // folds the picture away or brings it back, R replays the opening and Esc returns to the opening
  // screen; the up and down arrows, Space and the page keys scroll the section (the settings spread
  // across the middle of the screen: their pictures). Letters and digits
  // are read off the key where it is one, else off where it sits (other keyboard layouts). While the
  // opening plays any key only skips it (Shift and the like on their own do not, so the key pressed
  // with them is the one that skips). In a field the page's keys are off, except on a ruler in the
  // settings, which keeps only the keys that move it.
  const SCROLL_KEYS = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', ' ', 'Home', 'End'];
  const SLIDER_KEYS = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'];
  const MODIFIERS = ['Shift', 'Control', 'Alt', 'AltGraph', 'Meta', 'OS', 'CapsLock', 'Fn'];
  addEventListener('keydown', event => {
    if (state.running) {
      if (!MODIFIERS.includes(event.key)) skip();
      return;
    }
    if (!state.layout || event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) return;
    const target = event.target instanceof Element ? event.target : document.body;
    const field = target.closest('input, textarea, select');
    if (target.isContentEditable || field && (field.type !== 'range' || SLIDER_KEYS.includes(event.key))) return;
    const { key } = event, place = event.code.match(/^(?:Key|Digit)([A-Z0-9])$/);
    const char = /^[a-z0-9]$/i.test(key) ? key.toLowerCase() : place ? place[1].toLowerCase() : '';
    if (char >= '0' && char <= '9') {
      if (Number(char) < TABS.length && !event.repeat) navigate(TABS[Number(char)]);
    } else if (key === 'ArrowLeft' || key === 'ArrowRight') {
      event.preventDefault();
      const i = TABS.indexOf(dock.tab), n = TABS.length;
      if (!event.repeat) navigate(TABS[(i + (key === 'ArrowRight' ? 1 : n - 1)) % n]);
    } else if (char === 'b') {
      if (!event.repeat) toggleFold();
    } else if (char === 'r') {
      if (!event.repeat) replay();
    } else if (key === 'Escape') {
      navigate('home');
    } else if (SCROLL_KEYS.includes(key) && dock.tab !== 'home' && !scroller().contains(target)
      && !(key === ' ' && target.closest('button, [role="button"]'))) {
      event.preventDefault();   // the page itself does not scroll: the section (or its pictures) does
      scrollPanel(key, event.shiftKey, event.repeat);
    }
  });

  // The divider: dragged by the pointer (from where it was pressed, so the line does not jump to it),
  // or moved by the arrow keys while it has the keyboard's focus (then they do not change the section;
  // Enter folds the picture away or brings it back). The mouse does not give it the focus.
  divider.addEventListener('mousedown', event => event.preventDefault());
  divider.addEventListener('pointerdown', event => {
    if (event.button !== 0 || drag.id != null) return;
    Object.assign(drag, { id: event.pointerId, x0: event.clientX, x: event.clientX, grab: event.clientX - dividerX(), from: prefs.split, moved: false });
    divider.setPointerCapture(event.pointerId);
  });
  divider.addEventListener('pointermove', event => {
    if (event.pointerId !== drag.id) return;
    drag.x = event.clientX;
    if (!drag.moved) {
      if (Math.abs(drag.x - drag.x0) < 3) return;
      drag.moved = true;
      divider.classList.add('dragging');
      stage.classList.add('resizing');
      endSwap();
      if (foldWanted()) setFold(false);   // dragged out from the screen's left edge
    }
    tweens.delete(split);
    split.value = splitAt(drag.x - drag.grab);
    drawSoon();
  });
  divider.addEventListener('pointerup', event => { if (event.pointerId === drag.id) dropDivider(); });
  divider.addEventListener('pointercancel', event => { if (event.pointerId === drag.id) dropDivider(); });
  divider.addEventListener('lostpointercapture', event => { if (event.pointerId === drag.id) dropDivider(); });
  divider.addEventListener('dblclick', () => { if (!foldWanted()) setSplit(SPLIT.normal, 400); });
  divider.addEventListener('keydown', event => {
    if (event.ctrlKey || event.altKey || event.metaKey) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      if (foldWanted()) return;
      const D = state.layout.dock, from = Math.min(D.max, Math.max(D.min, prefs.split));
      setSplit(Math.min(D.max, Math.max(D.min, from + (event.key === 'ArrowRight' ? SPLIT.step : -SPLIT.step))), 150);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (!event.repeat) toggleFold();
    }
  });
  // Hidden tabs stop painting; hold the opening's clock while hidden instead of jumping ahead.
  let hiddenAt = 0;
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) hiddenAt = performance.now();
    else if (hiddenAt && state.running && state.start) state.start += performance.now() - hiddenAt;
    // (and the fill's soft light goes out, its passes waiting until the tab is seen again; the birds
    // wait where they are)
    if (document.hidden) dropLight(false, true);
    else if (!state.running && state.layout) {
      waitForPass();
      flyBirds();
    }
    if (!document.hidden) tick();   // (the time of day may have moved on a long way)
  });
  const relayout = () => {
    if (!state.layout) return;
    endSwap();   // the picture is framed afresh
    if (state.debugT != null) { layout(); render(state.debugT); return; }
    if (state.running) { layout(); return; }   // the running loop draws the next frame
    layout();
    render(END);
  };
  let resizeTimer = 0;
  addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (state.running && state.debugT == null) enterIdle();
      relayout();
    }, 120);
  });
  // HELLO is measured (and rasterised for its dust) in its display font, and so is the section
  // index; redo them once the web fonts have arrived.
  if (document.fonts) document.fonts.ready.then(relayout);

  // assets/manifest.js carries the same data as a script, so a page opened from disk (where
  // fetch is blocked) still finds its pictures.
  const manifest = window.HOME_MANIFEST
    ? Promise.resolve(window.HOME_MANIFEST)
    : fetch('assets/manifest.json')
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(response.status))));
  manifest
    .then(data => { state.manifest = { scenes: [], sky: {}, ...data }; })
    .catch(() => {})   // without assets the page still shows its name and links
    .finally(() => {
      // a picture chosen earlier in the visit that has left the pool: a random one again
      if (prefs.scene && !state.manifest.scenes.some(s => s.far === prefs.scene)) {
        prefs.scene = null;
        keepPrefs();
      }
      makePicks();
      for (const [name, el] of Object.entries(clouds)) {
        const info = state.manifest.sky[name];
        if (info) el.src = `assets/${info.file}`;
        // the surf's puffs and the cloud sea are cut and painted from these: they are laid out again as
        // each comes in (a frame held for inspection is drawn again)
        el.addEventListener('load', () => {
          if (state.layout) layoutSurf(state.layout);
          if (state.debugT != null) render(state.debugT);
        }, { once: true });
      }
      // a link to a section opens on it, past the opening
      const tab = tabFromHash();
      if (window.homeDebug && params.has('t')) {
        // the picture paints in place whenever it arrives, so the frame does not wait for it
        homeDebug.scene(Number(params.get('scene') || 0));
        homeDebug.seek(Number(params.get('t')));
        document.documentElement.classList.remove('arriving');
      } else if (tab === 'home' && firstOpening()) {
        play();
      } else {
        showFinal();
      }
      if (tab !== 'home') go(tab, true);
    });
})();
