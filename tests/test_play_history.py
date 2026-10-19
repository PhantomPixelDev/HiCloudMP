"""Recently/Most Played: play history persisted as JSON in the data dir,
surfaced as two Tools submenus. Recording dedups (a re-play moves to the
front), counts feed Most Played, the recent list is capped, and a corrupt
file must never break startup.
"""
import os

import pytest

import player as player_mod


class _PlayerFacade:
    """House pattern: records, keeps the real C++ object alive."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def setSource(self, *a, **k):
        pass

    def play(self, *a, **k):
        pass

    def setPlaybackRate(self, *a, **k):
        pass


def _fresh(mp):
    """Start from an empty history (the session data dir is shared)."""
    mp._history = {"recent": [], "counts": {}, "names": {}}
    try:
        os.remove(mp._history_path())
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _fresh_history(music_player):
    _fresh(music_player)
    yield


def test_record_play_dedups_and_counts(music_player):
    mp = music_player
    mp.record_play("C:/m/one.mp3")
    mp.record_play("C:/m/two.mp3")
    mp.record_play("C:/m/one.mp3")

    assert mp._history["recent"][:2] == ["C:/m/one.mp3", "C:/m/two.mp3"]
    assert mp._history["recent"].count("C:/m/one.mp3") == 1
    assert mp._history["counts"]["C:/m/one.mp3"] == 2
    assert mp._history["counts"]["C:/m/two.mp3"] == 1


def test_history_persists_and_reloads(music_player):
    mp = music_player
    mp.record_play("C:/music/song.mp3")

    assert os.path.isfile(mp._history_path()), "history file must be written"
    reloaded = mp._load_play_history()
    assert reloaded["recent"][0] == "C:/music/song.mp3"
    assert reloaded["counts"]["C:/music/song.mp3"] == 1


def test_history_recent_capped(music_player):
    mp = music_player
    for i in range(player_mod.HISTORY_LIMIT + 10):
        mp.record_play(f"C:/m/{i}.mp3")

    assert len(mp._history["recent"]) == player_mod.HISTORY_LIMIT
    assert mp._history["recent"][0].endswith(
        f"{player_mod.HISTORY_LIMIT + 9}.mp3")


def test_corrupt_history_file_ignored(music_player):
    mp = music_player
    with open(mp._history_path(), "w", encoding="utf-8") as f:
        f.write("{definitely not json")

    data = mp._load_play_history()

    assert data["recent"] == []
    assert data["counts"] == {}


def test_play_records_stream_url_row(music_player, monkeypatch):
    mp = music_player
    streamed = []
    monkeypatch.setattr(mp, "_play_stream",
                        lambda url, name: streamed.append(url), raising=False)
    mp.playlist = ["http://radio.example/live.m3u8"]
    mp.current_index = 0

    mp.play()

    assert streamed == ["http://radio.example/live.m3u8"]
    assert mp._history["recent"][0] == "http://radio.example/live.m3u8"


def test_play_records_existing_local_file_only(music_player, tmp_path,
                                               monkeypatch):
    mp = music_player
    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    monkeypatch.setattr(mp, "player", _PlayerFacade(mp.player), raising=False)

    mp.playlist = [str(song)]
    mp.current_index = 0
    mp.play()
    assert mp._history["recent"][0] == str(song)

    mp.playlist = [r"C:\no\such\file.mp3"]
    mp.current_index = 0
    mp.play()
    assert r"C:\no\such\file.mp3" not in mp._history["recent"], \
        "a missing file must not pollute the history"


def test_recent_menu_newest_first_and_click_replays(music_player, monkeypatch):
    mp = music_player
    mp.record_play("http://a.example/one.mp3")
    mp.record_play("http://b.example/two.mp3")
    mp._rebuild_recent_menu()

    acts = [a for a in mp.recent_menu.actions() if a.text()]
    assert [a.text() for a in acts] == ["two.mp3", "one.mp3"]

    played = []
    monkeypatch.setattr(mp, "play",
                        lambda: played.append(mp.current_index), raising=False)
    acts[1].trigger()

    assert mp.playlist[-1] == "http://a.example/one.mp3"
    assert mp.current_index == len(mp.playlist) - 1
    assert played == [mp.current_index]


def test_most_played_menu_sorted_with_counts(music_player):
    mp = music_player
    mp.record_play("http://a.example/one.mp3")
    mp.record_play("http://a.example/one.mp3")
    mp.record_play("http://a.example/two.mp3")
    mp._rebuild_most_menu()

    texts = [a.text() for a in mp.most_menu.actions()]
    assert texts[0].startswith("one.mp3") and "2" in texts[0]
    assert texts[1].startswith("two.mp3")


def test_menu_click_on_missing_file_is_graceful(music_player):
    mp = music_player
    mp.record_play(r"C:\gone\track.mp3")
    mp._rebuild_recent_menu()

    mp.recent_menu.actions()[0].trigger()

    assert mp.playlist == []
    assert "no longer exists" in mp.status_bar.currentMessage().lower()

