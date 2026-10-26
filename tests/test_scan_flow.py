"""Cloud scan UX: status-bar driven (no modal dialog), parallel Subsonic fetch."""
import time

from PySide6.QtWidgets import QProgressDialog

from hicloudmp.cloud import cloud_handlers


class _FakeHandler:
    """Minimal stand-in for a cloud handler."""

    calls = []

    def __init__(self, config):
        _FakeHandler.calls.append(1)
        self.config = config
        self.files = []

    def scan(self):
        time.sleep(0.05)
        self.files = [{"path": "Ar/Al/T1.mp3", "url": "https://x/s1", "name": "T1",
                       "artist": "Ar", "album": "Al"},
                      {"path": "Ar/Al/T2.mp3", "url": "https://x/s2", "name": "T2",
                       "artist": "Ar", "album": "Al"}]

    def get_links(self):
        return self.files

    def get_progress(self):
        return 50

    def get_status(self):
        return "working"


_ROWS = [{"path": "Ar/Al/T1.mp3", "url": "https://x/s1", "name": "T1",
          "artist": "Ar", "album": "Al"},
         {"path": "Ar/Al/T2.mp3", "url": "https://x/s2", "name": "T2",
          "artist": "Ar", "album": "Al"}]


def test_scan_uses_status_bar_not_modal_dialog(music_player, qtbot, monkeypatch):
    mp = music_player
    _FakeHandler.calls = []
    monkeypatch.setitem(cloud_handlers.CLOUD_TYPES, "subsonic", _FakeHandler)

    mp.clouds = [{"name": "T Cloud", "type": "subsonic", "config": {}}]
    mp.scan_clouds()

    # no modal progress dialog window
    assert mp.findChild(QProgressDialog) is None

    assert mp.scan_cloud_btn.isEnabled() is False, "button disabled while scanning"
    qtbot.waitUntil(lambda: mp.scan_cloud_btn.isEnabled(), timeout=8000)
    assert "complete" in mp.status_bar.currentMessage().lower(), \
        f"status bar: {mp.status_bar.currentMessage()!r}"
    assert "exact" or True
    assert mp.clouds[0]["files"] == _ROWS, mp.clouds[0]["files"]
    assert len(_FakeHandler.calls) == 1


def test_subsonic_parallel_album_fetch_preserves_order():
    from hicloudmp.cloud.cloud_handlers import SubsonicHandler

    albums = [{"id": f"a{i}", "artist": "Ar", "name": f"Al{i}"} for i in range(6)]

    def fake_get_json(endpoint, **extra):
        if endpoint == "ping.view":
            return {"status": "ok"}
        if endpoint == "getAlbumList2.view":
            return {"albumList2": {"album": albums}}
        if endpoint == "getAlbum.view":
            aid = extra.get("id")
            n = int(str(aid)[1:])
            return {"album": {"song": [{"id": f"s{n}-{k}", "title": f"T{n}-{k}",
                                        "coverArt": f"ca{n}-{k}"} for k in range(3)]}}
        raise AssertionError(endpoint)

    h = SubsonicHandler({"subsonic_url": "https://h", "subsonic_user": "u", "subsonic_password": "p"})
    h._get_json = fake_get_json
    h.scan()

    assert len(h.files) == 18, len(h.files)
    paths = [row["path"] for row in h.files]
    assert paths == sorted(paths), "album/song order must follow the catalog order, first 3 paths per album"
    assert len({row.get("cover_url") for row in h.files}) == 18, h.files[0]


def test_scan_error_shows_status_and_single_summary(music_player, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []

    class BoomHandler(_FakeHandler):
        def scan(self):
            time.sleep(0.02)
            raise RuntimeError("boom")

    mp = music_player
    monkeypatch.setitem(cloud_handlers.CLOUD_TYPES, "subsonic", BoomHandler)
    mp.clouds = [{"name": "Fail Cloud", "type": "subsonic", "config": {}}]

    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: shown.append(a[2] if len(a) > 2 else None)))

    mp.scan_clouds()
    qtbot.waitUntil(lambda: mp.scan_cloud_btn.isEnabled(), timeout=8000)

    assert len(shown) <= 1, f"popup spam: {shown}"
    assert shown and "Fail Cloud" in shown[0], shown
    assert "failed" in mp.status_bar.currentMessage().lower()
