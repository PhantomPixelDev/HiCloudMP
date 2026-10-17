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
sys.modules["platformdirs"] = _platformdirs_stub

# QSettings still targets the registry on Windows; APPDATA redirect keeps any
# env-sensitive code paths honest as well.
os.environ["APPDATA"] = str(_session_appdata)


def session_appdata() -> Path:
    """The isolated APPDATA-equivalent directory tests must run against."""
    return _session_appdata
