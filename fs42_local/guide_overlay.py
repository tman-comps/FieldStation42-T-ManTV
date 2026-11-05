# FieldStation42 local: T-ManTV i-Guide overlay with the live channel in the top-right box.
# Loads the guide page once at startup and keeps it hidden, so the Guide button opens it
# instantly. While it is open, the running mpv picture is moved into the guide's preview
# box (mpv video margins over runtime/mpv.socket -- the same mpv, no second player) and
# a hole is cut in the window there (X11 window shape). Real transparency doesn't work:
# xcompmgr runs as -aR, which ignores alpha. remote.py drives it over a small local
# HTTP API: /show /hide /toggle /key/<Key> /status.
#
# The same window also hosts the On Demand menu (2026-11-01): static/ondemand/ondemand.html in a second
# view, full screen with live TV muted underneath. OK on a title writes an "ondemand" command to
# runtime/channel.socket and field_player plays it (play_ondemand, FS42 patch in apply_patches.py).
# API: /ondemand/show|hide|toggle|key/<Key>|control/<pause|back|ahead>|back, and the player's
# /ondemand/started|stopped|ended|failed. remote.py routes buttons here while it's open or playing.
import json, os, socket, subprocess, sys, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtCore import QRect
from PySide6.QtGui import QRegion
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

FS42 = os.path.expanduser("~/FieldStation42")
API = "http://127.0.0.1:4242"
PORT = 4243
MPV_SOCKET = os.path.join(FS42, "runtime/mpv.socket")
GUIDE_URL = (API + "/static/iguide/customguide.html?theme=00s&interactive=1"
             "&show_description=true&slots=3&videos=false")  # look + station name: fs42_local/guide-theme
IDLE_CLOSE = 120          # seconds without a button press before the guide closes itself
RELOAD_EVERY = 30 * 60    # reload the hidden page now and then (fresh listings, no leaks)
KEYS = {"ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Enter", "Home"}
MARGINS = ("left", "right", "top", "bottom")
BANNER_SECS = 4           # channel-change info banner stays up this long (Tristan, 2026-11-02)
BANNER_WAIT = 5           # give up if the channel hasn't changed this long after the button
REMINDERS = os.path.join(FS42, "runtime/reminders.json")   # OK on a future show in the guide (2026-11-04)
REMINDER_SECS = 60        # reminder pop-up stays up this long unless OK/Back
REMINDER_LATE = 10 * 60   # still pop up this long after the start (guide/On Demand menu was open)
REMINDER_AHEAD = 30       # OK on a show starting within this many seconds tunes instead
OD_URL = API + "/static/ondemand/ondemand.html"
OD_KEYS = KEYS | {"Escape"}
OD_IDLE_CLOSE = 5 * 60    # On Demand menu closes itself after this long without a press
OD_LOAD_WAIT = 45         # give up on the "stand by" card if playback hasn't started by then
POSITIONS = os.path.join(FS42, "runtime/ondemand_positions.json")
CHANNEL_SOCKET = os.path.join(FS42, "runtime/channel.socket")
MUTED_FLAG = os.path.join(FS42, "runtime/ondemand_muted")   # we muted the TV; unmute after a crash
# remote button -> mpv command while an On Demand title plays (+ what the OSD says)
OD_CONTROLS = {"pause": (["cycle", "pause"], None),
               "back": (["seek", -10, "relative+keyframes"], "-10 s"),
               "ahead": (["seek", 30, "relative+keyframes"], "+30 s")}


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def player_status():
    try:
        with urllib.request.urlopen(API + "/player/status", timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log(f"status failed: {e}")
        return {}


def mpv_set_margins(values):
    """Set mpv video-margin-ratio-* (dict side -> ratio). Returns True on success."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(MPV_SOCKET)
            replies = s.makefile("rb")
            for n, side in enumerate(MARGINS, 1):
                cmd = {"command": ["set_property", f"video-margin-ratio-{side}", values.get(side, 0.0)],
                       "request_id": n}
                s.sendall((json.dumps(cmd) + "\n").encode())
                # wait for mpv's answer, or it may drop the rest when the socket closes
                while json.loads(replies.readline() or "{}").get("request_id", n) != n:
                    pass
        return True
    except OSError as e:
        log(f"mpv margins failed: {e}")
        return False


def mpv_command(args):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(MPV_SOCKET)
            s.sendall((json.dumps({"command": args, "request_id": 1}) + "\n").encode())
            replies = s.makefile("rb")
            while json.loads(replies.readline() or "{}").get("request_id", 1) != 1:
                pass
        return True
    except OSError as e:
        log(f"mpv command {args} failed: {e}")
        return False


def set_muted(on):
    # The whole TV (PipeWire sink), so web channels like Weather go quiet too
    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if on else "0"], check=False)
    if on:
        open(MUTED_FLAG, "w").close()
    elif os.path.exists(MUTED_FLAG):
        os.remove(MUTED_FLAG)


def is_muted():
    r = subprocess.run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"], capture_output=True, text=True, check=False)
    return "yes" in r.stdout


def send_to_player(cmd):
    # Same file FS42's own command input uses; field_player reads it and clears it
    with open(CHANNEL_SOCKET, "w") as f:
        f.write(json.dumps(cmd))


class Page(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        log(f"js: {message} ({source.rsplit('/', 1)[-1]}:{line})")


class OnDemandPage(Page):
    def __init__(self, view, overlay):
        super().__init__(view)
        self.overlay = overlay

    def javaScriptConsoleMessage(self, level, message, line, source):
        if message.startswith("ODPLAY "):
            self.overlay.od_play(json.loads(message[7:]))
        elif message == "ODCLOSE":
            self.overlay.od_close()
        else:
            super().javaScriptConsoleMessage(level, message, line, source)


class Bridge(QObject):
    request = Signal(str, str)   # (action, arg) from the HTTP thread to the Qt thread


class Overlay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_open = False
        self.live = False
        self.load_ok = False
        self.last_input = 0.0
        self.banner_on = False
        self.banner_timer = QTimer(self)
        self.banner_timer.setSingleShot(True)
        self.banner_timer.timeout.connect(self.hide_banner)
        self.reminder = None      # the reminder pop-up on screen now
        try:
            with open(REMINDERS) as f:
                self.reminders = json.load(f)
        except (OSError, ValueError):
            self.reminders = []

        # Always above mpv and FS42's web window; the window manager never touches it.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.X11BypassWindowManagerHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.stack = QStackedWidget(self)
        self.view = QWebEngineView(self.stack)
        self.view.setPage(Page(self.view))
        self.view.settings().setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        self.view.loadFinished.connect(self.loaded)
        self.stack.addWidget(self.view)
        self.od_menu = ""         # On Demand menu: "menu", "loading" (stand-by card up) or ""
        self.od_playing = False   # an On Demand title is playing in field_player
        self.od_live_muted = False
        self.od_last_input = 0.0
        self.od_load_ok = False
        self.od_view = QWebEngineView(self.stack)
        self.od_view.setPage(OnDemandPage(self.od_view, self))
        self.od_view.loadFinished.connect(self.od_loaded)
        self.stack.addWidget(self.od_view)
        self.stack.setCurrentWidget(self.view)
        self.setCentralWidget(self.stack)
        if os.path.exists(MUTED_FLAG):   # left muted by a crash while the menu was up
            set_muted(False)
        # "Closed" = parked off-screen, not hidden: Chromium pauses hidden pages, which
        # stalled the guide's grid build. Off-screen it keeps running, ready to slide in.
        self.screen_rect = QApplication.primaryScreen().geometry()
        self.setGeometry(self.screen_rect)
        self.park()
        self.show()

        self.idle = QTimer(self)
        self.idle.timeout.connect(self.check_idle)
        self.idle.start(5000)
        self.reloader = QTimer(self)
        self.reloader.timeout.connect(self.reload_if_closed)
        self.reloader.start(RELOAD_EVERY * 1000)
        self.reminder_check = QTimer(self)
        self.reminder_check.timeout.connect(self.check_reminders)
        self.reminder_check.start(5000)
        self.load()
        self.od_view.load(QUrl(OD_URL))

    def od_loaded(self, ok):
        self.od_load_ok = ok
        log(f"on demand page loaded: {ok}")
        if not ok:
            QTimer.singleShot(5000, lambda: self.od_view.load(QUrl(OD_URL)))

    def load(self):
        self.load_ok = False
        self.view.load(QUrl(GUIDE_URL))

    def loaded(self, ok):
        self.load_ok = ok
        log(f"guide page loaded: {ok}")
        if not ok:   # FS42's web server may not be up yet at boot
            QTimer.singleShot(5000, self.load)
        else:
            self.push_reminders()

    def reload_if_closed(self):
        if not self.is_open and not self.banner_on:
            self.load()
        if not self.od_menu:   # also picks up the new catalog.json after the night's export
            self.od_view.load(QUrl(OD_URL))

    def check_idle(self):
        if self.is_open and time.time() - self.last_input > IDLE_CLOSE:
            log("closing after idle")
            self.close_guide()
        if self.od_menu == "menu" and time.time() - self.od_last_input > OD_IDLE_CLOSE:
            log("on demand: closing after idle")
            self.od_close()
        if self.od_menu == "loading" and time.time() - self.od_last_input > OD_LOAD_WAIT:
            log("on demand: playback never started, back to the menu")
            self.od_menu = "menu"
            self.od_js("odOpened()")

    def handle(self, action, arg):
        if action.startswith("od_"):
            self.od_handle(action[3:], arg)
        elif action == "show":
            self.open_guide()
        elif action == "hide":
            self.close_guide()
        elif action == "toggle":
            self.close_guide() if self.is_open else self.open_guide()
        elif action == "key":
            self.key(arg)
        elif action == "banner":
            self.show_banner(arg)
        elif action == "reminder_dismiss":
            if self.reminder:
                self.hide_banner()
        elif action == "eval":   # debugging: run JS in the page, result goes to the log
            self.view.page().runJavaScript(arg, 0, lambda r: log(f"eval -> {r!r}"))

    def open_guide(self):
        if self.is_open:
            return
        if not self.load_ok:
            log("open ignored: guide page not loaded")
            return
        if self.od_menu:
            self.od_close()
        self.hide_banner()
        self.stack.setCurrentWidget(self.view)
        status = player_status()
        ch = status.get("channel_number")
        # Web channels (Weather, Guide) are not mpv, so there's no live picture to show.
        self.live = status.get("content_type") != "web"
        self.is_open = True
        self.last_input = time.time()
        # Open on the current channel with the listings already on the page (instant), then
        # refresh them in the background (the schedule API takes ~4 s on the Pi) and keep
        # whatever is highlighted by then.
        js = """(async () => { try {
            const pick = () => {
                const rows = getInteractiveRows();
                const i = rows.findIndex(r => r.dataset.channelNumber === '%s');
                selectInteractiveRow(i < 0 ? 0 : i, Date.now());
                return rows.length;
            };
            const remember = () => {
                const sel = document.querySelector('.grid-program-block.guide-selected');
                window.__tmanSelMs = sel ? Number(sel.dataset.startMs) : Date.now();
            };
            if (!window.__tmanTracking) {   // follow arrow presses made while the refresh runs
                window.__tmanTracking = true;
                document.addEventListener('keydown', () => setTimeout(remember, 50));
            }
            if (interactiveSlotOffset !== 0) { interactiveSlotOffset = 0; await buildGrid(); }
            pick();
            remember();
            await buildGrid();
            selectInteractiveRow(interactiveRowIndex, Math.max(window.__tmanSelMs, Date.now() - 1));
            console.log('guide open: refreshed ' + getInteractiveRows().length + ' rows');
        } catch (e) { console.log('guide open failed: ' + e); } })();""" % ch
        self.view.page().runJavaScript(js, 0, lambda r: None)  # the one-argument form never ran here
        if self.live:
            self.view.page().runJavaScript(
                "(() => { const r = document.getElementById('video-panel').getBoundingClientRect();"
                " return JSON.stringify([r.left, r.top, r.width, r.height]); })()", 0, self.place_video)  # arrays come back empty; text works
        else:
            QTimer.singleShot(150, self.show_window)
        log(f"open on ch {ch} (live picture: {self.live})")

    def place_video(self, rect):
        if self.is_open and rect:
            x, y, w, h = (round(v) for v in json.loads(rect))
            W, H = self.width(), self.height()
            mpv_set_margins({"left": x / W, "right": 1 - (x + w) / W,
                             "top": y / H, "bottom": 1 - (y + h) / H})
            self.setMask(QRegion(0, 0, W, H) - QRegion(QRect(x, y, w, h)))
        self.show_window()

    def park(self):
        self.move(self.screen_rect.x() - self.screen_rect.width() - 100, self.screen_rect.y())

    def show_window(self):
        if self.is_open:
            self.move(self.screen_rect.topLeft())
            self.raise_()

    def close_guide(self):
        if not self.is_open:
            return
        self.is_open = False
        self.park()
        if self.live:
            mpv_set_margins({})
            self.clearMask()
        # Back to the current time slots, so the info banner finds what's on now
        self.view.page().runJavaScript(
            "if (interactiveSlotOffset !== 0) { interactiveSlotOffset = 0; buildGrid(); }", 0, lambda r: None)
        log("closed")

    # ---------- channel-change info banner ----------
    def show_banner(self, status_json):
        # Bar along the bottom with what's on (WeatherStar skin, tmantv_skin.js). The window is
        # masked to just the bar, so the show stays full screen around it.
        if self.is_open or self.od_menu or not self.load_ok:
            return
        self.reminder = None   # a tune replaces the reminder pop-up
        self.view.page().runJavaScript(f"tmanBanner({status_json})", 0, self.place_banner)

    def place_banner(self, rect, secs=BANNER_SECS):
        if self.is_open or self.od_menu or not rect:
            return
        x, y, w, h = (round(v) for v in json.loads(rect))
        self.stack.setCurrentWidget(self.view)
        self.setMask(QRegion(x - 1, y - 1, w + 2, h + 2))   # + the 1px outer outline
        self.banner_on = True
        self.banner_timer.start(secs * 1000)
        QTimer.singleShot(60, self.raise_banner)   # let the page paint the new text first

    def raise_banner(self):
        if self.banner_on:
            self.move(self.screen_rect.topLeft())
            self.raise_()

    def hide_banner(self):
        self.reminder = None
        if not self.banner_on:
            return
        self.banner_on = False
        self.banner_timer.stop()
        self.park()
        self.clearMask()
        self.view.page().runJavaScript("tmanBannerHide()", 0, lambda r: None)

    def key(self, name):
        if not self.is_open or name not in KEYS:
            return
        self.last_input = time.time()
        if name == "Enter":   # OK on the channel already playing just closes the guide
            self.view.page().runJavaScript("tmanSelectedInfo()", 0, self.enter)
            return
        self.send_key(name)

    def enter(self, info_json):
        info = json.loads(info_json or "{}")
        if info.get("start", 0) > (time.time() + REMINDER_AHEAD) * 1000:   # a future show: reminder on/off
            self.toggle_reminder(info)
            return
        selected = str(info.get("ch"))
        if str(player_status().get("channel_number")) == selected:
            log(f"OK on ch {selected}, already playing")
            self.close_guide()
            return
        log(f"tune ch {selected}")
        self.send_key("Enter")

    def send_key(self, name):
        self.view.page().runJavaScript(
            "document.dispatchEvent(new KeyboardEvent('keydown',"
            " {key: '%s', code: '%s', bubbles: true, cancelable: true}));" % (name, name), 0, lambda r: None)
        if name == "Enter":   # the page tunes the highlighted channel; get out of the way
            QTimer.singleShot(250, self.close_guide)

    # ---------- reminders ----------
    def save_reminders(self):
        tmp = REMINDERS + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.reminders, f)
        os.replace(tmp, REMINDERS)

    def push_reminders(self, msg=""):
        self.view.page().runJavaScript(
            f"tmanSetReminders({json.dumps(self.reminders)}, {json.dumps(msg)})", 0, lambda r: None)

    def toggle_reminder(self, info):
        key = (str(info["ch"]), int(info["start"]))
        kept = [r for r in self.reminders if (str(r["ch"]), r["start"]) != key]
        if len(kept) < len(self.reminders):
            self.reminders, msg = kept, "REMINDER OFF"
        else:
            self.reminders.append({k: info.get(k) for k in ("ch", "net", "start", "end", "title")})
            msg = "REMINDER SET"
        log(f"{msg.lower()}: ch {info['ch']} {info.get('title')} at {time.strftime('%H:%M', time.localtime(info['start'] / 1000))}")
        self.save_reminders()
        self.push_reminders(msg)

    def check_reminders(self):
        now = time.time() * 1000
        due = sorted((r for r in self.reminders if r["start"] <= now), key=lambda r: r["start"])
        # Wait while the guide, the On Demand menu or another reminder is up
        if not due or self.is_open or self.od_menu or self.reminder or not self.load_ok:
            return
        r = due[0]
        self.reminders.remove(r)
        self.save_reminders()
        self.push_reminders()
        on = str(player_status().get("channel_number"))
        if now - r["start"] > REMINDER_LATE * 1000:
            log(f"reminder too late, dropped: ch {r['ch']} {r.get('title')}")
        elif on == str(r["ch"]):
            log(f"reminder: already on ch {on}")
        else:
            log(f"reminder up: ch {r['ch']} {r.get('title')}")
            self.hide_banner()
            self.reminder = r
            self.view.page().runJavaScript(f"tmanReminder({json.dumps(r)})", 0, self.place_reminder)

    def place_reminder(self, rect):
        self.place_banner(rect, REMINDER_SECS)
        if not self.banner_on:   # the guide opened in the meantime
            self.reminder = None

    # ---------- On Demand ----------
    def od_js(self, js):
        self.od_view.page().runJavaScript(js, 0, lambda r: None)

    def od_push_positions(self):
        try:
            with open(POSITIONS) as f:
                data = f.read()
            json.loads(data)
        except (OSError, ValueError):
            data = "{}"
        self.od_js(f"odSetPositions({data})")

    def od_handle(self, action, arg):
        if action == "show":
            self.od_open()
        elif action == "hide":
            self.od_close()
        elif action == "toggle":
            self.od_close() if self.od_menu else self.od_open()
        elif action == "key":
            if self.od_menu and arg in OD_KEYS:
                self.od_last_input = time.time()
                self.od_js(f"odKey('{arg}')")
        elif action == "control":
            if self.od_playing and arg in OD_CONTROLS:
                cmd, osd = OD_CONTROLS[arg]
                mpv_command(cmd)
                mpv_command(["show-text", osd or "${?pause==yes:PAUSED}${?pause==no:PLAY}", 1500])
        elif action == "back":       # Back while a title plays: menu up, live TV back underneath
            self.od_open()
            ch = player_status().get("channel_number")
            if ch is not None:
                send_to_player({"command": "direct", "channel": ch})
        elif action == "started":
            self.od_playing = True
            log("on demand: playing")
            if self.od_menu == "loading":
                self.od_close()
        elif action == "stopped":
            self.od_playing = False
            self.od_push_positions()
        elif action == "ended":
            self.od_playing = False
            log("on demand: title ended")
            self.od_open()
        elif action == "failed":
            self.od_playing = False
            log("on demand: player could not play the title")
            if self.od_menu == "loading":
                self.od_menu = "menu"
                self.od_js("odOpened()")

    def od_open(self):
        if not self.od_load_ok:
            log("on demand open ignored: page not loaded")
            return
        if self.is_open:
            self.close_guide()
        self.hide_banner()
        self.od_last_input = time.time()
        if not self.od_menu and not self.od_live_muted and not is_muted():
            set_muted(True)          # live TV keeps playing under the menu, quietly
            self.od_live_muted = True
        self.od_menu = "menu"
        self.od_push_positions()
        self.od_js("odOpened()")
        self.stack.setCurrentWidget(self.od_view)
        self.clearMask()
        self.move(self.screen_rect.topLeft())
        self.raise_()
        log("on demand: menu open")

    def od_close(self):
        if not self.od_menu:
            return
        self.od_menu = ""
        self.park()
        self.stack.setCurrentWidget(self.view)
        if self.od_live_muted:
            set_muted(False)
            self.od_live_muted = False
        log("on demand: menu closed")

    def od_play(self, req):
        if not req.get("path") or not self.od_menu:
            return
        self.od_menu = "loading"
        self.od_last_input = time.time()
        log(f"on demand: play {req.get('title')} from {req.get('start', 0)}s")
        send_to_player({"command": "ondemand", "path": req["path"], "start": req.get("start", 0),
                        "title": req.get("title") or "On Demand"})


def banner_when_tuned(bridge, overlay, old_ch):
    # The remote calls right after sending the tune; wait until the player is on the new
    # channel (same moment the static starts) and the guide has closed itself (OK in the guide),
    # then show the banner. Silent if it never changes.
    deadline = time.time() + BANNER_WAIT
    while True:
        status = player_status()
        ch = status.get("channel_number")
        if ch is not None and (not old_ch or str(ch) != old_ch) and not overlay.is_open:
            bridge.request.emit("banner", json.dumps(status))
            return
        if time.time() > deadline:
            return
        time.sleep(0.15)


def serve(bridge, overlay):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parts = self.path.strip("/").split("/")
            action, arg = parts[0], (parts[1] if len(parts) > 1 else "")
            if action == "eval":
                arg = urllib.parse.unquote(self.path.split("/eval/", 1)[1])
            if action == "ondemand" and arg:
                bridge.request.emit("od_" + arg, parts[2] if len(parts) > 2 else "")
                body = {"ok": True}
            elif action in ("show", "hide", "toggle", "key", "eval"):
                bridge.request.emit(action, arg)
                body = {"ok": True}
            elif action == "banner":
                # /banner = what's on now (Info); /banner/<ch> = after a tune away from <ch>
                threading.Thread(target=banner_when_tuned, args=(bridge, overlay, arg), daemon=True).start()
                body = {"ok": True}
            elif action == "reminder":   # /reminder/dismiss (remote.py tunes itself for OK)
                bridge.request.emit("reminder_dismiss", "")
                body = {"ok": True}
            elif action == "reminders":
                body = overlay.reminders
            elif action == "status":
                body = {"open": overlay.is_open, "loaded": overlay.load_ok, "banner": overlay.banner_on,
                        "reminder": overlay.reminder and str(overlay.reminder["ch"]),
                        "od": overlay.od_menu or ("playing" if overlay.od_playing else ""),
                        "od_loaded": overlay.od_load_ok}
            else:
                self.send_error(404)
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_GET

        def log_message(self, *a):
            pass

    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


def main():
    os.environ.setdefault("DISPLAY", ":0")
    # Parked off-screen counts as "hidden" to Chromium, which then stops running the
    # page's scripts; these keep the parked guide live.
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") +
        " --disable-backgrounding-occluded-windows --disable-renderer-backgrounding"
        " --disable-background-timer-throttling").strip()
    # FS42 (local patch) runs `pkill -f QtWebEngineProcess` around web channels to stop
    # leftover audio. Start our browser helpers under another name so that leaves us alone.
    # A hard link in the same folder: it finds its Qt libraries relative to itself, and a
    # symlink would show up under the real name again once Chromium relaunches it.
    import PySide6
    libexec = os.path.join(os.path.dirname(PySide6.__file__), "Qt/libexec")
    alias = os.path.join(libexec, "TManGuideRenderer")
    if not os.path.exists(alias):
        os.link(os.path.join(libexec, "QtWebEngineProcess"), alias)
    os.environ["QTWEBENGINEPROCESS_PATH"] = alias
    app = QApplication(sys.argv)
    overlay = Overlay()
    bridge = Bridge()
    bridge.request.connect(overlay.handle, Qt.QueuedConnection)
    threading.Thread(target=serve, args=(bridge, overlay), daemon=True).start()
    log(f"guide overlay ready on 127.0.0.1:{PORT}")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
