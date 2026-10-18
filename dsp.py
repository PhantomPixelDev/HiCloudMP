"""FIR/EQ DSP: 10-band frequency-domain equalizer with overlap-add.

Pure numpy — no Qt — so the math is unit-testable without audio devices.
Analysis window only (hann, 50% overlap): the zero-gain response is an exact
identity because offset hann analysis windows sum to 1 (COLA), so sliders at 0
are audibly transparent.
"""
import numpy as np

BAND_CENTERS = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)

PRESETS = {
    "Flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "Bass Boost": (7, 7, 5, 3, 1, 0, 0, 0, 0, 0),
    "Rock": (6, 5, 3, 1, -1, -1, 1, 3, 5, 6),
    "Vocal": (-2, -2, 0, 3, 4, 4, 3, 1, 0, -1),
    "Electronic": (5, 5, 2, 0, -2, 1, 1, 2, 5, 5),
    "Treble Boost": (0, 0, 0, 0, 0, 1, 3, 5, 7, 8),
}


def gain_curve_db(n_bins, sample_rate, gains_db, frame=4096):
    """Per-bin gain in dB, log-spaced piecewise-linear between band centers."""
    freqs = np.arange(n_bins, dtype=np.float64) * (sample_rate / frame)
    with np.errstate(divide="ignore"):
        log_freqs = np.log2(np.maximum(freqs, 1e-3))
    centers = np.asarray(BAND_CENTERS, dtype=np.float64)
    xs = np.log2(centers)
    ys = np.asarray(gains_db, dtype=np.float64)
    return np.interp(log_freqs, xs, ys).astype(np.float64)


def _linear_gains(n_bins, sample_rate, gains_db, frame=4096):
    db = gain_curve_db(n_bins, sample_rate, gains_db, frame)
    return (10.0 ** (db / 20.0)).astype(np.float32)


def _soft_limit_over(x):
    """Soft-knee limiter for EQ output: only samples ABOVE 0 dBFS (would
    hard-clip at the int16 rails) are compressed smoothly toward a
    sub-rail ceiling; everything at or below +-32767 is returned
    untouched bit-exact (keeps the EQ-off/flat transparency contract)."""
    x = np.asarray(x, dtype=np.float32)
    absx = np.abs(x)
    over = absx > 32767.0
    if not np.any(over):
        return x
    e = absx[over] - 32767.0
    shaped = 32767.0 - _OVER_KNEE * (e / (e + _OVER_KNEE))
    res = x.copy()
    res[over] = np.sign(x[over]) * shaped
    return res


# Soft-limit ceiling depth beyond 0 dBFS (0.1 FS): asymptotically limits
# would-be clipping peaks to ~-0.2 dBFS instead of slamming the rails.
_OVER_KNEE = 3277.0


class EQProcessor:
    """Streaming 10-band EQ overlap-add processor (multichannel aware)."""

    FRAME = 4096

    def __init__(self, sample_rate, channels, gains_db=(0.0,) * 10):
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.frame = self.FRAME
        self.hop = self.frame // 2
        self._window = np.hanning(self.frame).astype(np.float32)
        self._gains = tuple(gains_db)
        self._curve = None
        self._set_curve()
        self._buf = np.zeros((0, self.channels), dtype=np.float32)
        self._carry = np.zeros((self.hop, self.channels), dtype=np.float32)
        self._outbuf = np.zeros((0, self.channels), dtype=np.float32)

    # --- configuration ---
    def set_gains(self, gains_db):
        self._gains = tuple(float(g) for g in gains_db)
        self._set_curve()

    def _set_curve(self):
        if self._gains and any(abs(g) > 1e-4 for g in self._gains):
            n_bins = self.frame // 2 + 1
            curve = _linear_gains(n_bins, self.sample_rate, self._gains, self.frame)
        else:
            curve = None  # zero-gain fast path: bypass FFT entirely
        self._curve = curve

    # --- streaming API ---
    def reset(self):
        self._buf = np.zeros((0, self.channels), dtype=np.float32)
        self._carry = np.zeros((self.hop, self.channels), dtype=np.float32)
        self._outbuf = np.zeros((0, self.channels), dtype=np.float32)

    def process(self, samples_i16):
        """Consume int16 samples (n, channels); return every finalized output
        sample so far, aligned with the input head (shorter than the input only
        while the first frames warm up)."""
        x = np.asarray(samples_i16, dtype=np.int16).reshape(-1, self.channels)
        n = x.shape[0]
        if n == 0:
            return x

        if self._curve is None:
            return x.reshape(-1, self.channels)

        data = x.astype(np.float32)
        self._buf = np.concatenate([self._buf, data], axis=0) if self._buf.size else data
        self._pump()
        return self._drain()

    def flush(self):
        """Push silence through to finalize the tail; returns remaining output."""
        if self._curve is None:
            return np.zeros((0, self.channels), dtype=np.int16)
        pad = np.zeros((self.frame * 2, self.channels), dtype=np.float32)
        self._buf = np.concatenate([self._buf, pad], axis=0) if self._buf.size else pad
        self._pump()
        return self._drain()

    def _pump(self):
        while self._buf.shape[0] >= self.frame:
            frame = self._buf[:self.frame]
            self._buf = self._buf[self.hop:]
            windowed = frame * self._window[:, None]
            spec = np.fft.rfft(windowed, axis=0)
            spec *= self._curve[:, None]
            res = np.fft.irfft(spec, n=self.frame, axis=0).astype(np.float32)
            out = res[:self.hop] + self._carry
            self._carry = res[self.hop:]
            if self._outbuf.size:
                self._outbuf = np.concatenate([self._outbuf, out], axis=0)
            else:
                self._outbuf = out

    def _drain(self):
        out = self._outbuf
        self._outbuf = np.zeros((0, self.channels), dtype=np.float32)
        return _soft_limit_over(out).astype(np.int16)
