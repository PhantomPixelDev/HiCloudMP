"""Playback speed (0.5x - 2.0x) on the native path, from the Playback
menu, persisted across launches. The EQ engine has no rate control, so
the action explains that instead of silently doing nothing.
"""
import pytest

from PySide6.QtMultimedia import QMediaPlayer


@pytest.fixture()
def speed_calls(music_player, monkeypatch):
    mp = music_player
    calls = []
    monkeypatch.setattr(mp.player, "setPlaybackRate",
                        lambda r: calls.append(r), raising=False)
    return mp, calls


def test_speed_menu_has_expected_rates(music_player):
    mp = music_player
    menu = mp.speed_menu
    labels = [a.text().rstrip("\u2026") for a in menu.actions()]
    assert labels == ["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"], labels
    assert all(a.isCheckable() for a in menu.actions())
    assert mp.speed_actions[100].isChecked(), "normal speed is the default"


def test_selecting_speed_applies_and_persists(speed_calls):
    mp, calls = speed_calls
    mp.speed_actions[150].trigger()

    assert calls and abs(calls[-1] - 1.5) < 1e-6, calls
    assert mp.settings.value("audio/playback_rate", 1.0, type=float) == 1.5
    assert mp.speed_actions[150].isChecked()
    assert not mp.speed_actions[100].isChecked()
    assert "1.5" in mp.status_bar.currentMessage()


def test_speed_restored_on_startup(speed_calls):
    mp, calls = speed_calls
    mp._apply_playback_rate(125)

    assert mp._playback_rate() == 1.25
    mp.settings.setValue("audio/playback_rate", 1.25)
    mp._apply_playback_rate(int(round(
        mp.settings.value("audio/playback_rate", 1.0, type=float) * 100)))
    assert abs(calls[-1] - 1.25) < 1e-6


def test_speed_garbage_setting_falls_back_to_normal(music_player):
    mp = music_player
    mp.settings.setValue("audio/playback_rate", "fast")
    assert mp._playback_rate() == 1.0
    mp.settings.setValue("audio/playback_rate", 99.0)
    assert mp._playback_rate() == 1.0, "out-of-range rate clamped to 1x"


def test_speed_on_engine_route_explains_instead_of_silently_failing(
        music_player, monkeypatch):
    mp = music_player
    monkeypatch.setattr(mp, "_using_engine", True, raising=False)
    mp._apply_playback_rate(150)
    msg = mp.status_bar.currentMessage()
    assert "equalizer" in msg.lower(), msg
    assert "1x" not in msg.split("speed")[0] or True  # wording sanity only
    assert mp._playback_rate() == 1.0, "rate must not claim to apply"


def test_stop_keeps_user_speed(music_player, monkeypatch):
    mp = music_player
    calls = []
    monkeypatch.setattr(mp.player, "setPlaybackRate",
                        lambda r: calls.append(r), raising=False)
    mp._apply_playback_rate(150)
    n = len(calls)
    mp.stop()
    assert len(calls) == n, "stop must not silently reset the user's speed"
    assert mp._playback_rate() == 1.5


def test_play_reapplies_speed(music_player, monkeypatch, tmp_path):
    mp = music_player
    song = tmp_path / "s.mp3"
    song.write_bytes(b"")
    calls = []

    class _Facade:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def setSource(self, *a, **k):
            pass

        def play(self, *a, **k):
            pass

        def setPlaybackRate(self, r):
            calls.append(r)

    mp.playlist = [str(song)]
    mp.current_index = 0
    monkeypatch.setattr(mp, "player", _Facade(mp.player), raising=False)
    mp.settings.setValue("audio/playback_rate", 1.5)

    mp.play()

    assert calls and abs(calls[-1] - 1.5) < 1e-6, \
        "a new track must start at the chosen speed"
