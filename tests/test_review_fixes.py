import threading
import time
import wave

from PySide6.QtMultimedia import QMediaPlayer

import pytest

# ---- Important 1: stale stream handler must not hijack later local tracks ----

def _make_wav(path, seconds=0.25, rate=8000):
    silence = b"\x80\x00" * int(rate * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x00\x40")
        w.writeframes(silence)
    return path


def test_local_end_of_media_not_hijacked_by_stale_stream_handler(music_player, monkeypatch, qtbot, tmp_path):
    """After a cloud-stream attempt, the stream retry closure stays attached and
    every later local EndOfMedia re-schedules a stream retry (playback hijack).
    play()'s LOCAL branch must first disconnect the stream-only handlers."""
    retry_spy = []

    def spy(url, name, immediate=False):
        retry_spy.append((url, name))

    monkeypatch.setattr(music_player, "_schedule_stream_retry", spy)

    wav1 = _make_wav(tmp_path / "t1.wav")
    music_player.playlist = [str(wav1)]
    music_player.playlist_widget.clear()
    music_player.playlist_widget.addItem(wav1.name)

    music_player._play_stream("http://0.0.0.0:9/unreachable.wav", "unreachable")
    music_player.current_index = 0
    music_player.play()

    with qtbot.waitSignal(music_player.player.mediaStatusChanged, timeout=15000,
                          check_params_cb=lambda s: s == QMediaPlayer.MediaStatus.EndOfMedia):
        pass

    qtbot.wait(200)  # allow any (wrong) retry QTimer side effects
    assert retry_spy == [], f"stale stream handler hijacked local EndOfMedia: {retry_spy}"


# ---- Important 2: add_cloud must persist config edits (deep snapshot) ----

class _ConfigEditStubDialog:
    """Edits an EXISTING cloud account's config in place; name/type unchanged."""

    def __init__(self, parent, clouds):
        if clouds:
            clouds[0]["config"]["webdav_password"] = "changed-secret"
        self.parent_ref = parent

    def exec(self):
        return 1


def test_add_cloud_saves_config_edits(qtbot, monkeypatch, music_player):
    import player as player_mod

    music_player.clouds = [{"type": "webdav", "name": "Box", "config": {"webdav_password": "orig"}, "files": [], "last_sync": "Never"}]
    monkeypatch.setattr(player_mod, "CloudAccountsDialog", _ConfigEditStubDialog)
    saved = []
    monkeypatch.setattr(music_player, "save_clouds", lambda: saved.append(1))
    monkeypatch.setattr(music_player, "update_library_tree", lambda: None)

    music_player.add_cloud()

    assert saved == [1], "credential/config edits (name/type unchanged) must trigger save_clouds"


# ---- Important 3: open_web_panel auto-start branch must carry the token ----

class _StubWebServer:
    def __init__(self, *a, **k):
        self.token = "stub-token-xyz"

    def start(self): pass

    def stop(self): pass


def test_open_web_panel_auto_start_branch_carries_token(music_player, qtbot, monkeypatch):
    import web_control as web_control_mod

    urls = []
    monkeypatch.setattr(web_control_mod, "WebControlServer", _StubWebServer)
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda u: urls.append(u))
    music_player.settings.setValue("web_interface", True)
    music_player.web_server = None

    music_player.open_web_panel()

    music_player.web_server = None  # stub does not hold a real thread
    assert urls and "token=stub-token-xyz" in urls[0], \
        f"panel URL must carry the token: {urls}"


# ---- Important 4: switch_playlist rejects non-dict payloads ----

def test_switch_playlist_bad_payload_is_ignored(sio_client_drained):
    sio_client_drained.emit("switch_playlist", None)
    sio_client_drained.emit("switch_playlist", "not-a-dict")
    sio_client_drained.emit("get_progress")
    received = sio_client_drained.get_received()
    assert any(e.get("name") == "progress" for e in received), \
        "malformed switch_playlist must not kill the connection"


# ---- Important 5: stop() must not block close with a 2 s join ----

def test_stop_does_not_block_on_join(web_server_holder, monkeypatch):
    server, music_player = web_server_holder

    release = threading.Event()

    def fake_run(*_a, **_k):
        release.wait(5)

    def fake_shutdown():
        release.set()

    monkeypatch.setattr(server.socketio, "run", fake_run)
    monkeypatch.setattr(server.socketio.server, "shutdown", fake_shutdown)

    server.start()
    server._thread.join(1.0)
    assert server._thread.is_alive()

    t0 = time.perf_counter()
    server.stop()
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.5, f"stop() waited {elapsed:.2f}s — join must not block close"
    deadline = t0 + 3
    while time.perf_counter() < deadline and server._thread.is_alive():
        time.sleep(0.05)
    assert not server._thread.is_alive(), "server loop still exits once shutdown is signalled"


@pytest.fixture()
def web_server_holder(music_player):
    import player as player_mod

    server = player_mod.WebControlServer(music_player, host="127.0.0.1", port=5000, token="tok")
    return server, music_player


# ---- Minor (branch-introduced): exactly one play handler registration ----

def test_single_play_handler_registration():
    src_txt = (__import__("pathlib").Path(__file__).resolve().parents[1] / "web_control.py").read_text(encoding="utf-8")
    assert src_txt.count("@self.socketio.on('play')") == 1, "duplicate play handler registration"
