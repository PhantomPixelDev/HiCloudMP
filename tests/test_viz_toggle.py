"""Live visualizer toggle: routing switches without interrupting the track.

The settings checkbox previously only changed the NEXT track's routing.
A user enabling the visualizer mid-track sees dead bars until the song
changes - broken UX. Now the toggle re-routes the CURRENT track through
the engine (flat gains, position preserved) and back to native when the
visualizer is turned off (with the EQ off, otherwise the EQ keeps the
engine route).
"""
import os




def test_enabling_viz_re_routes_current_track(music_player, monkeypatch, tmp_path):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    mp.settings.setValue("ui/visualizer_enabled", False)

    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    mp.playlist = [str(song)]
    mp.current_index = 0

    calls = []

    def fake_engine_start(kind, src, name='', start_ms=0):
        calls.append((kind, src, name, start_ms))

    seeks = []

    class _EngineStub:
        def play(self, src, start_ms=0):
            calls.append(("engine.play", src, start_ms))

        def seek(self, ms):
            seeks.append(ms)

        def is_playing(self):
            return True

    monkeypatch.setattr(mp, "eq_engine", _EngineStub(), raising=False)
    monkeypatch.setattr(mp, "_engine_start", fake_engine_start, raising=False)
    monkeypatch.setattr(mp, "effective_playback_state",
                        lambda: type("S", (), {"PlayingState": 1}).PlayingState()
                        if False else 1, raising=False)
    monkeypatch.setattr(mp.player, "position", lambda: 4321, raising=False)

    mp.apply_visualizer_toggle(True)
    assert calls, "toggle must re-route the current track through the engine"
    kind, src, _, _ = calls[0]
    assert kind == "file"
    assert os.path.normcase(str(src)) == os.path.normcase(str(song))
    assert seeks == [4321], "current position must be preserved"


def test_disabling_viz_returns_current_track_to_native(
        music_player, monkeypatch, qtbot):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    mp.settings.setValue("ui/visualizer_enabled", True)

    class _EngineStub:
        def position_ms(self):
            return 4321

        def is_playing(self):
            return True

        def stop(self):
            engine_state["stopped"] = True

    engine_state = {}
    monkeypatch.setattr(mp, "eq_engine", _EngineStub(), raising=False)
    mp._using_engine = True
    mp._engine_source = ("file", r"C:\music\song.mp3", "song")
    monkeypatch.setattr(mp.player, "position", lambda: 0, raising=False)

    setsource, setpos, play = [], [], []
    monkeypatch.setattr(mp.player, "setSource",
                        lambda u: setsource.append(u), raising=False)
    monkeypatch.setattr(mp.player, "setPosition",
                        lambda p: setpos.append(p), raising=False)
    monkeypatch.setattr(mp.player, "play", lambda: play.append(1), raising=False)
    monkeypatch.setattr(mp, "player_position_ms", lambda: 4321, raising=False)

    # production order: save_settings persists the new value, then applies
    mp.settings.setValue("ui/visualizer_enabled", False)
    mp.apply_visualizer_toggle(False)
    qtbot.wait(250)   # the 150 ms position-restore singleShot
    assert engine_state.get("stopped"), "engine must be stopped"
    set_urls = [str(u) for u in setsource]
    assert any(u.endswith("song.mp3')") for u in set_urls), set_urls
    assert setpos == [4321], "position must carry over to native"
    assert play


def test_viz_toggle_neutral_when_eq_is_on(music_player, monkeypatch):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", True)
    mp.settings.setValue("audio/eq_gains", "6,0,0,0,0,0,0,0,0,0")
    mp._using_engine = True
    started = []
    monkeypatch.setattr(mp, "_engine_start",
                        lambda *a, **k: started.append(a), raising=False)
    mp.apply_visualizer_toggle(False)   # EQ owns the route: nothing changes
    mp.apply_visualizer_toggle(True)
    assert started == [], "EQ route must be untouched by the viz toggle"


def test_viz_toggle_skips_cloud_stream(music_player, monkeypatch):
    mp = music_player
    mp.settings.setValue("audio/eq_enabled", False)
    mp.playlist = [{"type": "cloud", "path": "https://example.com/a.mp3"}]
    mp.current_index = 0
    started = []
    monkeypatch.setattr(mp, "_engine_start",
                        lambda *a, **k: started.append(a), raising=False)
    mp.apply_visualizer_toggle(True)
    assert started == [], "cloud streams re-route on the next track only"
