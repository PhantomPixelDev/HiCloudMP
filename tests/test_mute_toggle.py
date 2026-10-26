"""The main-window volume glyph was a disabled decoration - only the tray
could mute. It is now a real toggle: click mutes/unmutes (remembering the
level to restore), the slider follows, and the EQ-engine sink is muted
too (mute must not silently do nothing when EQ/viz owns playback).
"""
from PySide6.QtCore import Qt


class _EngineSpy:
    def __init__(self):
        self.volumes = []

    def set_volume(self, v):
        self.volumes.append(v)


def test_volume_icon_is_clickable(music_player):
    mp = music_player
    assert mp.volume_icon.isEnabled()
    assert mp.volume_icon.cursor().shape() == Qt.PointingHandCursor


def test_toggle_mutes_and_restores_level(music_player, monkeypatch):
    mp = music_player
    spy = _EngineSpy()
    monkeypatch.setattr(mp, "eq_engine", spy, raising=False)
    monkeypatch.setattr(mp, "_using_engine", True, raising=False)
    mp.volume_slider.setValue(70)

    mp.toggle_mute()
    assert mp.audio_output.isMuted()
    assert mp.volume_slider.value() == 0, "slider mirrors mute"
    assert spy.volumes and spy.volumes[-1] == 0.0, "engine sink muted too"
    assert "muted" in mp.status_bar.currentMessage().lower()

    mp.toggle_mute()
    assert not mp.audio_output.isMuted()
    assert mp.volume_slider.value() == 70, "previous level restored"
    assert spy.volumes[-1] == 0.7
    assert "unmuted" in mp.status_bar.currentMessage().lower()


def test_moving_slider_unmutes(music_player, monkeypatch):
    mp = music_player
    monkeypatch.setattr(mp, "eq_engine", _EngineSpy(), raising=False)
    mp.volume_slider.setValue(60)
    mp.toggle_mute()
    assert mp.audio_output.isMuted()

    mp.volume_slider.setValue(45)   # user drags volume up: unmute
    assert not mp.audio_output.isMuted()
    assert abs(mp.audio_output.volume() - 0.45) < 1e-3


def test_mute_from_zero_restores_sensible_level(music_player, monkeypatch):
    mp = music_player
    monkeypatch.setattr(mp, "eq_engine", _EngineSpy(), raising=False)
    mp.volume_slider.setValue(0)
    mp.toggle_mute()
    assert mp.audio_output.isMuted()

    mp.toggle_mute()
    assert not mp.audio_output.isMuted()
    assert mp.volume_slider.value() > 0, "must not stay silent after unmute"


def test_tray_mute_silences_engine_sink(music_player, monkeypatch):
    from hicloudmp.ui.tray import TrayController
    mp = music_player
    spy = _EngineSpy()
    monkeypatch.setattr(mp, "eq_engine", spy, raising=False)
    monkeypatch.setattr(mp, "_using_engine", True, raising=False)
    mp.volume_slider.setValue(80)
    tray = TrayController(mp)

    tray._on_tray_mute_toggled(True)
    assert mp.audio_output.isMuted()
    assert spy.volumes[-1] == 0.0

    tray._on_tray_mute_toggled(False)
    assert not mp.audio_output.isMuted()
    assert spy.volumes[-1] == 0.8
