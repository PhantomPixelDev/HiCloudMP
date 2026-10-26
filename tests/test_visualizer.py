"""Visualizer: spectrum bars in the transport bar, fed by the EQ engine.

Only the engine path has real audio data to show. When the EQ engine is
off the visualizer shows a calm idle baseline - never a fake dance (the
EQ must not be placebo, and neither may the visualizer).
"""



def test_widget_paints_more_bars_with_data(qapp):
    from hicloudmp.ui.visualizer import SFVisualizer
    w = SFVisualizer()
    w.resize(120, 32)

    def differs(a, b):
        n = 0
        for y in range(a.height()):
            for x in range(a.width()):
                if a.pixelColor(x, y) != b.pixelColor(x, y):
                    n += 1
        return n

    w.set_spectrum(None)
    idle = w.grab().toImage()
    w.set_spectrum([1.0] * 24)
    lit = w.grab().toImage()
    w.set_spectrum([0.0] * 24)
    calm = w.grab().toImage()
    # engine data changes the painting substantially...
    assert differs(idle, lit) > 300, "full bars must paint tall"
    # ...while silence collapses to the SAME calm baseline (no fake dance)
    assert differs(idle, calm) < 300, "zero spectrum must look idle"


def test_display_curve_lifts_quiet_bands(qapp):
    """Music peaks around 0.4 on the 60 dB scale; a raw linear bar barely
    moves. The display curve must lift real signal without faking silence."""
    from hicloudmp.ui.visualizer import SFVisualizer
    assert SFVisualizer.display_level(0.0) == 0.0
    assert SFVisualizer.display_level(1.0) == 1.0
    assert SFVisualizer.display_level(0.2) > 0.2
    assert SFVisualizer.display_level(0.4) > 0.45


def test_transport_bar_hosts_visualizer(music_player):
    from hicloudmp.ui.visualizer import SFVisualizer
    assert isinstance(music_player.visualizer, SFVisualizer)
    assert music_player.visualizer.parent() is not None


def test_visualizer_polls_engine_only_in_engine_mode(music_player, monkeypatch):
    mp = music_player
    feeds = []
    monkeypatch.setattr(mp.visualizer, "set_spectrum",
                        lambda data: feeds.append(data))
    mp._using_engine = True
    monkeypatch.setattr(mp.eq_engine, "get_spectrum",
                        lambda: [0.5] * 24, raising=False)
    mp._update_visualizer()
    assert feeds[-1] == [0.5] * 24
    mp._using_engine = False
    mp._update_visualizer()
    assert feeds[-1] is None


def test_viz_timer_pumps_at_20hz_only_while_playing(music_player):
    """The pump cadence is ~20 Hz, but it parks when nothing plays and
    restarts on a play-state change (deep coverage: tests/test_viz_timer.py).
    v1.0.4 ran it forever, even stopped."""
    mp = music_player
    assert mp._viz_timer.interval() == 50
    mp.show()

    class _Playing:
        def is_playing(self):
            return True

    mp._using_engine = True
    mp.eq_engine = _Playing()
    mp._update_visualizer()
    assert mp._viz_timer.isActive()

    class _Stopped:
        def is_playing(self):
            return False

    mp.eq_engine = _Stopped()
    mp._update_visualizer()
    assert not mp._viz_timer.isActive()
