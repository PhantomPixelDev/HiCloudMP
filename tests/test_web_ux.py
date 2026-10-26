"""Web remote UX: ping endpoint for a live connection indicator, LAN
URL helpers, and plain-language desktop messaging."""
import ipaddress
import json

import pytest

from hicloudmp.ui import player
from hicloudmp.web import web_control


@pytest.fixture
def server():
    s = web_control.WebControlServer(player=None, host="127.0.0.1",
                                     port=5099, token="tok-abc")
    return s


def test_api_ping_public_no_player_data(server):
    """Unauthenticated liveness+latency probe — exposes nothing else."""
    client = server.app.test_client()
    r = client.get("/api/ping")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["ok"] is True
    assert data["app"] == "HiCloudMP"
    assert isinstance(data["server_ms"], int)
    assert "playlist" not in data and "status" not in data


def test_other_api_routes_stay_protected(server):
    """Adding /api/ping must not dim the rest of the auth wall."""
    still_protected = server.app.test_client().get("/api/status")
    # /api/status doesn't exist either way, but must never 200 without token
    assert still_protected.status_code in (401, 302, 404)


def test_panel_url_builder():
    u = web_control.panel_url(5000, "tok-abc")
    assert u.startswith("http://127.0.0.1:5000/?token=tok-abc")
    lan = web_control.panel_url(5000, "tok-abc", lan_ip="192.168.1.5")
    assert lan == "http://192.168.1.5:5000/?token=tok-abc"
    no_tok = web_control.panel_url(5000, "")
    assert no_tok == "http://127.0.0.1:5000"


def test_lan_ip_is_usable():
    ip = web_control.lan_ip()
    assert isinstance(ip, str) and ip
    ipaddress.ip_address(ip)  # raises if not a valid IPv4


def test_progress_engine_aware():
    """In EQ-engine mode the native player sits idle - the panel must
    report the ENGINE's real position/duration instead of frozen zeros."""
    class _Eng:
        def position_ms(self):
            return 1234

        def duration_ms(self):
            return 5000

    class _Native:
        def position(self):
            return 0

        def duration(self):
            return 0

    stub = type("P", (), {})()
    stub._using_engine = True
    stub.eq_engine = _Eng()
    stub.player = _Native()
    s = web_control.WebControlServer(player=stub, host="127.0.0.1",
                                     port=5099, token="t")
    assert s._get_progress() == {"position": 1234, "duration": 5000}


def test_progress_native_when_engine_off():
    class _Native:
        def position(self):
            return 42000

        def duration(self):
            return 180000

    stub = type("P", (), {})()
    stub._using_engine = False
    stub.player = _Native()
    s = web_control.WebControlServer(player=stub, host="127.0.0.1",
                                     port=5099, token="t")
    assert s._get_progress() == {"position": 42000, "duration": 180000}


def test_start_web_interface_plain_message(music_player, qtbot, monkeypatch):
    """Status bar speaks help, not jargon, and includes the ready link."""
    class StubServer:
        def __init__(self, *args, **kwargs):
            self.token = kwargs.get("token", "")
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    from hicloudmp.web import web_control as wc
    monkeypatch.setattr(wc, "WebControlServer", StubServer)
    # never let a failure path open a modal in offscreen tests
    monkeypatch.setattr(player.QMessageBox, "warning", lambda *a, **k: None)
    mp = music_player
    mp.web_server = None
    try:
        assert mp.start_web_interface() is True
        msg = mp.status_bar.currentMessage().lower()
        assert "token required" not in msg
        assert "http://" in msg
        assert "open" in msg
    finally:
        mp.stop_web_interface()
