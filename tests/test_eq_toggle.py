"""Live equalizer toggle: enabling/disabling the EQ affects the CURRENT track.

The EQ dialog previously only flipped settings and called set_gains - when
the current track was playing NATIVELY (EQ was off when play() started),
nothing re-routed it through the engine, so sounds kept coming out flat.
Other players (VLC et al.) apply EQ live to the playing stream; we now
re-route the current track (position preserved) on the enable transition,
and hand back to native on disable unless the visualizer still owns the
engine route (flat gains then).
"""
import os



def _seed_local_track(mp, tmp_path):
    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    mp.playlist = [str(song)]
    mp.current_index = 0
    return song


def test_enabling_eq_re_routes_current_track(music_player, monkeypatch, tmp_path):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    song = _seed_local_track(mp, tmp_path)

    started = []
    gains_set = []
    seeks = []

    class _EngineStub:
        def set_gains(self, g):
            gains_set.append(list(g))

        def seek(self, ms):
            seeks.append(ms)

        def play(self, src, start_ms=0):
            started.append(("engine.play", src, start_ms))

        def is_playing(self):
            return True

    monkeypatch.setattr(mp, "eq_engine", _EngineStub(), raising=False)

    from PySide6.QtMultimedia import QMediaPlayer
    monkeypatch.setattr(mp, "effective_playback_state",
                        lambda: QMediaPlayer.PlaybackState.PlayingState,
                        raising=False)
    monkeypatch.setattr(mp.player, "position", lambda: 2500, raising=False)

    mp.apply_eq_toggle(True)
    assert started and started[0][0] == "engine.play", started
    assert os.path.normcase(started[0][1]) == os.path.normcase(str(song))
    assert seeks == [2500], "current position must survive the re-route"
    assert gains_set, "engine must receive the user's gains"


def test_disabling_eq_without_viz_returns_to_native(
        music_player, monkeypatch, qtbot, tmp_path):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    mp.settings.setValue("ui/visualizer_enabled", False)
    song = _seed_local_track(mp, tmp_path)

    status = {"stopped": False}

    class _EngineStub:
        def position_ms(self):
            return 5000

        def is_playing(self):
            return True

        def stop(self):
            status["stopped"] = True

    monkeypatch.setattr(mp, "eq_engine", _EngineStub(), raising=False)
    mp._using_engine = True
    mp._engine_source = ("file", str(song), "song")

    from PySide6.QtMultimedia import QMediaPlayer
    monkeypatch.setattr(mp, "effective_playback_state",
                        lambda: QMediaPlayer.PlaybackState.PlayingState,
                        raising=False)
    monkeypatch.setattr(mp.player, "position", lambda: 0, raising=False)

    set_urls, set_positions, plays = [], [], []
    monkeypatch.setattr(mp.player, "setSource",
                        lambda u: set_urls.append(u), raising=False)
    monkeypatch.setattr(mp.player, "setPosition",
                        lambda p: set_positions.append(p), raising=False)
    monkeypatch.setattr(mp.player, "play", lambda: plays.append(1),
                        raising=False)

    mp.apply_eq_toggle(False)
    qtbot.wait(250)   # the 150 ms position-restore singleShot
    assert status["stopped"], "engine must stop"
    assert any("song.mp3" in str(u) for u in set_urls), set_urls
    assert set_positions == [5000], "position must carry over"
    assert plays


def test_disabling_eq_with_viz_keeps_engine_flat(music_player, monkeypatch):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", True)
    mp.settings.setValue("ui/visualizer_enabled", True)

    gains_set = []
    stopped = []

    class _EngineStub:
        def set_gains(self, g):
            gains_set.append(list(g))

        def stop(self):
            stopped.append(True)

        def position_ms(self):
            return 0

        def is_playing(self):
            return True

    monkeypatch.setattr(mp, "eq_engine", _EngineStub(), raising=False)
    mp._using_engine = True

    mp.apply_eq_toggle(False)
    assert not stopped, "visualizer still needs the engine route"
    assert gains_set and all(v == 0.0 for v in gains_set[-1]), \
        "gains must go flat when the visualizer keeps the route"


def test_enabling_eq_on_cloud_defers_to_next_track(music_player, monkeypatch):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    mp.playlist = [{"type": "cloud", "path": "https://example.com/a.mp3"}]
    mp.current_index = 0
    started = []
    monkeypatch.setattr(mp, "_engine_start",
                        lambda *a, **k: started.append(a), raising=False)
    mp.apply_eq_toggle(True)
    assert started == [], "cloud streams re-route on the next track"


def test_eq_apply_cb_re_routes_only_on_transition(music_player, monkeypatch,
                                                  tmp_path):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    _seed_local_track(mp, tmp_path)

    routes = []
    monkeypatch.setattr(mp, "_engine_start",
                        lambda *a, **k: routes.append(a), raising=False)
    gains_applied = []
    monkeypatch.setattr(mp.eq_engine, "set_gains",
                        lambda g: gains_applied.append(tuple(g)), raising=False)
    monkeypatch.setattr(mp.player, "position", lambda: 0, raising=False)

    cb = mp.make_eq_apply_cb()

    cb((6.0, 0, 0, 0, 0, 0, 0, 0, 0, 0), True)     # transition on
    assert len(routes) == 1, "enable must re-route once"

    cb((8.0, 0, 0, 0, 0, 0, 0, 0, 0, 0), True)     # slider move, still on
    assert len(routes) == 1, "gains-only updates must NOT re-route"
    assert gains_applied and gains_applied[-1][0] == 8.0

    cb((0.0,) * 10, False)                          # transition off
    assert not getattr(mp, "_using_engine", False), "must return to native"


def test_make_eq_apply_cb_persists_settings(music_player, monkeypatch, tmp_path):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    _seed_local_track(mp, tmp_path)
    monkeypatch.setattr(mp.player, "position", lambda: 0, raising=False)
    monkeypatch.setattr(mp, "_engine_start", lambda *a, **k: None, raising=False)

    cb = mp.make_eq_apply_cb()
    cb((5.0, 0, 0, 0, 0, 0, 0, 0, 0, 0), True)

    assert mp.settings.value("audio/eq_enabled", False, type=bool) is True
    gains = [float(v) for v in
             str(mp.settings.value("audio/eq_gains", "")) .split(",")]
    assert gains[0] == 5.0
