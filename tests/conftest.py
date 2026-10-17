import os
import sys
import tempfile
import types
from pathlib import Path

# Make the repo root importable (tests are executed from the repo root,
# but this also supports running pytest from an IDE with another CWD).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Headless Qt for CI and for developers; must be set before QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Isolate user data. utils.py calls platformdirs.user_data_dir(...) at import
# time, and on Windows platformdirs ignores env vars (it uses the Windows
# known-folders API), so the only reliable isolation point is to hand it a
# stub module that resolves into a session-local temp directory. This must
# happen before anything imports utils/player.
_session_appdata = Path(tempfile.mkdtemp(prefix="hicloudmp-tests-appdata-"))

_platformdirs_stub = types.ModuleType("platformdirs")


def _stub_user_data_dir(app_name=None, app_author=None, ensure_exists=True, **_ignored):
    target = _session_appdata / (app_name or "HiCloudMP") / (app_author or app_name or "HiCloudMP")
    target.mkdir(parents=True, exist_ok=True)
    return str(target)


_platformdirs_stub.user_data_dir = _stub_user_data_dir


def _stub_user_cache_dir(*_args, **_kwargs):
    cache = _session_appdata / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return str(cache)


_platformdirs_stub.user_cache_dir = _stub_user_cache_dir
sys.modules["platformdirs"] = _platformdirs_stub

# QSettings still targets the registry on Windows; APPDATA redirect keeps any
# env-sensitive code paths honest as well.
os.environ["APPDATA"] = str(_session_appdata)


def session_appdata() -> Path:
    """The isolated APPDATA-equivalent directory tests must run against."""
    return _session_appdata


def isolated_qsettings_factory(monkeypatch):
    """Return a factory usable as monkeypatch.setattr(player_mod, "QSettings", factory).

    The app constructs QSettings("HiCloudMP", "HiCloudMP"), which on Windows targets
    HKCU\\Software (the native format). For tests every QSettings instance is forced
    to IniFormat under the session temp dir, so tests neither read nor write the
    user's real registry configuration (e.g. the saved web_interface flag).
    """
    from PySide6.QtCore import QSettings as _QSettings

    # PySide6 6.10 removed QSettings.setFormat/setPath (deprecated in Qt 6.9).
    # Equivalent isolation: redirect every construction to a file-backed
    # IniFormat instance under the session dir, so nothing touches the registry.
    # The app only ever constructs QSettings("HiCloudMP", "HiCloudMP"), so one
    # shared ini file per session is faithful to production behavior.
    root = _session_appdata / "settings"
    root.mkdir(parents=True, exist_ok=True)
    ini_file = str(root / "HiCloudMP.ini")

    def _factory(*args, **kwargs):
        return _QSettings(ini_file, _QSettings.IniFormat)

    return _factory

