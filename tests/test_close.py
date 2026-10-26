import threading

from sourcepaths import read


def test_no_legacy_shutdown_call_left():
    """The legacy dead-code block calling a nonexistent WebControlServer.shutdown()
    must stay deleted."""
    player_src = read("ui/player.py")
    web_src = read("web/web_control.py")
    assert "web_server.shutdown()" not in player_src, "dead shutdown() call reintroduced in closeEvent"
    assert "def shutdown" not in web_src, "placeholder shutdown() reintroduced in WebControlServer"


def test_web_server_stop_is_idempotent(music_player):
    """stop() must be callable from any state, twice, without raising."""
    from hicloudmp.ui import player as player_mod

    server = player_mod.WebControlServer(music_player)
    server.stop()
    server.stop()
    assert server._running is False


def test_stop_terminates_server_thread(music_player, monkeypatch):
    """Real behavioral gap: stop() must signal the server loop so its thread exits,
    instead of letting the daemon thread run until process death."""
    from hicloudmp.ui import player as player_mod

    server = player_mod.WebControlServer(music_player)

    release = threading.Event()

    def fake_run(*_args, **_kwargs):
        release.wait(5)  # fake server loop: runs until shutdown() fires

    def fake_shutdown():
        release.set()

    monkeypatch.setattr(server.socketio, "run", fake_run)
    monkeypatch.setattr(server.socketio.server, "shutdown", fake_shutdown)

    server.start()
    server._thread.join(1.0)
    assert server._thread.is_alive(), "sanity: fake server loop is running before stop()"

    server.stop()
    server._thread.join(3.0)
    assert not server._thread.is_alive(), "stop() must signal the server loop and let the thread exit"
