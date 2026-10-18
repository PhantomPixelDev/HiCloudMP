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


class _FakeIO:
    """Push device returned by QAudioSink.start() in PySide6 6.10."""

    def __init__(self):
        self.chunks = []

    def write(self, data):
        self.chunks.append(bytes(data))
        return len(data)


class _FakeSink:
    def __init__(self, io):
        self._io = io
        self.started = False
        self.free = 96000

    def start(self):
        self.started = True
        return self._io

    def bytesFree(self):
        return self.free

    def processedUSecs(self):
        return 0

    def suspend(self):
        pass

    def resume(self):
        pass

    def stop(self):
        self.started = False


def test_pump_writes_via_push_device_and_consumes_pending(qtbot):
    import numpy as np
    from eq_engine import EQEngine

    engine = EQEngine()
    io = _FakeIO()
    engine._sink = _FakeSink(io)
    engine._io = io                      # as play() will install it
    engine._playing = True
    engine._proc = dsp.EQProcessor(44100, 2, (0,) * 10)
    engine._pending = np.zeros((4096, 2), dtype=np.int16)

    engine._pump()

    assert len(io.chunks) == 1
    assert len(io.chunks[0]) == 4096 * 2 * 2
    assert engine._pending.shape[0] == 0, "all pending samples consumed"


def test_pump_exception_reports_error_for_native_fallback(qtbot):
    import numpy as np
    from eq_engine import EQEngine

    engine = EQEngine()
    engine._sink = _FakeSink(None)
    engine._io = None                    # broken install: no push device
    engine._sink.write = lambda d: (_ for _ in ()).throw(
        AttributeError('no attribute write'))
    engine._playing = True
    engine._proc = dsp.EQProcessor(44100, 2, (0,) * 10)
    engine._pending = np.zeros((2048, 2), dtype=np.int16)

    with qtbot.waitSignal(engine.error_occurred, timeout=3000):
        engine._pump()

    assert engine._sink is None, "engine tears down before reporting"


class _FakeDecoder:
    """Mimics the PySide6 6.10 QAudioDecoder surface (no setPosition)."""

    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.sources = []
        self.decode_pos = 0
        self.bufferAvail = False

    def source(self):
        return self.sources[0] if self.sources else None

    def stop(self):
        self.stops += 1

    def setSource(self, url):
        self.sources.append(url)

    def start(self):
        self.starts += 1

    def position(self):
        return self.decode_pos

    def bufferAvailable(self):
        return self.bufferAvail


def test_seek_restarts_decoder_and_discards_until_target(qtbot):
    from eq_engine import EQEngine

    engine = EQEngine()
    dec = _FakeDecoder()
    dec.decode_pos = 5000        # after restart it fast-decodes from the top
    engine._decoder = dec
    engine._proc = dsp.EQProcessor(44100, 2, (0,) * 10)
    import numpy as np
    engine._pending = np.zeros((1000, 2), dtype=np.int16)

    engine.seek(5000)            # must NOT raise AttributeError

    assert dec.stops >= 1 and dec.starts >= 1, "seek restarts the decoder"
    assert engine._skip_until_ms == 5000
    assert engine._base_ms == 5000
    assert engine._pending.shape[0] == 0, "pending audio dropped on seek"
    assert engine._skip_done is False


def test_process_or_discard_drops_pretarget_buffers(qtbot):
    import numpy as np
    from eq_engine import EQEngine

    engine = EQEngine()
    engine._proc = dsp.EQProcessor(44100, 2, (0,) * 10)
    engine._skip_until_ms = 4000
    engine._skip_done = False

    out = engine._process_or_discard(
        np.zeros((1000, 2), dtype=np.int16), buffer_end_position_ms=3500)
    assert out is not None and out.shape[0] == 0, "pre-target audio discarded"
    assert engine._skip_done is False

    out = engine._process_or_discard(
        np.zeros((2048, 2), dtype=np.int16), buffer_end_position_ms=4200)
    assert out is not None and out.shape[0] == 2048, "post-target processed"
    assert engine._skip_done is True
