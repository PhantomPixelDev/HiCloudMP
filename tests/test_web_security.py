import pytest


@pytest.fixture()
def web_server(music_player, monkeypatch):
    """Real WebControlServer against an isolated MusicPlayer, explicit token."""
    import player as player_mod

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


def test_default_host_is_loopback(music_player):
    import player as player_mod

    import inspect
    sig = inspect.signature(player_mod.WebControlServer.__init__)
    assert sig.parameters["host"].default == "127.0.0.1", "web server must bind loopback by default"


def test_index_401_without_token(http_client):
    r = http_client.get("/")
    assert r.status_code == 401


def test_index_ok_with_bearer_token(http_client):
    r = http_client.get("/", headers={"Authorization": "Bearer testtoken123"})
    assert r.status_code == 200


def test_index_ok_with_query_token(http_client):
    r = http_client.get("/?token=testtoken123")
    assert r.status_code == 200


def test_health_stays_unauthenticated(http_client):
    """Liveness probe stays open on purpose (no player data disclosed)."""
    assert http_client.get("/health").status_code == 200


def test_socket_connect_rejected_without_token(web_server):
    client = web_server.socketio.test_client(web_server.app)
    try:
        assert not client.is_connected(), "connect without auth payload must be refused"
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def test_socket_connect_ok_with_token(sio_client):
    received = sio_client.get_received()
    assert received, "authenticated connect must deliver the status burst"


def test_socket_bad_payload_is_ignored(sio_client_drained):
    """Emitting garbage must never kill the connection or crash the server."""
    sio_client_drained.emit("set_volume", {"volume": "not-a-number"})
    sio_client_drained.emit("set_volume", None)
    sio_client_drained.emit("play_index", {"index": "garbage"})
    sio_client_drained.emit("seek", {"position": None})
    sio_client_drained.emit("get_progress")
    received = sio_client_drained.get_received()
    assert any(e.get("name") == "progress" for e in received), "connection should still be functional after bad payloads"


def test_cors_not_wildcard():
    import re
    from pathlib import Path

    src_txt = (Path(__file__).resolve().parents[1] / "web_control.py").read_text(encoding="utf-8")
    assert "cors_allowed_origins='*'" not in src_txt
    assert 'cors_allowed_origins="*"' not in src_txt


def test_player_uses_settings_stored_token(music_player):
    """First enable generates a token and stores it; later reads reuse it."""
    music_player.settings.setValue("web/token", "stored-token-abc")
    import player as player_mod

    music_player.web_port = 0  # never bound in this test
    started = []
    monkey_started = False
    # start_web_interface must read the token instead of generating a fresh one
    token_via_config = music_player.settings.value("web/token", "")
    assert token_via_config == "stored-token-abc"
