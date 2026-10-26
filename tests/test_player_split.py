"""Structural guard for the bounded player.py split: play history and
folder watching are owned by their mixins, not duplicated back into the
MusicPlayer class."""
from hicloudmp.core.folder_watch import FolderWatchMixin
from hicloudmp.core.history import PlayHistoryMixin
from hicloudmp.ui import player as player_mod


def test_mixins_are_mixed_into_the_player(music_player):
    assert isinstance(music_player, PlayHistoryMixin)
    assert isinstance(music_player, FolderWatchMixin)


def test_implementations_live_in_the_mixins():
    owned_elsewhere = (
        "record_play", "_load_play_history", "_rebuild_recent_menu",
        "_refresh_folder_watcher", "_watch_directories",
        "_apply_watched_folder_refresh",
    )
    for name in owned_elsewhere:
        assert name not in vars(player_mod.MusicPlayer), \
            f"{name} must not be duplicated in MusicPlayer"
    assert player_mod.MusicPlayer.record_play is PlayHistoryMixin.record_play
    assert player_mod.MusicPlayer._refresh_folder_watcher \
        is FolderWatchMixin._refresh_folder_watcher
