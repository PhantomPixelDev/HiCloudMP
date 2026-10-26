"""Spectrum computation for the visualizer.

compute_spectrum turns a short mono sample block (int16 scale) into
n_bands log-spaced energy values in [0, 1] (60 dB floor). Pure numpy —
runs on the engine's pump thread budget in microseconds.
"""
import numpy as np

from hicloudmp.audio.spectrum import compute_spectrum


def _sine(freq, seconds=0.3, amp=8000, rate=44100):
    t = np.arange(int(seconds * rate), dtype=np.float64) / rate
    wave = amp * np.sin(2 * np.pi * freq * t)
    return np.stack([wave, wave], axis=1).astype(np.int16)


def test_returns_24_bands_finite_in_unit_range():
    spec = compute_spectrum(_sine(1000))
    assert spec.shape == (24,)
    assert np.all(np.isfinite(spec))
    assert np.all(spec >= 0.0)
    assert np.all(spec <= 1.0)


def test_loud_sine_peaks_in_its_log_band():
    # 1 kHz sits ~band 12 of 24 (40 Hz .. 16 kHz, log-spaced)
    spec = compute_spectrum(_sine(1000))
    peak = int(np.argmax(spec))
    assert 10 <= peak <= 13, f"1 kHz peaked at band {peak}"
    assert spec[peak] >= 0.4


def test_low_sine_peaks_low_high_sine_peaks_high():
    low = int(np.argmax(compute_spectrum(_sine(80))))
    high = int(np.argmax(compute_spectrum(_sine(12000))))
    assert low <= 4, f"80 Hz peaked at band {low}"
    assert high >= 20, f"12 kHz peaked at band {high}"
    assert low < high


def test_silence_is_near_zero():
    sil = np.zeros((4096, 2), dtype=np.int16)
    spec = compute_spectrum(sil)
    assert np.all(spec < 0.03)


def test_accepts_mono_int16_input():
    t = np.arange(8192) / 44100.0
    wave = (8000 * np.sin(2 * np.pi * 1000 * t)).astype(np.int16)
    spec = compute_spectrum(wave)
    peak = int(np.argmax(spec))
    assert 10 <= peak <= 13


def test_respects_source_sample_rate_for_band_mapping():
    """Native audio can be 48/96 kHz; the band edges are frequencies, so
    the FFT bin-to-Hz mapping must use the buffer's real rate."""
    t = np.arange(int(0.3 * 96000)) / 96000.0
    wave = np.stack([8000 * np.sin(2 * np.pi * 1000 * t)] * 2, axis=1)
    spec = compute_spectrum(wave.astype(np.int16), sample_rate=96000)
    peak = int(np.argmax(spec))
    assert 10 <= peak <= 13, f"1 kHz at 96 kHz peaked at band {peak}"
