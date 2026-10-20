import sys
import os
import tempfile
from datetime import datetime

# Crash forensics must exist before Qt/PySide load: Qt-level fatals
# (Windows 0xc0000409 fastfail) kill the process without a Python
# traceback, so every Qt message - including the fatal one that trips
# the abort - and faulthandler output are captured to a dated log next
# to the user data dir.
def _open_crash_log():
    try:
        from platformdirs import user_data_dir
        d = user_data_dir("HiCloudMP", "HiCloudMP", ensure_exists=True)
    except Exception:
        d = tempfile.gettempdir()
    path = os.path.join(d, "crashlog.txt")
    return open(path, "a", buffering=1, encoding="utf-8", errors="replace")

_crash_log = _open_crash_log()
_crash_log.write(
    f"\n===== session start {datetime.now().isoformat()} "
    f"pid={os.getpid()} =====\n")

try:
    import faulthandler
    faulthandler.enable(file=_crash_log)
except Exception:
    pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, qInstallMessageHandler, QtMsgType


def _qt_message(mode, ctx, msg):
    label = {
        QtMsgType.QtDebugMsg: "DEBUG",
        QtMsgType.QtInfoMsg: "INFO",
        QtMsgType.QtWarningMsg: "WARN",
        QtMsgType.QtCriticalMsg: "CRIT",
        QtMsgType.QtFatalMsg: "FATAL",
    }.get(mode, "?")
    where = f" ({ctx.file}:{ctx.line})" if getattr(ctx, "file", None) else ""
    try:
        _crash_log.write(f"[{label}] {msg}{where}\n")
    except Exception:
        pass
    if mode == QtMsgType.QtFatalMsg:
        _crash_log.flush()


qInstallMessageHandler(_qt_message)

# Import custom modules
from player import MusicPlayer
import theme

# MPRIS is Linux-only (dbus/gi backends). On Windows the import fails at
# mpris_dbus.py's module level, so degrade to None instead of crashing startup.
try:
    from mpris_dbus import MprisService
except Exception:
    MprisService = None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Single instance: a second launch pings the running window and exits
    # (two players would fight over the same settings/playlist files).
    from single_instance import InstanceLock
    _instance_lock = InstanceLock()
    if not _instance_lock.acquire():
        sys.exit(0)

    # Unified theme: Dark/Light + accent + density resolved from QSettings
    theme.apply_app_theme(app, settings=QSettings("HiCloudMP", "HiCloudMP"))
    
    player = MusicPlayer(startup_paths=sys.argv[1:])

    def _raise_from_second_launch():
        try:
            player.showNormal()
            player.raise_()
            player.activateWindow()
        except Exception:
            pass

    _instance_lock.activated.connect(_raise_from_second_launch)

    # Start MPRIS service for system media controls integration (separate module)
    # (import guard above sets MprisService to None where dbus/gi are missing,
    #  e.g. Windows — Windows media keys stay handled by Qt in that case)
    if MprisService is not None:
        try:
            player._mpris = MprisService(player)
            player._mpris.start()
        except Exception as e:
            # Non-fatal: continue even if MPRIS is unavailable
            print(f"MPRIS init failed: {e}")
    player.show()
    sys.exit(app.exec()) 