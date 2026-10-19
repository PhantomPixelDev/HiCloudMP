"""Play Next queue was invisible: you could queue tracks with no way to
see how many were waiting - or clear them. Now a status-bar badge shows
the count (hidden at zero, click clears) and the playlist context menu
gains a Clear action that is only enabled while something is queued.
"""
from PySide6.QtWidgets import QMenu


def _seed(mp):
    mp.playlist = [f"C:/q/{n}.mp3" for n in "abc"]
    mp.playlist_widget.clear()
    for n in "abc":
        mp.playlist_widget.addItem(f"{n}.mp3")
    mp.current_index = 0


def test_queue_badge_tracks_count(music_player):
    mp = music_player
    _seed(mp)
    assert mp.queue_indicator.isHidden(), "no badge while empty"

    mp.playlist_widget.item(1).setSelected(True)
    mp.playlist_widget.item(2).setSelected(True)
    mp.queue_play_next()

    assert not mp.queue_indicator.isHidden()
    assert mp.queue_indicator.text() == "Play Next: 2"
    assert "2 queued" in mp.status_bar.currentMessage()


def test_take_updates_and_hides_badge(music_player):
    mp = music_player
    _seed(mp)
    mp._play_next_queue = [1, 2]
    mp._update_queue_indicator()
    assert mp.queue_indicator.text() == "Play Next: 2"

    assert mp._take_from_play_next_queue() == 1
    assert mp.queue_indicator.text() == "Play Next: 1"
    assert mp._take_from_play_next_queue() == 2
    assert mp.queue_indicator.isHidden()


def test_click_clears_queue(music_player):
    mp = music_player
    _seed(mp)
    mp._play_next_queue = [1, 2]
    mp._update_queue_indicator()

    mp.clear_play_next_queue()

    assert mp._play_next_queue == []
    assert mp.queue_indicator.isHidden()
    assert "cleared" in mp.status_bar.currentMessage().lower()


def test_context_menu_clear_enabled_only_when_queued(music_player):
    mp = music_player
    _seed(mp)

    def _clear_action():
        menu = QMenu(mp)
        mp._build_playlist_context_menu(menu, 0)
        for act in menu.actions():
            if act.text() == "Clear Play Next Queue":
                return act
        raise AssertionError("Clear Play Next Queue action missing")

    assert not _clear_action().isEnabled(), "nothing to clear yet"

    mp._play_next_queue = [1]
    mp._update_queue_indicator()
    action = _clear_action()
    assert action.isEnabled()
    action.trigger()
    assert mp._play_next_queue == []
    assert mp.queue_indicator.isHidden()
