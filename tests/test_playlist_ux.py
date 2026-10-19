"""Playlist UX (P3): Play Next queue, duplicate cleanup, keyboard ops,
and a testable context-menu builder.

Before this round driving the live playlist was mouse-only: no Play Next
queue (auto-advance ignored anything the user wanted held back), no
duplicate cleanup, no keyboard operation, and the context menu was
built inline where tests cannot reach it.
"""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMenu


def _seed(mp, names, current=0):
    mp.playlist = [str(n) for n in names]
    mp.playlist_widget.clear()
    for n in names:
        mp.playlist_widget.addItem(str(n))
    mp.current_index = current
    return [str(n) for n in names]


def _key(key):
    return QKeyEvent(QEvent.KeyPress, key, Qt.KeyboardModifier.NoModifier)


# --- Play Next queue ---------------------------------------------------------

def test_queue_selected_play_next(music_player, monkeypatch, tmp_path):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3", "c.mp3"])

    mp.playlist_widget.item(2).setSelected(True)
    mp.queue_play_next()

    assert mp._play_next_queue == [2], mp._play_next_queue


def test_native_autoadvance_consumes_queue_before_order(
        music_player, monkeypatch):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3", "c.mp3"], current=0)
    mp.repeat_btn.setChecked(False)
    mp.shuffle_btn.setChecked(False)
    plays = []
    monkeypatch.setattr(mp, "play", lambda: plays.append(1), raising=False)

    mp.playlist_widget.item(2).setSelected(True)
    mp.queue_play_next()
    mp.on_media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)

    assert plays, "queued track must start playing"
    assert mp.current_index == 2, "queue outranks playlist order"
    assert mp._play_next_queue == [], "queue entry consumed"


def test_engine_autoadvance_consumes_queue_even_with_repeat(
        music_player, monkeypatch):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3"], current=0)
    mp.repeat_btn.setChecked(True)   # repeat must not swallow the queue
    plays = []
    monkeypatch.setattr(mp, "play", lambda: plays.append(1), raising=False)

    mp._play_next_queue = [1]
    mp._on_engine_track_finished()

    assert mp.current_index == 1 and plays and mp._play_next_queue == []
    # repeat stays checked: it resumes once the queue drains (not tested)


def test_queue_skips_stale_rows(music_player, monkeypatch):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3"], current=0)
    mp.repeat_btn.setChecked(False)
    mp.shuffle_btn.setChecked(False)
    plays = []
    monkeypatch.setattr(mp, "play", lambda: plays.append(1), raising=False)

    mp._play_next_queue = [99, 1]   # 99 outlived a removal
    mp.on_media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)

    assert mp.current_index == 1
    assert mp._play_next_queue == []


# --- duplicates ---------------------------------------------------------------

def test_remove_duplicates_keeps_first_occurrence(music_player):
    mp = music_player
    _seed(mp, ["alpha.mp3", "beta.mp3", "alpha.mp3",
               "gamma.mp3", "ALPHA.MP3"])
    mp.playlist.append({"type": "cloud", "cloud_idx": 0, "file_idx": 1})
    mp.playlist_widget.addItem("same (Cloud)")
    mp.playlist.append({"type": "cloud", "cloud_idx": 0, "file_idx": 1})
    mp.playlist_widget.addItem("dupe (Cloud)")
    mp.current_index = 4

    mp.remove_duplicates_from_playlist()

    keys = [os if False else (str(i)) for i in mp.playlist]
    paths = [p for p in mp.playlist if not isinstance(p, dict)]
    clouds = [c for c in mp.playlist if isinstance(c, dict)]
    assert len(paths) == 3, paths      # alpha, beta, gamma - one alpha only
    assert len(clouds) == 1, clouds    # same cloud row once
    assert mp.playlist_widget.count() == len(mp.playlist)
    assert mp.current_index < len(mp.playlist)


def test_remove_duplicates_noop_message(music_player):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3"])
    mp.remove_duplicates_from_playlist()
    assert len(mp.playlist) == 2
    assert "No duplicates" in mp.status_bar.currentMessage()


# --- keyboard -----------------------------------------------------------------

def test_delete_key_removes_selection(music_player):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3", "c.mp3"])
    mp.playlist_widget.item(1).setSelected(True)
    mp.playlist_widget.item(2).setSelected(True)

    handled = mp.eventFilter(mp.playlist_widget, _key(Qt.Key_Delete))

    assert handled is True
    assert mp.playlist == ["a.mp3"]
    assert mp.playlist_widget.count() == 1


def test_space_key_plays_selected_row(music_player, monkeypatch):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3"], current=-1)
    started = []
    monkeypatch.setattr(mp, "play_item_at_index",
                        lambda i: started.append(i), raising=False)
    mp.playlist_widget.setCurrentRow(1)
    mp.playlist_widget.item(1).setSelected(True)

    handled = mp.eventFilter(mp.playlist_widget, _key(Qt.Key_Space))

    assert handled is True
    assert started == [1]


def test_home_end_keys_move_selection(music_player):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3", "c.mp3"])
    mp.playlist_widget.setCurrentRow(1)

    assert mp.eventFilter(mp.playlist_widget, _key(Qt.Key_Home)) is True
    assert mp.playlist_widget.currentRow() == 0

    assert mp.eventFilter(mp.playlist_widget, _key(Qt.Key_End)) is True
    assert mp.playlist_widget.currentRow() == 2
    assert mp.playlist_widget.item(2).isSelected()


def test_other_keys_pass_through(music_player):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3"])
    assert mp.eventFilter(mp.playlist_widget, _key(Qt.Key_X)) is not True


# --- context menu builder -------------------------------------------------------

def test_context_menu_offers_new_actions(music_player):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3", "c.mp3"])
    menu = QMenu()

    mp._build_playlist_context_menu(menu, 1)

    texts = [a.text() for a in menu.actions() if a.text()]
    assert "Play" in texts
    assert "Queue Next" in texts
    assert "Remove from Playlist" in texts
    assert "Remove Duplicates" in texts
    assert "Import Playlist…" in texts
    assert "Export Playlist…" in texts


def test_play_selected_action_in_multi_selection(music_player):
    mp = music_player
    _seed(mp, ["a.mp3", "b.mp3", "c.mp3"])
    mp.playlist_widget.item(0).setSelected(True)
    mp.playlist_widget.item(2).setSelected(True)
    menu = QMenu()

    mp._build_playlist_context_menu(menu, 2)

    texts = [a.text() for a in menu.actions() if a.text()]
    assert "Play Selected" in texts, texts
    assert "Move Selected Up" in texts
    assert "Move Selected Down" in texts
