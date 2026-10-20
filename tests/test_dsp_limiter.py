"""EQ output must not hard-clip (the 'harsh' sound).

User report: EQ playback sounds harsh/distorted. Root cause:
EQProcessor amplified float output was hard-clipped at the int16 rails
(np.clip to +-32768) with limiter absent. Probe evidence with the
user's own 12/7/.../12/12 dB curve: a full-scale input saturated
62.6% of all output samples - flat-topped wave = harsh digital crackle.
Research standard: float processing + soft limiting, int16 last.
The EQ-off/flat contract stays bit-exact: samples at or below 0 dBFS
are untouched (the knee engages strictly above 0 dBFS).
"""
import numpy as np

import dsp

USER_CURVE = (12, 7, 5, 3, 1, 0, 0, 0, 12, 12)


def _messy_input(seconds=2):
    """Full-scale messy audio: bass + treble + noise, like real music."""
    t = np.arange(44100 * seconds)
    rng = np.random.default_rng(7)
    x = (np.sin(2 * np.pi * 50 * t / 44100) * 0.7
         + np.sin(2 * np.pi * 10000 * t / 44100) * 0.5
         + rng.standard_normal(44100 * seconds) * 0.15)
    x = np.clip(x, -1, 1)
    return np.stack([x, -x], axis=1)


def _run_processor(channels_in_stereo, gains):
    i16 = (channels_in_stereo * 32767).astype(np.int16)
    proc = dsp.EQProcessor(44100, 2, gains)
    outs = []
    for i in range(0, i16.shape[0], 4096):
        outs.append(proc.process(i16[i:i + 4096]))
    outs.append(proc.flush())
    settled = np.concatenate(outs, axis=0)[6000:]
    return settled.astype(np.int32)


def test_user_curve_no_rail_saturation():
    """The user's +12/+12 curve on full-scale audio must not slam the rails.

    Probe numbers (same data): pre-fix 62.6% of samples hard-saturated at
    +-32767/32768; post-fix 0 at the rail, 0.02% within 20 LSB."""
    settled = _run_processor(_messy_input(), USER_CURVE)
    rail = int(np.sum(np.abs(settled) >= 32767))
    assert rail == 0, f"{rail} samples hard-saturated at the int16 rails"
    near_rail = float(np.mean(np.abs(settled) >= 32750))
    assert near_rail < 0.01, \
        f"{near_rail * 100:.1f}% of samples bunched at the rail shelf"


def test_soft_limit_knee_is_continuous_and_ceil_sub_fs():
    """Above-0dBFS samples compress smoothly toward a sub-rail ceiling;
    nothing ends at +-32767/32768."""
    x = np.array([0.0, 16000.0, 32767.0, 32768.0, 40000.0, 65534.0, -60000.0],
                 dtype=np.float32)
    y = dsp._soft_limit_over(x)
    assert y[0] == 0.0
    assert y[1] == 16000.0                     # untouched below FS
    assert y[2] == 32767.0                     # exactly FS: untouched
    assert np.max(np.abs(y)) < 32768.0         # nothing at/over the rail
    assert not np.any(np.isclose(np.abs(y[3:]), 32768.0))


def test_soft_limit_untouched_below_fs():
    rng = np.random.default_rng(3)
    x = (rng.random(5000).astype(np.float32) * 32767.0   # <= FS exactly
         * rng.choice([1.0, -1.0], size=5000))
    y = dsp._soft_limit_over(x)
    np.testing.assert_array_equal(y, x)          # bit-exact pass-through
