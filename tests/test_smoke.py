import pytest

from conftest import isolated_qsettings_factory


@pytest.fixture()
def music_player(qtbot, monkeypatch):
    """Fully isolated MusicPlayer: offscreen Qt, stubbed user dirs, no registry writes."""
    import player as player_mod

    monkeypatch.setattr(player_mod, "QSettings", isolated_qsettings_factory(monkeypatch))
    mp = player_mod.MusicPlayer()
    qtbot.addWidget(mp)
    return mp


def test_player_constructs_offscreen(music_player):
    """Task 2 regression: MusicPlayer() must construct with pywin32 present.

    Before the fix, utils.HAS_WIN32 is True (pywin32 installed in the test venv)
    and __init__ calls create_win_proc_handler(self), a name that exists nowhere.
    """
    assert music_player.player is not None
