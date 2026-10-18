"""One playback-state truth for native and EQ-engine paths.

The web panel and the tray both read the NATIVE player state, which sits
idle while the EQ engine plays - the panel showed "stopped" and the tray
icon showed "stop" during engine playback. effective_playback_state()
gives both the engine-aware answer."""
import pytest


class _NativeStub:
    class _State:
        PlayingState = "PlayingState"
        PausedState = "PausedState"
        StoppedState = "StoppedState"

    def __init__(self, state):
        self._s = state

    def playbackState(self):
        return self._s


class _EngineStub:
    def __init__(self, playing, paused):
        self._playing = playing
        self._paused = paused

    def is_playing(self):
        return self._playing

    def is_paused(self):
        return self._paused


def _make(player_state, using_engine=False, engine=None):
    from player import MusicPlayer
    obj = MusicPlayer.__new__(MusicPlayer)  # skip __init__; only mixin logic
    obj.player = player_state
    obj._using_engine = using_engine
    obj.eq_engine = engine
    return obj


def test_engine_playing_reports_playing():
    from playback import PlaybackEngineMixin
    obj = _make(_NativeStub(_NativeStub._State.StoppedState),
                using_engine=True,
                engine=_EngineStub(True, False))
    s = str(obj.effective_playback_state())
    assert "Playing" in s


def test_engine_paused_reports_paused():
    obj = _make(_NativeStub(_NativeStub._State.StoppedState),
                using_engine=True,
                engine=_EngineStub(False, True))
    assert "Paused" in str(obj.effective_playback_state())


def test_engine_idle_reports_stopped():
    obj = _make(_NativeStub(_NativeStub._State.StoppedState),
                using_engine=True,
                engine=_EngineStub(False, False))
    assert "Stopped" in str(obj.effective_playback_state())


def test_native_path_passthrough():
    obj = _make(_NativeStub(_NativeStub._State.PlayingState))
    assert "Playing" in str(obj.effective_playback_state())


def test_eq_engine_is_paused_flag():
    from eq_engine import EQEngine
    e = EQEngine()
    # no sink loaded -> neither playing nor paused
    assert e.is_playing() is False
    assert e.is_paused() is False
    e._sink = object()   # sink loaded but not playing = paused
    assert e.is_paused() is True
    e._playing = True
    assert e.is_paused() is False


def test_web_status_state_engine_aware(music_player, monkeypatch):
    """_get_status rides the unified state instead of the idle native one."""
    import web_control
    server = web_control.WebControlServer(music_player, host="127.0.0.1",
                                          port=5099, token="t")
    mp = music_player
    monkeypatch.setattr(mp, "_using_engine", True, raising=False)
    monkeypatch.setattr(mp.eq_engine, "is_playing", lambda: True)
    assert "Playing" in server._get_status()["state"]
    monkeypatch.setattr(mp.eq_engine, "is_playing", lambda: False)
    assert "Playing" not in server._get_status()["state"]


def test_tray_uses_effective_state():
    import tray
    src = tray.__file__
    src = __import__("pathlib").Path(src).read_text(encoding="utf-8")
    assert "effective_playback_state" in src, \
        "tray must derive its icon from the unified state"
