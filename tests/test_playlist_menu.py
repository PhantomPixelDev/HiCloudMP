"""File-menu playlist import/export wiring (P2b) + P1 followup: the
add-files dialog filter must follow SUPPORTED_EXTS (it still advertised
only the old set while scanning/decoding accepted more).
"""
import os

from PySide6.QtWidgets import QFileDialog

import player as player_mod
from utils import SUPPORTED_EXTS


def _song(dir_path, name):
    p = dir_path / name
    p.write_bytes(b"")
    return str(p)


def test_add_files_dialog_filter_follows_supported_exts(music_player,
                                                        monkeypatch):
    captured = {}

    def fake(parent, title, dirn, filt):
        captured["filter"] = filt
        return ([], "")

    monkeypatch.setattr(QFileDialog, "getOpenFileNames", fake)

    mp = music_player
    mp.add_files()

    filt = captured["filter"]
    for ext in (".opus", ".m4a", ".mka", ".oga", ".aiff", ".wma"):
        assert f"*{ext}" in filt, filt
    music_section = filt.split(";;")[0]
    for ext in SUPPORTED_EXTS:
        assert f"*{ext}" in music_section, (ext, music_section)


def test_import_playlist_appends_supported_files(music_player, monkeypatch,
                                                 tmp_path):
    mp = music_player
    mp.current_index = -1
    mp.playlist = []
    while mp.playlist_widget.count():
        mp.playlist_widget.takeItem(0)

    mus = tmp_path / "mus"
    mus.mkdir()
    one = _song(mus, "one.mp3")
    _song(mus, "two.opus")
    pl_dir = tmp_path / "pl"
    pl_dir.mkdir()
    m3u = pl_dir / "mix.m3u8"
    m3u.write_text("#EXTM3U\n"
                   "../mus/one.mp3\n"
                   "../mus/two.opus\n"
                   "missing.mka\n"
                   "https://skip.example/stream\n", encoding="utf-8")

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *a, **k: (str(m3u), ""))

    mp.import_playlist()

    assert [os.path.normcase(p) for p in mp.playlist] == [
        os.path.normcase(one),
        os.path.normcase(str(mus / "two.opus"))]
    assert mp.playlist_widget.count() == 2
    assert mp.current_index == 0, "first import becomes the ready track"
    msg = mp.status_bar.currentMessage()
    assert "Imported 2" in msg, msg
    assert "2 skipped" in msg, msg


def test_import_playlist_cancel_changes_nothing(music_player, monkeypatch):
    mp = music_player
    before = list(mp.playlist)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **k: ("", ""))
    mp.import_playlist()
    assert mp.playlist == before
    assert mp.playlist_widget.count() == len(before)


def test_export_all_when_nothing_selected(music_player, monkeypatch,
                                          tmp_path):
    mp = music_player
    mp.playlist = []
    while mp.playlist_widget.count():
        mp.playlist_widget.takeItem(0)

    mus = tmp_path / "musx"
    mus.mkdir()
    a = _song(mus, "alpha.flac")
    _song(mus, "beta.mp3")
    mp.playlist = [a, str(mus / "beta.mp3"),
                   {"type": "cloud", "cloud_idx": 0, "file_idx": 0}]
    mp.playlist_widget.addItem(os.path.basename(a))
    mp.playlist_widget.addItem("beta.mp3")
    mp.playlist_widget.addItem("cloud (Cloud)")
    mp.current_index = 0

    out = tmp_path / "queue.m3u8"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(out), ""))

    mp.export_playlist()

    text = out.read_text(encoding="utf-8")
    assert "alpha.flac" in text and "beta.mp3" in text
    assert text.count("\n") >= 4  # header + 2 EXTINF + 2 paths at least
    # cloud rows are not exportable entries
    assert "cloud" not in text
    assert "cloud track" in mp.status_bar.currentMessage()


def test_export_selection_only(music_player, monkeypatch, tmp_path):
    mp = music_player
    mp.playlist = []
    while mp.playlist_widget.count():
        mp.playlist_widget.takeItem(0)

    mus = tmp_path / "sely"
    mus.mkdir()
    a = _song(mus, "first.mp3")
    b = _song(mus, "second.mp3")
    c = _song(mus, "third.mp3")
    mp.playlist = [a, b, c]
    for name in ("first.mp3", "second.mp3", "third.mp3"):
        mp.playlist_widget.addItem(name)
    mp.current_index = 0

    mp.playlist_widget.item(1).setSelected(True)

    out = tmp_path / "sel.m3u8"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(out), ""))

    mp.export_playlist()

    text = out.read_text(encoding="utf-8")
    assert "second.mp3" in text
    assert "first.mp3" not in text and "third.mp3" not in text


def test_export_cancel_writes_nothing(music_player, monkeypatch):
    mp = music_player
    mp.playlist = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: ("", ""))
    mp.export_playlist()
    # no exception and no message crash - cancelled is a no-op
    assert mp.playlist == []
