// The time of day (CONTEXT: 时段), worked out before the page is first painted, so that a visit at night
// does not open on the white paper. Where the visitor is is guessed from the time zone their device is
// set to (no location is asked for): the zone's own city as the tz database has it (ZONES), or elsewhere
// a place on the meridian of the zone's standard time. The sun's elevation there gives the sky's phase
// (sky: 0 by day, 1 at dusk, 2 at night, mixed between), how dark the paper is and the period the
// pictures are chosen by; the moon is today's. A period chosen in the settings holds instead. main.js
// keeps it up to date while the page is open and paints the window's sky with it.
window.HOME_TIME = (() => {
  'use strict';

  const DEG = Math.PI / 180;
  const PERIODS = ['day', 'dusk', 'night'];
  const MODES = ['auto', ...PERIODS];
  // The sky by the sun's elevation (degrees): day down to day[0], going over to dusk by day[1], dusk
  // until night[0], going over to night by night[1]. The period the pictures are chosen by is day above
  // `period`, night under minus that and dusk between: an hour or so round sunset, and round sunrise.
  // The paper darkens through that hour, the lines and the lettering going over from ink to light at
  // sunset, its middle.
  const SKY = { day: [8, 2], night: [-2, -8], period: 6 };
  // the paper by day and at night (as in styles.css), for the browser's own colour round the page
  const PAPER = [[244, 246, 248], [13, 22, 40]];
  const PREFS_KEY = 'home:prefs';   // where main.js keeps the visitor's choices, the period among them
  // [latitude, longitude] of the commoner zones' cities (tz database, zone.tab), with the old names some
  // browsers still give a few of them
  const ZONES = {
    'Asia/Shanghai': [31.23, 121.47], 'Asia/Urumqi': [43.8, 87.58], 'Asia/Hong_Kong': [22.28, 114.15],
    'Asia/Macau': [22.2, 113.54], 'Asia/Taipei': [25.05, 121.5], 'Asia/Tokyo': [35.65, 139.74],
    'Asia/Seoul': [37.55, 126.97], 'Asia/Singapore': [1.28, 103.85], 'Asia/Kuala_Lumpur': [3.17, 101.7],
    'Asia/Bangkok': [13.75, 100.52], 'Asia/Ho_Chi_Minh': [10.75, 106.67], 'Asia/Saigon': [10.75, 106.67],
    'Asia/Manila': [14.58, 121], 'Asia/Jakarta': [-6.17, 106.8], 'Asia/Kolkata': [22.53, 88.37],
    'Asia/Calcutta': [22.53, 88.37], 'Asia/Dubai': [25.3, 55.3], 'Europe/Moscow': [55.76, 37.62],
    'Europe/London': [51.51, -0.12], 'Europe/Paris': [48.87, 2.33], 'Europe/Berlin': [52.5, 13.37],
    'America/New_York': [40.71, -74.01], 'America/Chicago': [41.85, -87.65], 'America/Denver': [39.74, -104.98],
    'America/Los_Angeles': [34.05, -118.24], 'America/Toronto': [43.65, -79.38], 'America/Vancouver': [49.27, -123.12],
    'America/Sao_Paulo': [-23.53, -46.62], 'Australia/Sydney': [-33.87, 151.22], 'Australia/Melbourne': [-37.82, 144.97],
    'Australia/Brisbane': [-27.47, 153.03], 'Australia/Perth': [-31.95, 115.85], 'Pacific/Auckland': [-36.87, 174.77],
  };

  const smooth = (a, b, x) => { const p = Math.min(1, Math.max(0, (x - a) / (b - a))); return p * p * (3 - 2 * p); };
  const days = ms => ms / 864e5 - 10957.5;   // days since 2000-01-01 12:00 UTC

  function place(date) {
    let zone = '';
    try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch { /* (a browser without it) */ }
    if (ZONES[zone]) return ZONES[zone];
    // (summer time in January: south of the equator)
    const year = date.getFullYear(), jan = -new Date(year, 0, 1).getTimezoneOffset(), jul = -new Date(year, 6, 1).getTimezoneOffset();
    return [jan > jul || /^(Australia|Antarctica)\//.test(zone) ? -30 : 35, Math.min(jan, jul) / 4];
  }
  const [lat, lon] = place(new Date());

  // The sun's elevation (degrees, refraction left out) at ms: the Astronomical Almanac's low-precision
  // formulas, good to a fraction of a degree.
  function sunAt(ms) {
    const n = days(ms), g = (357.529 + 0.98560028 * n) * DEG;
    const ecliptic = (280.459 + 0.98564736 * n + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * DEG, tilt = (23.439 - 3.6e-7 * n) * DEG;
    const ra = Math.atan2(Math.cos(tilt) * Math.sin(ecliptic), Math.cos(ecliptic)), dec = Math.asin(Math.sin(tilt) * Math.sin(ecliptic));
    const hour = (280.46061837 + 360.98564736629 * n + lon) * DEG - ra;
    return Math.asin(Math.sin(lat * DEG) * Math.sin(dec) + Math.cos(lat * DEG) * Math.cos(dec) * Math.cos(hour)) / DEG;
  }

  // The sun's last rising or setting before ms and its next one after it ({ rise, at }, its top on the
  // horizon), looked for a day either way in ten-minute steps; null where there is none (the midnight
  // sun, the polar night).
  function sunTimes(ms) {
    const HORIZON = -0.833, STEP = 6e5;
    let last = null, next = null, t0 = ms - 864e5, h0 = sunAt(t0) - HORIZON;
    for (let t = t0 + STEP; t <= ms + 864e5 && !next; t += STEP) {
      const h = sunAt(t) - HORIZON;
      if (h0 < 0 !== h < 0) {
        const event = { rise: h > 0, at: new Date(t - STEP * h / (h - h0)) };
        if (event.at <= ms) last = event;
        else next = event;
      }
      [t0, h0] = [t, h];
    }
    return { last, next };
  }

  // The moon's lit share, and whether it is waxing (under 180 degrees from the sun): the low-precision
  // phase angle in Meeus, Astronomical Algorithms, chapter 48.
  function moonAt(ms) {
    const T = days(ms) / 36525, D = (297.8501921 + 445267.1114034 * T) * DEG;
    const M = (357.5291092 + 35999.0502909 * T) * DEG, Mm = (134.9633964 + 477198.8675055 * T) * DEG;
    const i = (180 - D / DEG - 6.289 * Math.sin(Mm) + 2.1 * Math.sin(M) - 1.274 * Math.sin(2 * D - Mm)
      - 0.658 * Math.sin(2 * D) - 0.214 * Math.sin(2 * Mm) - 0.11 * Math.sin(D)) * DEG;
    return { lit: (1 + Math.cos(i)) / 2, waxing: Math.sin(i) > 0 };
  }

  // The time of day at date: as chosen (mode 'day', 'dusk' or 'night'), or for 'auto' the sky over the
  // visitor then. period: what the pictures are chosen by; sky: the window's sky (0 to 2); dark: the
  // paper (0 white, 1 the night paper); light: the lines and the lettering (0 ink, 1 light); real: the
  // period now, whatever was chosen; sun: its last and next rising or setting; moon: its lit share and
  // whether it is lit on the right (waxing, north of the equator).
  function at(date, mode) {
    const ms = +date, h = sunAt(ms), moon = moonAt(ms);
    const real = h > SKY.period ? 'day' : h < -SKY.period ? 'night' : 'dusk';
    const time = { mode: MODES.includes(mode) ? mode : 'auto', real, sun: sunTimes(ms), moon: { lit: moon.lit, right: moon.waxing !== lat < 0 } };
    if (time.mode !== 'auto') {
      const night = time.mode === 'night';
      return { ...time, period: time.mode, sky: PERIODS.indexOf(time.mode), dark: night ? 1 : 0, light: night ? 1 : 0 };
    }
    // (the paper eased twice over, so that it lingers white and dark and goes quickly through the greys)
    const p = smooth(SKY.period, -SKY.period, h), dark = p * p * (3 - 2 * p);
    const sky = smooth(SKY.day[0], SKY.day[1], h) + smooth(SKY.night[0], SKY.night[1], h);
    return { ...time, period: real, sky, dark, light: dark >= 0.5 ? 1 : 0 };
  }

  // Puts the paper up for a time of day (styles.css: --dark and --light), smoothly once the page is up,
  // and the browser's own colour round the page to match it.
  function paper(time, smoothly) {
    const root = document.documentElement;
    if (smoothly) root.classList.add('time-ease');
    root.style.setProperty('--dark', time.dark.toFixed(3));
    root.style.setProperty('--light', String(time.light));
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = `rgb(${PAPER[0].map((v, i) => Math.round(v + (PAPER[1][i] - v) * time.dark)).join(', ')})`;
  }

  let mode = 'auto';
  try { mode = (JSON.parse(sessionStorage.getItem(PREFS_KEY) || 'null') || {}).time; } catch { /* no storage: the time now */ }
  paper(at(new Date(), mode), false);
  return { PERIODS, MODES, at, paper };
})();
