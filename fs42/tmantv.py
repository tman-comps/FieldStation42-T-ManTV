# T-ManTV additions used by fs42/station_player.py: CRT picture filters,
# Internet Archive .strm stubs, cached direct archive.org links and the
# local index proxy (fs42-mkv-proxy).
import io
import json
import os
import socket

from python_mpv_jsonipc import MPV as _BaseMPV


# --- Picture: mpv.conf overscan shrink and the stub's side-bar crop ---------

def _load_base_vf():
    # Reuse the vf= line from ~/.config/mpv/mpv.conf (per-TV overscan shrink)
    try:
        conf = os.path.expanduser("~/.config/mpv/mpv.conf")
        with open(conf) as f:
            for line in f:
                line = line.strip()
                if line.startswith("vf="):
                    return line[3:].strip().strip('"')
    except OSError:
        pass
    return ""


BASE_VF = _load_base_vf()
CROP = {"vf": ""}  # this file's #crop= from its .strm stub (set in play_file)


class ShrinkMPV(_BaseMPV):
    # Effect filters get the file's crop in front and the mpv.conf shrink appended; clearing restores crop + shrink.
    def __setattr__(self, name, value):
        if name == "vf" and BASE_VF:
            value = ",".join(v for v in (CROP["vf"], value, BASE_VF) if v)
        super().__setattr__(name, value)


# --- Direct archive.org links (runtime/archive_urls.json, from fs42_local/archive_urls.py) ---

URLS_FILE = "runtime/archive_urls.json"
_urls = {"mtime": None, "map": {}}


def direct_url(url):
    # Cached direct archive.org server link for an archive.org/download/ URL, or None
    try:
        m = os.path.getmtime(URLS_FILE)
        if m != _urls["mtime"]:
            with open(URLS_FILE) as f:
                _urls["map"] = json.load(f)
            _urls["mtime"] = m
        e = _urls["map"].get(url)
        return e["url"] if e else None
    except Exception:
        return None


def forget_direct_url(url):
    # A direct link failed: don't use it again until archive_urls.json changes
    _urls["map"].pop(url, None)


# --- .strm stubs (text cached in runtime/archive_stubs.json, so tunes skip the NAS) ---

STUBS_FILE = "runtime/archive_stubs.json"
_stubs = {"mtime": None, "map": {}}


def stub_text(path):
    # Cached text of a .strm stub, or None
    if not str(path).endswith(".strm"):
        return None
    try:
        m = os.path.getmtime(STUBS_FILE)
        if m != _stubs["mtime"]:
            with open(STUBS_FILE) as f:
                _stubs["map"] = json.load(f)
            _stubs["mtime"] = m
        return _stubs["map"].get(path)
    except Exception:
        return None


def open_stub(path):
    # The stub's text from the cache, else from the file itself
    text = stub_text(path)
    if text is not None:
        return io.StringIO(text)
    return open(path)


def read_stub(path):
    # Parse a .strm stub:
    #   line "http..."   -> target "lavf://<url>" (lavf:// skips mpv's yt-dlp hook, which added ~11 s per load)
    #   line "/..."      -> target is that NAS file (local tapes)
    #   #start=N         -> skip the first N seconds
    #   #duration=N      -> length in seconds (after the #start trim)
    #   #crop=w:h:x:y    -> mpv crop for side bars
    #   #aid=N           -> audio track
    # target stays None when the stub has no URL/path line.
    stub = {"target": None, "start": 0.0, "duration": None, "crop": "", "aid": "auto"}
    with open_stub(path) as f:
        for line in f:
            if line.startswith("http"):
                stub["target"] = "lavf://" + line.strip()
            elif line.startswith("/"):
                stub["target"] = line.strip()
            elif line.startswith("#start="):
                stub["start"] = float(line.split("=", 1)[1])
            elif line.startswith("#duration="):
                try:
                    stub["duration"] = float(line.split("=", 1)[1])
                except ValueError:
                    pass
            elif line.startswith("#crop="):
                stub["crop"] = "crop=" + line.split("=", 1)[1].strip()
            elif line.startswith("#aid="):
                stub["aid"] = line.split("=", 1)[1].strip()
    return stub


# --- Local index proxy (fs42-mkv-proxy): http://127.0.0.1:8742/<item>/<file> ---

PROXY = "http://127.0.0.1:8742/"


def proxy_up():
    # Is the local index proxy accepting connections?
    try:
        socket.create_connection(("127.0.0.1", 8742), timeout=0.3).close()
        return True
    except OSError:
        return False


def proxy_to_archive(file_path):
    # lavf:// proxy URL -> lavf:// archive.org URL (cached direct link if we have one)
    ia = "https://archive.org/download/" + file_path[len("lavf://" + PROXY):]
    return "lavf://" + (direct_url(ia) or ia)


def archive_url(file_path):
    # lavf:// proxy URL -> plain lavf:// archive.org redirect URL
    return "lavf://https://archive.org/download/" + file_path[len("lavf://" + PROXY):]
