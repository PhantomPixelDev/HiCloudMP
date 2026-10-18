"""Theme system: one module owns every color/spacing decision.

- build_qss(theme, accent, density) generates the full app stylesheet
- apply_theme() resolves values from QSettings and applies them
- SettingsDialog exposes Appearance controls and persists them
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow

import theme as theme_mod


def test_build_qss_interpolates_accent():
    qss = theme_mod.build_qss(theme="Dark", accent="#10b981", density="comfortable")
    # Progress fill, slider handle and accent-active buttons carry the accent
    assert "#10b981" in qss
    assert 'QPushButton[accentActive="true"]' in qss


def test_build_qss_dark_and_light_differ():
    dark = theme_mod.build_qss(theme="Dark", accent="#10b981", density="comfortable")
    light = theme_mod.build_qss(theme="Light", accent="#10b981", density="comfortable")
    assert dark != light
    # The light theme must not keep dark chrome backgrounds
    assert "#0f1218" not in light
    assert "background-color:#ffffff" in light.replace("background-color: #ffffff", "background-color:#ffffff")


def test_build_qss_density_tokens():
    comfy = theme_mod.build_qss(theme="Dark", accent="#10b981", density="comfortable")
    compact = theme_mod.build_qss(theme="Dark", accent="#10b981", density="compact")
    assert comfy != compact
    # compact drops the comfortable control padding
    assert "padding: 6px 12px" not in compact
    assert "padding: 6px 12px" in comfy


def test_apply_theme_sets_stylesheet_with_accent(qtbot):
    w = QMainWindow()
    theme_mod.apply_theme(w, theme="Dark", accent="#3b82f6", density="compact")
    styled = w.styleSheet()
    assert "#3b82f6" in styled
    assert w.windowTitle() != "fail"


def test_settings_dialog_persists_appearance(music_player, qtbot, monkeypatch):
    """Combos write ui/accent + ui/density alongside theme via isolated QSettings."""
    import player as player_mod

    dlg = player_mod.SettingsDialog(music_player)
    dlg.theme_combo.setCurrentText("Light")
    dlg.accent_combo.setCurrentText("Violet")
    dlg.density_combo.setCurrentText("Compact")
    dlg.save_settings()

    assert dlg.settings.value("theme", "") == "Light"
    assert dlg.settings.value("ui/accent", "") == "#8b5cf6"
    assert dlg.settings.value("ui/density", "") == "compact"


def test_settings_dialog_defaults_read_back(music_player, qtbot):
    import player as player_mod

    dlg = player_mod.SettingsDialog(music_player)
    assert dlg.accent_combo.currentText() == "Emerald"
    assert dlg.density_combo.currentText() == "Comfortable"
