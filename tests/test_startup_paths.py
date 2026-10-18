"""Command-line startup paths: `HiCloudMP.exe track.mp3` enqueues and
preselects the file (also powers Windows 'open with' HiCloud MP).
Nothing is auto-played and nothing is persisted."""
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def wav(tmp_path):
    import wave

    path = tmp_path / "tone.wav"
    sr = 44100
    t = np.arange(sr * 2) / sr
    data = (np.sin(2 * np.pi * 440.0 * t) * 12000).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(sr)
        inter = np.empty(data.size * 2, dtype=np.int16)
        inter[0::2] = data
        inter[1::2] = data
        f.writeframes(inter.tobytes())
    return path


def test_startup_paths_enqueued_and_selected(music_player, wav):
    mp = music_player
    mp.playlist.clear()
    mp.playlist_widget.clear()
    missing = str(wav.parent / "nope.wav")
    mp._apply_startup_paths([str(wav), missing])
    assert mp.playlist == [str(wav)]
    assert mp.playlist_widget.count() == 1
    assert mp.current_index == 0


def test_startup_paths_missing_only_is_noop(music_player, tmp_path):
    mp = music_player
    before = list(mp.playlist)
    mp._apply_startup_paths([str(tmp_path / "ghost.mp3")])
    assert mp.playlist == before


def test_main_passes_cli_paths():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "startup_paths" in src, "main.py must forward CLI paths"
    assert "sys.argv" in src
