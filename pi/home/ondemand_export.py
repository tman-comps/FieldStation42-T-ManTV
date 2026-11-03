#!/usr/bin/env python3
"""Export the FS42 catalog as On Demand menu data (shows > seasons > episodes, movies).

Walks file names under ~/FieldStation42/catalog, then fills runtimes, plots, titles and
season/episode numbers from FS42's own database (runtime/fs42_fluid.db): catalog_entries
has each file's duration, and file_meta.meta holds the NFO FS42 already parsed. So no
NFO reads or ffprobe on the NAS (slow), and .strm stubs get runtimes too.

Usage: ondemand_export.py [out.json] [--paths]
  --paths  also store each episode's/movie's catalog path (the real menu needs it to play;
           the mockup leaves it out to stay small)
Episode rows: [ep, title, minutes, plot, aired(, path)]
"""
import glob, json, os, re, sqlite3, sys
from collections import Counter

FS42 = os.path.expanduser("~/FieldStation42")
CAT = os.path.join(FS42, "catalog")
args = [a for a in sys.argv[1:] if not a.startswith("--")]
WITH_PATHS = "--paths" in sys.argv
OUT = args[0] if args else os.path.expanduser("~/ondemand_catalog.json")
VIDEO = {".mkv", ".mp4", ".avi", ".m4v", ".strm", ".webm", ".mpg", ".mpeg", ".mov", ".wmv", ".ts"}
SKIP_TAGS = {"bump", "bumps", "commercial", "commercials", "logos", "logo", "sign_off", "sign_on", "offair"}
SKIP_STATIONS = {"news", "eighties_music", "guide", "weather"}   # catalog folders left out of the menu
KIDS_STATIONS = {"disney", "nick", "pbs_kids", "game_shows"}   # listed under Kids; every other channel goes under TV Shows
SHORT_NAMES = {"The Disney Channel": "Disney", "The Simpsons": "Simpsons"}   # menu labels

# Channels come from FS42's own confs (2026-11-01), so new or renumbered channels show up in the
# menu on the next export. A station whose name starts with "Movies " is a movie decade.
STATIONS = {}
for fn in sorted(glob.glob(os.path.join(FS42, "confs", "*.json"))):
    try:
        c = json.load(open(fn)).get("station_conf") or {}
    except (OSError, ValueError):
        continue
    if not c.get("content_dir") or c.get("hidden"):
        continue
    folder = os.path.basename(c["content_dir"].rstrip("/"))
    name = c.get("network_name") or folder
    STATIONS[folder] = {"key": folder, "name": SHORT_NAMES.get(name, name), "ch": c.get("channel_number"),
                        "kids": folder in KIDS_STATIONS,
                        "dec": name[len("Movies "):] if name.startswith("Movies ") else None}
# T-Man Box Office / T-Max (2026-11-02): movie channels not split by decade; each movie goes under its own decade
YEAR_DEC_STATIONS = {"tbo", "tmax"}
for _k in YEAR_DEC_STATIONS & set(STATIONS):
    STATIONS[_k]["dec"] = "by year"


def year_dec(y):
    if not y or y < 1970:
        return "Pre-70s"
    return "2000s" if y >= 2000 else f"{str(y)[2]}0s"

SE = re.compile(r"\bS(\d{1,2})\s*E(\d{1,3})\b", re.I)
PROD = re.compile(r"\(([A-Z]{1,4})-(\d)(\d{2})\)")
SEASON_DIR = re.compile(r"season\s*(\d+)", re.I)
GENERIC = re.compile(r"^(season\s*\d+,?\s*)?episode\s*\d+$", re.I)   # "Season 1, Episode 1"
DATE_LINE = re.compile(r"^\d{4}(?:[-.][\dx]{2}){0,2}\b(?:\s*-\s*.*)?$", re.I)  # "1993-05-xx - KPDX-49 FOX"
DATE_ONLY = re.compile(r"^\[?\d{4}-\d{2}-\d{2}\w?\]?$")

# path (relative to ~/FieldStation42) -> (duration seconds, parsed NFO dict)
db = sqlite3.connect(os.path.join(FS42, "runtime", "fs42_fluid.db"))
META = {}
for path, dur, meta in db.execute(
        "select e.path, e.duration, f.meta from catalog_entries e left join file_meta f on f.path = e.realpath"):
    try:
        m = json.loads(meta) if meta else {}
    except ValueError:
        m = {}
    META[path] = (dur, m)
missing = 0


def lookup(root, f):
    global missing
    rel = os.path.relpath(os.path.join(root, f), FS42)
    hit = META.get(rel)
    if not hit:
        missing += 1
        return None, {}
    return (round(hit[0] / 60) or 1) if hit[0] else None, hit[1]


def videos(top):
    for root, dirs, files in os.walk(top, followlinks=True):
        dirs.sort()
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in VIDEO:
                yield root, f


def clean_title(rest):
    rest = re.sub(r"\s*\d{9,}$", "", rest)                 # archive id tail
    rest = re.sub(r"\s*\[[^\]]*\]", "", rest)              # [tags]
    rest = re.split(r"\s+-\s+(?:[A-Z]{3,4}\b|\w+\s+\d+\s+[A-Z]{3})", rest)[0]  # " - KPDX 49 FOX ..." station tail
    rest = re.sub(r"\s*\((?:19|20)\d\d\)\s*$", "", rest)   # trailing (1991)
    rest = re.sub(r"\s*\((rerun[^)]*)\)", "", rest)
    rest = re.sub(r"\s*\([a-z0-9]+(?:-[a-z0-9]+){2,}\)$", "", rest)  # (archive-org-identifier)
    return rest.strip(" -_.") or "Untitled"


def clean_plot(pl, *titles):
    """NFO plots are often just 'S1E1 · Title (1989) – real plot' or only the title + air date."""
    out, aired = [], None
    for line in (pl or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if DATE_LINE.match(line):
            aired = aired or line
            continue
        line = re.sub(r"^S\d+\s*E\d+\s*[·:\-–]\s*", "", line, flags=re.I)
        for t in titles:
            if t and line.lower().startswith(t.lower()):
                line = line[len(t):]
                break
        line = re.sub(r"^\s*\((?:rerun[^)]*|full|(?:19|20)\d\d)\)", "", line).lstrip(" -–·:,.")
        out.append(line)
    text = " ".join(out).strip()
    if len(text) < 30 or any(t and text.lower() == t.lower() for t in titles):
        text = ""
    return text, aired


TAPE_DATE = re.compile(r"^(\d{4})(?:[ .-](\d{2}))?(?:[ .-](\d{2}))?\b\s*-?\s*")


def tidy(t, show, dated=True):
    """Display clean-up: 'Show - ' prefixes, dotted scene names, leading tape dates."""
    aired = None
    for p in (show + " - ", show.replace(":", "") + " - "):
        if t.lower().startswith(p.lower()):
            t = t[len(p):]
    if " " not in t and "." in t:   # Flight.of.the.Condor.Ice.Wind.and.Fire.1982.VHSRip
        t = re.sub(r"\.(?:19|20)\d\d\..*$", "", t).replace(".", " ")
    m = TAPE_DATE.match(t)
    if dated and m and len(t) > m.end() + 3:   # "1990 11 16 The Disney Afternoon ..." -> aired 1990-11-16
        aired = "-".join(g for g in m.groups() if g)
        t = t[m.end():]
        t = re.sub(r"^(?:The\s+)?Disney (?:Channel|Afternoon)\s*-?\s*", "", t) or t
    t = re.sub(r"\s*\(\s*[^)]*$", "", t)            # unbalanced "( FOX W" tail
    t = re.sub(r"^\(\s*(.*?)\s*\)$", r"\1", t)       # "( Aloha From Hawaii ... )"
    return t.strip(" -") or "Untitled", aired


def episode(root, f, show_dir, meta, show):
    stem = os.path.splitext(f)[0]
    m = SE.search(stem)
    p = PROD.search(stem)
    if m:
        s, e, t = int(m.group(1)), int(m.group(2)), clean_title(stem[m.end():].lstrip(" -"))
    elif p:
        s, e, t = int(p.group(2)), int(p.group(3)), clean_title(stem[p.end():])
    else:
        sd = SEASON_DIR.search(os.path.relpath(root, show_dir))
        n = re.search(r"\bEpisode (\d+)\b", stem)     # "Sesame Street - Episode 10 (1969)"
        s, e = (int(sd.group(1)) if sd else 1), (int(n.group(1)) if n else None)
        t = clean_title(re.sub(r"^\[?\d{4}-\d{2}-\d{2}\w?\]?\s*", "", stem))
    if meta.get("type") == "episode":
        mt = (meta.get("title") or "").strip()
        if mt and mt != meta.get("show_title") and not GENERIC.match(mt):
            t = mt
        try:
            if meta.get("season") is not None and meta.get("episode") is not None:
                s, e = int(meta["season"]), int(meta["episode"])
        except (TypeError, ValueError):
            pass
    t, aired = tidy(t, show, dated=e is None)   # only undated tapes start with a date
    if GENERIC.match(t) or DATE_ONLY.match(t) or t == "Untitled":
        t = f"Episode {e}" if e is not None else t
    return s, e, t, aired


def pretty(tag):
    return " ".join(w.capitalize() for w in tag.replace("_", " ").split())


def movie(f, dec):
    stem = os.path.splitext(f)[0]
    aired = None
    m = re.match(r"^\[([^\]]+)\]\s*", stem)
    if m:
        aired, stem = m.group(1), stem[m.end():]
    tags = re.findall(r"\[([^\]]+)\]", stem)
    head = re.sub(r"\s*\[[^\]]*\]", "", stem).strip()
    y = re.search(r"\((\d{4})(?:[^)]*)\)", head)
    year = int(y.group(1)) if y else None
    title = head[:y.start()].strip() if y else head
    return {"t": title, "y": year, "dec": dec, "aired": aired, "tags": tags[:2]}


shows, movies, seen_movies = [], [], set()
for station in sorted(os.listdir(CAT)):
    sp = os.path.join(CAT, station)
    if station in SKIP_STATIONS or station not in STATIONS or not os.path.isdir(sp):
        continue
    for tag in sorted(os.listdir(sp)):
        if tag in SKIP_TAGS:
            continue
        tp = os.path.join(sp, tag)
        if STATIONS[station]["dec"]:
            for root, f in videos(tp):
                mv = movie(f, STATIONS[station]["dec"])
                if station in YEAR_DEC_STATIONS:
                    mv["dec"] = year_dec(mv["y"])
                key = (mv["t"].lower(), mv["y"])
                if key in seen_movies:
                    continue
                seen_movies.add(key)
                mins, meta = lookup(root, f)
                plot, _ = clean_plot(meta.get("plot"), mv["t"], meta.get("title"))
                mv.update(min=mins, plot=plot)
                if WITH_PATHS:
                    mv["path"] = os.path.relpath(os.path.join(root, f), FS42)
                movies.append(mv)
            continue
        # a tag folder holds either one show folder (named after the show) or loose files
        subs = [d for d in sorted(os.listdir(tp)) if os.path.isdir(os.path.join(tp, d))] if os.path.isdir(tp) else []
        units = [(d, os.path.join(tp, d)) for d in subs] if len(subs) >= 1 and not any(SEASON_DIR.search(d) for d in subs) else [(pretty(tag), tp)]
        for name, path in units:
            eps, seen, show_titles, hits = {}, set(), Counter(), 0
            for root, f in videos(path):
                mins, meta = lookup(root, f)
                hits += mins is not None
                s, e, t, tape_aired = episode(root, f, path, meta, name)
                k = (s, e, t)
                if k in seen:
                    continue
                seen.add(k)
                if meta.get("show_title"):
                    show_titles[meta["show_title"]] += 1
                plot, aired = clean_plot(meta.get("plot"), t, meta.get("title"))
                row = [e, t, mins, plot, meta.get("aired") or tape_aired or aired]
                if WITH_PATHS:
                    row.append(os.path.relpath(os.path.join(root, f), FS42))
                eps.setdefault(s, []).append(row)
            if not eps or not hits:   # not in FS42's catalog (e.g. the old combined Marvel folder)
                continue
            seasons = []
            for s in sorted(eps):
                lst = sorted(eps[s], key=lambda x: (x[0] is None, x[0] or 0))
                seasons.append({"n": s, "eps": lst})
            # folder names like dates or "Tapes" get the NFO show title when one dominates
            nfo_name = show_titles.most_common(1)[0][0] if show_titles else None
            years = sorted(int(r[4][:4]) for x in seasons for r in x["eps"] if r[4] and r[4][:4].isdigit())
            yrs = (str(years[0]) if years[0] == years[-1] else f"{years[0]}–{years[-1]}") if years else None
            shows.append({"t": name, "nfo": nfo_name, "yrs": yrs, "station": station, "tag": tag, "seasons": seasons})

used = sorted((st for k, st in STATIONS.items() if k not in SKIP_STATIONS), key=lambda st: st["ch"] or 0)
json.dump({"stations": used, "shows": shows, "movies": movies}, open(OUT, "w"), separators=(",", ":"))
all_eps = [r for s in shows for x in s["seasons"] for r in x["eps"]]
print(f"shows={len(shows)} episodes={len(all_eps)} movies={len(movies)} "
      f"ep_runtime={sum(1 for r in all_eps if r[2])} ep_plot={sum(1 for r in all_eps if r[3])} "
      f"movie_runtime={sum(1 for m in movies if m['min'])} movie_plot={sum(1 for m in movies if m['plot'])} "
      f"not_in_db={missing}")
