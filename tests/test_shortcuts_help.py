"""The app had global shortcuts (Space/arrows/Ctrl+S, Del/Home/End in the
playlist) that were discoverable only by accident. Help > Keyboard
Shortcuts now opens a dialog generated from one data table, so the doc
cannot drift from the actions it describes.
"""
from PySide6.QtWidgets import QLabel

from hicloudmp.ui import player as player_mod


def _help_menu(mp):
    for action in mp.menuBar().actions():
        menu = action.menu()
        if menu is not None and menu.title() == "Help":
            return menu
    raise AssertionError("Help menu missing")


def test_help_menu_offers_shortcuts_dialog(music_player):
    mp = music_player
    texts = [a.text() for a in _help_menu(mp).actions()]
    assert "Keyboard Shortcuts" in texts, texts


def test_dialog_lists_every_documented_shortcut(music_player):
    mp = music_player
    dlg = mp._build_shortcuts_dialog()
    keys = [lbl.text() for lbl in dlg.findChildren(QLabel, "shortcut_keys")]
    labels = [lbl.text() for lbl in dlg.findChildren(QLabel, "shortcut_desc")]

    expected_keys = [k for k, _ in player_mod.SHORTCUT_HELP]
    expected_desc = [d for _, d in player_mod.SHORTCUT_HELP]
    assert keys == expected_keys
    assert labels == expected_desc
    assert "Space" in keys and "Del" in keys


def test_documented_transport_keys_match_real_actions(music_player):
    mp = music_player
    doc = dict(player_mod.SHORTCUT_HELP)
    assert doc[mp.play_action.shortcut().toString()] == "Play / Pause"
    assert doc[mp.next_action.shortcut().toString()] == "Next track"
    assert doc[mp.prev_action.shortcut().toString()] == "Previous track"
    assert doc[mp.stop_action.shortcut().toString()] == "Stop"


def test_shortcut_dialog_is_modal_safe(music_player):
    mp = music_player
    dlg = mp._build_shortcuts_dialog()
    assert dlg.windowTitle() == "Keyboard Shortcuts"
    assert not dlg.isVisible(), "building the dialog must not show it"
