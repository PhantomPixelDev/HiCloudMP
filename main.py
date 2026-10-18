import sys
import os
import json
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

# Import custom modules
from utils import HAS_WIN32
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

    # Unified theme: Dark/Light + accent + density resolved from QSettings
    theme.apply_app_theme(app, settings=QSettings("HiCloudMP", "HiCloudMP"))
    
    player = MusicPlayer()
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