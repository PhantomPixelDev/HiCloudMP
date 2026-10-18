"""Engine buffering: the pump must never run just-in-time.

QAudioDecoder exposes a single buffer slot; after one read() it refills
asynchronously. The 40ms pump used to pull ~one buffer per tick (~46ms of
audio per 40ms) — zero cushion, so any event-loop or network jitter
underran the sink and playback 'hopped'. bufferReady must WAKE the pump
(never read directly — single-consumer rule), and the pending cushion must
be deep enough to smooth network streams.
"""
import numpy as np
import pytest

import dsp
from eq_engine import EQEngine


class FakeBuffer:
    def __init__(self, frames=2048, channels=2):
        self._arr = np.zeros((frames, channels), dtype=np.int16)
        self._data = self._arr.tobytes()

    def byteCount(self):
        return len(self._data)

    def constData(self):
        return self._data


class FakeDecoder:
    """Mimics the single-slot decoder: bufferAvailable until read, then
    the caller must wait for the next (simulated) bufferReady event."""
    def __init__(self, n_buffers):
        self.remaining = n_buffers
        self.reads = 0

    def bufferAvailable(self):
        return self.remaining > 0

    def read(self):
        if self.remaining <= 0:
            return None
        self.remaining -= 1
        self.reads += 1
        return FakeBuffer()

    def position(self):
        return 0


def _engine_with_fake(qapp, n_buffers):
    eng = EQEngine()
    eng._decoder = FakeDecoder(n_buffers)
    eng._proc = dsp.EQProcessor(EQEngine.SAMPLE_RATE, EQEngine.CHANNELS,
                                 (0.0,) * 10)
    eng._skip_done = True
    eng._playing = True
    return eng


def test_refill_drains_every_available_buffer(qapp):
    eng = _engine_with_fake(qapp, n_buffers=10)
    eng._refill()
    assert eng._decoder.reads == 10, "one refill must drain all queued buffers"
    assert eng._pending.shape[0] == 10 * 2048


def test_refill_stops_at_pending_cap(qapp):
    eng = _engine_with_fake(qapp, n_buffers=1000)
    eng._refill()
    cap_frames = int(EQEngine._MAX_PENDING_SECONDS * EQEngine.SAMPLE_RATE)
    # the cap is checked before each read: overshoot is at most one buffer
    assert eng._pending.shape[0] <= cap_frames + 2048
    assert eng._pending.shape[0] >= int(4.0 * EQEngine.SAMPLE_RATE), \
        "cushion must be deep (>=4s), not a single buffer"


def test_pending_cap_is_deep(qapp):
    assert EQEngine._MAX_PENDING_SECONDS >= 5.0


def test_buffer_ready_wakes_pump_once(qapp, monkeypatch):
    eng = EQEngine()
    eng._playing = True
    eng._proc = dsp.EQProcessor(EQEngine.SAMPLE_RATE, EQEngine.CHANNELS,
                                 (0.0,) * 10)
    eng._decoder = FakeDecoder(0)
    calls = []
    monkeypatch.setattr(eng, "_pump", lambda: calls.append(1))

    eng._on_buffer_ready()
    assert eng._wake_scheduled is True
    assert calls == []                      # not pumped synchronously
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    assert len(calls) == 1                  # woke via the coalesced timer
    assert eng._wake_scheduled is False

    # a burst of bufferReady events coalesces to a single wake
    for _ in range(5):
        eng._on_buffer_ready()
    QApplication.processEvents()
    QApplication.processEvents()
    assert len(calls) == 2


def test_late_buffer_ready_after_stop_is_ignored(qapp):
    eng = EQEngine()
    eng._decoder = FakeDecoder(3)
    eng._proc = dsp.EQProcessor(EQEngine.SAMPLE_RATE, EQEngine.CHANNELS,
                                 (0.0,) * 10)
    eng._playing = True
    eng._wake_scheduled = True
    eng._wake_timer.start()
    eng.stop()                              # teardown must kill the wake
    assert eng._wake_scheduled is False
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    assert eng._pending.shape[0] == 0
