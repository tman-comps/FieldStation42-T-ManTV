// T-ManTV WeatherStar skin add-on for the i-Guide (only active with ?skin=ws).
// customguide.js still builds the 00s layout and does all navigation/tuning; this file
// wraps a few of its functions to add the WeatherStar pieces: header bar + clock,
// live-picture frame on the left, info panel (NOW PLAYING, progress bar, UP NEXT),
// start times under each show, WeatherStar time labels and the status bar.
(function () {
  if (new URLSearchParams(window.location.search).get('skin') !== 'ws') return;

  const pad = n => String(n).padStart(2, '0');
  const clockText = d => {
    const h = d.getHours() % 12 || 12;
    return `${h}:${pad(d.getMinutes())}:${pad(d.getSeconds())} ${d.getHours() < 12 ? 'AM' : 'PM'}`;
  };
  const timeText = d => {
    const h = d.getHours() % 12 || 12;
    return `${h}:${pad(d.getMinutes())} ${d.getHours() < 12 ? 'AM' : 'PM'}`;
  };
  const durText = ms => {
    const s = Math.max(0, Math.round(ms / 1000));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
  };

  // Split a program block (NFO meta copied onto it below) into the parts the banner and info box
  // show (planned-nfo-redo.md, 2026-11-02). Only NFO types episode/movie; music, news-style movie
  // plots and web channels return null and show as before.
  // Episodes: plot "S1E4 · Title (Year) – summary" -> show = grid title, ep = Title, code "S1E4  Year".
  //   Older plots ("S3E02 - Title (1984)", "Title (Year)", a second tape line) still give ep + code.
  // Movies:   plot "1984 · WXYZ-7 Detroit – summary" -> ep = grid title minus "(Year)", code = left part.
  function splitPlot(el) {
    const d = el.dataset, title = String(d.title || '').trim();
    const plot = String(d.description || '').trim();
    const line = plot.split('\n')[0].trim();
    const cut = line.indexOf(' – ');
    const left = (cut >= 0 ? line.slice(0, cut) : line).trim();
    const summary = cut >= 0 ? line.slice(cut + 3).trim() : '';
    if (d.metaType === 'movie') {
      if (!/^\d{4}(\s*·|$)/.test(left)) return null;
      return { show: '', ep: title.replace(/\s*\(\d{4}\)$/, ''), code: left.replace(/\s*·\s*/g, '  '), summary };
    }
    if (d.metaType !== 'episode') return null;
    const m = left.match(/^(?:(S\d+E\d+)\s*[·-]\s*)?(.+?)(?:\s*\((\d{4})\))?$/) || [];
    const code = m[1] || (d.season && d.episode ? `S${d.season}E${d.episode}` : '');
    const ep = (d.metaEp && d.metaEp !== title) ? d.metaEp : m[2];
    if (!ep || ep === title) return null;
    return { show: title, ep, code: [code, m[3]].filter(Boolean).join('  '), summary };
  }

  function decorate() {
    const listings = document.getElementById('guide-listings');
    const top = document.getElementById('top-panel');
    if (!listings || !top || document.getElementById('ws-header')) return;

    const header = document.createElement('div');
    header.id = 'ws-header';
    header.innerHTML = '<div class="brand">T-MANTV<small>TV GUIDE</small></div><div id="ws-clock"></div>';
    listings.insertBefore(header, top);

    // Frame around the live box; #video-panel itself stays the exact picture area.
    const video = document.getElementById('video-panel');
    const frame = document.createElement('div');
    frame.id = 'ws-video-frame';
    frame.className = 'ws-panel';
    top.insertBefore(frame, video);
    frame.appendChild(video);

    // Info panel. Keeps the ids customguide.js fills in (title, channel, time, description).
    const text = document.getElementById('text-panel');
    text.className = 'ws-panel';
    text.innerHTML = `
      <div class="ws-chline">
        <span><span class="ws-net" id="ws-net"></span><span class="ws-chnum" id="ws-chnum"></span></span>
        <span class="ws-label" id="ws-airlabel">NOW PLAYING</span>
      </div>
      <div id="selected-program-title"></div>
      <div id="selected-channel-label" hidden></div>
      <div id="selected-program-time"></div>
      <div id="selected-program-description"></div>
      <div class="ws-vcr" id="ws-vcr"><span id="ws-elapsed"></span><div class="bar"><div class="fill" id="ws-fill"></div></div><span class="rem" id="ws-remaining"></span></div>
      <div class="ws-next" id="ws-next"><span class="ws-label">UP NEXT</span><span class="t" id="ws-next-time"></span><span id="ws-next-title"></span></div>`;

    const status = document.createElement('div');
    status.id = 'ws-status';
    status.innerHTML = '<span id="ws-count"></span><span class="r">T-MANTV</span>';
    listings.appendChild(status);

    const clock = document.getElementById('ws-clock');
    const tick = () => { clock.textContent = clockText(new Date()); };
    tick();
    setInterval(tick, 1000);
    setInterval(updateInfo, 5000);   // keep the progress bar moving
  }

  function selected() {
    const rows = getInteractiveRows();
    const row = rows[interactiveRowIndex];
    const programs = getProgramsForRow(row);
    return { row, programs, program: programs[interactiveProgramIndex], index: interactiveProgramIndex };
  }

  function updateInfo() {
    const { row, programs, program, index } = selected();
    if (!row || !program) return;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    // Split plot: show name where the network name was, episode + yellow code as the title,
    // summary only below (same as the banner). customguide.js filled them first (baseInfo).
    const split = splitPlot(program);
    set('ws-net', (split && split.show) || row.dataset.channelName || '');
    set('ws-chnum', row.dataset.channelNumber ? `CH ${row.dataset.channelNumber}` : '');
    if (split) {
      const t = document.getElementById('selected-program-title');
      t.textContent = split.ep;
      if (split.code) {
        const c = document.createElement('span');
        c.className = 'ws-code';
        c.textContent = split.code;
        t.appendChild(c);
      }
      set('selected-program-description', split.summary);
    }

    const now = Date.now();
    const start = Number(program.dataset.startMs), end = Number(program.dataset.endMs);
    const live = start <= now && now < end;
    set('ws-airlabel', live ? 'NOW PLAYING' : (start > now ? `AT ${timeText(new Date(start))}` : 'EARLIER'));

    const vcr = document.getElementById('ws-vcr');
    vcr.classList.toggle('ws-hidden', !live);
    if (live) {
      set('ws-elapsed', durText(now - start));
      set('ws-remaining', durText(end - now));
      document.getElementById('ws-fill').style.width = `${Math.min(100, 100 * (now - start) / (end - start))}%`;
    }

    const next = programs[index + 1];
    document.getElementById('ws-next').classList.toggle('ws-hidden', !next);
    if (next) {
      set('ws-next-time', timeText(new Date(Number(next.dataset.startMs))));
      set('ws-next-title', next.dataset.title || '');
    }
  }

  // ---- Channel-change info banner (2026-11-02), shown by guide_overlay.py ----
  function bannerEl() {
    let b = document.getElementById('ws-banner');
    if (b) return b;
    b = document.createElement('div');
    b.id = 'ws-banner';
    b.innerHTML = `
      <div class="top">
        <div class="tab"><span class="num" id="wsb-num"></span><span class="net" id="wsb-net"></span></div>
        <span class="show" id="wsb-show"></span>
        <div class="spacer"></div><span class="brand">T-ManTV</span><span class="clock" id="wsb-clock"></span>
      </div>
      <div class="body">
        <div class="title"><span id="wsb-title"></span><span class="code" id="wsb-code"></span></div>
        <div class="when" id="wsb-when"><span class="time" id="wsb-time"></span><span class="bar"><i id="wsb-fill"></i></span><span class="next" id="wsb-next"><b>NEXT</b><span id="wsb-next-title"></span></span></div>
        <div class="desc" id="wsb-desc"></div>
      </div>`;
    document.body.appendChild(b);
    return b;
  }

  // status = FS42 /player/status. Fills the bar from the listings already on the page (the
  // player's own title if the channel isn't in the grid) and returns its rectangle as JSON text.
  window.tmanBanner = function (status) {
    const b = bannerEl();
    // Star4000 has no "·" or long dashes (they show as gaps)
    const clean = v => String(v).replace(/\s*[·•–—]\s*/g, ' - ').replace(/\s+/g, ' ').trim();
    const set = (id, v) => { document.getElementById(id).textContent = clean(v); };
    const hide = (id, off) => document.getElementById(id).classList.toggle('ws-hidden', off);
    const ch = String(status.channel_number ?? '');
    const now = Date.now();
    const row = Array.from(document.querySelectorAll('#grid-scroll-strip .grid-row'))
      .find(r => r.dataset.channelNumber === ch);
    const programs = row ? getProgramsForRow(row) : [];
    const i = programs.findIndex(p => Number(p.dataset.startMs) <= now && now < Number(p.dataset.endMs));
    const prog = i >= 0 ? programs[i] : null, next = i >= 0 ? programs[i + 1] : null;

    set('wsb-num', ch);
    set('wsb-net', (row && row.dataset.channelName) || status.network_name || '');
    set('wsb-clock', timeText(new Date()));
    const split = prog && splitPlot(prog);
    set('wsb-show', (split && split.show) || '');
    set('wsb-title', (split && split.ep) || (prog && prog.dataset.title) || status.title || status.network_name || '');
    set('wsb-code', (split && split.code) || '');
    hide('wsb-when', !prog);
    if (prog) {
      const s = new Date(Number(prog.dataset.startMs)), e = new Date(Number(prog.dataset.endMs));
      const from = timeText(s), to = timeText(e);
      set('wsb-time', `${from.slice(-2) === to.slice(-2) ? from.slice(0, -3) : from} - ${to}`);
      document.getElementById('wsb-fill').style.width = `${Math.min(100, 100 * (now - s) / (e - s))}%`;
    }
    hide('wsb-next', !next);
    if (next) set('wsb-next-title', next.dataset.title || '');
    set('wsb-desc', split ? split.summary : ((prog && prog.dataset.description) || ''));
    document.body.classList.add('ws-banner-on');
    const r = b.getBoundingClientRect();
    return JSON.stringify([r.left, r.top, r.width, r.height]);
  };
  window.tmanBannerHide = function () { document.body.classList.remove('ws-banner-on'); };

  const baseBuildDOM = window.buildGridDOM;
  window.buildGridDOM = function () { baseBuildDOM(); decorate(); };

  const baseHeader = window.updateGridHeader;
  window.updateGridHeader = function (slots) {
    baseHeader(slots);
    const labels = document.querySelectorAll('#grid-header .grid-time-slot');
    slots.forEach((slot, i) => { if (labels[i]) labels[i].textContent = timeText(slot.start); });
  };

  const baseBlock = window.createGridProgramBlock;
  window.createGridProgramBlock = function () {
    const el = baseBlock.apply(this, arguments);
    const meta = arguments[0] && arguments[0].meta;
    if (el && meta) {   // for splitPlot()
      el.dataset.metaType = meta.type || '';
      el.dataset.metaEp = meta.title || '';
      if (meta.season != null) el.dataset.season = meta.season;
      if (meta.episode != null) el.dataset.episode = meta.episode;
    }
    if (el && el.dataset.startMs) {
      const t = document.createElement('span');
      t.className = 'ws-time';
      t.textContent = timeText(new Date(Number(el.dataset.startMs)));
      el.appendChild(t);
    }
    return el;
  };

  const baseGrid = window.buildGrid;
  window.buildGrid = async function () {
    await baseGrid.apply(this, arguments);
    const count = document.querySelectorAll('#grid-scroll-strip .grid-row').length;
    const el = document.getElementById('ws-count');
    if (el) el.textContent = `${count} CHANNELS`;
  };

  const baseInfo = window.updateSelectedProgramInfo;
  window.updateSelectedProgramInfo = function () { baseInfo(); updateInfo(); };
})();
