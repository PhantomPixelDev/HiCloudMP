"""Live search as you type.

Search reads the in-memory index now (instant), so it should fire per
keystroke, debounced, instead of waiting for the user to press Enter.
"""
import pytest

QTIMER_MS = 150


def test_textchange_starts_debounce(music_player):
    mp = music_player
    assert hasattr(mp, "_search_debounce")
    mp.search_input.setText("somequery")
    assert mp._search_debounce.isActive()


def test_debounce_fires_search_once_per_pause(music_player, qtbot):
    """Typing coalesces into ONE search after the pause."""
    mp = music_player
    called = []
    mp.search_music = (lambda: called.append(1))  # replace bound delegate
    mp.search_input.setText("a")
    mp.search_input.setText("ab")
    mp.search_input.setText("abc")
    assert called == []
    qtbot.wait(QTIMER_MS + 120)
    assert called == [1]


def test_debounce_timer_config(music_player):
    mp = music_player
    assert mp._search_debounce.interval() == QTIMER_MS
    assert mp._search_debounce.isSingleShot()


def test_enter_still_searches_immediately(music_player, monkeypatch):
    """Explicit Enter must search without waiting for the debounce."""
    mp = music_player
    called = []
    monkeypatch.setattr(mp, "search_music", lambda: called.append(1),
                        raising=False)
    mp.search_input.setText(" immediately")
    mp._search_now()
    assert called == [1]
