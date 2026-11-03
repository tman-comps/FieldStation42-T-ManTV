# Re-applies local FieldStation42 changes. Safe to run any number of times.
import os
os.chdir(os.path.expanduser("~/FieldStation42"))

SHRINK = '''from python_mpv_jsonipc import MPV as _BaseMPV


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


_BASE_VF = _load_base_vf()
_FS42_CROP = {"vf": ""}  # this file's #crop= from its .strm stub (set in play_file)


class _FS42ShrinkMPV(_BaseMPV):
    # Effect filters get the file's crop in front and the mpv.conf shrink appended; clearing restores crop + shrink.
    def __setattr__(self, name, value):
        if name == "vf" and _BASE_VF:
            value = ",".join(v for v in (_FS42_CROP["vf"], value, _BASE_VF) if v)
        super().__setattr__(name, value)


MPV = _FS42ShrinkMPV
'''

OSD_PLAY = '''
                # FS42 local: channel number on screen after a channel change (mpv OSD)
                if getattr(self, "_fs42_osd_pending", False) and self.station_config:
                    self._fs42_osd_pending = False
                    try:
                        sc = self.station_config
                        self.mpv.command("show-text", f"{sc['channel_number']}", 2500)
                    except Exception as e:
                        self._l.warning(f"Could not show channel OSD: {e}")
'''

OSD_PRESS = '''            player._fs42_osd_pending = True
            try:  # _fs42_osd_now: show the number right away, before the new channel loads
                player.mpv.command("show-text", f"{channel_conf['channel_number']}", 5000)
            except Exception:
                pass
'''

SEEK = ("                if not is_stream and offset_seconds is not None and offset_seconds > 0:\n"
        "                    self._seek_with_verify(file_path, offset_seconds, timeout_seconds)\n")

# FS42 local: fold the seek into the initial load so mpv never renders a pre-seek
# frame (this was the cause of the single-frame flash on channel change)
PLAY_STOCK = "                self.mpv.play(file_path)\n"

PLAY_ATLOAD = ('                self.mpv.hr_seek = "no"  # keyframe seeks only -- exact seeks are what made channel changes freeze\n'
               '                if not is_stream and offset_seconds is not None and offset_seconds > 0:\n'
               '                    # Seek as part of the initial load so mpv never renders a pre-seek frame\n'
               '                    # (this is what caused the single-frame flash on channel change)\n'
               '                    self.mpv.command("loadfile", file_path, "replace", f"start={offset_seconds}")\n'
               '                else:\n'
               '                    self.mpv.play(file_path)\n')

# FS42 local: the old post-load seek becomes a verify-only fallback (rarely used
# now that the seek happens at load time above)
SEEK_ATLOAD = ('                if not is_stream and offset_seconds is not None and offset_seconds > 0:\n'
               '                    pos = None\n'
               '                    try:\n'
               '                        pos = self.mpv.time_pos\n'
               '                    except Exception:\n'
               '                        pos = None\n'
               '                    if pos is None or abs(pos - offset_seconds) > 20.0:\n'
               '                        self._l.warning(f"Landed at {pos} instead of {offset_seconds} on {file_path}, correcting")\n'
               '                        self._seek_with_verify(file_path, offset_seconds, timeout_seconds)\n')

WEB_MUTE = '''                try:  # FS42 local: silence this page right away so its audio can't linger
                    self.window.browser.page().setAudioMuted(True)
                    self.window.browser.page().runJavaScript("document.querySelectorAll('video,audio').forEach(function(m){try{m.pause();m.removeAttribute('src');m.load();}catch(e){}});")
                except Exception:
                    pass
'''

KILL_WEB = '''        import subprocess as _fs42_sp  # FS42 local: clear leftover web audio from the last web channel
        _fs42_sp.run(["pkill", "-9", "-f", "QtWebEngineProcess"], check=False)
'''

KILL_WEB_AFTER_JOIN = '''                    import subprocess as _fs42_sp  # FS42 local: clear leftover web audio
                    _fs42_sp.run(["pkill", "-9", "-f", "QtWebEngineProcess"], check=False)
'''

LOGO_FADE = '''        # FS42 local: T-ManTV logo fade in/out (0.5s at each end)
        _fs42_t = self.time_since_change
        self._fs42_fade = min(1.0, max(0.0, _fs42_t / 0.5))
        if not permanent and not self.config.always_show:
            self._fs42_fade = min(self._fs42_fade, max(0.0, (display_time - _fs42_t) / 0.5))
'''

LOGO_FADE_ALPHA = '''        glColor4f(1.0, 1.0, 1.0, alpha * getattr(self, "_fs42_fade", 1.0))  # FS42 local: logo fade
'''

# FS42 local: Internet Archive streaming (TechTV). A .strm stub is a tiny text file:
# line 1 the archive.org URL, then #duration=<s> and optional #start=<s> (trim)
STRM_FORMATS_STOCK = '    VIDEO_FORMATS = ["mp4", "mpg", "mpeg", "avi", "mov", "mkv", "ts", "m4v", "webm", "wmv"]\n'
STRM_FORMATS = ('    VIDEO_FORMATS = ["mp4", "mpg", "mpeg", "avi", "mov", "mkv", "ts", "m4v", "webm", "wmv",\n'
                '                     "strm"]  # FS42 local: Archive stream stubs\n')

STRM_DURATION_ANCHOR = '        """Returns (duration, error_hint). duration is -1 on failure; error_hint is a human-readable cause or None."""\n'
STRM_DURATION = '''        if str(file_name).endswith(".strm"):  # FS42 local: stub carries its own duration, no network needed
            try:
                with open(file_name) as f:
                    for line in f:
                        if line.startswith("#duration="):
                            return float(line.split("=", 1)[1]), None
            except Exception as e:
                return -1, f"could not read stream stub: {e}"
            return -1, "stream stub has no #duration= line"
'''

STRM_PLAY_ANCHOR = '                self._l.info(f"playing {file_path}")\n'
STRM_PLAY = '''                if file_path.endswith(".strm"):  # FS42 local: Archive stream stub -> its URL (+ trim start)
                    _fs42_start = 0.0
                    with open(file_path) as _f:
                        for _line in _f:
                            if _line.startswith("http"):
                                # lavf:// skips mpv's yt-dlp hook (it added ~11 s per load)
                                file_path = "lavf://" + _line.strip()
                            elif _line.startswith("#start="):
                                _fs42_start = float(_line.split("=", 1)[1])
                    offset_seconds = (offset_seconds or 0) + _fs42_start
''' + STRM_PLAY_ANCHOR

# FS42 local: a stub's line 1 may also be a NAS file path (starts with "/"), so unencoded local tapes
# (1994 WOC tapes, Tristan OK 2026-11-03) get the stub's #crop=, #start= and the live volume leveling too.
# Kept as an "upgrade" so it lands inside STRM_PLAY's loop (after it on a stock install).
STRM_LOCAL_OLD = ('                                file_path = "lavf://" + _line.strip()\n'
                  '                            elif _line.startswith("#start="):\n')
STRM_LOCAL = ('                                file_path = "lavf://" + _line.strip()\n'
              '                            elif _line.startswith("/"):  # FS42 local: stub pointing at a NAS file\n'
              '                                file_path = _line.strip()\n'
              '                            elif _line.startswith("#start="):\n')

STRM_DOWN_STOCK = ('                    if is_stream:\n'
                   '                        self._l.warning(f"Stream unavailable, activating fallback: {entry.path}")\n')
STRM_DOWN = ('                    if is_stream or entry.path.endswith(".strm"):  # FS42 local: Archive down -> TECHNICAL DIFFICULTIES\n'
             '                        self._l.warning(f"Stream unavailable, activating fallback: {entry.path}")\n')

STRM_INPUT_STOCK = ('                        if is_stream:\n'
                    '                            response = self.input_check_fn()\n')
STRM_INPUT = ('                        if is_stream or file_path.startswith("lavf://"):  # FS42 local: remote works during Archive loads\n'
              '                            response = self.input_check_fn()\n')

# FS42 local: a named rebuild (-r "Station") skips the whole-cache trim. The trim checks every cached
# file (~7,900) over the NAS and took most of a 6 min rebuild. A plain -r (all stations) still trims.
TRIM_STOCK = ('        if FF_USE_FLUID_FILE_CACHE:\n'
              '            try:\n'
              '                FluidBuilder().trim_file_cache(execution_start_time)\n')
TRIM_NAMED = ('        if FF_USE_FLUID_FILE_CACHE and not args.rebuild_catalog:  # FS42 local: named -r skips the trim\n'
              '            try:\n'
              '                FluidBuilder().trim_file_cache(execution_start_time)\n')

# FS42 local: a .strm stub may carry "#crop=W:H:X:Y" (4:3 picture stored with side bars, e.g. Zoboomafoo).
# The crop is kept in _FS42_CROP, which _FS42ShrinkMPV puts in front of every vf it sets, so the static and
# reception filters after a channel change keep it (2026-11-01: setting vf once was wiped by them).
# Every play_file resets it, so the next file (and static.mp4) is plain again.
CROP_ANCHOR = '                if file_path.endswith(".strm"):  # FS42 local: Archive stream stub -> its URL (+ trim start)\n'
CROP_OLD = """                if file_path.endswith(".strm"):  # FS42 local: side-bar crop from the stub (#crop=)
                    with open(file_path) as _f:
                        for _line in _f:
                            if _line.startswith("#crop="):
                                self.mpv.vf = "crop=" + _line.split("=", 1)[1].strip()
""" + CROP_ANCHOR
CROP = """                _fs42_prev_crop = _FS42_CROP["vf"]  # FS42 local: side-bar crop from the stub (#crop=)
                _FS42_CROP["vf"] = ""
                if file_path.endswith(".strm"):
                    with open(file_path) as _f:
                        for _line in _f:
                            if _line.startswith("#crop="):
                                _FS42_CROP["vf"] = "crop=" + _line.split("=", 1)[1].strip()
                if _FS42_CROP["vf"] or _fs42_prev_crop:
                    self._apply_vfx(datetime.datetime.now())  # vf again, now with this file's crop (or none)
""" + CROP_ANCHOR
SHRINK_OLD_CLASS = '''_BASE_VF = _load_base_vf()


class _FS42ShrinkMPV(_BaseMPV):
    # Effect filters get the mpv.conf shrink appended; clearing restores the shrink.
    def __setattr__(self, name, value):
        if name == "vf" and _BASE_VF:
            value = f"{value},{_BASE_VF}" if value else _BASE_VF
        super().__setattr__(name, value)
'''
SHRINK_NEW_CLASS = SHRINK[SHRINK.index("_BASE_VF = _load_base_vf()"):SHRINK.index("\n\n\nMPV = _FS42ShrinkMPV") + 1]

# FS42 local: i-Guide needs arrow keys (+ Home) passed into the web guide page
KEYS_API_STOCK = '    allowed_keys = {"PageUp", "PageDown", "Enter"}\n'
KEYS_API = '    allowed_keys = {"PageUp", "PageDown", "Enter", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home"}  # FS42 local: i-Guide keys\n'
KEYS_WEB_STOCK = '                if key_name not in {"PageUp", "PageDown", "Enter"}:\n'
KEYS_WEB = '                if key_name not in {"PageUp", "PageDown", "Enter", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home"}:  # FS42 local: i-Guide keys\n'

# FS42 local: direct archive.org server links. fs42_local/archive_urls.py saves each stub's
# dnNNN.*.archive.org link to runtime/archive_urls.json; playing that skips archive.org's ~2 s
# redirect, which lavf pays again on the start seek (13.9 s -> 4.7 s in a test, 2026-11-01).
# If a direct link fails to start, the player retries once through the normal redirect link.
DIRECT_HELPERS_ANCHOR = "MPV = _FS42ShrinkMPV\n"
DIRECT_HELPERS = """

_FS42_URLS = "runtime/archive_urls.json"
_fs42_urls = {"mtime": None, "map": {}}


def _fs42_direct_url(url):
    # FS42 local: cached direct archive.org server link for an archive.org/download/ URL, or None
    try:
        m = os.path.getmtime(_FS42_URLS)
        if m != _fs42_urls["mtime"]:
            import json
            with open(_FS42_URLS) as f:
                _fs42_urls["map"] = json.load(f)
            _fs42_urls["mtime"] = m
        e = _fs42_urls["map"].get(url)
        return e["url"] if e else None
    except Exception:
        return None
"""

DIRECT_PLAY = """                _fs42_fallback = None  # FS42 local: use the cached direct archive.org server link
                if file_path.startswith("lavf://"):
                    _fs42_direct = _fs42_direct_url(file_path[len("lavf://"):])
                    if _fs42_direct:
                        _fs42_fallback = file_path
                        file_path = "lavf://" + _fs42_direct
                        self._l.info(f"direct link {file_path}")
"""

DIRECT_RETRY_ANCHOR = ('                        if time.time() - start_time > timeout_seconds:\n'
                       '                            self._l.error(f"Timeout waiting for playback to start on {file_path}")\n')
DIRECT_RETRY = """                        if _fs42_fallback and (time.time() - start_time > timeout_seconds / 2
                                               or (time.time() - start_time > 1.5 and self.mpv.idle_active)):
                            # FS42 local: direct link failed -> retry once through the archive.org redirect
                            self._l.warning(f"Direct link failed, retrying {_fs42_fallback}")
                            _fs42_urls["map"].pop(_fs42_fallback[len("lavf://"):], None)
                            file_path, _fs42_fallback = _fs42_fallback, None
                            if offset_seconds is not None and offset_seconds > 0:
                                self.mpv.command("loadfile", file_path, "replace", f"start={offset_seconds}")
                            else:
                                self.mpv.play(file_path)
                            start_time = time.time()
                            continue
""" + DIRECT_RETRY_ANCHOR

# FS42 local: .strm stub text from runtime/archive_stubs.json (written by archive_urls.py).
# Reading the stub off the NAS stalled ~6 s behind the last channel's leftover NAS reads
# (2026-11-01, NAS over a Tailscale relay). Stubs missing from the cache still come from the NAS.
# Shadowing open() in station_player.py covers the crop and URL reads of the stub patches above.
STUB_HELPERS_ANCHOR = "        return e[\"url\"] if e else None\n    except Exception:\n        return None\n"
STUB_HELPERS = """

_FS42_STUBS = "runtime/archive_stubs.json"
_fs42_stubs = {"mtime": None, "map": {}}
_fs42_builtin_open = open


def _fs42_stub_text(path):
    # FS42 local: cached text of a .strm stub, or None
    if not str(path).endswith(".strm"):
        return None
    try:
        m = os.path.getmtime(_FS42_STUBS)
        if m != _fs42_stubs["mtime"]:
            with _fs42_builtin_open(_FS42_STUBS) as f:
                _fs42_stubs["map"] = json.load(f)
            _fs42_stubs["mtime"] = m
        return _fs42_stubs["map"].get(path)
    except Exception:
        return None


def open(file, *args, **kwargs):  # FS42 local: cached .strm stubs, everything else as normal
    text = _fs42_stub_text(file)
    if text is not None:
        import io
        return io.StringIO(text)
    return _fs42_builtin_open(file, *args, **kwargs)
"""

STUB_EXISTS_STOCK = "            if os.path.exists(file_path) or is_stream or AutoBumpAgent.is_autobump_url(file_path):\n"
STUB_EXISTS = ("            if _fs42_stub_text(file_path) is not None or os.path.exists(file_path) or is_stream or AutoBumpAgent.is_autobump_url(file_path):"
               "  # FS42 local: cached stubs skip the NAS\n")

# FS42 local: On Demand menu (2026-11-01). fs42_local/guide_overlay.py writes
# {"command": "ondemand", "path": ..., "start": secs, "title": ...} to runtime/channel.socket; field_player
# plays it with play_ondemand() on the same mpv until it ends or any channel command comes in.
# Watch positions go to runtime/ondemand_positions.json (path -> {pos, dur, ts, done}, seconds from the
# start of the episode, after a stub's #start= trim). The overlay is told started/stopped/ended/failed.
OD_LOOP_ANCHOR = "        # reset skip\n        skip_play = False\n"
OD_LOOP = '''
        while (player_state.status == PlayerState.CHANNEL_CHANGE and isinstance(player_state.payload, str)
               and '"ondemand"' in player_state.payload):  # FS42 local: On Demand menu plays a file here
            try:
                _od = json.loads(player_state.payload)
            except ValueError:
                break
            if _od.get("command") != "ondemand":
                break
            player_state = player.play_ondemand(_od.get("path", ""), float(_od.get("start") or 0),
                                                _od.get("title") or "On Demand")
'''
OD_METHOD_ANCHOR = "    def play_slot(self, network_name, when):\n"
OD_METHOD = '''    def play_ondemand(self, path, start=0.0, title="On Demand"):  # FS42 local: On Demand menu
        import json as _od_json, urllib.request as _od_url
        pos_file = "runtime/ondemand_positions.json"

        def tell_overlay(event):
            try:
                _od_url.urlopen("http://127.0.0.1:4243/ondemand/" + event, timeout=1).close()
            except Exception:
                pass

        def save(pos, dur, done=False):
            try:
                with open(pos_file) as f:
                    data = _od_json.load(f)
            except (OSError, ValueError):
                data = {}
            data[path] = {"pos": round(max(pos, 0), 1), "dur": round(dur or 0, 1), "ts": int(time.time()), "done": done}
            try:
                with open(pos_file + ".tmp", "w") as f:
                    _od_json.dump(data, f)
                os.replace(pos_file + ".tmp", pos_file)
            except OSError as e:
                self._l.warning(f"On Demand: could not save position: {e}")

        # stub trim: positions are kept from the episode's own start
        stub_start, dur = 0.0, None
        try:
            if path.endswith(".strm"):
                with open(path) as f:
                    for line in f:
                        if line.startswith("#start="):
                            stub_start = float(line.split("=", 1)[1])
                        elif line.startswith("#duration="):
                            dur = float(line.split("=", 1)[1])
        except (OSError, ValueError):
            pass
        self._l.info(f"On Demand: {path} from {start:.0f}s")
        self._fs42_osd_pending = False
        self.mpv.loop_playlist = "no"
        try:
            self.mpv.pause = False
        except Exception:
            pass
        worked = self.play_file(path, file_duration=dur, offset_seconds=start, title=title,
                                content_type="ondemand", media_type="video")
        if self._pending_response:
            response, self._pending_response = self._pending_response, None
            tell_overlay("stopped")
            return response
        if not worked:
            self._l.error(f"On Demand: could not play {path}")
            tell_overlay("failed")
            return PlayerOutcome(PlayerState.SUCCESS)
        tell_overlay("started")
        end_at = stub_start + dur if dur else None
        pos, last_check, last_save = start, 0.0, time.time()
        try:
            while True:
                time.sleep(0.05)
                response = self.input_check_fn()
                if response:
                    if self.handle_runtime_command_outcome(response) or self.is_non_interrupting(response):
                        continue
                    save(pos, dur)
                    tell_overlay("stopped")
                    return response
                now = time.time()
                if now - last_check < 0.5:
                    continue
                last_check = now
                try:
                    tp, eof, idle = self.mpv.time_pos, self.mpv.eof_reached, self.mpv.idle_active
                    if dur is None and self.mpv.duration:
                        dur = self.mpv.duration - stub_start
                except Exception:
                    tp, eof, idle = None, False, False
                if tp is not None:
                    pos = tp - stub_start
                if eof or idle or (end_at and tp is not None and tp >= end_at - 0.5):
                    finished = bool(dur) and pos >= dur * 0.9
                    self._l.info(f"On Demand: {'finished' if finished else 'stopped early'} at {pos:.0f}s")
                    save(dur if finished else pos, dur, finished)
                    tell_overlay("ended")
                    return PlayerOutcome(PlayerState.SUCCESS)
                if now - last_save >= 10:
                    save(pos, dur)
                    last_save = now
        finally:
            try:
                self.mpv.pause = False   # a paused On Demand title must not leave live TV paused
            except Exception:
                pass

''' + OD_METHOD_ANCHOR

# FS42 local: index proxy fallback (Tristan OK 2026-11-01). Archive stubs point at the local
# index proxy (fs42-mkv-proxy, http://127.0.0.1:8742/<item>/<file>). If nothing answers on that
# port, play the file straight from archive.org (cached direct link if we have one); if a proxy
# link fails to start (mpv goes idle), retry once from archive.org. A slow proxy start is left alone.
PROXY_HELPERS = """

_FS42_PROXY = "http://127.0.0.1:8742/"


def _fs42_proxy_up():
    # FS42 local: is the local index proxy accepting connections?
    import socket
    try:
        socket.create_connection(("127.0.0.1", 8742), timeout=0.3).close()
        return True
    except OSError:
        return False


def _fs42_proxy_to_archive(file_path):
    # FS42 local: lavf:// proxy URL -> lavf:// archive.org URL (cached direct link if we have one)
    ia = "https://archive.org/download/" + file_path[len("lavf://" + _FS42_PROXY):]
    return "lavf://" + (_fs42_direct_url(ia) or ia)
"""

PROXY_PLAY = """                _fs42_proxy_fb = None  # FS42 local: index proxy down -> straight from archive.org
                if file_path.startswith("lavf://" + _FS42_PROXY):
                    if _fs42_proxy_up():
                        _fs42_proxy_fb = _fs42_proxy_to_archive(file_path)
                    else:
                        _fs42_ia = "lavf://https://archive.org/download/" + file_path[len("lavf://" + _FS42_PROXY):]
                        file_path = _fs42_proxy_to_archive(file_path)
                        if file_path != _fs42_ia:
                            _fs42_fallback = _fs42_ia  # direct link fails -> the redirect retry below
                        self._l.warning(f"index proxy down, playing {file_path}")
"""

PROXY_RETRY_ANCHOR = "                        if _fs42_fallback and (time.time() - start_time > timeout_seconds / 2\n"
PROXY_RETRY = """                        if _fs42_proxy_fb and time.time() - start_time > 1.5 and self.mpv.idle_active:
                            # FS42 local: proxy link failed to start -> retry once from archive.org
                            self._l.warning(f"Proxy link failed, retrying {_fs42_proxy_fb}")
                            file_path, _fs42_proxy_fb = _fs42_proxy_fb, None
                            if offset_seconds is not None and offset_seconds > 0:
                                self.mpv.command("loadfile", file_path, "replace", f"start={offset_seconds}")
                            else:
                                self.mpv.play(file_path)
                            start_time = time.time()
                            continue
""" + PROXY_RETRY_ANCHOR

# FS42 local: live volume leveling for Archive streams only (Tristan 2026-11-01). Local files and ads are
# already loudnorm'd to -18 LUFS on the PC; .strm episodes are not, so they get a live loudnorm to the same
# target (LRA 7 = mild). Labelled @fs42level so it never touches other audio filters; every file resets it.
LEVEL_ANCHOR = '                _fs42_prev_crop = _FS42_CROP["vf"]  # FS42 local: side-bar crop from the stub (#crop=)\n'
LEVEL = """                try:  # FS42 local: live volume leveling, Archive streams only (@fs42level)
                    self.mpv.command("af", "remove", "@fs42level")
                except Exception:
                    pass
                if file_path.endswith(".strm"):
                    try:
                        self.mpv.command("af", "add", "@fs42level:lavfi=[loudnorm=I=-18:LRA=7:TP=-1.5:dual_mono=true,aresample=48000]")
                    except Exception as e:
                        self._l.warning(f"Could not add volume leveling: {e}")
""" + LEVEL_ANCHOR


# FS42 local: mid-show ad breaks (Tristan 2026-11-01). Seeks are keyframe-only (see PLAY_ATLOAD), so a piece
# that starts with a seek (resume after a break, tune-in mid-act) begins a few seconds before the asked spot,
# and it used to end on the wall clock, so the next cut came early (mid "will return after these messages").
# Now such a streamed piece ends by mpv's real position: when the clock says done but time_pos is still short
# of the cut point, it plays on (at most 15 s). (A first try that measured the gap right after loadfile read 0:
# mpv reports the asked spot there, not the keyframe.) STOPPOS_SET goes after OSD_PLAY so the older
# SEEK_ATLOAD + OSD_PLAY pair stays together (inserting between them made them re-apply).
STOPPOS_SET = ('                if not is_stream and offset_seconds is not None and offset_seconds > 0:  # FS42 local: asked seek spot (file time, incl. #start)\n'
               '                    self._fs42_seek_target = offset_seconds\n'
               '                else:\n'
               '                    self._fs42_seek_target = None\n')
STOPPOS_CALC_ANCHOR = ('                    target_end_time = datetime.datetime.now() + datetime.timedelta(seconds=(entry.duration - initial_skip))\n')
STOPPOS_CALC = ('                    _fs42_tgt = getattr(self, "_fs42_seek_target", None)  # FS42 local: end a resumed stream piece by its real position\n'
                '                    self._fs42_seek_target = None\n'
                '                    _fs42_stop_pos = (_fs42_tgt + entry.duration - initial_skip) if (_fs42_tgt and entry.path.endswith(".strm")) else None\n'
                '                    _fs42_ext = False\n')
STOPPOS_CHECK_ANCHOR = "                        if time_remaining <= 0:\n"
# v1 (22:40) checked the position only after the fade had started on the clock -> picture went black early.
# v2 (22:55) moves the check before the fade, so fade + cut both follow the real position; v1 is removed.
STOPPOS_OLD_CHECK = ('                        if _fs42_stop_pos is not None and -15 < time_remaining <= 0:  # FS42 local: landed early -> play on to the cut point\n'
                 '                            try:\n'
                 '                                _fs42_p = self.mpv.time_pos\n'
                 '                                if _fs42_p is not None and _fs42_p < _fs42_stop_pos - 0.05:\n'
                 '                                    if not _fs42_ext:\n'
                 '                                        self._l.info(f"Clock says done at {_fs42_p:.2f}s, playing on to {_fs42_stop_pos:.2f}s")\n'
                 '                                        _fs42_ext = True\n'
                 '                                    time_remaining = 0.01\n'
                 '                            except Exception:\n'
                 '                                pass\n'
                 + STOPPOS_CHECK_ANCHOR)

STOPPOS_POS_ANCHOR = "                        time_remaining = (target_end_time - datetime.datetime.now()).total_seconds()\n"
STOPPOS_POS = ('                        if _fs42_stop_pos is not None and -15 < time_remaining <= FADE_DURATION + 1:  # FS42 local: landed early -> fade and cut by the real position\n'
               '                            try:\n'
               '                                _fs42_p = self.mpv.time_pos\n'
               '                                if _fs42_p is not None and _fs42_stop_pos - _fs42_p > time_remaining + 0.05:\n'
               '                                    if not _fs42_ext:\n'
               '                                        self._l.info(f"Clock says {time_remaining:.2f}s left at {_fs42_p:.2f}s, playing on to {_fs42_stop_pos:.2f}s")\n'
               '                                        _fs42_ext = True\n'
               '                                    time_remaining = min(_fs42_stop_pos - _fs42_p, time_remaining + 15)\n'
               '                            except Exception:\n'
               '                                pass\n')

# Ad catch-up (Tristan OK'd 2026-11-02): FS42 plays a block's entries back to back with no catch-up, so stream
# loads, ad loads and the STOPPOS play-on add up (10-80 s per half hour on ch 11) and the next block then skips
# that far into its first episode. Now: an ad/bump is dropped while the player is late by at least its length,
# and a block that follows straight on from the last one (and has enough ads to soak it up) starts its first
# episode from the beginning instead of skipping in. Tune-ins (channel changes) still join mid-show as before.
CATCHUP_START_ANCHOR = "            initial_skip = play_point.offset\n"
CATCHUP_START = ('            _fs42_clock = datetime.datetime.now() - datetime.timedelta(seconds=initial_skip)  # FS42 local: planned start of each entry (ad catch-up)\n'
                 '            _fs42_ads = sum(e.duration for e in play_point.plan[play_point.index + 1:] if getattr(e, "content_type", "feature") in ("commercial", "bump"))\n'
                 '            if (0 < initial_skip <= 120 and _fs42_ads >= initial_skip + 30 and time.time() - getattr(self, "_fs42_block_done", 0) < 10\n'
                 '                    and getattr(play_point.plan[play_point.index], "content_type", "feature") not in ("commercial", "bump")):\n'
                 '                self._l.info(f"Running {initial_skip:.1f}s late from the last block: starting from the top, ads will catch up")\n'
                 '                initial_skip = 0\n')
CATCHUP_DROP_ANCHOR = "            for entry in play_point.plan[play_point.index :]:\n"
CATCHUP_DROP = ('                _fs42_late = (datetime.datetime.now() - _fs42_clock).total_seconds()  # FS42 local: ad catch-up\n'
                '                _fs42_clock += datetime.timedelta(seconds=entry.duration)\n'
                '                if initial_skip == 0 and getattr(entry, "content_type", "feature") in ("commercial", "bump") and _fs42_late >= entry.duration:\n'
                '                    self._l.info(f"Running {_fs42_late:.1f}s late: dropped {os.path.basename(entry.path)} ({entry.duration:.1f}s)")\n'
                '                    continue\n')
CATCHUP_DONE_ANCHOR = '            self._l.info("Done playing block")\n'
CATCHUP_DONE = '            self._fs42_block_done = time.time()  # FS42 local: the next block follows straight on (ad catch-up)\n'

# FS42 local: a .strm stub may carry "#aid=N" to pick the audio track (Tristan OK'd 2026-11-02). Superman TAS
# AVIs on archive.org have Spanish as track 1 and English as track 2 (the IA mp4 copies kept only the Spanish).
# play_file sets it for every file (auto when the stub has none); the other play paths reset it to auto.
AID_ANCHOR = '                _FS42_CROP["vf"] = ""\n'
AID = '''                _fs42_aid = "auto"  # FS42 local: audio track from the stub (#aid=N)
                if file_path.endswith(".strm"):
                    with open(file_path) as _f:
                        for _line in _f:
                            if _line.startswith("#aid="):
                                _fs42_aid = _line.split("=", 1)[1].strip()
                self.mpv.aid = "auto"  # the stub's track is picked once the file plays (below)
'''
AID_OLD = AID.replace('                self.mpv.aid = "auto"  # the stub\'s track is picked once the file plays (below)\n',
                      "                self.mpv.aid = _fs42_aid\n")
AID_START_ANCHOR = "                        if self.mpv.time_pos is not None:\n"
AID_START = '                            if _fs42_aid != "auto":  # FS42 local: stub audio track, now that the new file plays\n' \
            "                                self.mpv.aid = _fs42_aid\n"
AID_WAIT_ANCHOR = '        self._l.info(f"Play and wait on file {file_path}")\n'
AID_LIST_ANCHOR = "    def play_file_list(self, file_list):\n"
AID_RESET = '        self.mpv.aid = "auto"  # FS42 local: no stub audio track (#aid) carried over\n'

# (file, name, anchor, new_text, mode)  mode: "replace" swaps anchor, "after" inserts after it
PATCHES = [
    # "upgrade": turns an older version of one of our own patches into the current one (skipped when absent)
    ("fs42/station_player.py", "shrink class upgraded to keep the stub crop",
     SHRINK_OLD_CLASS, SHRINK_NEW_CLASS, "upgrade"),
    ("fs42/station_player.py", "stub crop upgraded to survive channel-change filters",
     CROP_OLD, CROP, "upgrade"),
    ("fs42/station_player.py", "extra blank line from the 2026-11-01 shrink upgrade removed",
     SHRINK_NEW_CLASS + "\n\n\nMPV = _FS42ShrinkMPV", SHRINK_NEW_CLASS + "\n\nMPV = _FS42ShrinkMPV", "upgrade"),
    ("fs42/station_player.py", "96% shrink kept during effects",
     "from python_mpv_jsonipc import MPV\n", SHRINK, "replace"),
    ("fs42/station_player.py", "seek folded into initial load (no pre-seek frame flash)",
     PLAY_STOCK, PLAY_ATLOAD, "replace"),
    ("fs42/station_player.py", "fast keyframe seeks instead of frame-exact (was freezing channel changes)",
     SEEK, SEEK_ATLOAD, "replace"),
    ("fs42/station_player.py", "channel number after new video starts", SEEK_ATLOAD, OSD_PLAY, "after"),
    ("field_player.py", "channel number on button press",
     "            player.station_config = channel_conf\n", OSD_PRESS, "after"),
    ("field_player.py", "channel number at startup",
     "    player = StationPlayer(manager.stations[channel_index], input_check)\n",
     "    player._fs42_osd_pending = True\n", "after"),
    ("fs42/webrender/web_render.py", "web channel goes silent when you leave it",
     '                print("WebRender window is shutting down now.")\n', WEB_MUTE, "after"),
    ("fs42/station_player.py", "leftover web audio cleared before a web channel starts",
     '        ctx = multiprocessing.get_context("spawn")\n', KILL_WEB, "after"),
    ("fs42/station_player.py", "leftover web audio cleared after leaving a web channel",
     "                    self.web_process.join()\n", KILL_WEB_AFTER_JOIN, "after"),
    ("fs42/osd/logo_display.py", "logo fade timing",
     "            y = -h / 2.0\n", LOGO_FADE, "after"),
    ("fs42/osd/logo_display.py", "logo fade alpha",
     "        glColor4f(1.0, 1.0, 1.0, alpha)\n", LOGO_FADE_ALPHA, "after"),
    ("fs42/media_processor.py", "Archive stubs (.strm) picked up by catalog scans",
     STRM_FORMATS_STOCK, STRM_FORMATS, "replace"),
    ("fs42/media_processor.py", "Archive stub duration read from the stub",
     STRM_DURATION_ANCHOR, STRM_DURATION, "after"),
    ("fs42/station_player.py", "Archive stub played from its URL",
     STRM_PLAY_ANCHOR, STRM_PLAY, "replace"),
    ("fs42/station_player.py", "stub line 1 may be a NAS file path (local tapes)",
     STRM_LOCAL_OLD, STRM_LOCAL, "upgrade"),
    ("fs42/station_player.py", "Archive down shows TECHNICAL DIFFICULTIES",
     STRM_DOWN_STOCK, STRM_DOWN, "replace"),
    ("fs42/station_player.py", "remote works while an Archive episode loads",
     STRM_INPUT_STOCK, STRM_INPUT, "replace"),
    ("station_42.py", "named rebuilds skip the slow file cache trim",
     TRIM_STOCK, TRIM_NAMED, "replace"),
    ("fs42/station_player.py", "stubs with side bars cropped to 4:3",
     CROP_ANCHOR, CROP, "replace"),
    ("fs42/fs42_server/api/ppv.py", "i-Guide arrow keys accepted by the key API",
     KEYS_API_STOCK, KEYS_API, "replace"),
    ("fs42/webrender/web_render.py", "i-Guide arrow keys passed into the guide page",
     KEYS_WEB_STOCK, KEYS_WEB, "replace"),
    ("fs42/station_player.py", "direct archive.org link helpers",
     DIRECT_HELPERS_ANCHOR, DIRECT_HELPERS, "after"),
    ("fs42/station_player.py", "Archive episodes play from the direct server link",
     STRM_PLAY_ANCHOR, DIRECT_PLAY, "after"),
    ("fs42/station_player.py", "direct link failure retries through the redirect",
     DIRECT_RETRY_ANCHOR, DIRECT_RETRY, "replace"),
    ("fs42/station_player.py", "stub text read from the local cache",
     STUB_HELPERS_ANCHOR, STUB_HELPERS, "after"),
    ("fs42/station_player.py", "cached stubs skip the NAS check",
     STUB_EXISTS_STOCK, STUB_EXISTS, "replace"),
    ("fs42/station_player.py", "On Demand playback (play_ondemand)",
     OD_METHOD_ANCHOR, OD_METHOD, "replace"),
    ("field_player.py", "On Demand requests played by field_player",
     OD_LOOP_ANCHOR, OD_LOOP, "after"),
    ("fs42/station_player.py", "index proxy helpers",
     STUB_HELPERS, PROXY_HELPERS, "after"),
    ("fs42/station_player.py", "proxy down -> play from archive.org",
     DIRECT_PLAY, PROXY_PLAY, "after"),
    ("fs42/station_player.py", "proxy link failure retries from archive.org",
     PROXY_RETRY_ANCHOR, PROXY_RETRY, "replace"),
    ("fs42/station_player.py", "Archive streams get live volume leveling",
     LEVEL_ANCHOR, LEVEL, "replace"),
    ("fs42/station_player.py", "seek spot kept for resumed pieces",
     OSD_PLAY, STOPPOS_SET, "after"),
    ("fs42/station_player.py", "cut point of a resumed stream piece",
     STOPPOS_CALC_ANCHOR, STOPPOS_CALC, "after"),
    ("fs42/station_player.py", "older end-by-position check removed (v1)",
     STOPPOS_OLD_CHECK, STOPPOS_CHECK_ANCHOR, "upgrade"),
    ("fs42/station_player.py", "resumed stream piece fades and ends by real position (mid-show breaks)",
     STOPPOS_POS_ANCHOR, STOPPOS_POS, "after"),
    ("fs42/station_player.py", "late blocks start their first episode from the top (ad catch-up)",
     CATCHUP_START_ANCHOR, CATCHUP_START, "after"),
    ("fs42/station_player.py", "ads dropped while running late (ad catch-up)",
     CATCHUP_DROP_ANCHOR, CATCHUP_DROP, "after"),
    ("fs42/station_player.py", "block end time noted (ad catch-up)",
     CATCHUP_DONE_ANCHOR, CATCHUP_DONE, "after"),
    ("fs42/station_player.py", "stub audio track set after load (v2)",
     AID_OLD, AID, "upgrade"),
    ("fs42/station_player.py", "stub picks its audio track (#aid=)",
     AID_ANCHOR, AID, "after"),
    ("fs42/station_player.py", "stub audio track picked once the file plays",
     AID_START_ANCHOR, AID_START, "after"),
    ("fs42/station_player.py", "play-and-wait resets the audio track",
     AID_WAIT_ANCHOR, AID_RESET, "after"),
    ("fs42/station_player.py", "file lists reset the audio track",
     AID_LIST_ANCHOR, AID_RESET, "after"),
]

MARKERS = ("_FS42ShrinkMPV", "_fs42_osd", "FS42 local")
ok = True
for path, name, anchor, text, mode in PATCHES:
    s = open(path).read()
    if mode == "upgrade":
        if s.count(anchor) == 1:
            open(path, "w").write(s.replace(anchor, text))
            print(f"OK   {name} (applied)")
        continue
    done = (text in s) if mode == "replace" else (anchor + text in s)
    if done:
        print(f"OK   {name} (already in place)")
        continue
    if s.count(anchor) != 1:
        print(f"WARN {name}: FS42 code changed, could not apply - ask Claude to update the patch")
        ok = False
        continue
    if not any(m in s for m in MARKERS):
        open(path + ".bak", "w").write(s)  # keep a copy of the untouched FS42 file
    s = s.replace(anchor, text if mode == "replace" else anchor + text)
    open(path, "w").write(s)
    print(f"OK   {name} (applied)")
print("All patches in place" if ok else "Some patches could not be applied")
