"""Child-process scenario for the 0xC0000409 fatal AT INTERPRETER EXIT.

Retires a still-running, uninterruptible cover-extraction QThread exactly
like closeEvent does (MetadataController.stop() detaches it and parks the
(thread, worker) pair in _ORPHAN_THREADS), then ENDS THE EVENT LOOP and
lets Python finalization run — no os._exit shortcut.

Module-global retention lists are cleared during finalization; the pair's
last reference can therefore drop while the thread is still running ->
C++ ~QThread() -> qFatal("Destroyed while thread is still running") ->
fastfail 0xC0000409. With the finalization guard registered by the
modules themselves, atexit runs before the globals are cleared and the
process hard-exits 0 instead.

Invoked by tests/test_qthread_lifecycle.py as a subprocess; not a test.
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

TMPDIR = tempfile.mkdtemp(prefix="hicloudmp-teardown-child-")
platformdirs.user_data_dir = lambda *a, **k: TMPDIR   # type: ignore

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication        # noqa: E402
from PySide6.QtCore import QTimer, QSettings      # noqa: E402

from hicloudmp.ui import player as player_mod          # noqa: E402
from hicloudmp.core import metadata as metadata_mod      # noqa: E402

INI = os.path.join(TMPDIR, "settings.ini")


def qf(*a, **k):
    return QSettings(INI, QSettings.IniFormat)


player_mod.QSettings = qf
_s = qf()
_s.setValue("volume", 0)
_s.setValue("web_interface", False)
_s.sync()

# Block the extraction for far longer than the scenario window: abort()
# cannot interrupt a blocking call, the worst case for the lifecycle bug.
metadata_mod.CoverExtractor.extract_cover = (
    lambda source, is_url=False, **_kw: time.sleep(30))

qapp = QApplication(sys.argv)
mp = player_mod.MusicPlayer()
qapp.processEvents()

STATE = {}


def poll_running():
    th = mp.meta._cover_thread
    if th is not None and th.isRunning():
        STATE["thread"] = th
        detach_now()
        return
    if STATE.get("steps", 0) > 80:  # ~2 s of 25 ms polls
        print("[child] cover thread never started", flush=True)
        os._exit(9)
    STATE["steps"] = STATE.get("steps", 0) + 1
    QTimer.singleShot(25, poll_running)


def detach_now():
    th = STATE["thread"]
    running_before = th.isRunning()
    mp.meta.stop()  # closeEvent pathway: retire/detach, thread still running
    orphans = len(metadata_mod._ORPHAN_THREADS)
    detached = (th.parent() is None)
    print(f"[child] before stop running={running_before} "
          f"after running={th.isRunning()} detached={detached} "
          f"orphans={orphans}", flush=True)
    if orphans != 1:
        print("[child] pair not retained - scenario invalid", flush=True)
        os._exit(9)
    QTimer.singleShot(300, qapp.quit)  # end the loop -> finalization runs


QTimer.singleShot(300, lambda: mp.meta._start_cover_art_fetch(
    "probe-src", False))
QTimer.singleShot(400, poll_running)
# Watchdog: if anything wedges (no crash, no clean exit), die non-zero.
QTimer.singleShot(8000, lambda: os._exit(9))

qapp.exec()
# NO os._exit here on purpose: interpreter teardown is the crash site.
