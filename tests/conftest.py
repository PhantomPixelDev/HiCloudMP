import gc
import os
import sys
import types
import tempfile
from pathlib import Path

import pytest

# Make the repo root importable (tests are executed from the repo root,
# but this also supports running pytest from an IDE with another CWD).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Headless Qt for CI and for developers; must be set before QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Qt 6.10.3 + PySide6: an unparented QMediaPlayer/QAudioOutput can only be
# freed by the cyclic collector (signal connections to bound methods put
# them in a cycle), and that dealloc crashes the interpreter on audio-less
# headless runners - faulthandler showed "Garbage-collecting" inside
# MusicPlayer.__init__ (ledger runs 40229404221 / 40231898041). Disabling
# the cyclic collector for the session keeps refcount teardown at its
# deterministic points and leaves cycles for interpreter exit, where the CI
# verdict comes from the junit report (tools/junit_gate.py) rather than the
# process exit code. Restoring Qt-side ownership was tried and made it
# worse: the deferred delete then ran inside a later test's event loop and
# segfaulted deterministically.
gc.disable()

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


@pytest.fixture()
def music_player(qtbot, monkeypatch):
    """Fully isolated MusicPlayer: offscreen Qt, stubbed user dirs, no registry writes."""
    from hicloudmp.ui import player as player_mod

    monkeypatch.setattr(player_mod, "QSettings", isolated_qsettings_factory(monkeypatch))
    mp = player_mod.MusicPlayer()
    qtbot.addWidget(mp)
    return mp


# ---- shared web-server fixtures (usable from any test module) ----

@pytest.fixture()
def web_server(music_player, monkeypatch):
    """Real WebControlServer against an isolated MusicPlayer, explicit token."""
    from hicloudmp.ui import player as player_mod

    server = player_mod.WebControlServer(music_player, host="127.0.0.1", port=5000, token="testtoken123")
    yield server
    server.stop()


@pytest.fixture()
def http_client(web_server):
    return web_server.app.test_client()


@pytest.fixture()
def sio_client(web_server):
    """Authenticated client; the status burst is available to the test (not pre-drained)."""
    client = web_server.socketio.test_client(web_server.app, auth={"token": "testtoken123"})
    yield client
    try:
        client.disconnect()
    except Exception:
        pass


@pytest.fixture()
def sio_client_drained(sio_client):
    sio_client.get_received()
    return sio_client


def isolated_qsettings_factory(monkeypatch):
    """Return a factory usable as monkeypatch.setattr(player_mod, "QSettings", factory).

    The app constructs QSettings("HiCloudMP", "HiCloudMP"), which on Windows targets
    HKCU\\Software (the native format). For tests every QSettings instance is redirected
    to a FRESH IniFormat file under the session dir, so tests neither read nor write the
    user's real registry configuration, and settings set in one test cannot leak into
    the next music_player construction (e.g. the saved web_interface autostart flag).
    """
    import uuid

    from PySide6.QtCore import QSettings as _QSettings

    # PySide6 6.10 removed QSettings.setFormat/setPath (deprecated in Qt 6.9).
    # Equivalent isolation: rewrite every construction to a file-backed
    # IniFormat instance unique to this factory call.
    root = _session_appdata / "settings" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    ini_file = str(root / "HiCloudMP.ini")

    def _factory(*args, **kwargs):
        return _QSettings(ini_file, _QSettings.IniFormat)

    return _factory

