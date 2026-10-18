"""Engine seek must keep the sink alive (real devices, Windows audio).

Root cause (2026-10-18, user report 'seeking does not work at all'):
Qt6 QAudioSink.reset() leaves the sink in StoppedState and closes the
push-mode QIODevice, so after eq_engine.seek() the pump silently writes
nothing (bytesFree()==0 no-ops) - playback dies and the position freezes
at the seek target.
"""
import os
import time
import wave
import struct
import math

import pytest

from PySide6.QtCore import QCoreApplication

from PySide6.QtMultimedia import QMediaDevices, QtAudio

pytestmark = pytest.mark.skipif(
    not QMediaDevices.audioOutputs(),
    reason="no audio output device on this host")


def _make_tone(path, seconds=9):
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(44100)
        frames = bytearray()
        for i in range(44100 * seconds):
            frames += struct.pack(
                "<h", int(12000 * math.sin(2 * math.pi * 440 * i / 44100)))
        f.writeframes(bytes(frames))


def _settle(app, ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def _wait_position(app, engine, pred, timeout_s=6.0):
    end = time.time() + timeout_s
    while time.time() < end:
        app.processEvents()
        if pred(engine.position_ms()):
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def engine_and_tone(tmp_path, qapp):
    from eq_engine import EQEngine
    tone = tmp_path / "tone9.wav"
    _make_tone(tone)
    engine = EQEngine()
    yield engine, str(tone), qapp
    engine.stop()


def test_seek_keeps_sink_active_and_progressing(engine_and_tone):
    """Plain seek while playing: audio must keep flowing after the jump."""
    engine, tone, app = engine_and_tone
    engine.play(tone)
    assert _wait_position(app, engine, lambda p: p > 400), \
        f"never got an early position (pos={engine.position_ms()})"

    engine.seek(4000)
    _settle(app, 900)
    p1 = engine.position_ms()
    assert 3000 <= p1 <= 5200, f"seek result wrong: {p1}"
    assert engine.is_playing(), "engine no longer playing after seek"
    assert engine._sink is not None, "sink torn down by seek"
    assert engine._sink.state() != QtAudio.State.StoppedState, \
        f"sink dead after seek: {engine._sink.state()}"

    # audio must resume within a decode-walk budget: wait for real progress
    before = p1
    resumed = False
    end = time.time() + 8
    while time.time() < end:
        app.processEvents()
        if (engine._sink.state() == QtAudio.State.ActiveState
                and engine.position_ms() - before > 400):
            resumed = True
            break
        time.sleep(0.02)
    assert resumed, \
        f"audio never resumed after seek (sink={engine._sink.state()}, " \
        f"pos={engine.position_ms()})"


def test_slider_sequence_pause_seek_resume_keeps_playing(engine_and_tone):
    """Desktop slider UX: press (pause) -> drag (seek, paused) -> release."""
    engine, tone, app = engine_and_tone
    engine.play(tone)
    assert _wait_position(app, engine, lambda p: p > 400)

    engine.pause()
    _settle(app, 200)
    engine.seek(3000)
    _settle(app, 700)
    p3 = engine.position_ms()
    assert 2400 <= p3 <= 4200, f"paused seek landed at {p3}"

    engine.resume()
    # audio must come back within a decode-walk budget
    resumed = False
    p_base = engine.position_ms()
    end = time.time() + 8
    while time.time() < end:
        app.processEvents()
        if (engine._sink.state() == QtAudio.State.ActiveState
                and engine.position_ms() - p_base > 350):
            resumed = True
            break
        time.sleep(0.02)
    assert resumed, \
        f"no progress after resume (sink={engine._sink.state()}, " \
        f"pos={engine.position_ms()})"
    assert engine._sink is not None
    assert engine._sink.state() != QtAudio.State.StoppedState, \
        f"sink dead after resume: {engine._sink.state()}"
