"""player.py split round 2: the EQ-engine glue lives in playback.py as a
mixin; MusicPlayer mixes it in. Methods must keep working verbatim."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

METHODS = ("_eq_active", "_engine_start", "_on_engine_state",
           "_on_engine_track_finished", "_engine_playback_error")


def test_playback_module_owns_engine_glue():
    import playback
    for name in METHODS:
        assert hasattr(playback.PlaybackEngineMixin, name), name


def test_musicplayer_mixes_it_in():
    from player import MusicPlayer
    import playback
    assert issubclass(MusicPlayer, playback.PlaybackEngineMixin)


def test_methods_moved_out_of_player_source():
    src = (ROOT / "player.py").read_text(encoding="utf-8")
    for name in METHODS:
        assert f"def {name}(" not in src, f"{name} must live in playback.py"
