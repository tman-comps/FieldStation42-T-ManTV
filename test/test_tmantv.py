# Tests for the T-ManTV additions: .strm stubs, direct archive.org links,
# the index proxy, the CRT shrink filter and play_file's stub handling.
import json
import logging
import os
import time

import sys
import types
from unittest import mock

import pytest

from fs42 import tmantv
from fs42.media_processor import MediaProcessor
from fs42.nfo_agent import NFOAgent


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    # tmantv reads runtime/*.json relative to the FS42 folder
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runtime").mkdir()
    monkeypatch.setitem(tmantv._urls, "mtime", None)
    monkeypatch.setitem(tmantv._urls, "map", {})
    monkeypatch.setitem(tmantv._stubs, "mtime", None)
    monkeypatch.setitem(tmantv._stubs, "map", {})
    monkeypatch.setitem(tmantv.CROP, "vf", "")
    return tmp_path


# --- read_stub ---------------------------------------------------------------

def test_read_stub_all_options(in_tmp):
    p = write(in_tmp / "a.strm",
              "https://archive.org/download/item/ep1.mp4\n#duration=1720.74\n#start=23\n"
              "#crop=640:480:40:0\n#aid=2\n")
    assert tmantv.read_stub(p) == {
        "target": "lavf://https://archive.org/download/item/ep1.mp4",
        "start": 23.0, "duration": 1720.74, "crop": "crop=640:480:40:0", "aid": "2"}


def test_read_stub_defaults_and_proxy_url(in_tmp):
    p = write(in_tmp / "b.strm", "http://127.0.0.1:8742/item/ep.mkv\n#duration=60\n")
    s = tmantv.read_stub(p)
    assert s["target"] == "lavf://http://127.0.0.1:8742/item/ep.mkv"
    assert (s["start"], s["crop"], s["aid"]) == (0.0, "", "auto")


def test_read_stub_nas_path(in_tmp):
    p = write(in_tmp / "c.strm", "/mnt/nas/Tapes/tape1.mp4\n#duration=10\n")
    assert tmantv.read_stub(p)["target"] == "/mnt/nas/Tapes/tape1.mp4"


def test_read_stub_without_target(in_tmp):
    p = write(in_tmp / "d.strm", "#duration=10\n#start=5\n")
    s = tmantv.read_stub(p)
    assert s["target"] is None and s["start"] == 5.0


def test_read_stub_bad_duration_is_ignored_bad_start_raises(in_tmp):
    assert tmantv.read_stub(write(in_tmp / "e.strm", "http://x/y\n#duration=abc\n"))["duration"] is None
    with pytest.raises(ValueError):
        tmantv.read_stub(write(in_tmp / "f.strm", "http://x/y\n#start=abc\n"))


# --- stub text cache ----------------------------------------------------------

def test_stub_cache_is_used_first(in_tmp):
    p = write(in_tmp / "g.strm", "http://disk/version\n")
    (in_tmp / "runtime/archive_stubs.json").write_text(json.dumps({p: "http://cached/version\n#start=7\n"}))
    assert tmantv.stub_text(p) == "http://cached/version\n#start=7\n"
    assert tmantv.read_stub(p)["target"] == "lavf://http://cached/version"
    assert tmantv.stub_text(str(in_tmp / "not-a-stub.mp4")) is None


def test_stub_falls_back_to_file_without_cache(in_tmp):
    p = write(in_tmp / "h.strm", "http://disk/version\n")
    assert tmantv.stub_text(p) is None
    assert tmantv.read_stub(p)["target"] == "lavf://http://disk/version"


def test_stub_cache_reloads_when_file_changes(in_tmp):
    p = str(in_tmp / "i.strm")
    cache = in_tmp / "runtime/archive_stubs.json"
    cache.write_text(json.dumps({p: "one"}))
    assert tmantv.stub_text(p) == "one"
    cache.write_text(json.dumps({p: "two"}))
    os.utime(cache, (time.time() + 5, time.time() + 5))
    assert tmantv.stub_text(p) == "two"


# --- direct links and the index proxy ---------------------------------------

IA = "https://archive.org/download/item/ep.mp4"
DIRECT = "https://ia800.us.archive.org/1/items/item/ep.mp4"


def test_direct_url_and_forget(in_tmp):
    (in_tmp / "runtime/archive_urls.json").write_text(json.dumps({IA: {"url": DIRECT}}))
    assert tmantv.direct_url(IA) == DIRECT
    assert tmantv.direct_url("https://archive.org/download/other/x.mp4") is None
    tmantv.forget_direct_url(IA)
    assert tmantv.direct_url(IA) is None


def test_direct_url_without_cache_file(in_tmp):
    assert tmantv.direct_url(IA) is None


def test_proxy_url_to_archive(in_tmp):
    proxied = "lavf://" + tmantv.PROXY + "item/ep.mp4"
    assert tmantv.archive_url(proxied) == "lavf://" + IA
    assert tmantv.proxy_to_archive(proxied) == "lavf://" + IA
    (in_tmp / "runtime/archive_urls.json").write_text(json.dumps({IA: {"url": DIRECT}}))
    assert tmantv.proxy_to_archive(proxied) == "lavf://" + DIRECT


# --- CRT shrink filter -------------------------------------------------------

def test_shrink_mpv_wraps_vf(monkeypatch):
    seen = {}
    monkeypatch.setattr(tmantv._BaseMPV, "__setattr__", lambda self, n, v: seen.__setitem__(n, v))
    m = object.__new__(tmantv.ShrinkMPV)
    for k, v in {"properties": {}, "mpv_process": None, "mpv_inter": None,
                 "event_handler": types.SimpleNamespace(stop=lambda join: None)}.items():
        object.__setattr__(m, k, v)  # enough for MPV.__del__ on a never-started instance
    monkeypatch.setattr(tmantv, "BASE_VF", "lavfi=[scale=iw*0.98:ih*0.98]")
    monkeypatch.setitem(tmantv.CROP, "vf", "crop=640:480:40:0")
    m.vf = "lavfi=[noise]"
    assert seen["vf"] == "crop=640:480:40:0,lavfi=[noise],lavfi=[scale=iw*0.98:ih*0.98]"
    m.vf = ""
    assert seen["vf"] == "crop=640:480:40:0,lavfi=[scale=iw*0.98:ih*0.98]"
    m.aid = "2"
    assert seen["aid"] == "2"
    monkeypatch.setattr(tmantv, "BASE_VF", "")
    m.vf = "lavfi=[noise]"
    assert seen["vf"] == "lavfi=[noise]"  # no mpv.conf shrink: filters pass through untouched


# --- catalog side (media_processor) ----------------------------------------

def test_strm_is_a_video_format():
    assert "strm" in MediaProcessor.VIDEO_FORMATS


def test_strm_duration_comes_from_stub(tmp_path):
    assert MediaProcessor._get_duration(write(tmp_path / "a.strm", "http://x\n#duration=1500.5\n")) == (1500.5, None)
    d, hint = MediaProcessor._get_duration(write(tmp_path / "b.strm", "http://x\n"))
    assert d == -1 and "no #duration" in hint
    d, hint = MediaProcessor._get_duration(str(tmp_path / "missing.strm"))
    assert d == -1 and "could not read" in hint


# --- NFO hand patches ------------------------------------------------------

def test_musicvideo_nfo_reads_plot_and_overlay_is_off():
    meta = NFOAgent.parse_nfo_string(
        "<musicvideo><title>Song</title><artist>Band</artist><plot>Live, 1985.</plot></musicvideo>")
    assert meta and meta.get("plot") == "Live, 1985."
    assert NFOAgent.show_overlay(meta) is None
    assert "music" not in NFOAgent.OVERLAY_TYPES


# --- play_file with a fake mpv ----------------------------------------------

class FakeMPV:
    """Records what the player asks of mpv. Playback 'starts' on the next time_pos read."""

    def __init__(self, fail_first=False):
        object.__setattr__(self, "log", [])
        object.__setattr__(self, "props", {"time_pos": None, "idle_active": False})
        object.__setattr__(self, "fail_first", fail_first)

    def command(self, *args):
        self.log.append(("command",) + args)
        if args[0] == "loadfile":
            self._loaded()

    def play(self, path):
        self.log.append(("play", path))
        self._loaded()

    def _loaded(self):
        if self.fail_first:
            object.__setattr__(self, "fail_first", False)
            self.props.update(time_pos=None, idle_active=True)  # this link won't start
        else:
            self.props.update(time_pos=0.0, idle_active=False)

    def __setattr__(self, name, value):
        self.log.append(("set", name, value))
        self.props[name] = value

    def __getattr__(self, name):
        return self.props.get(name)

    def loads(self):
        return [e for e in self.log if e[:2] == ("command", "loadfile") or e[0] == "play"]


@pytest.fixture
def player(in_tmp, monkeypatch):
    try:
        import tkinter  # noqa: F401
    except ImportError:  # Python builds without Tk: guide_tk only needs the name at import
        monkeypatch.setitem(sys.modules, "tkinter", mock.MagicMock())
    from fs42.station_player import StationPlayer
    p = object.__new__(StationPlayer)
    p._l = logging.getLogger("test")
    p.mpv = FakeMPV()
    p.station_config = {"network_name": "Test", "channel_number": 4}
    p.input_check_fn = lambda: None
    p._pending_response = None
    p._active_afx = None
    p.vfx_calls = []
    monkeypatch.setattr(p, "_apply_vfx", lambda when: p.vfx_calls.append(tmantv.CROP["vf"]), raising=False)
    monkeypatch.setattr(p, "_close_now_playing", lambda: None, raising=False)
    monkeypatch.setattr(tmantv, "proxy_up", lambda: True)
    return p


def call_play(player, path, offset=0):  # FS42 always passes an offset (None breaks the status line)
    try:
        return player.play_file(path, file_duration=100, offset_seconds=offset, title="t",
                                content_type="feature", media_type="video")
    except Exception as e:  # play_file swallows most errors; surface the rest
        pytest.fail(f"play_file raised {e!r}")


def test_play_stub_loads_url_with_trim_leveling_crop_and_track(player, in_tmp):
    p = write(in_tmp / "ep.strm", f"{IA}\n#duration=100\n#start=23\n#crop=640:480:40:0\n#aid=2\n")
    assert call_play(player, p, offset=10) is True
    log = player.mpv.log
    assert player.mpv.loads()[-1] == ("command", "loadfile", "lavf://" + IA, "replace", "start=33.0")
    assert ("command", "af", "add",
            "@fs42level:lavfi=[loudnorm=I=-18:LRA=7:TP=-1.5:dual_mono=true,aresample=48000]") in log
    assert ("set", "hr_seek", "no") in log
    assert tmantv.CROP["vf"] == "crop=640:480:40:0" and "crop=640:480:40:0" in player.vfx_calls
    sets = [e for e in log if e[:2] == ("set", "aid")]
    assert sets[0] == ("set", "aid", "auto") and sets[-1] == ("set", "aid", "2")


def test_play_local_file_after_stub_clears_crop_and_leveling(player, in_tmp):
    tmantv.CROP["vf"] = "crop=640:480:40:0"  # left over from the last stub
    f = write(in_tmp / "local.mp4", "x")
    assert call_play(player, f) is True
    log = player.mpv.log
    assert ("command", "af", "remove", "@fs42level") in log
    assert not any(e[:3] == ("command", "af", "add") for e in log)
    assert tmantv.CROP["vf"] == "" and player.vfx_calls[-1] == ""
    assert player.mpv.loads()[-1] == ("play", f)


def test_play_stub_uses_cached_direct_link(player, in_tmp):
    (in_tmp / "runtime/archive_urls.json").write_text(json.dumps({IA: {"url": DIRECT}}))
    p = write(in_tmp / "ep.strm", f"{IA}\n#duration=100\n")
    assert call_play(player, p) is True
    assert player.mpv.loads()[-1] == ("play", "lavf://" + DIRECT)


def test_failed_direct_link_retries_through_redirect(player, in_tmp):
    (in_tmp / "runtime/archive_urls.json").write_text(json.dumps({IA: {"url": DIRECT}}))
    player.mpv = FakeMPV(fail_first=True)
    p = write(in_tmp / "ep.strm", f"{IA}\n#duration=100\n")
    assert call_play(player, p) is True
    assert [e[-1] for e in player.mpv.loads()] == ["lavf://" + DIRECT, "lavf://" + IA]
    assert tmantv.direct_url(IA) is None  # the bad link is not used again


def test_proxy_down_plays_from_archive(player, in_tmp, monkeypatch):
    monkeypatch.setattr(tmantv, "proxy_up", lambda: False)
    p = write(in_tmp / "ep.strm", f"{tmantv.PROXY}item/ep.mp4\n#duration=100\n")
    assert call_play(player, p) is True
    assert player.mpv.loads()[-1] == ("play", "lavf://" + IA)


def test_failed_proxy_link_retries_from_archive(player, in_tmp):
    player.mpv = FakeMPV(fail_first=True)
    p = write(in_tmp / "ep.strm", f"{tmantv.PROXY}item/ep.mp4\n#duration=100\n")
    assert call_play(player, p) is True
    assert [e[-1] for e in player.mpv.loads()] == ["lavf://" + tmantv.PROXY + "item/ep.mp4", "lavf://" + IA]


def test_cached_stub_plays_without_the_file(player, in_tmp):
    p = str(in_tmp / "nas-offline.strm")  # not on disk, only in the stub cache
    (in_tmp / "runtime/archive_stubs.json").write_text(json.dumps({p: f"{IA}\n#duration=100\n"}))
    assert call_play(player, p) is True
    assert player.mpv.loads()[-1] == ("play", "lavf://" + IA)


def test_play_and_wait_drops_stream_leveling(player, in_tmp):
    player.mpv.props["time_pos"] = 0.0
    player.input_check_fn = lambda: "stop"
    monkeypatch_handle = lambda r: False
    player.handle_runtime_command_outcome = monkeypatch_handle
    player.is_non_interrupting = lambda r: False
    try:
        player.play_and_wait(write(in_tmp / "standby.png", "x"))
    except Exception:
        pass
    log = player.mpv.log
    # tmantv-update removes the label itself; older FS42 cleared all of af
    assert ("command", "af", "remove", "@fs42level") in log or ("set", "af", "") in log
