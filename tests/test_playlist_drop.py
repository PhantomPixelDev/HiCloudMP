"""Explorer drop onto the playlist (P2b leftover): playlist files import
through the shared _import_playlist_file path, supported audio files
queue up at the end, junk is refused, and internal reorder drags keep
working (drag events for item views land on the viewport, not the view).

Lifetime rule (learned the hard way): QDropEvent stores a raw pointer to
the mime - the Python reference to the QMimeData MUST outlive the event,
so every call site holds it in a local named ``mime``. Passing
``_drop(_mime(...))`` inline lets shiboken destroy the mime while the
event still points at it; the next mimeData()/repr() access then takes
the whole process down with an access violation.
"""
import os

from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent


def _song(dir_path, name):
    p = dir_path / name
    p.write_bytes(b"")
    return str(p)


def _mime(paths):
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return m


def _drag_enter(mime):
    return QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime,
                           Qt.LeftButton, Qt.NoModifier)


def _drop(mime):
    return QDropEvent(QPointF(10.0, 10.0), Qt.CopyAction | Qt.MoveAction,
                      mime, Qt.LeftButton, Qt.NoModifier)


def _clear(mp):
    mp.playlist = []
    while mp.playlist_widget.count():
        mp.playlist_widget.takeItem(0)
    mp.current_index = -1


def _vp(mp):
    return mp.playlist_widget.viewport()


def test_drag_enter_accepts_audio_files(music_player, tmp_path):
    mp = music_player
    mime = _mime([_song(tmp_path, "ok.mp3")])
    ev = _drag_enter(mime)
    ev.ignore()
    handled = mp.eventFilter(_vp(mp), ev)
    assert handled is True
    assert ev.isAccepted(), "external audio drop must be welcomed"


def test_drag_enter_rejects_junk(music_player, tmp_path):
    mp = music_player
    txt = tmp_path / "notes.txt"
    txt.write_text("nope")
    mime = _mime([str(txt)])
    ev = _drag_enter(mime)
    ev.ignore()
    handled = mp.eventFilter(_vp(mp), ev)
    assert handled is False
    assert not ev.isAccepted()


def test_internal_drag_passes_through(music_player):
    mp = music_player
    mime = QMimeData()   # internal moves carry no urls
    ev = _drag_enter(mime)
    ev.ignore()
    handled = mp.eventFilter(_vp(mp), ev)
    assert handled is False, "reorder drags must not be hijacked"


def test_drop_audio_files_appends_to_queue(music_player, tmp_path):
    mp = music_player
    _clear(mp)
    a = _song(tmp_path, "a.mp3")
    b = _song(tmp_path, "b.opus")
    mime = _mime([a, b])
    ev = _drop(mime)

    handled = mp.eventFilter(_vp(mp), ev)

    assert handled is True
    assert [os.path.normcase(p) for p in mp.playlist] == \
        [os.path.normcase(a), os.path.normcase(b)]
    assert mp.playlist_widget.count() == 2
    assert mp.current_index == 0, "first drop becomes the ready track"
    assert "2" in mp.status_bar.currentMessage()


def test_drop_playlist_file_imports(music_player, tmp_path):
    mp = music_player
    _clear(mp)
    mus = tmp_path / "mus"
    mus.mkdir()
    one = _song(mus, "one.mp3")
    pl = tmp_path / "drop.m3u8"
    pl.write_text("#EXTM3U\nmus/one.mp3\n", encoding="utf-8")
    mime = _mime([str(pl)])
    ev = _drop(mime)

    handled = mp.eventFilter(_vp(mp), ev)

    assert handled is True
    assert [os.path.normcase(p) for p in mp.playlist] == \
        [os.path.normcase(one)]
    assert "Imported 1" in mp.status_bar.currentMessage()


def test_drop_mixed_playlist_and_audio(music_player, tmp_path):
    mp = music_player
    _clear(mp)
    mus = tmp_path / "mus2"
    mus.mkdir()
    one = _song(mus, "one.mp3")
    two = _song(tmp_path, "two.flac")
    pl = tmp_path / "mix.pls"
    pl.write_text("[playlist]\nFile1=mus2/one.mp3\n", encoding="utf-8")
    mime = _mime([str(pl), two])
    ev = _drop(mime)

    handled = mp.eventFilter(_vp(mp), ev)

    assert handled is True
    assert [os.path.normcase(p) for p in mp.playlist] == \
        [os.path.normcase(one), os.path.normcase(two)]
    assert mp.playlist_widget.count() == 2


def test_drop_junk_is_noop(music_player, tmp_path):
    mp = music_player
    _clear(mp)
    txt = tmp_path / "x.txt"
    txt.write_text("x")
    mime = _mime([str(txt)])
    ev = _drop(mime)
    ev.ignore()

    handled = mp.eventFilter(_vp(mp), ev)

    assert handled is False
    assert mp.playlist == []
    assert not ev.isAccepted()
