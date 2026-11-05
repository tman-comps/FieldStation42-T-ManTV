// T-ManTV guide settings (2026-11-05). One file sets the look and the station name of the
// i-Guide, the channel-change banner, the reminder pop-up and the Up Next card:
//   fs42/fs42_server/static/iguide/settings.json   {"skin": "cable", "brand": "My TV"}   (not in git)
// or on the Pi: fs42_local/guide-theme <name> / fs42_local/guide-theme brand "My TV".
// ?skin= and ?header= in the page URL still win over the file.
// Each theme is themes/<name>.css (+ themes/<name>-upnext.css for the Up Next card).
// "none" = the stock FS42 00s look (no banner or reminders).
window.TMAN_SKINS = {
  ws: 'WeatherStar (blue/gold, Star4000 font)',
  cable: '90s digital cable box (flat blue, yellow highlight)',
  modern: 'Modern dark (clean, no retro)',
  vcr: 'VCR on-screen display (blue screen, block letters)',
};
window.TMAN_DEFAULT_SKIN = 'ws';
window.TMAN_DEFAULT_BRAND = 'FieldStation42';

let tmanSettingsPromise = null;
window.tmanSettings = function () {
  if (!tmanSettingsPromise) {
    tmanSettingsPromise = fetch('/static/iguide/settings.json', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : {}))
      .catch(() => ({}));   // no file: defaults
  }
  return tmanSettingsPromise;
};

window.tmanResolveSkin = async function () {
  let name = new URLSearchParams(window.location.search).get('skin') || (await window.tmanSettings()).skin;
  name = String(name || '').trim().toLowerCase();
  if (name === 'none') return '';
  if (!window.TMAN_SKINS[name]) {
    if (name) console.warn(`guide skin "${name}" unknown, using ${window.TMAN_DEFAULT_SKIN}`);
    name = window.TMAN_DEFAULT_SKIN;
  }
  return name;
};

// Station name shown in the guide header, status bar, banner and Up Next ticker
window.tmanBrand = async function () {
  const name = new URLSearchParams(window.location.search).get('header') || (await window.tmanSettings()).brand;
  return String(name || '').trim() || window.TMAN_DEFAULT_BRAND;
};
