// T-ManTV guide themes (2026-11-05). One setting picks the look of the i-Guide, the
// channel-change banner, the reminder pop-up and the Up Next card:
//   fs42/fs42_server/static/iguide/skin.json   {"skin": "cable"}   (not in git)
// or on the Pi: fs42_local/guide-theme <name>. A ?skin= in the page URL still wins.
// Each theme is themes/<name>.css (+ themes/<name>-upnext.css for the Up Next card).
// "none" = the stock FS42 00s look (no banner or reminders).
window.TMAN_SKINS = {
  ws: 'WeatherStar (blue/gold, Star4000 font)',
  cable: '90s digital cable box (flat blue, yellow highlight)',
  modern: 'Modern dark (clean, no retro)',
  vcr: 'VCR on-screen display (blue screen, block letters)',
};
window.TMAN_DEFAULT_SKIN = 'ws';

window.tmanResolveSkin = async function () {
  let name = new URLSearchParams(window.location.search).get('skin');
  if (!name) {
    try {
      const r = await fetch('/static/iguide/skin.json', { cache: 'no-store' });
      if (r.ok) name = String((await r.json()).skin || '');
    } catch (e) { /* no file: default */ }
  }
  name = String(name || '').trim().toLowerCase();
  if (name === 'none') return '';
  if (!window.TMAN_SKINS[name]) {
    if (name) console.warn(`guide skin "${name}" unknown, using ${window.TMAN_DEFAULT_SKIN}`);
    name = window.TMAN_DEFAULT_SKIN;
  }
  return name;
};
