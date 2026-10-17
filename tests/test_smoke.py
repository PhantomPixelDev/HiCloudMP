def test_player_constructs_offscreen(music_player):
    """Task 2 regression: MusicPlayer() must construct with pywin32 present.

    Before the fix, utils.HAS_WIN32 is True (pywin32 installed in the test venv)
    and __init__ calls create_win_proc_handler(self), a name that exists nowhere.
    """
    assert music_player.player is not None
