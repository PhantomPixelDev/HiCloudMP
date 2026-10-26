"""Visualizer for every playback path.

A 'Show visualizer' setting routes playback through the EQ engine even
with the equalizer OFF — zero-gain routing is bit-transparent (proven by
the dsp identity tests), so the spectrum gets real data with no
coloration and no placebo bars.
"""
import pytest

from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def _silence_modals(monkeypatch):
    for name in ("critical", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name,
                            staticmethod(
                                lambda *a, **k: QMessageBox.StandardButton.Ok))


def test_route_gate_off_by_default(music_player):
    assert music_player._route_through_engine() is False


def test_route_gate_viz_flag_alone(music_player):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    mp.settings.setValue("ui/visualizer_enabled", True)
    assert mp._route_through_engine() is True


def test_route_gate_eq_only(music_player):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", True)
    mp.settings.setValue("audio/eq_gains", "6,0,0,0,0,0,0,0,0,0")
    mp.settings.setValue("ui/visualizer_enabled", False)
    assert mp._route_through_engine() is True


def test_viz_only_engine_gets_flat_gains(music_player, monkeypatch):
    """EQ disabled + visualizer on: the engine must run FLAT (transparent)."""
    mp = music_player
    mp.settings.setValue("ui/visualizer_enabled", True)
    mp.settings.setValue("audio/eq_enabled", False)

    class _EngineStub:
        def __init__(self):
            self.gains = []
            self.plays = []

        def set_gains(self, g):
            self.gains.append(tuple(g))

        def play(self, src):
            self.plays.append(src)

    stub = _EngineStub()
    monkeypatch.setattr(mp, "eq_engine", stub, raising=False)
    mp.playlist = [r"C:\nonexistent\track.mp3"]
    mp.current_index = 0
    mp._disconnect_stream_handlers = lambda: None
    mp.play()
    assert stub.gains == [(0.0,) * 10], stub.gains
    assert mp._using_engine is True


def test_eq_engine_keeps_user_gains(music_player, monkeypatch):
    """EQ ON: the engine gets the user's gains (not flat)."""
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", True)
    mp.settings.setValue("audio/eq_gains", "6,0,0,0,0,0,0,0,0,0")

    class _EngineStub:
        def __init__(self):
            self.gains = []

        def set_gains(self, g):
            self.gains.append(tuple(g))

        def play(self, src):
            return None

    stub = _EngineStub()
    monkeypatch.setattr(mp, "eq_engine", stub, raising=False)
    mp.playlist = [r"C:\nonexistent\track.mp3"]
    mp.current_index = 0
    mp._disconnect_stream_handlers = lambda: None
    mp.play()
    assert stub.gains == [(6.0, 0, 0, 0, 0, 0, 0, 0, 0, 0)], stub.gains


def test_all_routing_sites_use_the_gate():
    from sourcepaths import read
    src = read("ui/player.py")
    # the three play()-family routing sites must call the combined gate;
    # _eq_active survives only inside _route_through_engine and the
    # visualizer-toggle's EQ-stays-on-the-engine guard
    assert src.count("if self._eq_active():") == 1
    assert src.count("if self._route_through_engine():") >= 3


def test_settings_persist_visualizer(music_player):
    from hicloudmp.ui import player as player_mod
    mp = music_player
    dlg = player_mod.SettingsDialog(mp)
    assert hasattr(dlg, "visualizer_checkbox")
    dlg.visualizer_checkbox.setChecked(True)
    dlg.save_settings()
    assert mp.settings.value("ui/visualizer_enabled", False, type=bool) is True
    dlg2 = player_mod.SettingsDialog(mp)
    assert dlg2.visualizer_checkbox.isChecked() is True
