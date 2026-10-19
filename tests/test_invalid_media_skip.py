"""A corrupt local file must never stop the queue.

P4 removed the blocking modal; the queue still stopped dead at the bad
row (the status message was the end of the story). Now the bad row is
skipped: playback advances to the next entry; at the tail the player
stops with a clear end-of-playlist message. The skip is bounded by the
playlist itself - each skip moves the index forward, so no loop.
"""
import os

import pytest
from PySide6.QtMultimedia import QMediaPlayer


def _seed(mp, names, current=0):
    mp.playlist = [str(n) for n in names]
    mp.playlist_widget.clear()
    for n in names:
        mp.playlist_widget.addItem(os.path.basename(str(n)))
    mp.current_index = current


@pytest.fixture
def spy_tray(music_player, monkeypatch):
    mp = music_player
    toasts = []

    class _Icon:
        def showMessage(self, *a, **k):
            toasts.append((str(a[0]), str(a[1])))

    monkeypatch.setattr(mp, "tray",
                        type("T", (), {"tray_icon": _Icon()})(),
                        raising=False)
    return mp, toasts


def test_corrupt_track_auto_advances(spy_tray, monkeypatch, music_player):
    mp, toasts = spy_tray
    _seed(mp, ["a.mp3", "b.mp3", "c.mp3"], current=0)
    plays = []
    monkeypatch.setattr(mp, "play",
                        lambda: plays.append(mp.current_index), raising=False)

    mp.on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia)

    assert mp.current_index == 1, "queue must advance past the bad row"
    assert plays == [1], "the next track must actually start"
    assert toasts, "the failure is still reported"
    assert "Could not play" in mp.status_bar.currentMessage(), \
        mp.status_bar.currentMessage()
    assert "skip" in mp.status_bar.currentMessage().lower()


def test_corrupt_track_at_tail_stops_cleanly(spy_tray, monkeypatch,
                                             music_player):
    mp, toasts = spy_tray
    _seed(mp, ["a.mp3", "b.mp3"], current=1)
    plays = []
    monkeypatch.setattr(mp, "play",
                        lambda: plays.append(mp.current_index), raising=False)

    mp.on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia)

    assert mp.current_index == 1, "no advance past the tail"
    assert plays == [], "nothing left to play"
    msg = mp.status_bar.currentMessage().lower()
    assert "end of playlist" in msg, msg


def test_corrupt_with_empty_playlist_is_safe(spy_tray, monkeypatch,
                                             music_player):
    mp, toasts = spy_tray
    mp.playlist = []
    mp.current_index = -1
    monkeypatch.setattr(mp, "play",
                        lambda: (_ for _ in ()).throw(
                            AssertionError("must not play")), raising=False)

    mp.on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia)

    assert toasts, "still reported"
