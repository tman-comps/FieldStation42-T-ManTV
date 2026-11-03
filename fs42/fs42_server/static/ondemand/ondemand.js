// T-ManTV On Demand menu (step 2, 2026-11-01). Navigation and layout from the approved mockup
// (pi/ondemand-ws-mockup.html); data from catalog.json, watch positions from guide_overlay.py.
// Channels come from catalog.json ("stations", read from FS42's confs by the export), in channel order,
// so new or renumbered channels show up without touching this file.
const STATIONS = {}, DECADES = [], DEC_CH = {};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const STARTED = 120, FINISHED = 0.95;   // Continue Watching: past 2 min and not past 95%

function hue(s) { let h = 0; for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; }
const colorsFor = t => { const h = hue(t); return [`hsl(${h} 55% 42%)`, `hsl(${(h + 30) % 360} 60% 12%)`]; };
function airedText(a) {
  if (!a) return "";
  const m = a.match(/^(\d{4})-(\d{2}|xx)-(\d{2}|xx)/);
  if (!m) return a;
  if (m[2] === "xx") return m[1];
  const mon = MONTHS[+m[2] - 1] || "";
  return m[3] === "xx" ? `${mon} ${m[1]}` : `${mon} ${+m[3]}, ${m[1]}`;
}

// show names: these folder names win; otherwise the NFO show title, then the folder name
const RENAME = {
  "PBS Nature": "Nature", "Nature (Archive)": "Nature: The Early Years", "Video Game TV": "Video Game TV",
};
const SHOWS = {}, MOVIES = [], PATHS = {};
let showIds = [];
const nameOf = s => RENAME[s.t] || s.nfo || s.t;
const byTitle = (a, b) => a.t.replace(/^(the|a|an) /i, "").localeCompare(b.t.replace(/^(the|a|an) /i, ""));

function loadCatalog(cat) {
  (cat.stations || []).forEach(st => {
    if (st.dec) { DECADES.push(st.dec); DEC_CH[st.dec] = st.ch; }
    else STATIONS[st.key] = { name: st.name, ch: st.ch, kids: !!st.kids };
  });
  const raw = (cat.shows || []).filter(s => STATIONS[s.station]);
  const nameCount = {}, seenNames = {};
  raw.forEach(s => { const t = nameOf(s); nameCount[t] = (nameCount[t] || 0) + 1; });
  raw.forEach((s, i) => {
    const st = STATIONS[s.station], id = "s" + i;
    let t = nameOf(s);
    if (nameCount[t] > 1) { seenNames[t] = (seenNames[t] || 0) + 1; t += s.yrs ? ` (${s.yrs})` : ` (Tapes ${seenNames[t]})`; }
    // episode rows from the export: [ep, title, minutes, plot, aired, path]
    const seasons = s.seasons.map((x, si) => ({ n: x.n, eps: x.eps.map((e, j) => {
      if (e[5]) PATHS[e[5]] = { show: id, s: si, e: j };
      return { n: e[0] ?? j + 1, t: e[1], min: e[2], plot: e[3] || "", aired: airedText(e[4]), path: e[5] };
    }) }));
    const mins = seasons.flatMap(x => x.eps.map(e => e.min)).filter(Boolean).sort((a, b) => a - b);
    SHOWS[id] = { t, k: st.kids ? "Kids" : "TV", st, c: colorsFor(t), seasons, typ: mins.length ? mins[mins.length >> 1] : null };
  });
  (cat.movies || []).forEach((m, i) => {
    const tags = m.tags.map(x => x.split("[")[0]).join(" · ");
    if (m.path) PATHS[m.path] = { movie: "m" + i };
    MOVIES.push({ id: "m" + i, t: m.t, y: m.y, dec: m.dec, aired: airedText(m.aired), tags, min: m.min, plot: m.plot || "", c: colorsFor(m.t), path: m.path });
  });
  MOVIES.sort(byTitle);
  showIds = Object.keys(SHOWS).sort((a, b) => byTitle(SHOWS[a], SHOWS[b]));
}

const movie = id => MOVIES.find(m => m.id === id);
const epCount = s => s.seasons.reduce((a, x) => a + x.eps.length, 0);
const seasonLabel = (s, x) => s.seasons.length === 1 && x.n === 1 ? "Episodes" : `Season ${x.n}`;
const showMeta = s => {
  const n = s.seasons.length;
  return `CH ${s.st.ch} ${s.st.name.toUpperCase()} · ${n > 1 ? n + " SEASONS · " : ""}${epCount(s)} EPISODE${epCount(s) > 1 ? "S" : ""}${s.typ ? ` · ${s.typ} MIN` : ""}`;
};
const runtime = min => (min ? (min >= 60 ? `${Math.floor(min / 60)} HR ${String(min % 60).padStart(2, "0")} MIN` : `${min} MIN`) : "");
const movieMeta = m => [m.y, runtime(m.min)].filter(Boolean).join(" · ");
const epMeta = (x, e) => [`S${x.n} E${e.n}`, runtime(e.min), e.aired && "AIRED " + e.aired.toUpperCase()].filter(Boolean).join(" · ");

// ---------- watch positions (runtime/ondemand_positions.json, path -> {pos, dur, ts, done}) ----------
let POS = {}, CONTINUE = [];
const inProgress = p => p && !p.done && p.pos > STARTED && (!p.dur || p.pos < p.dur * FINISHED);
const pctOf = p => (p && p.dur ? Math.max(1, Math.min(100, Math.round(p.pos / p.dur * 100))) : 0);
function buildContinue() {
  CONTINUE = Object.entries(POS).filter(([path, p]) => inProgress(p) && PATHS[path])
    .sort((a, b) => b[1].ts - a[1].ts).slice(0, 12)
    .map(([path, p]) => ({ ...PATHS[path], path, pct: pctOf(p) }));
}
// Show page: the episode to resume, or the one after the last finished one
function showNext(id) {
  const s = SHOWS[id];
  let best = null;
  s.seasons.forEach((x, si) => x.eps.forEach((e, ei) => {
    const p = POS[e.path];
    if (p && (!best || p.ts > best.p.ts)) best = { si, ei, p };
  }));
  if (!best) return null;
  if (inProgress(best.p)) return { s: best.si, e: best.ei, resume: true };
  if (!best.p.done && !(best.p.dur && best.p.pos >= best.p.dur * FINISHED)) return null;
  let { si, ei } = best;
  if (++ei >= s.seasons[si].eps.length) { si++; ei = 0; }
  return si < s.seasons.length ? { s: si, e: ei, resume: false } : null;
}

const TABS = ["Home", "TV Shows", "Kids", "Movies"];

// ---------- helpers ----------
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
const grad = c => `background: linear-gradient(160deg, ${c[0]} 0%, ${c[1]} 100%)`;
const posterHTML = (title, kicker, c, attrs) =>
  `<div class="poster" ${attrs} style="${grad(c)}"><div class="stripe" style="${grad(c)}"></div><div class="pt">${esc(title)}</div><div class="pk">${esc(kicker)}</div></div>`;
const showPoster = (id, a) => { const s = SHOWS[id]; return posterHTML(s.t, `CH ${s.st.ch} · ${epCount(s)} EPS`, s.c, a); };
const moviePoster = (m, a) => posterHTML(m.t, m.y || m.dec, m.c, a);
const epOf = c => SHOWS[c.show].seasons[c.s].eps[c.e];
const progHTML = path => inProgress(POS[path]) ? `<div class="prog"><i style="width:${pctOf(POS[path])}%"></i></div>` : "";

// ---------- playback: hand the file to field_player through the overlay ----------
function playEp(id, si, ei, resume) {
  const s = SHOWS[id], x = s.seasons[si], e = x.eps[ei];
  const p = POS[e.path];
  play(e.path, resume && inProgress(p) ? p.pos : 0, s.t, `S${x.n} E${e.n}`, e.t);
}
function playMovie(m, resume) {
  const p = POS[m.path];
  play(m.path, resume && inProgress(p) ? p.pos : 0, m.t, "Movie", m.y || m.dec);
}
function play(path, start, show, where, title) {
  if (!path) return;
  $("play").innerHTML = `<div class="kicker">${start ? "Resuming" : "Now loading"}</div><div class="htitle">${esc(show)}</div><div class="meta">${esc(where)} · ${esc(title)}</div><div class="meta">PLEASE STAND BY</div>`;
  $("play").hidden = false;
  console.log("ODPLAY " + JSON.stringify({ path, start: start > 0 ? Math.max(0, Math.floor(start - 3)) : 0, title: `${show} · ${where} · ${title}` }));
}

// ---------- screens ----------
// Each render returns { html, zones, after? }; zones[z] = { dir: "h"|"v", acts: [fn], focus?: fn(i), items? }.
let stack = [{ type: "tab", tab: 0, z: 1, idx: {}, sx: {}, sy: 0 }];
const cur = () => stack[stack.length - 1];
const resetTab = sc => { sc.idx = { 0: sc.tab }; sc.sx = {}; sc.sy = 0; sc.chip = 0; };

function tabZone(sc) {
  return { dir: "h", acts: TABS.map(() => () => {}), focus: i => { if (sc.tab !== i) { sc.tab = i; resetTab(sc); } } };
}

function renderHome(sc) {
  const zones = [tabZone(sc)];
  const rows = [];
  if (CONTINUE.length) rows.push({ title: "Continue Watching", wide: true, items: CONTINUE,
    act: c => c.movie ? playMovie(movie(c.movie), true) : playEp(c.show, c.s, c.e, true) });
  Object.entries(STATIONS).forEach(([key, st]) => {
    const ids = showIds.filter(id => SHOWS[id].st === st);
    if (ids.length) rows.push({ title: st.name, sub: `CH ${st.ch} · ${ids.length} SHOW${ids.length > 1 ? "S" : ""}`, items: ids.map(id => ({ show: id })), act: it => openShow(it.show) });
  });
  DECADES.forEach(d => {
    const ms = MOVIES.filter(m => m.dec === d);
    if (ms.length) rows.push({ title: `Movies · ${d}`, sub: `CH ${DEC_CH[d]} · ${ms.length} MOVIES`, items: ms.map(m => ({ movie: m.id })), act: it => openMovie(it.movie) });
  });

  let html = `<div class="hero" id="hero"></div><div class="vscroll" id="vs">`;
  rows.forEach((r, ri) => {
    const z = ri + 1;
    zones.push({ dir: "h", acts: r.items.map(it => () => r.act(it)), items: r.items, wide: r.wide });
    html += `<div class="shelf"><h3>${r.title}${r.sub ? `<small>${r.sub}</small>` : ""}</h3><div class="hscroll"><div class="track">`;
    r.items.forEach((it, i) => {
      const a = `data-z="${z}" data-i="${i}"`;
      if (r.wide) {
        const m = it.movie && movie(it.movie), s = it.show && SHOWS[it.show];
        const k = m ? "Movie" : `${s.t} · S${s.seasons[it.s].n} E${epOf(it).n}`, t = m ? m.t : epOf(it).t, c = (m || s).c;
        html += `<div class="wide" ${a} style="${grad(c)}"><div class="stripe" style="${grad(c)}"></div><div class="ws-k">${esc(k)}</div><div class="wt">${esc(t)}</div><div class="prog"><i style="width:${it.pct}%"></i></div></div>`;
      } else if (it.show) html += showPoster(it.show, a);
      else html += moviePoster(movie(it.movie), a);
    });
    html += `</div></div></div>`;
  });
  html += `</div>`;

  const hero = () => {
    const z = sc.z, row = z > 0 ? zones[z] : zones[1];
    if (!row) return;
    const it = row.items[z > 0 ? sc.idx[z] || 0 : 0];
    let k, t, meta, desc, c;
    if (row.wide && it.show) { const s = SHOWS[it.show], e = epOf(it); k = "Continue Watching"; t = s.t; meta = `${esc(epMeta(s.seasons[it.s], e))} · ${esc(e.t)}`; desc = e.plot || `${it.pct}% watched. OK picks up where you stopped.`; c = s.c; }
    else if (it.movie) { const m = movie(it.movie); k = row.wide ? "Continue Watching" : `Movie · ${m.dec}`; t = m.t; meta = `${movieMeta(m)}${m.aired ? " · RECORDED " + m.aired.toUpperCase() : ""}`; desc = row.wide ? `${it.pct}% watched. OK picks up where you stopped.` : m.plot || m.tags; c = m.c; }
    else { const s = SHOWS[it.show]; k = s.k === "Kids" ? "Kids" : "TV Show"; t = s.t; meta = showMeta(s); desc = s.seasons.map(x => `${seasonLabel(s, x)}: ${x.eps.length}`).join(" · "); c = s.c; }
    $("hero").innerHTML = `<div class="bd" style="${grad(c)}"></div><div class="kicker">${k}</div><div class="htitle">${esc(t)}</div><div class="meta">${meta}</div><div class="desc">${esc(desc)}</div>`;
  };
  return { html, zones, after: hero };
}

function renderGrid(sc) {
  const zones = [tabZone(sc)];
  let chips, list, unit;
  if (sc.tab === 3) {
    chips = ["All", ...DECADES.filter(d => MOVIES.some(m => m.dec === d))];
    const f = chips[sc.chip || 0];
    list = MOVIES.filter(m => f === "All" || m.dec === f).map(m => ({ movie: m.id }));
    unit = "MOVIES";
  } else {
    const kids = sc.tab === 2;
    const sts = Object.values(STATIONS).filter(st => st.kids === kids && showIds.some(id => SHOWS[id].st === st));
    chips = ["All", ...sts.map(st => st.name)];
    const f = chips[sc.chip || 0];
    list = showIds.filter(id => SHOWS[id].k === (kids ? "Kids" : "TV") && (f === "All" || SHOWS[id].st.name === f)).map(id => ({ show: id }));
    unit = "SHOWS";
  }
  zones.push({ dir: "h", acts: chips.map(() => () => {}), focus: i => { if ((sc.chip || 0) !== i) { sc.chip = i; sc.sy = 0; Object.keys(sc.idx).forEach(k => +k > 1 && delete sc.idx[k]); } } });
  let html = `<div class="chips">${chips.map((c, i) => `<div class="chip${i === (sc.chip || 0) ? " on" : ""}" data-z="1" data-i="${i}">${esc(c)}</div>`).join("")}</div>`;
  html += `<div class="gridhead"><div class="meta">${list.length} ${unit} · A–Z</div></div>`;
  const per = 6, base = zones.length;
  html += `<div class="vscroll" id="vs">`;
  for (let r = 0; r * per < list.length; r++) {
    const items = list.slice(r * per, r * per + per), z = base + r;
    zones.push({ dir: "h", acts: items.map(it => () => it.show ? openShow(it.show) : openMovie(it.movie)), keepCol: true });
    html += `<div class="shelf"><div class="hscroll"><div class="track">`;
    items.forEach((it, i) => {
      const a = `data-z="${z}" data-i="${i}"`;
      html += it.show ? showPoster(it.show, a) : moviePoster(movie(it.movie), a);
    });
    html += `</div></div></div>`;
  }
  html += `</div>`;
  return { html, zones };
}

function renderShow(sc) {
  const s = SHOWS[sc.show], season = s.seasons[sc.season];
  const next = showNext(sc.show);
  const btns = [];
  if (next) {
    const x = s.seasons[next.s], e = x.eps[next.e];
    btns.push({ l: `▶ ${next.resume ? "Resume" : "Next"} S${x.n} E${e.n}`, main: true, a: () => playEp(sc.show, next.s, next.e, next.resume) });
  }
  btns.push({ l: next ? "From the start" : `▶ Play S${s.seasons[0].n} E${s.seasons[0].eps[0].n}`, main: !next, a: () => playEp(sc.show, 0, 0, false) });
  btns.push({ l: "Shuffle", a: () => { const si = Math.floor(Math.random() * s.seasons.length); playEp(sc.show, si, Math.floor(Math.random() * s.seasons[si].eps.length), false); } });
  const zones = [
    { dir: "h", acts: btns.map(b => b.a) },
    { dir: "h", acts: s.seasons.map(() => () => {}), focus: i => { if (sc.season !== i) { sc.season = i; sc.idx[2] = 0; sc.sy = 0; } } },
    { dir: "v", acts: season.eps.map((e, i) => () => playEp(sc.show, sc.season, i, true)) },
  ];
  // on the episode list, the info box shows the focused episode's details and plot
  const fe = sc.z === 2 ? season.eps[sc.idx[2] || 0] : null;
  const info = fe
    ? `<div class="meta">${esc(epMeta(season, fe))}</div><div class="desc">${esc(fe.plot || fe.t)}</div>`
    : `<div class="meta">${showMeta(s)}</div>`;
  let html = `<div class="detail">${posterHTML(s.t, `CH ${s.st.ch}`, s.c, "")}<div class="info">
    <div class="kicker">${s.k === "Kids" ? "Kids" : "TV Show"} · ${esc(s.st.name)}</div>
    <div class="htitle">${esc(s.t)}</div>${info}
    <div class="btns">${btns.map((b, i) => `<div class="btn${b.main ? " main" : ""}" data-z="0" data-i="${i}">${b.l}</div>`).join("")}</div></div></div>`;
  html += `<div class="seasons" id="seasons">${s.seasons.map((x, i) => `<div class="season${i === sc.season ? " on" : ""}" data-z="1" data-i="${i}">${seasonLabel(s, x)} <span style="opacity:.6">(${x.eps.length})</span></div>`).join("")}</div>`;
  html += `<div class="vscroll eps" id="vs">${season.eps.map((e, i) => {
    const p = POS[e.path];
    const tag = inProgress(p) ? `<span class="seen">${pctOf(p)}% WATCHED</span>` : p && (p.done || (p.dur && p.pos >= p.dur * FINISHED)) ? `<span class="seen done">WATCHED</span>` : "";
    return `<div class="ep" data-z="2" data-i="${i}"><span class="en">E${String(e.n).padStart(2, "0")}</span><span class="et">${esc(e.t)}</span>${e.min ? `<span class="em">${e.min} MIN</span>` : ""}${tag}${progHTML(e.path)}</div>`;
  }).join("")}</div>`;
  return { html, zones };
}

function renderMovie(sc) {
  const m = movie(sc.movie);
  const p = POS[m.path], cw = inProgress(p);
  const btns = cw
    ? [{ l: "▶ Resume", main: true, a: () => playMovie(m, true) }, { l: "Start over", a: () => playMovie(m, false) }]
    : [{ l: "▶ Play", main: true, a: () => playMovie(m, false) }];
  const more = MOVIES.filter(x => x.dec === m.dec && x.id !== m.id);
  const zones = [{ dir: "h", acts: btns.map(b => b.a) }, { dir: "h", acts: more.map(x => () => openMovie(x.id, true)) }];
  let html = `<div class="detail">${moviePoster(m, "")}<div class="info">
    <div class="kicker">Movie · ${m.dec} · CH ${DEC_CH[m.dec]}</div><div class="htitle">${esc(m.t)}</div>
    <div class="meta">${movieMeta(m)}</div><div class="desc">${esc(m.plot || m.tags)}</div>
    ${m.aired ? `<div class="aired">Recorded off the air ${esc(m.aired)}</div>` : ""}
    <div class="btns">${btns.map((b, i) => `<div class="btn${b.main ? " main" : ""}" data-z="0" data-i="${i}">${b.l}</div>`).join("")}</div>
    ${cw ? `<div class="prog" style="max-width:260px"><i style="width:${pctOf(p)}%"></i></div>` : ""}</div></div>`;
  html += `<div class="vscroll" id="vs"><div class="shelf"><h3>More from the ${m.dec}</h3><div class="hscroll"><div class="track">${more.map((x, i) => moviePoster(x, `data-z="1" data-i="${i}"`)).join("")}</div></div></div></div>`;
  return { html, zones };
}

function openShow(id) { stack.push({ type: "show", show: id, season: 0, z: 0, idx: {}, sx: {}, sy: 0 }); }
function openMovie(id, replace) {
  const sc = { type: "movie", movie: id, z: 0, idx: {}, sx: {}, sy: 0 };
  if (replace) stack[stack.length - 1] = sc; else stack.push(sc);
}

// ---------- render + focus ----------
let Z = [], loadError = "";
function render() {
  const sc = cur();
  if (!showIds.length && !MOVIES.length) { $("view").innerHTML = `<div class="hero"><div class="kicker">${loadError ? "No catalog data" : "Loading"}</div><div class="desc">${esc(loadError || "Please stand by")}</div></div>`; return; }
  const out = sc.type === "show" ? renderShow(sc) : sc.type === "movie" ? renderMovie(sc) : sc.tab === 0 ? renderHome(sc) : renderGrid(sc);
  Z = out.zones;
  const onTabs = sc.type === "tab";
  $("tabs").innerHTML = onTabs
    ? TABS.map((t, i) => `<div class="tab${i === sc.tab ? " on" : ""}" data-z="0" data-i="${i}">${t}</div>`).join("")
    : `<div class="tab" style="opacity:.7">◄ Back</div>`;
  $("view").innerHTML = out.html;
  sc.z = Math.min(sc.z, Z.length - 1);
  sc.idx[sc.z] = Math.max(0, Math.min(sc.idx[sc.z] || 0, Z[sc.z].acts.length - 1));
  const el = document.querySelector(`[data-z="${sc.z}"][data-i="${sc.idx[sc.z]}"]`);
  if (el) el.classList.add("f");
  if (out.after) out.after();
  keepInView(sc, el);
  $("st-r").textContent = sc.type === "show" ? `${SHOWS[sc.show].t}`.toUpperCase().slice(0, 30) : `${showIds.length} SHOWS · ${MOVIES.length} MOVIES`;
}
function nearest(box, el, axis, pad) {
  const [pos, size, scroll, client] = axis === "x" ? ["offsetLeft", "offsetWidth", "scrollLeft", "clientWidth"] : ["offsetTop", "offsetHeight", "scrollTop", "clientHeight"];
  const a = el[pos] - pad, b = el[pos] + el[size] + pad;
  if (a < box[scroll]) box[scroll] = a;
  else if (b > box[scroll] + box[client]) box[scroll] = b - box[client];
}
function keepInView(sc, el) {
  document.querySelectorAll(".hscroll").forEach(h => {
    const z = h.querySelector("[data-z]")?.dataset.z;
    if (z == null) return;
    h.scrollLeft = sc.sx[z] || 0;
    if (el && h.contains(el)) { nearest(h, el, "x", 14); sc.sx[z] = h.scrollLeft; }
  });
  const sz = $("seasons");
  if (sz && el && sz.contains(el)) nearest(sz, el, "x", 8);
  else if (sz) { const on = sz.querySelector(".on"); if (on) nearest(sz, on, "x", 8); }
  const vs = $("vs");
  if (!vs) return;
  vs.scrollTop = sc.sy || 0;
  if (el && vs.contains(el)) {
    let row = el; while (row.parentElement !== vs) row = row.parentElement;
    nearest(vs, row, "y", 0);
    sc.sy = vs.scrollTop;
  }
}
function move(dz, di) {
  const sc = cur(), zone = Z[sc.z];
  if (!zone) return;
  const i = sc.idx[sc.z] || 0;
  if (di) {
    const n = Math.max(0, Math.min(zone.acts.length - 1, i + di));
    sc.idx[sc.z] = n;
    if (zone.focus) zone.focus(n);
    return;
  }
  if (zone.dir === "v") {
    const n = i + dz;
    if (n >= 0 && n < zone.acts.length) { sc.idx[sc.z] = n; return; }
  }
  const nz = sc.z + dz;
  if (nz < 0 || nz >= Z.length || !Z[nz].acts.length) return;
  if (Z[nz].keepCol && zone.keepCol) sc.idx[nz] = Math.min(i, Z[nz].acts.length - 1);
  sc.z = nz;
}
function key(k) {
  if (!$("play").hidden) {   // while a title loads, only BACK does anything (it cancels the stand-by card)
    if (k === "Escape" || k === "Backspace") $("play").hidden = true;
    return;
  }
  const sc = cur(), zone = Z[sc.z];
  if (k === "ArrowLeft") move(0, -1);
  else if (k === "ArrowRight") move(0, 1);
  else if (k === "ArrowUp") move(-1, 0);
  else if (k === "ArrowDown") move(1, 0);
  else if (k === "PageUp") for (let n = 0; n < 4; n++) move(-1, 0);
  else if (k === "PageDown") for (let n = 0; n < 4; n++) move(1, 0);
  else if (k === "Enter") zone?.acts[sc.idx[sc.z] || 0]?.();
  else if (k === "Escape" || k === "Backspace") {
    if (stack.length > 1) stack.pop();
    else if (sc.tab !== 0 || sc.z > 1) { sc.tab = 0; resetTab(sc); sc.z = 1; }
    else { console.log("ODCLOSE"); return; }
  }
  if (!$("play").hidden) return;   // a play request: keep the stand-by card up
  render();
}

// ---------- hooks for guide_overlay.py ----------
window.odKey = k => key(k);
window.odSetPositions = p => { POS = p || {}; buildContinue(); render(); };
window.odOpened = () => { $("play").hidden = true; render(); };
window.odHome = () => { stack = [{ type: "tab", tab: 0, z: 1, idx: {}, sx: {}, sy: 0 }]; render(); };

document.addEventListener("keydown", e => {   // a real keyboard, for testing in a browser
  if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Enter", "Escape", "Backspace"].includes(e.key)) return;
  e.preventDefault(); key(e.key);
});

function tick() {
  const d = new Date(), h = d.getHours() % 12 || 12;
  $("clock").textContent = `${h}:${String(d.getMinutes()).padStart(2, "0")} ${d.getHours() < 12 ? "AM" : "PM"}`;
}
setInterval(tick, 10000);
tick();
render();
fetch("catalog.json", { cache: "no-store" })
  .then(r => { if (!r.ok) throw new Error("catalog.json: HTTP " + r.status); return r.json(); })
  .then(cat => { loadCatalog(cat); buildContinue(); console.log(`catalog: ${showIds.length} shows, ${MOVIES.length} movies`); })
  .catch(e => { loadError = String(e); console.log("catalog failed: " + e); })
  .finally(() => (document.fonts ? document.fonts.ready : Promise.resolve()).then(render));
