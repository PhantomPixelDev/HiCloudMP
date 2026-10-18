"""Equalizer session: settings gate, dialog apply/cancel, engine routing."""
import pytest

from PySide6.QtWidgets import QDialog, QMessageBox

import dsp
from dialogs import EqualizerDialog


@pytest.fixture(autouse=True)
def _silence_modal_errors(monkeypatch):
    """Native-player errors on missing test files must never block headless runs."""
    for name in ("critical", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name,
                            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))


def test_eq_inactive_by_default(music_player):
    mp = music_player
    assert mp._eq_active() is False
    assert mp._eq_gains() == [0.0] * 10


def test_eq_gains_malformed_settings_fall_back_to_flat(music_player):
    mp = music_player
    mp.settings.setValue("audio/eq_gains", "1,2,3")   # wrong length
    assert mp._eq_gains() == [0.0] * 10
    mp.settings.setValue("audio/eq_gains", "x,y,z,w,a,b,c,d,e,f")
    assert mp._eq_gains() == [0.0] * 10


def test_eq_gate_requires_enabled_and_nonzero_gains(music_player):
    mp = music_player
    mp.settings.setValue("audio/eq_gains", "0,3,0,0,0,0,0,0,0,0")
    assert mp._eq_active() is False, "gains without enable must stay native"
    mp.settings.setValue("audio/eq_enabled", True)
    assert mp._eq_active() is True
    mp.settings.setValue("audio/eq_gains", "0,0,0,0,0,0,0,0,0,0")
    assert mp._eq_active() is False, "enabled + flat gains = native path"


def test_local_play_routes_engine_when_eq_on(music_player, monkeypatch):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", True)
    mp.settings.setValue("audio/eq_gains", "6,0,0,0,0,0,0,0,0,0")

    calls = []
    monkeypatch.setattr(mp.eq_engine, "play", lambda s: calls.append(s), raising=False)

    mp.playlist = [r"C:\nonexistent\track.mp3"]
    mp.current_index = 0
    mp._disconnect_stream_handlers = lambda: None
    mp.play()

    assert mp._using_engine is True
    assert len(calls) == 1 and calls[0].endswith("track.mp3")

    mp.stop()
    assert mp._using_engine is False


def test_play_routes_native_when_eq_off(music_player, monkeypatch):
    mp = music_player
    calls = []
    monkeypatch.setattr(mp.eq_engine, "play", lambda s: calls.append(s), raising=False)

    mp.playlist = [r"C:\nonexistent\track.mp3"]
    mp.current_index = 0
    mp._disconnect_stream_handlers = lambda: None
    mp.play()

    assert calls == []
    assert mp._using_engine is False
    assert mp.player.source().isLocalFile()


def test_engine_error_falls_back_to_native_replay(music_player):
    mp = music_player
    mp.playlist = [r"C:\nonexistent\track.mp3"]
    mp.current_index = 0
    mp._engine_source = ('file', r"C:\nonexistent\track.mp3", "track.mp3")
    mp._using_engine = True
    mp._engine_playback_error("boom")
    assert mp._using_engine is False
    assert mp.player.source().isLocalFile(), "fallback replays via native player"


def test_equilizer_dialog_applies_live_and_restores_on_cancel():
    applied = []

    dlg = EqualizerDialog(None, (0.0,) * 10, False, "Flat",
                          lambda g, on: applied.append((tuple(g), bool(on))))
    assert dlg.preset_combo.currentText() == "Flat"

    dlg.preset_combo.setCurrentText("Bass Boost")
    gains, on = applied[-1]
    assert on is False
    assert gains == tuple(float(v) for v in dsp.PRESETS["Bass Boost"])

    dlg._sliders[3].setValue(4)
    gains, on = applied[-1]
    assert gains[3] == 4.0
    assert dlg.preset_combo.currentText() == "Custom"

    # Cancel resets gains + enable to the state at open
    dlg.enabled_check.setChecked(True)
    n_before = len(applied)
    dlg.reject()
    gains, on = applied[-1]
    assert (gains, on) == ((0.0,) * 10, False),"cancel restores initial state"


def test_engine_probe_zero_gains_bypass_is_transparent():
    # sanity: EQProcessor identity path (also used live by the engine)
    import numpy as np
    proc = dsp.EQProcessor(44100, 2, (0,) * 10)
    x = np.zeros((4096, 2), dtype=np.int16)
    x[100] = (1000, -1000)
    out = proc.process(x)
    assert int(out[100, 0]) == 1000 and int(out[100, 1]) == -1000
