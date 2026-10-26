"""player.py split: dialogs live in dialogs.py; player.py re-exports."""
from sourcepaths import read


def test_dialogs_own_the_dialog_classes():
    from hicloudmp.ui import dialogs
    for name in ("AddCloudDialog", "EditCloudDialog", "CloudAccountsDialog",
                 "SettingsDialog", "EqualizerDialog"):
        assert hasattr(dialogs, name), name


def test_player_reexports_dialogs():
    from hicloudmp.ui import dialogs
    from hicloudmp.ui import player
    for name in ("CloudAccountsDialog", "SettingsDialog"):
        assert getattr(player, name) is getattr(dialogs, name), name


def test_player_no_longer_defines_dialogs_inline():
    src = read("ui/player.py")
    for name in ("class SettingsDialog", "class CloudAccountsDialog"):
        assert name not in src, f"{name} must move to dialogs.py"
