"""Spectrum tap for the visualizer.

Turns a short mono block of int16-scale PCM into log-spaced band
energies in [0, 1] (60 dB floor). Runs in the EQ engine's pump tick —
a 2048-point real FFT per ~40 ms of audio is microseconds with numpy.
"""
import numpy as np

N_BANDS = 24
N_FFT = 2048
F_MIN = 40.0
F_MAX = 16000.0
_DYN_RANGE_DB = 60.0
_WINDOW = np.hanning(N_FFT)


def compute_spectrum(block, n_bands=N_BANDS):
    """Band energies of `block` (int16-scale mono (n,) or (n, ch)).

    Returns float32 array of length n_bands: per-band RMS-magnitude on a
    60 dB scale mapped to 0..1 (0 = silence/inaudible, 1 = full scale).
    """
    arr = np.asarray(block)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    tail = arr.astype(np.float32)[-N_FFT:]
    if tail.size < N_FFT:
        tail = np.pad(tail, (N_FFT - tail.size, 0), mode="constant")
    spec = np.abs(np.fft.rfft(tail * _WINDOW))
    freqs = np.fft.rfftfreq(N_FFT, d=1.0 / 44100.0)

    # Log-spaced band edges, DC excluded (offset noise shows up there).
    edges = np.geomspace(F_MIN, F_MAX, n_bands + 1)
    values = np.zeros(n_bands, dtype=np.float32)
    for i in range(n_bands):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bands - 1:
            mask = (freqs >= lo) & (freqs <= hi)
        else:
            mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            continue
        rel = float(np.mean(spec[mask])) / (N_FFT // 4) / 32768.0
        db = 20.0 * np.log10(rel + 1e-9)
        values[i] = float(np.clip((db + _DYN_RANGE_DB) / _DYN_RANGE_DB,
                                  0.0, 1.0))
    return values
