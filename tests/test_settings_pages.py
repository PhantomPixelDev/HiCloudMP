"""Settings dialog rework: sidebar navigation, custom accent, bg image,
and a plain-language Web Remote page."""
import pytest

from hicloudmp.ui import player as player_mod


@pytest.fixture
def dlg(music_player):
    d = player_mod.SettingsDialog(music_player)
    yield d
    d.close()
    d.deleteLater()


def test_navigation_containers(dlg):
    assert dlg.nav_list is not None and dlg.pages is not None
    # one page per nav entry, navigation switches pages
    assert dlg.pages.count() == dlg.nav_list.count()
    assert dlg.pages.count() >= 4
    dlg.nav_list.setCurrentRow(1 if dlg.nav_list.currentRow() != 1 else 0)
    assert dlg.pages.currentIndex() == dlg.nav_list.currentRow()


def test_pinned_controls_survive_redesign(dlg):
    for attr in ("theme_combo", "accent_combo", "density_combo",
                 "volume_slider", "download_folder_edit",
                 "web_checkbox", "lan_checkbox", "cloud_btn"):
        assert getattr(dlg, attr, None) is not None, attr


def test_custom_accent_flow(dlg, qtbot, monkeypatch):
    from PySide6.QtGui import QColor
    monkeypatch.setattr(
        "PySide6.QtWidgets.QColorDialog.getColor",
        lambda *a, **k: QColor("#ff0055"))
    dlg.pick_custom_accent()
    assert dlg.custom_accent_hex == "#ff0055"
    assert "Custom" in [dlg.accent_combo.itemText(i)
                        for i in range(dlg.accent_combo.count())]
    assert dlg.accent_combo.currentText() == "Custom"
    dlg.save_settings()
    assert dlg.settings.value("ui/accent", "") == "#ff0055"

    # cancel keeps previous state
    before = dlg.accent_combo.currentText()
    monkeypatch.setattr(
        "PySide6.QtWidgets.QColorDialog.getColor",
        lambda *a, **k: None)
    dlg.pick_custom_accent()
    assert dlg.accent_combo.currentText() == before


def test_stored_custom_accent_roundtrip(music_player):
    music_player.settings.setValue("ui/accent", "#0f766e")
    music_player.settings.sync()
    d2 = player_mod.SettingsDialog(music_player)
    try:
        assert d2.accent_combo.currentText() == "Custom"
        assert d2.custom_accent_hex == "#0f766e"
        d2.save_settings()
        assert d2.settings.value("ui/accent", "") == "#0f766e"
    finally:
        d2.close()
        d2.deleteLater()


def test_background_image_controls(dlg, qtbot, monkeypatch, tmp_path):
    fake = str(tmp_path / "wall.jpg")
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getOpenFileName",
        lambda *a, **k: (fake, ""))
    dlg.browse_bg_image()
    assert dlg.bg_image_edit.text() == fake
    dlg.bg_dim_slider.setValue(55)
    assert "55%" in dlg.bg_dim_label.text()
    dlg.save_settings()
    assert dlg.settings.value("ui/bg_image", "") == fake
    assert dlg.settings.value("ui/bg_dim", 0, int) == 55

    dlg.bg_clear_btn.click()
    assert dlg.bg_image_edit.text() == ""
    dlg.save_settings()
    assert dlg.settings.value("ui/bg_image", "") == ""


def test_web_remote_plain_language(dlg, music_player):
    """The Web Remote page speaks user, not tokens."""
    link = dlg.web_link_edit.text()
    assert link.startswith("http://")
    assert "token" in link
    assert dlg.web_token_edit is not None
    assert not dlg.web_link_edit.text().startswith("Bearer")
    hint = dlg.web_hint_label.text().lower()
    assert "phone" in hint or "wi-fi" in hint or "wifi" in hint
    # hero actions exist
    assert dlg.web_copy_btn is not None and dlg.web_open_btn is not None


def test_copy_web_link(dlg, qtbot):
    from PySide6.QtWidgets import QApplication
    dlg.web_copy_btn.click()
    clip = QApplication.clipboard().text()
    assert clip == dlg.web_link_edit.text() and clip
