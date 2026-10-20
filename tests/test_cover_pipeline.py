"""Cover pipeline: worker contract, cloud cover URLs, and toast behavior."""
import types

from PySide6.QtWidgets import QMenuBar  # noqa: F401  (ensures widgets initialized via conftest)

import metadata as metadata_mod
from metadata import CoverArtWorker
from PIL import Image


class _Capture:
    """Synchronous finished-signal capture for a QThread run manually."""

    def __init__(self):
        self.result = None
        worker_slots = self
        self._worker = None

    def attach(self, worker):
        self._worker = worker
        worker.finished.connect(self._on_finished)

    def _on_finished(self, data):
        self.result = data


def test_cover_worker_calls_extractor_correctly_and_emits_png(monkeypatch):
    img = Image.new("RGB", (6, 6), (200, 10, 10))
    recorded = {}

    def fake_extract(source, is_url=False, **_kw):
        recorded["source"] = source
        recorded["is_url"] = is_url
        return img

    monkeypatch.setattr(metadata_mod.CoverExtractor, "extract_cover", fake_extract)

    worker = CoverArtWorker("C:/music/song.mp3", is_url=False)
    cap = _Capture()
    cap.attach(worker)
    worker.run()  # synchronous, no real thread start

    assert recorded == {"source": "C:/music/song.mp3", "is_url": False}, recorded
    assert cap.result, "worker emitted empty bytes"
    assert cap.result.startswith(b"\x89PNG"), cap.result[:8]


def test_cover_worker_url_cover(monkeypatch):
    img = Image.new("RGB", (4, 4), (10, 200, 30))
    recorded = {}

    def fake_extract(source, is_url=False, **_kw):
        recorded["source"] = source
        recorded["is_url"] = is_url
        return img

    monkeypatch.setattr(metadata_mod.CoverExtractor, "extract_cover", fake_extract)

    worker = CoverArtWorker("https://server/cover.jpg", is_url=True)
    cap = _Capture()
    cap.attach(worker)
    worker.run()

    assert recorded == {"source": "https://server/cover.jpg", "is_url": True}, recorded
    assert cap.result and cap.result.startswith(b"\x89PNG")


def test_subsonic_rows_carry_getcoverart_url():
    from cloud_handlers import SubsonicHandler

    h = SubsonicHandler({"subsonic_url": "https://h", "subsonic_user": "u", "subsonic_password": "p"})

    def fake_get_json(endpoint, **extra):
        if endpoint == "ping.view":
            return {"status": "ok"}
        if endpoint == "getAlbumList2.view":
            return {"albumList2": {"album": [{"id": "a1", "artist": "Ar", "name": "Al"}]}}
        if endpoint == "getAlbum.view":
            return {"album": {"song": [{"id": "s1", "title": "T", "coverArt": "ca1"}]}}
        raise AssertionError(endpoint)

    h._get_json = fake_get_json
    h.scan()

    assert len(h.files) == 1
    row = h.files[0]
    assert "cover_url" in row, row
    assert "getCoverArt.view" in row["cover_url"], row
    assert "id=ca1" in row["cover_url"], row
    assert "t=" in row["cover_url"] and "s=" in row["cover_url"], \
        "cover URL must carry auth params (token auth)"
    assert "p=" not in row["cover_url"], "plaintext password never in URLs"


def test_ampache_rows_carry_art_url():
    from cloud_handlers import AmpacheHandler

    class FakeResp:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    xml_files = {
        "handshake": "<root><auth>tok</auth></root>",
        "songs": ("<root><song>"
                  "<title>T</title><url>https://h/stream?s=auth</url>"
                  "<artist><name>Ar</name></artist><album><name>Al</name></album>"
                  "<art>https://h/art/album-1.jpg</art>"
                  "</song></root>"),
    }
    state = {"calls": []}

    def fake_http_get(url, params=None, timeout=None):
        state["calls"].append(dict(params or {}))
        if "action=handshake" in url or (params or {}).get("action") == "handshake":
            return FakeResp(xml_files["handshake"])
        return FakeResp(xml_files["songs"])

    h = AmpacheHandler({"ampache_url": "https://h/ampache/server/xml.server.php",
                       "ampache_user": "u", "ampache_password": "pw"})
    h._http_get = fake_http_get
    h.scan()

    assert len(h.files) == 1, h.files
    row = h.files[0]
    assert row.get("cover_url") == "https://h/art/album-1.jpg", row


def test_update_cover_art_prefers_row_cover_url(music_player, monkeypatch):
    mp = music_player
    mp.clouds = [{"name": "Test Cloud", "config": {}, "files": [
        {"path": "Artist/Album/Song.mp3", "url": "https://s/stream?x=1",
         "cover_url": "https://s/getCoverArt?id=ca1"}]}]
    item = {"type": "cloud", "cloud_idx": 0, "file_idx": 0, "url": "https://s/stream?x=1"}

    captured = {}
    mp.meta._start_cover_art_fetch = lambda src, isu: captured.update(src=src, isu=isu)
    mp.meta.update_cover_art(item)

    assert captured == {"src": "https://s/getCoverArt?id=ca1", "isu": True}, captured


def test_no_now_playing_toasts(music_player):
    mp = music_player   # the blocking ffprobe path no longer exists at all

    calls = []

    class FakeIcon:
        def showMessage(self, *a, **k):
            calls.append(a)

    mp.tray = types.SimpleNamespace(tray_icon=FakeIcon(), update_tray_ui=lambda: None)

    mp.clouds = [{"name": "Test Cloud", "config": {}, "files": [
        {"path": "Artist/Album/Song.mp3", "url": "https://s/stream?x=1"}]}]
    mp.playlist = [{"type": "cloud", "title": "Song", "artist": "Ar", "album": "Al",
                    "cloud_idx": 0, "file_idx": 0, "url": "https://s/stream?x=1"}]
    mp.current_index = 0

    mp.meta.update_metadata_display()

    assert calls == [], f"toast spam: {len(calls)} 'Now Playing' notifications shown"


def test_metadata_display_skips_ffprobe_when_row_complete(music_player):
    import cover_extractor as cover_mod
    mp = music_player
    # Structural: no ffprobe path exists to call (see the deletion ruling).
    assert not hasattr(cover_mod.CoverExtractor, "extract_metadata")
    mp.tray = types.SimpleNamespace(tray_icon=None, update_tray_ui=lambda: None)

    mp.clouds = [{"name": "T Cloud", "config": {}, "files": [
        {"path": "A/B/S.flac", "url": "https://s/x?y=1"}]}]
    mp.playlist = [{"type": "cloud", "title": "S", "artist": "A", "album": "B",
                    "cloud_idx": 0, "file_idx": 0, "url": "https://s/x?y=1"}]
    mp.current_index = 0

    mp.meta.update_metadata_display()

    assert "S" in mp.track_title_label.text()
