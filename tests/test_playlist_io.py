"""Playlist import/export: M3U/M3U8, PLS and XSPF.

No repo codepath was able to read or write any playlist file; users' work
(zotan libraries built elsewhere, MTP playlists, other players) could not
enter or leave the app. This module is the format engine; the UI hookup
lands as its own change.
"""
import pytest

from playlist_io import PlaylistIO


def _write(path, text, encoding="utf-8"):
    path.write_text(text, encoding=encoding)


def test_import_m3u8_unicode_and_extinf(tmp_path):
    p = tmp_path / "mix.m3u8"
    _write(p, "#EXTM3U\n"
              "#EXTINF:213,Tede – Ścieżka Dźwiękowa\n"
              "../Music/Tede/01. Intro.mp3\n"
              "https://server.example/stream.mp3\n")

    res = PlaylistIO.import_playlist(str(p))

    assert res["format"] == "m3u"
    e1, e2 = res["entries"]
    assert e1["path"] == "../Music/Tede/01. Intro.mp3"
    assert e1["title"] == "Tede – Ścieżka Dźwiękowa"
    assert e1["duration"] == 213
    assert e2["path"] == "https://server.example/stream.mp3"
    assert e2["title"] is None and e2["duration"] is None


def test_import_m3u_legacy_cp1252_fallback(tmp_path):
    p = tmp_path / "old.m3u"
    _write(p, "#EXTM3U\n"
              "#EXTINF:-1,Björn\n"
              "01. First.mp3\n"
              "#EXTINF:-1,Yuno\n"
              "02.\t22 Gibony.mp3\n", encoding="cp1252")

    res = PlaylistIO.import_playlist(str(p))

    assert [e["path"] for e in res["entries"]] == ["01. First.mp3",
                                                  "02.\t22 Gibony.mp3"]
    assert res["entries"][0]["title"] == "Björn"


def test_m3u8_export_import_roundtrip_stays_lossless(tmp_path):
    entries = [
        {"path": str(tmp_path / "album/Tede – 01. Intro.mp3"),
         "title": "Tede – Title, with comma", "duration": 213},
        {"path": "https://server.example/stream", "title": None, "duration": None},
    ]
    out = tmp_path / "out.m3u8"

    n = PlaylistIO.export_playlist(str(out), entries, base_dir=str(tmp_path))

    assert n == 2
    back = PlaylistIO.import_playlist(str(out))
    assert back["entries"][0]["path"] == "album/Tede – 01. Intro.mp3"  # relative inside base
    assert back["entries"][0]["title"] == "Tede – Title, with comma"
    assert back["entries"][0]["duration"] == 213
    assert back["entries"][1]["path"] == "https://server.example/stream"


def test_pls_import_maps_file_title_length(tmp_path):
    p = tmp_path / "vmix.pls"
    _write(p, "[playlist]\n"
              "File1=D:/Music/a.mp3\n"
              "Title1=Song A\n"
              "Length1=185\n"
              "File2=https://radio.example/live\n"
              "Title2=\n"
              "Length2=-1\n"
              "NumberOfEntries=2\n"
              "Version=2\n")

    res = PlaylistIO.import_playlist(str(p))

    assert res["format"] == "pls"
    a, b = res["entries"]
    assert a == {"path": "D:/Music/a.mp3", "title": "Song A", "duration": 185}
    assert b["path"] == "https://radio.example/live"
    assert b["title"] is None and b["duration"] is None


def test_pls_index_holes_and_order(tmp_path):
    p = tmp_path / "gap.pls"
    _write(p, "[playlist]\nFile1=first.mp3\nFile3=third.mp3\nNumberOfEntries=2\n")

    res = PlaylistIO.import_playlist(str(p))

    assert [e["path"] for e in res["entries"]] == ["first.mp3", "third.mp3"]


def test_pls_export_import_roundtrip(tmp_path):
    entries = [
        {"path": "C:/Music/Tede/x.mp3", "title": "X", "duration": 42},
        {"path": "https://r/f", "title": None, "duration": None},
    ]
    out = tmp_path / "list.pls"

    PlaylistIO.export_playlist(str(out), entries)

    back = PlaylistIO.import_playlist(str(out))
    assert [e["path"] for e in back["entries"]] == [e["path"] for e in entries]
    assert back["entries"][0]["title"] == "X"
    assert back["entries"][0]["duration"] == 42


def test_xspf_import_reads_namespaced_location(tmp_path):
    p = tmp_path / "lib.xspf"
    _write(p, '<?xml version="1.0" encoding="UTF-8"?>\n'
              '<playlist xmlns="http://xspf.org/ns/0/" version="1" trackCount="1">\n'
              '  <trackList>\n'
              '    <track><location>https://server/get?id=1</location>'
              '<title>Tede – G.R.U.B.Y.</title><duration>214000</duration></track>\n'
              '    <track><location>file:///C:/Music/Tede%20%E2%80%93%20Sciezka/02.mp3</location></track>\n'
              '  </trackList>\n'
              '</playlist>\n')

    res = PlaylistIO.import_playlist(str(p))

    assert res["format"] == "xspf"
    a, b = res["entries"]
    assert a["path"] == "https://server/get?id=1"
    assert a["title"] == "Tede – G.R.U.B.Y."
    assert a["duration"] == 214
    import ntpath
    assert ntpath.normpath(b["path"]).lower() == "c:\\music\\tede – sciezka\\02.mp3"


def test_xspf_windows_drive_uri_posix_hosts(monkeypatch):
    r"""Windows playlists travel: file:///C:/... must land as the same
    Windows filespec even on macOS/Linux, where POSIX url2pathname keeps
    the leading "/" of the URI (regression: linux CI saw backslash-C:\...)."""
    import playlist_io as pio
    from urllib.parse import unquote as _unquote

    # Simulate the POSIX url2pathname (unquote only, keeps the slash).
    monkeypatch.setattr(pio, "url2pathname", lambda p: _unquote(p), raising=False)
    got = pio.PlaylistIO._location_to_path("file:///C:/Music/Tede/02.mp3")
    assert got == "C:/Music/Tede/02.mp3", got


def test_xspf_export_import_roundtrip(tmp_path):
    entries = [
        {"path": "C:/M/T.mp3", "title": "T", "duration": 61},
        {"path": "https://s/x", "title": None, "duration": None},
    ]
    out = tmp_path / "out.xspf"

    n = PlaylistIO.export_playlist(str(out), entries)

    assert n == 2
    back = PlaylistIO.import_playlist(str(out))
    assert [e["path"] for e in back["entries"]] == [
        "C:/M/T.mp3", "https://s/x"]
    assert back["entries"][0]["title"] == "T"
    assert back["entries"][0]["duration"] == 61


def test_import_errors_are_actionable(tmp_path):
    with pytest.raises(FileNotFoundError):
        PlaylistIO.import_playlist(str(tmp_path / "nope.m3u8"))
    junk = tmp_path / "weird.m3z"
    _write(junk, "x\n")
    with pytest.raises(ValueError):
        PlaylistIO.import_playlist(str(junk))
    with pytest.raises(ValueError):
        PlaylistIO.export_playlist(str(tmp_path / "o.unk"), [{"path": "a"}][0:1])


def test_import_skips_blanks_comments_and_trailing_garbage(tmp_path):
    p = tmp_path / "rt.m3u8"
    _write(p, "#EXTM3U\n\n#This-is-a-comment\n\n  \none.mp3\n\n")
    res = PlaylistIO.import_playlist(str(p))
    assert [e["path"] for e in res["entries"]] == ["one.mp3"]
