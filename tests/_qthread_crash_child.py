"""Child-process scenario for the QThread-destroyed-while-running crash.

Drives the production MusicPlayer._download_and_play() twice in a row with
the first download still in flight (slow stand-in worker). With the fixed
code the replacement RETIRES the running thread (keeps references) and the
process survives; exit code 0. With the old code the second call dropped
the last reference to a RUNNING QThread, and C++ ~QThread() called
qFatal -> abort -> exit code 0xC0000409 (STATUS_STACK_BUFFER_OVERRUN).

Invoked by tests/test_qthread_lifecycle.py in a subprocess; not a test
itself. Prints SURVIVED on success and exits via os._exit to skip
interpreter teardown.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import platformdirs  # noqa: E402

TMPDIR = tempfile.mkdtemp(prefix="hicloudmp-qthread-child-")
platformdirs.user_data_dir = lambda *a, **k: TMPDIR   # type: ignore

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                # noqa: E402
from PySide6.QtCore import QTimer, QSettings, QObject, Signal  # noqa: E402

import player as player_mod                                # noqa: E402

INI = os.path.join(TMPDIR, "settings.ini")


def qf(*a, **k):
    return QSettings(INI, QSettings.IniFormat)


player_mod.QSettings = qf
_s = qf()
_s.setValue("volume", 0)
_s.setValue("web_interface", False)
_s.sync()


class _SleepyDownloadWorker(QObject):
    """Blocks its run() far longer than the scenario window; abort() cannot
    interrupt the sleep (the worst case for the lifecycle bug)."""

    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, url, path, auth=None):
        super().__init__()
        self.path = path
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        time.sleep(20)


player_mod.DownloadWorker = _SleepyDownloadWorker

qapp = QApplication(sys.argv)
mp = player_mod.MusicPlayer()
qapp.processEvents()


def _start_second():
    # First download's thread is still running at this point.
    mp._download_and_play("http://127.0.0.1/x/two.mp3", "webdav", {},
                          "two.mp3")
    print("SURVIVED", flush=True)
    os._exit(0)


QTimer.singleShot(300, lambda: mp._download_and_play(
    "http://127.0.0.1/x/one.mp3", "webdav", {}, "one.mp3"))
QTimer.singleShot(900, _start_second)
# Watchdog: if anything wedges (no crash, no success), exit non-zero.
QTimer.singleShot(8000, lambda: os._exit(9))

qapp.exec()
