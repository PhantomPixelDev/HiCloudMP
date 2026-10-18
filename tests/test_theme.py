"""Theme system: one module owns every color/spacing decision.

- build_qss(theme, accent, density) generates the full app stylesheet
- apply_theme() resolves values from QSettings and applies them
- SettingsDialog exposes Appearance controls and persists them
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
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


# =====================================================================
# Extended customization: more presets, custom accent, background image
# =====================================================================

def test_accent_preset_gallery_extended():
    """A richer preset gallery (10+) so accents do not feel restrictive."""
    assert len(theme_mod.ACCENTS) >= 10
    for must in ("Cyan", "Orange", "Pink", "Lime", "Indigo"):
        assert must in theme_mod.ACCENTS, must
    for name, hexval in theme_mod.ACCENTS.items():
        c = QColor(hexval)
        assert c.isValid(), f"{name}: invalid preset color {hexval}"


def test_accent_hex_handles_custom(qapp):
    """'Custom' resolves to the dialog-provided hex; name lookups unchanged."""
    assert theme_mod.accent_hex("Violet") == "#8b5cf6"
    assert theme_mod.accent_hex("Custom", custom="#ff0055") == "#ff0055"
    assert theme_mod.accent_hex("#a1b2c3") == "#a1b2c3"
    assert theme_mod.accent_hex("Custom", custom=None) == theme_mod._DEFAULTS["accent"]


def test_build_qss_without_bg_has_no_background_section():
    qss = theme_mod.build_qss(theme="Dark", accent="#10b981", density="comfortable")
    assert "#central {" not in qss  # honest: no bg image requested, no rule


def test_build_qss_with_bg_embeds_image_and_glass_surfaces():
    qss = theme_mod.build_qss(theme="Dark", accent="#10b981",
                              density="comfortable",
                              bg="C:/Users/x/bgcache/bg_1.png")
    assert repr(qss) and "url('C:/Users/x/bgcache/bg_1.png')" in qss
    assert "QWidget#central" in qss
    # With a photo behind, big surfaces go translucent glass so it shows
    tail = qss[qss.index("QWidget#central"):]
    assert "rgba(" in tail
    assert tail.count("sidebar") >= 1


def test_prepare_background_dims_and_caches(qapp, tmp_path):
    from PySide6.QtGui import QColor, QImage

    src = tmp_path / "bright.png"
    img = QImage(40, 20, QImage.Format.Format_ARGB32)
    img.fill(0)
    for x in range(40):
        for y in range(20):
            img.setPixelColor(x, y, QColor(250, 250, 250))
    img.save(str(src))
    cache = tmp_path / "c"
    cache.mkdir()

    out = theme_mod.prepare_background(str(src), 60, str(cache))
    assert out and os.path.exists(out)
    proc = QImage(out)
    assert not proc.isNull()
    sample = proc.pixelColor(20, 10)
    assert sample.red() < 120, "60% dim must visibly darken a white photo"
    # deterministic cache: same request returns the same file
    assert theme_mod.prepare_background(str(src), 60, str(cache)) == out
    # different dim -> different artifact
    out2 = theme_mod.prepare_background(str(src), 0, str(cache))
    assert os.path.exists(out2) and out2 != out


def test_prepare_background_bad_input(qapp, tmp_path):
    cache = tmp_path / "c2"
    cache.mkdir()
    assert theme_mod.prepare_background(str(tmp_path / "nope.png"), 50,
                                        str(cache)) is None
    text_file = tmp_path / "t.png"
    text_file.write_text("this is not an image")
    assert theme_mod.prepare_background(str(text_file), 50, str(cache)) is None


def test_apply_theme_threads_bg_from_settings(qtbot, tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMainWindow

    # bright source image
    src = tmp_path / "b.png"
    img = QImage(30, 30, QImage.Format.Format_ARGB32)
    img.fill(0)
    for x in range(30):
        for y in range(30):
            img.setPixelColor(x, y, QColor(240, 240, 240))
    img.save(str(src))

    setattr(QSettings, "_hi_bg_test_ec7a", None)  # marker to avoid sharing
    q = QSettings("HiCloudMP", "HiCloudMP-bgtest")
    q.clear()
    q.setValue("ui/bg_image", str(src))
    q.setValue("ui/bg_dim", 40)
    w = QMainWindow()
    theme_mod.apply_theme(w, settings=q, theme="Dark", accent="#10b981",
                          density="comfortable")
    styled = w.styleSheet()
    assert "QWidget#central" in styled and "url('" in styled

    # bg cleared -> no overlay section
    q.setValue("ui/bg_image", "")
    w2 = QMainWindow()
    theme_mod.apply_theme(w2, settings=q, theme="Dark", accent="#10b981",
                          density="comfortable")
    assert "QWidget#central" not in w2.styleSheet()
