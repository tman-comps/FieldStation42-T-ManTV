// Server: Express proxy and data enrichment
import express      from 'express';
import fetch        from 'node-fetch';
import pMap         from 'p-map';
import dotenv       from 'dotenv';
import { LRUCache } from 'lru-cache';
import path         from 'path';
import fs           from 'fs';

dotenv.config();

const app      = express();
const TV_BASE  = process.env.FS42_API_URL;
const TMDB_KEY = process.env.TMDB_KEY;
if (!TV_BASE)  throw new Error('Set FS42_API_URL in .env');
// T-ManTV: TMDb is optional; plots come from our NFOs via FS42 meta
const TMDB_ON = Boolean(TMDB_KEY);

// T-ManTV: build the guide title from FS42 meta in the formats main.js expects
// ("Show - S01E02" for episodes, "Title (YYYY)" for movies)
const pad2 = n => String(parseInt(n, 10)).padStart(2, '0');
function metaTitle(blk) {
  const m = blk.meta;
  if (!m || !m.title) return null;
  if (m.type === 'episode' && m.show_title && m.season && m.episode)
    return `${m.show_title} - S${pad2(m.season)}E${pad2(m.episode)}`;
  if (m.type === 'music' && m.artist) return `${m.artist} – ${m.title}`;
  return m.title.trim();
}

// Cache: in-memory (up to 1000 entries, 1-hour TTL)
const tmdbCache = new LRUCache({ max: 1000, ttl: 1000 * 60 * 60 });
let lastCall = 0;

// T-ManTV: FS42 answers ~1 s per channel (summary ~10 s), so cache its replies
// for 15 min and pre-warm today's guide every 10 min so the page opens fast
const fs42Cache = new LRUCache({ max: 200, ttl: 1000 * 60 * 15 });
async function fs42Json(p, fresh = false) {
  if (!fresh && fs42Cache.has(p)) return fs42Cache.get(p);
  const j = await fetch(`${TV_BASE}${p}`).then(r => r.json());
  fs42Cache.set(p, j);
  return j;
}
const fmtLocal = dt => {
  const p = n => String(n).padStart(2, '0');
  return `${dt.getFullYear()}-${p(dt.getMonth()+1)}-${p(dt.getDate())}T${p(dt.getHours())}:${p(dt.getMinutes())}:${p(dt.getSeconds())}`;
};
async function prewarm() {
  // Same window main.js asks for: 06:00 today (yesterday before 6am) to 07:00 the next day
  const d = new Date();
  if (d.getHours() < 6) d.setDate(d.getDate() - 1);
  const s = new Date(d); s.setHours(6,0,0,0);
  const e = new Date(d); e.setDate(e.getDate() + 1); e.setHours(7,0,0,0);
  const q = `?start=${encodeURIComponent(fmtLocal(s))}&end=${encodeURIComponent(fmtLocal(e))}&include_meta=true`;
  try {
    await fs42Json('/summary', true);
    const st = await fs42Json('/summary/stations', true);
    for (const net of st.network_names || [])
      await fs42Json(`/schedules/${encodeURIComponent(net)}${q}`, true);
  } catch (e) {
    console.error('Prewarm error', e.message);
  }
}
setTimeout(prewarm, 5000);
setInterval(prewarm, 1000 * 60 * 10);

// Route 1: Proxy channel list
app.get('/api/stations', async (req, res) => {
  try {
    const j = await fs42Json('/summary/stations');
    res.json(j.network_names);
  } catch (e) {
    console.error('Stations fetch error', e);
    res.status(502).json([]);
  }
});

// Route 2: Proxy schedule blocks with TMDb ID enrichment
app.get('/api/schedules/:net', async (req, res) => {
  const net   = encodeURIComponent(req.params.net);
  const { start, end } = req.query;
  const q     = `?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&include_meta=true`;
  try {
    const j = await fs42Json(`/schedules/${net}${q}`);
    const blocks = (j.schedule_blocks || []).map(blk => {
      const t = metaTitle(blk);
      const out = { ...blk, plot: (blk.meta?.plot || '').trim() };
      if (t) { out.title = t; out.content = { title: t }; }
      delete out.meta; delete out.reel_blocks;
      return out;
    });
    if (!TMDB_ON) return res.json(blocks.map(b => ({ ...b, tmdb_id: null, series_id: null, starRating: null })));

    // Enrich each block with tmdb_id (movies) or series_id (TV)
    const enriched = await pMap(blocks, async blk => {
      let raw = (blk.content?.title || blk.title || '').trim();
      const cutMatch = raw.match(/^(.*S\d{2}E\d{2})/i);
      if (cutMatch) raw = cutMatch[1];
      let tmdb_id = null, series_id = null;

      // TV episode?
      const epMatch = raw.match(/^(.*?)\s[-–]\s*S(\d+?)E(\d+?)(?:[-–]E\d+)?$/i);
      if (epMatch) {
        const seriesName = epMatch[1].trim();
        const searchUrl = new URL('https://api.themoviedb.org/3/search/tv');
        searchUrl.searchParams.set('api_key', TMDB_KEY);
        searchUrl.searchParams.set('query', seriesName);
        const searchJ = await (await fetch(searchUrl)).json();
        if (searchJ.results?.length) {
          series_id = searchJ.results[0].id;
        }
        return { ...blk, tmdb_id, series_id, starRating: null };
      } else {
        // Movie block
        const mvMatch = raw.match(/^(.*?)\s*\((\d{4})\)\s*$/);
        if (mvMatch) {
          const movieName = mvMatch[1].trim();
          const movieYear = mvMatch[2];
          const mUrl = new URL('https://api.themoviedb.org/3/search/movie');
          mUrl.searchParams.set('api_key', TMDB_KEY);
          mUrl.searchParams.set('query', movieName);
          mUrl.searchParams.set('year', movieYear);
          const mJ = await (await fetch(mUrl)).json();
          if (mJ.results?.length) {
            tmdb_id = mJ.results[0].id;
            if (tmdb_id) {
              const detailsUrl = new URL(`https://api.themoviedb.org/3/movie/${tmdb_id}`);
              detailsUrl.searchParams.set('api_key', TMDB_KEY);
              const detailsJ = await (await fetch(detailsUrl)).json();
              const starRating = detailsJ.vote_average || 0;
              // Attach rating
              return { ...blk, tmdb_id, series_id, starRating };
            }
          }
        }
      }

      return { ...blk, tmdb_id, series_id, starRating: null };
    }, { concurrency: 4 });

    res.json(enriched);
  } catch (e) {
    console.error('Schedule fetch error for', net, e);
    res.status(502).json([]);
  }
});

// Route 3: Proxy summary of all stations
app.get('/api/summary', async (req, res) => {
  try {
    const j = await fs42Json('/summary');
    res.json(j);
  } catch (e) {
    console.error('Summary fetch error', e);
    res.status(502).json({ summary_data: [] });
  }
});

// Route 4: TMDb summary, certification, director, and image lookup
app.get('/api/tmdb-summary', async (req, res) => {
  const title = (req.query.title || '').trim();
  if (!title || !TMDB_ON) return res.json({ overview: '', certification: '', image: '' });
  if (tmdbCache.has(title)) {
    return res.json(tmdbCache.get(title));
  }

  // Throttle to 4/sec
  const now = Date.now();
  const wait = Math.max(0, 250 - (now - lastCall));
  if (wait) await new Promise(r => setTimeout(r, wait));
  lastCall = Date.now();

  let overview = '', certification = '', image = '';
  let series_id = null;
  try {
    const epMatch = title.match(/^(.*?)\s[-–]\s*S(\d+?)E(\d+?)(?:[-–]E\d+)?$/i);
    if (epMatch) {
      // TV episode lookup
      const [, seriesName, seasonStr, episodeStr] = epMatch;
      const season = parseInt(seasonStr, 10), episode = parseInt(episodeStr, 10);
      const searchUrl = new URL('https://api.themoviedb.org/3/search/tv');
      searchUrl.searchParams.set('api_key', TMDB_KEY);
      searchUrl.searchParams.set('query', seriesName);
      const searchJ = await (await fetch(searchUrl)).json();
      if (searchJ.results?.length) {
        const seriesId = searchJ.results[0].id;
        series_id = seriesId;
        const epUrl = `https://api.themoviedb.org/3/tv/${seriesId}`
                    + `/season/${season}/episode/${episode}`
                    + `?api_key=${TMDB_KEY}`;
        const epJ = await (await fetch(epUrl)).json();
        overview = epJ.overview || '';
        image = epJ.still_path || '';
        const tmdb_id = seriesId;
        const out = { overview, certification, tmdb_id, image, image_path: image, series_id };
        tmdbCache.set(title, out);
        return res.json(out);
      }
    } else {
      // Movie lookup
      const mvMatch   = title.match(/^(.*?)\s*\((\d{4})\)\s*$/);
      const movieName = mvMatch ? mvMatch[1].trim() : title;
      const movieYear = mvMatch ? mvMatch[2] : '';
      const mUrl = new URL('https://api.themoviedb.org/3/search/movie');
      mUrl.searchParams.set('api_key', TMDB_KEY);
      mUrl.searchParams.set('query', movieName);
      if (movieYear) mUrl.searchParams.set('year', movieYear);
      const mJ = await (await fetch(mUrl)).json();
      let director = '';
      if (mJ.results?.length) {
        const m = mJ.results[0];
        // Fetch full movie details to get runtime
        const detailsUrl = `https://api.themoviedb.org/3/movie/${m.id}?api_key=${TMDB_KEY}`;
        const detailsJ = await (await fetch(detailsUrl)).json();
        const runtime = detailsJ.runtime || 0;
        overview = m.overview || '';
        image = m.backdrop_path || m.poster_path || '';
        const tmdb_id = m.id;
        const rdUrl = `https://api.themoviedb.org/3/movie/${m.id}/release_dates?api_key=${TMDB_KEY}`;
        const rdJ = await (await fetch(rdUrl)).json();
        const usEntry = (rdJ.results || []).find(r => r.iso_3166_1 === 'US');
        if (usEntry && Array.isArray(usEntry.release_dates)) {
          const cd = usEntry.release_dates.find(d => d.certification);
          certification = cd?.certification || '';
        }
        // Director lookup
        const creditsUrl = `https://api.themoviedb.org/3/movie/${m.id}/credits?api_key=${TMDB_KEY}`;
        const creditsJ   = await (await fetch(creditsUrl)).json();
        const directorEntry = (creditsJ.crew || [])
          .find(c => c.job === 'Director');
        director = directorEntry ? directorEntry.name : '';
        const out = { overview, certification, director, tmdb_id, image, image_path: image, runtime, series_id: null };
        tmdbCache.set(title, out);
        return res.json(out);
      }
    }
  } catch (err) {
    console.error('TMDb lookup error for', title, err);
  }

  const out = { overview, certification, image: '', runtime: 0, series_id: null };
  tmdbCache.set(title, out);
  res.json(out);
});

// Route 5: Proxy “zap to channel” requests
app.get('/api/player/channels/:chanNum', async (req, res) => {
  const { chanNum } = req.params;
  try {
    const response = await fetch(`${TV_BASE}/player/channels/${chanNum}`);
    res.sendStatus(response.status);
  } catch (err) {
    console.error('Channel-zap proxy error for', chanNum, err);
    res.sendStatus(502);
  }
});

// Route: Inject IGNORE_CHANS into window for client-side use
app.get('/', (req, res) => {
  const indexPath = path.join(process.cwd(), 'public', 'index.html');
  let html = fs.readFileSync(indexPath, 'utf8');
  const script = `<script>window.IGNORE_CHANS = ${JSON.stringify(process.env.IGNORE_CHANS || '')}; window.TMDB_ON = ${TMDB_ON};</script>`;
  html = html.replace('</head>', `${script}</head>`);
  res.send(html);
});

// Static: Serve frontend
app.use(express.static(path.join(process.cwd(), 'public')));

// Startup
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`📺 TV-guide proxy listening at http://localhost:${PORT}/`);
});
