"""Stream retries were unbounded: a dead playlist URL reconnected forever
(and EndOfMedia reconnects never counted at all). Retries are now capped;
when the exhausted stream is the playlist row being played, playback
advances to the next entry. Each give-up moves the index forward, so a
playlist of dead stream URLs terminates.
"""
import player as player_mod


class _TimerSpy:
    calls = []

    @staticmethod
    def singleShot(ms, fn):
        _TimerSpy.calls.append((ms, fn))


def _arm(mp, url="http://dead.example/x.mp3", attempts=None):
    mp._reset_stream_retry()
    if attempts is not None:
        mp._stream_retry["attempts"] = attempts
    mp._stream_retry["url"] = url
    mp._stream_retry["name"] = "x.mp3"


def test_retries_exhausted_skips_to_next_row(music_player, monkeypatch):
    mp = music_player
    mp.playlist = ["http://dead.example/x.mp3", "C:/next.mp3"]
    mp.current_index = 0
    _arm(mp, attempts=player_mod.STREAM_MAX_RETRIES)
    played = []
    monkeypatch.setattr(mp, "play",
                        lambda: played.append(mp.current_index),
                        raising=False)

    mp._schedule_stream_retry("http://dead.example/x.mp3", "x.mp3")

    assert mp.current_index == 1
    assert played == [1], "the next row must actually start"
    assert "skipping" in mp.status_bar.currentMessage().lower()
    assert mp._stream_retry["attempts"] == 0, "state resets after give-up"


def test_retry_below_limit_still_schedules(music_player, monkeypatch):
    mp = music_player
    _TimerSpy.calls = []
    monkeypatch.setattr(player_mod, "QTimer", _TimerSpy, raising=False)
    _arm(mp)

    mp._schedule_stream_retry("http://dead.example/x.mp3", "x.mp3")

    assert mp._stream_retry["attempts"] == 1
    assert len(_TimerSpy.calls) == 1, "first retry must be scheduled"


def test_last_row_gives_up_without_crashing(music_player, monkeypatch):
    mp = music_player
    mp.playlist = ["http://dead.example/x.mp3"]
    mp.current_index = 0
    _arm(mp, attempts=player_mod.STREAM_MAX_RETRIES)
    played = []
    monkeypatch.setattr(mp, "play", lambda: played.append(1), raising=False)

    mp._schedule_stream_retry("http://dead.example/x.mp3", "x.mp3")

    assert mp.current_index == 0
    assert played == []
    assert "unavailable" in mp.status_bar.currentMessage().lower()


def test_immediate_retries_are_bounded_too(music_player, monkeypatch):
    mp = music_player
    _TimerSpy.calls = []
    monkeypatch.setattr(player_mod, "QTimer", _TimerSpy, raising=False)
    _arm(mp, attempts=player_mod.STREAM_MAX_RETRIES)

    mp._schedule_stream_retry("http://dead.example/x.mp3", "x.mp3",
                              immediate=True)

    assert _TimerSpy.calls == [], "EndOfMedia reconnect loop must stop too"


def test_failed_stream_not_in_the_queue_does_not_skip(music_player, monkeypatch):
    mp = music_player
    mp.playlist = ["C:/local/song.mp3"]
    mp.current_index = 0
    _arm(mp, url="http://dead.example/other.mp3",
         attempts=player_mod.STREAM_MAX_RETRIES)
    played = []
    monkeypatch.setattr(mp, "play", lambda: played.append(1), raising=False)

    mp._schedule_stream_retry("http://dead.example/other.mp3", "other.mp3")

    assert mp.current_index == 0, "unrelated stream failure must not skip"
    assert played == []
    assert "unavailable" in mp.status_bar.currentMessage().lower()
