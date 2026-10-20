"""The visualizer timer parks itself when nothing interesting happens.

v1.0.4 ran the ~20 Hz visualizer pump forever, playing or not, visible
or not — 20 event-loop wakeups per second for a dead spectrum. Now the
tick stops itself when nothing plays (or the window is hidden), and
state changes (native or engine) restart it.
"""


def _fake_engine(playing):
    class _E:
        def is_playing(self):
            return playing
    return _E()


def test_timer_parks_when_not_playing(music_player):
    music_player.show()
    music_player._using_engine = True
    music_player.eq_engine = _fake_engine(False)
    music_player._update_visualizer()
    assert not music_player._viz_timer.isActive()


def test_timer_runs_while_playing(music_player):
    music_player.show()
    music_player._using_engine = True
    music_player.eq_engine = _fake_engine(True)
    music_player._update_visualizer()
    assert music_player._viz_timer.isActive()


def test_show_restarts_a_parked_pump(music_player):
    """A tick while the window was hidden parks the pump (nothing to paint);
    showing the window while audio plays must restart it. Regression guard
    for the suite-order race (fixture setup ticks park the pump before
    show() happens)."""
    music_player._using_engine = True
    music_player.eq_engine = _fake_engine(True)
    music_player._viz_timer.stop()   # parked by an earlier idle tick
    music_player.show()
    assert music_player._viz_timer.isActive()


def test_state_change_parks_and_resumes(music_player):
    music_player.show()
    music_player._using_engine = True
    music_player.eq_engine = _fake_engine(False)
    music_player._update_visualizer()
    assert not music_player._viz_timer.isActive()

    # Engine resumes: the state_changed signal restarts the pump.
    music_player.eq_engine = _fake_engine(True)
    music_player._viz_follow_state("playing")
    assert music_player._viz_timer.isActive()

    # Engine pauses again: the next tick parks it.
    music_player.eq_engine = _fake_engine(False)
    music_player._update_visualizer()
    assert not music_player._viz_timer.isActive()


def test_follow_state_tolerates_broken_state(music_player):
    # A raise inside the state probe must not leave the pump stopped
    # while audio may actually be running (fail open).
    music_player.show()

    class _Broken:
        def is_playing(self):
            raise RuntimeError("backend died")

    music_player._using_engine = True
    music_player.eq_engine = _Broken()
    music_player._viz_follow_state("playing")
    assert music_player._viz_timer.isActive()
