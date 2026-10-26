"""Hardening (P4): corrupt-file handling must not stop the queue, and a
close must never be hijacked by one broken subsystem.

Before: an undecodable local file (bad download, exotic codec) popped a
MODAL critical box in the middle of playlist auto-advance - the queue
stopped requiring a click even though the next track was seconds away;
and closeEvent ran subsystem teardown unguarded after the EQ round's
stub-teardown trails showed AttributeErrors could tear a close half
through (state saves after the breakage point were silently skipped).
"""
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtMultimedia import QMediaPlayer


class _Facade:
    """Delegating stand-in that KEEPS the real object referenced.

    Plain SimpleNamespace replacement drops the last Python reference to
    the live QMediaPlayer / EQEngine - PySide then destroys the C++
    object while the media backend still touches it, which is an access
    violation class crash of the whole test process (observed 0xC0000005
    in suite runs). Every override here routes to the facade; everything
    else delegates to the kept-alive real object.
    """

    def __init__(self, real, **overrides):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, name):
        try:
            return self._overrides[name]
        except KeyError:
            return getattr(self._real, name)


def _seed(mp, names, current=0):
    mp.playlist = [str(n) for n in names]
    mp.playlist_widget.clear()
    for n in names:
        mp.playlist_widget.addItem(str(n))
    mp.current_index = current


@pytest.fixture
def toast_spy(music_player, monkeypatch):
    mp = music_player
    toasts = []

    class _Icon:
        def showMessage(self, *a, **k):
            toasts.append((str(a[0]), str(a[1])))

    monkeypatch.setattr(mp, "tray",
                        SimpleNamespace(tray_icon=_Icon()), raising=False)
    return mp, toasts


def test_invalid_media_local_never_modals(toast_spy, monkeypatch):
    mp, toasts = toast_spy
    modals = []
    monkeypatch.setattr(
        mp, "player", _Facade(mp.player, stop=lambda: None), raising=False)
    from hicloudmp.ui.player import QMessageBox as player_QMessageBox

    class _Box:
        @staticmethod
        def critical(*a, **k):
            modals.append(a)

    monkeypatch.setattr(player_QMessageBox, "critical", _Box)
    _seed(mp, ["badfile.mp3"], current=0)

    mp.on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia)

    assert not modals, "a corrupt file must not block the queue modally"
    assert "Could not play" in mp.status_bar.currentMessage()
    assert toasts, "corrupt-file failure must surface a tray toast"


def test_invalid_media_cloud_keeps_retry_path(toast_spy, monkeypatch):
    mp, toasts = toast_spy
    monkeypatch.setattr(mp, "player", _Facade(mp.player), raising=False)
    from hicloudmp.ui.player import QMessageBox as player_QMessageBox

    class _Box:
        @staticmethod
        def critical(*a, **k):
            raise AssertionError("cloud rows must retry, not modal")

    monkeypatch.setattr(player_QMessageBox, "critical", _Box)
    mp.playlist = [{"url": "https://x/s.mp3", "path": "s.mp3"}]
    mp.playlist_widget.addItem("s.mp3 (Cloud)")
    mp.current_index = 0
    monkeypatch.setattr(mp, "retry_current_playback",
                        lambda: None, raising=False)

    mp.on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia)

    assert "Retrying" in mp.status_bar.currentMessage()
    assert not toasts   # retry path already reports; no toast needed


def test_close_survives_broken_subsystem(toast_spy, monkeypatch):
    mp, _toasts = toast_spy
    saved = []

    def broken_save():
        raise RuntimeError("disk full mid-gc")

    monkeypatch.setattr(mp, "save_media_folders", broken_save,
                        raising=False)
    monkeypatch.setattr(mp, "save_clouds",
                        lambda: saved.append("clouds"), raising=False)
    monkeypatch.setattr(mp, "save_playlists",
                        lambda: saved.append("playlists"), raising=False)
    monkeypatch.setattr(mp, "player",
                        _Facade(mp.player, stop=lambda: None), raising=False)
    monkeypatch.setattr(mp, "eq_engine",
                        _Facade(mp.eq_engine, stop=lambda: None),
                        raising=False)
    monkeypatch.setattr(mp, "meta",
                        _Facade(mp.meta, stop=lambda: None), raising=False)
    monkeypatch.setattr(mp, "web_server", None, raising=False)

    event = QCloseEvent()
    try:
        mp.closeEvent(event)   # must not raise despite broken save
    finally:
        pass

    assert saved == ["clouds", "playlists"], \
        "state saves after the broken step must still run"
    assert event.isAccepted(), "close must still complete"


def test_engine_error_toast_refactor_keeps_surface(music_player, monkeypatch,
                                                   tmp_path):
    """Refactor guard: _engine_playback_error still toasts via the helper."""
    mp = music_player
    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    mp._using_engine = True
    mp._engine_source = ("file", str(song), "song")
    toasts = []

    class _Icon:
        def showMessage(self, *a, **k):
            toasts.append((str(a[0]), str(a[1])))

    monkeypatch.setattr(mp, "tray",
                        SimpleNamespace(tray_icon=_Icon()), raising=False)
    monkeypatch.setattr(
        mp, "player",
        _Facade(mp.player, setSource=lambda *a, **k: None,
                play=lambda: None),
        raising=False)

    mp._engine_playback_error("decoder gone")

    assert mp._using_engine is False
    assert toasts and "HiCloud MP" in toasts[0][0]
