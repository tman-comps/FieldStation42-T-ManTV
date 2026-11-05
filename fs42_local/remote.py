# FieldStation42 local remote listener for the MX3 air-mouse remote (USB dongle).
# Reads every input device whose name matches REMOTE_NAME (the dongle shows up as
# several: Keyboard, Consumer Control, Mouse), grabs them so button presses don't
# leak into the desktop/web pages, and turns buttons into FS42 remote commands.
import os, sys, time, json, select, threading, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from evdev import InputDevice, ecodes, list_devices

HOST = "http://127.0.0.1:4242"
REMOTE_NAME = "USB Composite Device"     # part of the dongle's device name
DIGIT_WAIT = 1.2                          # seconds to wait for a 2nd/3rd digit
DEBOUNCE = 0.25                           # ignore repeats of the same button faster than this
OVERLAY = "http://127.0.0.1:4243"         # guide overlay with the live picture (Guide button)
BACK_KEYS = {"KEY_BACK", "KEY_BACKSPACE", "KEY_ESC"}
GUIDE_CHANNEL = 2                         # i-Guide: arrows/OK go into the guide page here
GUIDE_DEBOUNCE = 0.12                     # faster repeat for scrolling the guide
ONDEMAND_CHANNEL = 99                     # dialing 99 opens the On Demand menu (no FS42 channel)
TV_IR_HOOK = os.environ.get("TV_IR_HOOK", "")   # optional: Home Assistant webhook URL for TV power/volume IR (set in boot.conf)
WEB_PORT = 4244                          # phone remote: http://<pi>:4244/ (same handling as the MX3)
WEB_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote_web.html")
OD_CONTROLS = {"KEY_ENTER": "pause", "KEY_KPENTER": "pause", "KEY_SELECT": "pause", "BTN_LEFT": "pause",
               "KEY_LEFT": "back", "KEY_RIGHT": "ahead"}   # while an On Demand title plays
GUIDE_KEYS = {"KEY_UP": "ArrowUp", "KEY_DOWN": "ArrowDown",
              "KEY_LEFT": "ArrowLeft", "KEY_RIGHT": "ArrowRight",
              "KEY_PAGEUP": "PageUp", "KEY_PAGEDOWN": "PageDown",
              "KEY_ENTER": "Enter", "KEY_KPENTER": "Enter", "KEY_SELECT": "Enter",
              "BTN_LEFT": "Enter"}                # MX3 OK button sends a mouse click

# evdev key name -> action
KEYS = {
    "KEY_PAGEUP": "channel_up",   "KEY_PAGEDOWN": "channel_down",
    "KEY_CHANNELUP": "channel_up", "KEY_CHANNELDOWN": "channel_down",
    "KEY_UP": "channel_up",       "KEY_DOWN": "channel_down",
    "KEY_VOLUMEUP": "volume_up",  "KEY_VOLUMEDOWN": "volume_down",
    "KEY_RIGHT": "volume_up",     "KEY_LEFT": "volume_down",
    "KEY_MUTE": "mute", "KEY_POWER": "power",
    "KEY_CONFIG": "ondemand",   # the movie-clapper button (Tristan, 2026-11-01)
    "KEY_HOMEPAGE": "guide", "KEY_HOME": "guide", "KEY_MENU": "guide", "KEY_COMPOSE": "guide",
    "KEY_BACK": "last_channel", "KEY_BACKSPACE": "last_channel", "KEY_ESC": "last_channel",
    "KEY_ENTER": "enter", "KEY_KPENTER": "enter", "KEY_SELECT": "enter", "BTN_LEFT": "enter",
}
DIGITS = {f"KEY_{i}": str(i) for i in range(10)}
DIGITS.update({f"KEY_KP{i}": str(i) for i in range(10)})

def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)

def api(path, method="GET"):
    try:
        req = urllib.request.Request(HOST + path, method=method)
        with urllib.request.urlopen(req, timeout=3) as r:
            body = r.read().decode("utf-8", "ignore")
            try:
                return json.loads(body)
            except ValueError:
                return {}
    except Exception as e:
        log(f"API {method} {path} failed: {e}")
        return None

def tv_ir(key):
    # Power/volume/mute drive the TV itself: HA webhook -> script.tmantv_ir -> RM4 Mini (Tristan 2026-11-02)
    if not TV_IR_HOOK:
        return
    def send():
        try:
            req = urllib.request.Request(TV_IR_HOOK, data=json.dumps({"key": key}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=3).close()
        except Exception as e:
            log(f"TV IR {key} failed: {e}")
    threading.Thread(target=send, daemon=True).start()

def overlay(path):
    # Guide overlay (fs42_local/guide_overlay.py). None if it isn't running.
    try:
        with urllib.request.urlopen(OVERLAY + path, timeout=1) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def current_channel():
    s = api("/player/status")
    return s.get("channel_number") if isinstance(s, dict) else None

class Remote:
    def __init__(self):
        self.digits = ""
        self.timer = None
        self.lock = threading.Lock()
        self.last_press = {}
        self.last_channel = None

    def _remember(self):
        ch = current_channel()
        if ch is not None:
            self.last_channel = ch
        return ch

    def banner(self, old_ch):
        # Info banner over the new channel; the overlay waits until the tune has happened
        overlay(f"/banner/{old_ch}" if old_ch is not None else "/banner")

    def tune(self, number):
        if number == ONDEMAND_CHANNEL:
            log("on demand (dialed)")
            overlay("/ondemand/show")
            return
        old = self._remember()
        log(f"tune {number}")
        api(f"/player/channels/{number}")
        self.banner(old)

    def flush_digits(self):
        with self.lock:
            number, self.digits, self.timer = self.digits, "", None
        if number:
            self.tune(int(number))

    def digit(self, d):
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.digits += d
            wait = 0.05 if len(self.digits) >= 3 else DIGIT_WAIT
            self.timer = threading.Timer(wait, self.flush_digits)
            self.timer.start()

    def action(self, name):
        now = time.time()
        if now - self.last_press.get(name, 0) < DEBOUNCE:
            return
        self.last_press[name] = now
        log(f"action {name}")
        if name == "channel_up":
            old = self._remember(); api("/player/channels/up"); self.banner(old)
        elif name == "channel_down":
            old = self._remember(); api("/player/channels/down"); self.banner(old)
        elif name == "volume_up":
            tv_ir("vol_up")
        elif name == "volume_down":
            tv_ir("vol_down")
        elif name == "mute":
            tv_ir("mute")
        elif name == "power":
            tv_ir("power")
        elif name == "guide":
            status = overlay("/status")
            if current_channel() == GUIDE_CHANNEL and self.last_channel not in (None, GUIDE_CHANNEL):
                self.tune(self.last_channel)   # Guide again closes the guide
            elif status and status.get("loaded"):
                overlay("/toggle")             # guide over the show, show keeps playing in the box
            else:                              # overlay not running: fall back to the ch 2 guide
                self._remember(); api("/player/channels/guide", "POST")
        elif name == "ondemand":
            overlay("/ondemand/toggle")
        elif name == "last_channel":
            if self.last_channel is not None:
                self.tune(self.last_channel)
        elif name == "enter":
            with self.lock:
                if self.timer:
                    self.timer.cancel()
            self.flush_digits()

    def guide_key(self, keyname):
        # On the i-Guide channel, arrows/OK scroll and tune inside the guide page.
        if keyname not in GUIDE_KEYS or self.digits or current_channel() != GUIDE_CHANNEL:
            return False
        now = time.time()
        if now - self.last_press.get(keyname, 0) < GUIDE_DEBOUNCE:
            return True
        self.last_press[keyname] = now
        if GUIDE_KEYS[keyname] == "Enter":
            self.last_channel = GUIDE_CHANNEL   # Back/Last after tuning returns to the guide
        log(f"guide {GUIDE_KEYS[keyname]}")
        api(f"/ppv/{GUIDE_CHANNEL}/key/{GUIDE_KEYS[keyname]}", "POST")
        if GUIDE_KEYS[keyname] == "Enter":
            self.banner(GUIDE_CHANNEL)
        return True

    def overlay_key(self, keyname):
        # While the guide overlay is open: arrows/CH/OK go into it, Back closes it,
        # number buttons close it and tune as usual. Volume/mute/Guide work as normal.
        if keyname not in GUIDE_KEYS and keyname not in BACK_KEYS and keyname not in DIGITS:
            return False
        status = overlay("/status")
        if not (status and status.get("open")):
            return False
        if keyname in DIGITS:
            overlay("/hide")
            return False
        now = time.time()
        if now - self.last_press.get(keyname, 0) < GUIDE_DEBOUNCE:
            return True
        self.last_press[keyname] = now
        if keyname in BACK_KEYS:
            log("overlay close")
            overlay("/hide")
            return True
        old = self._remember() if GUIDE_KEYS[keyname] == "Enter" else None   # Back after tuning returns to this show
        log(f"overlay {GUIDE_KEYS[keyname]}")
        overlay(f"/key/{GUIDE_KEYS[keyname]}")
        if old is not None:
            self.banner(old)
        return True

    def ondemand_key(self, keyname):
        # On Demand menu open: arrows/CH/OK go into it, Back steps back (closes it at the top),
        # number buttons close it and tune. A title playing: OK pauses, Left/Right skip, Back
        # returns to the menu; CH/numbers/Guide/volume work as normal.
        if keyname not in GUIDE_KEYS and keyname not in BACK_KEYS and keyname not in DIGITS:
            return False
        status = overlay("/status")
        od = status.get("od") if status else ""
        if not od or (status.get("open") and keyname not in DIGITS):
            return False                        # nothing On Demand, or the guide is on top
        if keyname in DIGITS:
            if od != "playing":
                overlay("/ondemand/hide")
            return False
        now = time.time()
        if now - self.last_press.get(keyname, 0) < GUIDE_DEBOUNCE:
            return True
        self.last_press[keyname] = now
        if od == "playing":
            if keyname in BACK_KEYS:
                log("on demand back to menu")
                overlay("/ondemand/back")
                return True
            if keyname in OD_CONTROLS:
                log(f"on demand {OD_CONTROLS[keyname]}")
                overlay(f"/ondemand/control/{OD_CONTROLS[keyname]}")
                return True
            return False
        name = "Escape" if keyname in BACK_KEYS else GUIDE_KEYS[keyname]
        log(f"on demand {name}")
        overlay(f"/ondemand/key/{name}")
        return True

    def reminder_key(self, keyname):
        # Reminder pop-up up (guide_overlay.py): OK tunes to that show, Back dismisses it.
        # Everything else works as normal (a channel change replaces the pop-up).
        if self.digits or not (GUIDE_KEYS.get(keyname) == "Enter" or keyname in BACK_KEYS):
            return False
        status = overlay("/status")
        ch = status.get("reminder") if status else None
        if not ch or status.get("open"):
            return False
        overlay("/reminder/dismiss")
        if keyname in BACK_KEYS:
            log("reminder dismissed")
        else:
            log(f"reminder: watch ch {ch}")
            self.tune(int(ch))
        return True

    def key(self, keyname):
        if (self.reminder_key(keyname) or self.overlay_key(keyname) or self.ondemand_key(keyname)
                or self.guide_key(keyname)):
            return
        if keyname in DIGITS:
            self.digit(DIGITS[keyname])
        elif keyname in KEYS:
            self.action(KEYS[keyname])
        else:
            log(f"unmapped button {keyname}")

def key_name(code):
    n = ecodes.KEY.get(code) or ecodes.BTN.get(code) or str(code)
    if isinstance(n, (list, tuple)):   # aliases, e.g. KEY_MIN_INTERESTING/KEY_MUTE: use the one we map
        return next((k for k in n if k in KEYS or k in GUIDE_KEYS or k in DIGITS), n[0])
    return n

def open_devices():
    devs = []
    for p in list_devices():
        try:
            d = InputDevice(p)
        except OSError:
            continue
        if REMOTE_NAME.lower() in d.name.lower() and ecodes.EV_KEY in d.capabilities():
            try:
                d.grab()        # keep presses out of the desktop / web pages
            except OSError as e:
                log(f"could not grab {d.name}: {e}")
            devs.append(d)
    return devs

def start_web(remote):
    # Phone remote. Buttons send evdev key names (/key/KEY_UP), so a web press goes through
    # exactly the same routing as the MX3 (guide overlay, On Demand, i-Guide, digits).
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/remote"):
                try:
                    with open(WEB_PAGE, "rb") as f:
                        self._send(200, f.read(), "text/html; charset=utf-8")
                except OSError:
                    self._send(500, '{"error": "page missing"}')
            elif path == "/status":
                s = api("/player/status") or {}
                o = overlay("/status") or {}
                self._send(200, json.dumps({"channel": s.get("channel_number"), "network": s.get("network_name"),
                                            "title": s.get("title"), "guide": bool(o.get("open")),
                                            "od": o.get("od") or ""}))
            else:
                self._send(404, '{"error": "not found"}')

        def do_POST(self):
            path = self.path.split("?")[0]
            name = path[len("/key/"):] if path.startswith("/key/") else ""
            if name and (name in KEYS or name in DIGITS or name in GUIDE_KEYS):
                log(f"web {name}")
                remote.key(name)
                self._send(200, '{"ok": true}')
            else:
                self._send(400, '{"error": "unknown key"}')

        def log_message(self, *args):
            pass

    HTTPServer.allow_reuse_address = True
    try:
        srv = HTTPServer(("0.0.0.0", WEB_PORT), Handler)
    except OSError as e:
        log(f"web remote not started: {e}")
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"web remote on port {WEB_PORT}")

def main():
    remote = Remote()
    start_web(remote)
    while True:
        devs = open_devices()
        if not devs:
            time.sleep(3)
            continue
        log("listening on: " + ", ".join(f"{d.name} ({d.path})" for d in devs))
        fds = {d.fd: d for d in devs}
        try:
            while True:
                r, _, _ = select.select(fds, [], [], 5)
                for fd in r:
                    for e in fds[fd].read():
                        if e.type == ecodes.EV_KEY and e.value == 1:   # press only, no auto-repeat
                            remote.key(key_name(e.code))
        except OSError:
            log("remote dongle disconnected, waiting for it to come back")
            for d in devs:
                try:
                    d.close()
                except Exception:
                    pass
            time.sleep(3)

if __name__ == "__main__":
    main()
