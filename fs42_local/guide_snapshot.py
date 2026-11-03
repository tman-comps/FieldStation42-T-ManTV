# Render a guide page at the CRT's 720x480 in an off-screen window and save a PNG,
# without showing anything on the TV. For checking guide themes/mockups.
# Usage (FS42 venv): python fs42_local/guide_snapshot.py <url> <out.png> [wait_seconds]
import os, sys

os.environ.setdefault("DISPLAY", ":0")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-backgrounding-occluded-windows --disable-renderer-backgrounding"
    " --disable-background-timer-throttling")

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

url, out = sys.argv[1], sys.argv[2]
wait_ms = int(float(sys.argv[3]) * 1000) if len(sys.argv) > 3 else 2500

app = QApplication(sys.argv)
view = QWebEngineView()
view.setWindowFlags(Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint | Qt.Tool)
view.setGeometry(-2000, 0, 720, 480)   # off-screen: nothing appears on the TV


def save():
    ok = view.grab().save(out)
    print(f"saved {out}: {ok}")
    app.quit()


view.loadFinished.connect(lambda ok: QTimer.singleShot(wait_ms, save))
view.load(QUrl(url))
view.show()
QTimer.singleShot(wait_ms + 20000, app.quit)   # give up if the page never loads
app.exec()
