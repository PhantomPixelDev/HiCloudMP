"""Engine failure must be loud: EQ and visualizer live or die with the
decoder->EQ->sink route. When that route fails on the user's real device
there is no spectrum and no EQ effect - and until now the ONLY signal was
a status-bar line expiring after 4 seconds, easily missed, worded as if
only the equalizer were affected. The fallback must name the engine
generally and also raise a tray notification (the surface the user is
looking at while music plays).

The native player is replaced whole (repo house pattern, cf. test_eq_toggle
replacing eq_engine): method-level shadowing on shiboken instances is
bypassed by class-level descriptors and is not trustworthy here.
"""
from types import SimpleNamespace

import pytest


class _NativeStub:
    """Facade on the real player: setSource/play are recorded only (the
    real WMF probe of empty files proved flaky under pytest); every other
    attribute — closeEvent teardown uses stop() etc — delegates untouched."""

    def __init__(self, real, log):
        self._real = real
        self._log = log

    def __getattr__(self, name):
        return getattr(self._real, name)

    def setSource(self, *a, **k):
        self._log.append("setSource")   # no delegation: no backend probing

    def play(self, *a, **k):
        self._log.append("play")   # no delegation: no real start


def test_engine_failure_shows_tray_toast_and_reverts(
        music_player, monkeypatch, tmp_path):
    mp = music_player
    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    mp._using_engine = True
    mp._engine_source = ("file", str(song), "song")

    native = []
    monkeypatch.setattr(mp, "player", _NativeStub(mp.player, native),
                        raising=False)

    toasts = []

    class _Icon:
        def showMessage(self, *a, **k):
            toasts.append(a)

    stub_tray = SimpleNamespace(tray_icon=_Icon())
    monkeypatch.setattr(mp, "tray", stub_tray, raising=False)

    mp._engine_playback_error("decoder exploded")

    assert mp._using_engine is False
    assert "setSource" in native and "play" in native, native
    assert toasts, "engine failure must surface a tray toast"


def test_engine_failure_message_covers_viz_not_only_eq(
        music_player, monkeypatch, tmp_path):
    mp = music_player
    song = tmp_path / "viz.mp3"
    song.write_bytes(b"")
    mp._using_engine = True
    mp._engine_source = ("file", str(song), "song")

    monkeypatch.setattr(mp, "player", _NativeStub(mp.player, []),
                        raising=False)

    toasts = []

    class _Icon:
        def showMessage(self, *a, **k):
            toasts.append(a)

    monkeypatch.setattr(mp, "tray",
                        SimpleNamespace(tray_icon=_Icon()), raising=False)

    mp._engine_playback_error("sink dead")

    assert toasts, "engine failure must surface a tray toast"
    joined = " ".join(str(a) for a in toasts[0]).lower()
    assert "visual" in joined or "engine" in joined, toasts


def test_engine_failure_without_tray_still_recovers(
        music_player, monkeypatch, tmp_path):
    mp = music_player
    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    mp._using_engine = True
    mp._engine_source = ("file", str(song), "song")

    native = []
    monkeypatch.setattr(mp, "player", _NativeStub(mp.player, native),
                        raising=False)
    monkeypatch.setattr(mp, "tray", None, raising=False)

    mp._engine_playback_error("boom")   # must not raise despite no tray

    assert mp._using_engine is False
    assert "play" in native, native
