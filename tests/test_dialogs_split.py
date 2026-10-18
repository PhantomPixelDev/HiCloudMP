"""player.py split: dialogs live in dialogs.py; player.py re-exports."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dialogs_own_the_dialog_classes():
    import dialogs
    for name in ("AddCloudDialog", "EditCloudDialog", "CloudAccountsDialog",
                 "SettingsDialog", "EqualizerDialog"):
        assert hasattr(dialogs, name), name


def test_player_reexports_dialogs():
    import dialogs
    import player
    for name in ("CloudAccountsDialog", "SettingsDialog"):
        assert getattr(player, name) is getattr(dialogs, name), name


def test_player_no_longer_defines_dialogs_inline():
    src = (ROOT / "player.py").read_text(encoding="utf-8")
    for name in ("class SettingsDialog", "class CloudAccountsDialog"):
        assert name not in src, f"{name} must move to dialogs.py"
