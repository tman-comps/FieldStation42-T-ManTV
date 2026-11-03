# Looks up the direct archive.org server link (dnNNN.*.archive.org) for every .strm stub
# and saves them to runtime/archive_urls.json. The player uses these instead of
# archive.org/download/..., whose redirect costs ~2 s and gets paid again on seeks.
# Usage: archive_urls.py [max_age_hours]   (default 48; 0 = re-check everything)
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

os.chdir(os.path.expanduser("~/FieldStation42"))
CACHE = "runtime/archive_urls.json"
STUBS = "runtime/archive_stubs.json"
MAX_AGE = float(sys.argv[1] if len(sys.argv) > 1 else 48) * 3600


def stub_urls():
    # catalog/<station>/<tag>/<link>: only walk the links into "(Archive)" folders.
    # The stub text is saved too (runtime/archive_stubs.json, keyed by catalog path), so the
    # player doesn't have to read stubs off the NAS while the last channel's reads clog it.
    urls = set()
    for station in os.listdir("catalog"):
        for tag in os.listdir(f"catalog/{station}") if os.path.isdir(f"catalog/{station}") else []:
            tdir = f"catalog/{station}/{tag}"
            for entry in os.listdir(tdir) if os.path.isdir(tdir) else []:
                path = f"{tdir}/{entry}"
                if "(Archive)" not in os.path.realpath(path):
                    continue
                for root, _, files in os.walk(path, followlinks=True):
                    for name in files:
                        if name.endswith(".strm"):
                            with open(os.path.join(root, name)) as f:
                                text = f.read()
                            stubs[os.path.join(root, name)] = text
                            for line in text.splitlines():
                                if line.startswith("http"):
                                    urls.add(line.strip())
                                    break
    return urls


def save(path, data):
    with open(path + ".tmp", "w") as f:
        json.dump(data, f, indent=0)
    os.replace(path + ".tmp", path)


def resolve(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            final = r.geturl()
            if r.status == 200 and final != url:
                return url, final
    except Exception as e:
        print(f"FAIL {url}: {e}")
    return url, None


try:
    with open(CACHE) as f:
        cache = json.load(f)
except (OSError, ValueError):
    cache = {}

stubs = {}
urls = stub_urls()
save(STUBS, stubs)
now = time.time()
todo = [u for u in urls if now - cache.get(u, {}).get("ts", 0) > MAX_AGE]
print(f"{time.strftime('%F %T')} {len(urls)} stubs, {len(todo)} to check")
ok = 0
with ThreadPoolExecutor(8) as pool:
    for url, final in pool.map(resolve, todo):
        if final:
            cache[url] = {"url": final, "ts": now}
            ok += 1
        else:
            cache.pop(url, None)  # player falls back to the redirect link
for u in [u for u in cache if u not in urls]:
    del cache[u]

save(CACHE, cache)
print(f"{time.strftime('%F %T')} done: {ok} resolved, {len(todo) - ok} failed, {len(cache)} cached")
