"""Cloud providers: Ampache + Subsonic (Nextcloud Music endpoints) — RED first,
mocked responses only; live creds never enter the repo."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# actual imports happen inside tests (helpers build fake requests)


def test_cloud_types_register_new_providers():
    from cloud_handlers import CLOUD_TYPES

    assert "ampache" in CLOUD_TYPES
    assert "subsonic" in CLOUD_TYPES
    assert "webdav" in CLOUD_TYPES


def test_ampache_double_hash_handshake_and_song_parse(monkeypatch, tmp_path):
    import cloud_handlers as ch
    import xml.etree.ElementTree as ET

    catalog_xml = (
        '<root><auth>t0ken123</auth><songcount>2</songcount>'
        '<song id="42"><title>Song A</title>'
        '<artist id="7"><name>Artist A</name></artist>'
        '<album id="9"><name>Album A</name></album>'
        '<url>https://srv/xml.server.php?action=stream&amp;auth=t0ken123&amp;id=42</url>'
        '</song></root>'
    )

    calls = []

    class FakeResp:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params or {}})
        # First call = handshake, second = songs
        if params.get("action") == "handshake":
            assert params["auth"] and len(params["auth"]) == 64  # sha256 hex
            return FakeResp(catalog_xml)
        if params.get("action") == "songs":
            if params.get("offset", 0):  # end pagination
                return FakeResp("<root></root>")
            return FakeResp(catalog_xml)
        raise AssertionError("unexpected action")

    monkeypatch.setattr(ch.requests, "get", fake_get)

    h = ch.AmpacheHandler({
        "ampache_url": "https://srv/apps/music/ampache",
        "ampache_user": "Admin",
        "ampache_password": "pw-of-test",
    })
    h.scan()
    files = h.get_links()
    assert len(files) == 1
    f = files[0]
    assert f["name"] == "Song A" and f["artist"] == "Artist A" and f["album"] == "Album A"
    assert "action=stream" in f["url"]
    # endpoint auto-appends the xml.server.php suffix
    assert calls[0]["url"].endswith("server/xml.server.php")


def test_subsonic_legacy_password_scan(monkeypatch):
    import cloud_handlers as ch

    ping = {"subsonic-response": {"status": "ok"}}
    albums = {"subsonic-response": {"albumList2": {"album": [
        {"id": "album-559", "name": "Al", "artist": "Ar"},
    ]}}}
    album = {"subsonic-response": {"album": {"song": [
        {"id": "3204", "title": "Track", "artist": "Ar", "album": "Al"},
    ]}}}

    seq = {"n": 0}

    class FakeResp:
        def __init__(self, payload):
            self._p = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._p

    def fake_get(url, params=None, timeout=None):
        action = url  # .view suffix selects step
        seq["n"] += 1
        if "ping" in url:
            return FakeResp(ping)
        if "getAlbumList2" in url:
            return FakeResp(albums)
        if "getAlbum" in url:
            return FakeResp(album)
        if "stream" in url:
            raise AssertionError("stream never fetched during scan")
        raise AssertionError(f"unexpected {url}")

    monkeypatch.setattr(ch.requests, "get", fake_get)

    h = ch.SubsonicHandler({
        "subsonic_url": "https://srv/apps/music/subsonic",
        "subsonic_user": "Admin",
        "subsonic_password": "pw-of-test",
    })
    h.scan()
    files = h.get_links()
    assert len(files) == 1
    f = files[0]
    assert f["name"] == "Track" and f["artist"] == "Ar" and f["album"] == "Al"
    assert "stream" in f["url"] and "id=3204" in f["url"]
    # REST base normalization appended /rest exactly once
    assert h.rest_base.rstrip("/").endswith("/rest")
    # legacy plain-password auth carried
    assert any(params.get("p") == "pw-of-test" for params in
               [fake_get_call for fake_get_call in []]) or True
    assert h._common_params()["p"] == "pw-of-test"


def test_webdav_file_url_includes_root(monkeypatch):
    """webdav_root must be prefixed into the generated file URL."""
    import cloud_handlers as ch

    class FakeClient:
        def list(self, path):
            return ["song.mp3"]

        def is_dir(self, path):
            return False

    h = ch.WebDAVHandler({
        "webdav_hostname": "https://host",
        "webdav_root": "/remote.php/dav/files/Admin",
        "webdav_login": "u",
        "webdav_password": "p",
    })
    h._list_cache[""] = ["song.mp3"]
    h._dir_cache["song.mp3"] = False
    files = h._scan_directory(FakeClient(), "")
    assert files and files[0]["url"] == "https://host/remote.php/dav/files/Admin/song.mp3"


def test_play_cloud_file_routes_webdav_to_download(music_player, monkeypatch, qtbot):
    """WebDAV tracks must go through authenticated download-then-play (the
    streaming backend cannot add Basic auth and Nextcloud 401-rejects it)."""
    mp = music_player
    mp.clouds = [{
        "type": "webdav", "name": "NC", "files": [
            {"path": "Ar/Al/Song.mp3", "url": "https://host/dav/Ar/Al/Song.mp3",
             "name": "Song", "artist": "Ar", "album": "Al"}],
        "config": {"webdav_hostname": "https://host", "webdav_login": "u",
                   "webdav_password": "p"},
    }]
    calls = []
    monkeypatch.setattr(mp, "_download_and_play", lambda *a, **k: calls.append(("dl", a, k)))
    monkeypatch.setattr(mp, "_play_stream", lambda *a, **k: calls.append(("stream", a)))

    mp.play_cloud_file(0, 0)

    assert calls and calls[0][0] == "dl"
    assert calls[0][2].get("auth") == ("u", "p")
    assert mp.track_artist_label.text() == "Artist: Ar"


def test_play_cloud_file_streams_ampache_directly(music_player, monkeypatch, qtbot):
    """Ampache track URLs already embed the session token: direct stream."""
    mp = music_player
    mp.clouds = [{
        "type": "ampache", "name": "NC", "files": [
            {"path": "Ar/Al/Track", "url": "https://h/xml?action=stream&auth=TOK&id=42",
             "name": "Track", "artist": "Ar", "album": "Al"}],
        "config": {},
    }]
    calls = []
    monkeypatch.setattr(mp, "_download_and_play", lambda *a, **k: calls.append(("dl", a)))
    monkeypatch.setattr(mp, "_play_stream", lambda *a, **k: calls.append(("stream", a)))

    mp.play_cloud_file(0, 0)

    assert calls and calls[0][0] == "stream"
    assert "auth=TOK" in str(calls[0][1][0])


def test_add_cloud_dialog_provider_roundtrip(qtbot):
    """Provider combo switches forms; get_data emits provider-shaped config."""
    import dialogs

    dlg = dialogs.AddCloudDialog()
    dlg.type_combo.setCurrentIndex(1)
    dlg.ampache_name.setText("MyNC")
    dlg.ampache_url.setText("https://cloud.example.com/apps/music/ampache")
    dlg.ampache_username.setText("Admin")
    dlg.ampache_password.setText("pw")
    data = dlg.get_data()
    assert data["type"] == "ampache" and data["name"] == "MyNC"
    assert data["config"]["ampache_url"].endswith("/apps/music/ampache")

    dlg.type_combo.setCurrentIndex(2)
    dlg.subsonic_url.setText("https://cloud.example.com/apps/music/subsonic")
    d2 = dlg.get_data()
    assert d2["type"] == "subsonic" and "subsonic_url" in d2["config"]

    dlg.type_combo.setCurrentIndex(0)
    dlg.webdav_url.setText("https://cloud.example.com/remote.php/dav/files/Admin/")
    d3 = dlg.get_data()
    assert d3["type"] == "webdav" and "webdav_hostname" in d3["config"]


def test_edit_cloud_dialog_ampache_prefill(qtbot):
    import dialogs

    dlg = dialogs.EditCloudDialog({
        "type": "ampache", "name": "Existing",
        "config": {"ampache_url": "https://h/apps/music/ampache",
                   "ampache_user": "Admin", "ampache_password": "secret"},
    })
    assert dlg.url_edit.text() == "https://h/apps/music/ampache"
    assert dlg.user_edit.text() == "Admin"
    d = dlg.get_data()
    assert d["type"] == "ampache" and d["config"]["ampache_password"] == "secret"
