"""Visualizer must show real spectrum for native playback too.

The EQ engine is the preferred tap (post-EQ, bit-transparent when flat),
but when the engine cannot open the audio device playback falls back to
QMediaPlayer and the visualizer used to go idle. QAudioBufferOutput taps
the same decoded audio the listener hears, so the bars stay honest.
"""
import time

import numpy as np

from PySide6.QtMultimedia import QAudioFormat


def _sine_i16(freq=1000, rate=44100, seconds=0.3, amp=8000):
    t = np.arange(int(seconds * rate), dtype=np.float64) / rate
    wave = amp * np.sin(2 * np.pi * freq * t)
    return np.stack([wave, wave], axis=1).astype(np.int16)


class _FakeFormat:
    def __init__(self, rate=44100, channels=2, sample_format=None):
        self._rate = rate
        self._channels = channels
        self._format = sample_format or QAudioFormat.SampleFormat.Int16

    def sampleRate(self):
        return self._rate

    def channelCount(self):
        return self._channels

    def sampleFormat(self):
        return self._format


class _FakeBuffer:
    def __init__(self, samples, rate=44100):
        self._samples = samples
        self._format = _FakeFormat(rate=rate,
                                   channels=samples.shape[1] if samples.ndim == 2 else 1)

    def constData(self):
        return memoryview(np.ascontiguousarray(self._samples).tobytes())

    def format(self):
        return self._format


def test_native_tap_is_wired(music_player):
    mp = music_player
    assert mp._native_audio_output is not None
    assert mp.player.audioBufferOutput() is mp._native_audio_output


def test_native_buffer_produces_real_spectrum(music_player):
    mp = music_player
    mp._native_tap_enabled = True
    mp._on_native_audio_buffer(_FakeBuffer(_sine_i16(1000)))
    spec = mp._native_spectrum
    assert spec is not None
    assert len(spec) == 24
    peak = int(np.argmax(spec))
    assert 10 <= peak <= 13, f"1 kHz peaked at band {peak}"


def test_native_tap_handles_different_sample_rates(music_player):
    mp = music_player
    mp._native_tap_enabled = True
    mp._on_native_audio_buffer(_FakeBuffer(_sine_i16(1000, rate=96000), rate=96000))
    peak = int(np.argmax(mp._native_spectrum))
    assert 10 <= peak <= 13, f"1 kHz at 96 kHz peaked at band {peak}"


def test_visualizer_uses_native_spectrum_when_engine_is_off(
        music_player, monkeypatch):
    mp = music_player
    mp._using_engine = False
    mp._native_tap_enabled = True
    mp._on_native_audio_buffer(_FakeBuffer(_sine_i16(1000)))
    feeds = []
    monkeypatch.setattr(mp.visualizer, "set_spectrum",
                        lambda data: feeds.append(data))
    mp._update_visualizer()
    assert feeds and feeds[-1] is not None
    assert max(feeds[-1]) > 0.3


def test_native_spectrum_goes_idle_when_stale(music_player, monkeypatch):
    mp = music_player
    mp._using_engine = False
    mp._native_tap_enabled = True
    mp._on_native_audio_buffer(_FakeBuffer(_sine_i16(1000)))
    mp._native_spectrum_at = time.monotonic() - 5.0
    feeds = []
    monkeypatch.setattr(mp.visualizer, "set_spectrum",
                        lambda data: feeds.append(data))
    mp._update_visualizer()
    assert feeds[-1] is None


def test_native_spectrum_not_used_when_visualizer_disabled(
        music_player, monkeypatch):
    mp = music_player
    mp._using_engine = False
    mp._native_tap_enabled = False
    mp._on_native_audio_buffer(_FakeBuffer(_sine_i16(1000)))
    feeds = []
    monkeypatch.setattr(mp.visualizer, "set_spectrum",
                        lambda data: feeds.append(data))
    mp._update_visualizer()
    assert feeds[-1] is None
