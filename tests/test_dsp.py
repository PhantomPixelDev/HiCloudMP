"""DSP math: 10-band EQ gain curves and overlap-add processing."""
import numpy as np

from hicloudmp.audio import dsp


def _sine(freq, seconds, sr=44100, amp=12000):
    t = np.arange(int(sr * seconds)) / sr
    return (np.sin(2 * np.pi * freq * t) * amp).astype(np.int16)


def _magnitude(i16, target_freq, sr=44100):
    x = np.asarray(i16, dtype=np.float64)
    if x.ndim == 2:  # EQ output is (n, channels) — fold channels, never broadcast
        x = x.mean(axis=1)
    else:
        x = x.ravel()
    n = len(x)
    window = np.hanning(n)
    spec = np.fft.rfft(x * window)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    idx = int(np.argmin(np.abs(freqs - target_freq)))
    return np.abs(spec[idx])


def test_zero_gains_is_identity():
    proc = dsp.EQProcessor(44100, 2, (0,) * 10)
    x = _sine(440, 1.0)
    stereo = np.stack([x, x], axis=1)
    out = proc.process(stereo)
    assert len(out) > 0
    # emitted prefix is time-aligned with the input (COLA identity, exact)
    np.testing.assert_array_equal(out[:len(out) - 4098], stereo[:len(out) - 4098])


def test_bass_boost_lifts_low_and_spares_high():
    # 31 Hz = first band center (full +12 dB); 8 kHz = its band center (0 dB).
    # Low amplitude keeps the boosted output inside int16 range (no clipping).
    proc = dsp.EQProcessor(44100, 1, (12,) + (0,) * 9)
    low = _sine(31, 1.0, amp=4000)
    high = _sine(8000, 1.0, amp=4000)
    full_low = np.concatenate([proc.process(low.reshape(-1, 1)), proc.flush()])

    proc2 = dsp.EQProcessor(44100, 1, (12,) + (0,) * 9)
    full_high = np.concatenate([proc2.process(high.reshape(-1, 1)), proc2.flush()])

    m_low_in, m_low_out = _magnitude(low, 31), _magnitude(full_low, 31)
    m_high_in, m_high_out = _magnitude(high, 8000), _magnitude(full_high, 8000)
    assert m_low_out > m_low_in * 2.8, (m_low_in, m_low_out)   # ~+12 dB = 3.98x
    assert abs(m_high_out / m_high_in - 1.0) < 0.15, (m_high_in, m_high_out)


def test_gain_curve_interpolates_log_spacing():
    curve = dsp.gain_curve_db(dsp.EQProcessor.FRAME // 2 + 1, 44100, (0,) * 10)
    assert curve.shape == (4096 // 2 + 1,)
    assert float(np.max(curve)) < 1e-6
    boost = dsp.gain_curve_db(dsp.EQProcessor.FRAME // 2 + 1, 44100,
                              (12,) + (0,) * 9)
    # low bins get up to +12dB, high bands untouched
    assert float(np.max(boost)) > 11.0
    assert float(np.abs(boost[-1])) < 0.5

    bass = dsp.PRESETS["Bass Boost"]
    c = dsp.gain_curve_db(2049, 44100, bass)
    assert float(c[3]) > float(c[-3]), "low bins must gain more than high"
