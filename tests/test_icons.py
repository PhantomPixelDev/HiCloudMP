"""Accent-colored Feather icon set (QtSvg-rendered) replacing stock QStyle icons."""
import pytest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import player as player_mod

REQUIRED_GLYPHS = (
    "play", "pause", "stop", "skip-back", "skip-forward", "shuffle",
    "repeat", "volume", "folder", "music", "plus", "save", "trash",
    "refresh", "globe", "sliders", "info", "cloud",
)


def test_all_required_glyphs_render_with_ink(qapp):
    import icons
    for name in REQUIRED_GLYPHS:
        img = icons.pixmap(name, size=32, color="#e6e9ef").toImage()
        assert not img.isNull(), f"{name}: null image"
        ink = 0
        for x in range(0, img.width(), 2):
            for y in range(0, img.height(), 2):
                if img.pixelColor(x, y).alpha() > 40:
                    ink += 1
        assert ink > 15, f"{name}: glyph renders empty (bad path data?) — ink={ink}"


def test_unknown_glyph_is_honest_null(qapp):
    import icons
    assert icons.icon("does-not-exist").isNull()
    img = icons.pixmap("does-not-exist", size=24).toImage()
    assert img.isNull()


def test_play_glyph_is_solid_and_tinted(qapp):
    import icons
    img = icons.pixmap("play", size=32, color="#ff0000").toImage()
    reds = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = img.pixelColor(x, y)
            if c.alpha() > 200 and c.red() > 200 and c.green() < 90 \
                    and c.blue() < 90:
                reds += 1
    assert reds > 20, "filled play triangle must carry the tint color"
    # filled shape at viewBox coords: body exists at x=6,y=16 (of 24), and the
    # triangle stops before the right edge; QImage is in device pixels (DPR 2).
    body_x, body_y = img.width() * 6 // 24, img.height() * 16 // 24
    assert img.pixelColor(body_x, body_y).alpha() > 200, "left body of triangle"
    band = sum(
        1 for y in range(0, img.height(), 2)
        if img.pixelColor(img.width() - 3, y).alpha() > 40
    )
    assert band == 0, "play triangle must not extend to the right edge"


def test_cache_reuse_and_invalidation(qapp):
    import icons
    icons.invalidate()
    p1 = icons.pixmap("shuffle", size=24, color="#123456")
    p2 = icons.pixmap("shuffle", size=24, color="#123456")
    assert p1.toImage() == p2.toImage()

    icons.invalidate()
    # any color switch re-renders without crashing and differs
    p3 = icons.pixmap("shuffle", size=24, color="#654321")
    assert p3.toImage() != p1.toImage()


def test_player_has_no_stock_qstyle_icons_left():
    src = open(player_mod.__file__, encoding="utf-8").read()
    assert "standardIcon(" not in src, "player must use icons.py only"
    assert "SP_Media" not in src, "stock media icons must be gone"
    assert "SP_DirIcon" not in src and "SP_FileIcon" not in src
    assert "SP_TrashIcon" not in src and "SP_DialogSaveButton" not in src


def test_player_buttons_carry_factory_icons(music_player):
    mp = music_player
    assert mp.icon_factory is not None
    for btn, glyph in ((mp.play_btn, "play"), (mp.stop_btn, "stop"),
                       (mp.next_btn, "skip-forward"),
                       (mp.prev_btn, "skip-back"),
                       (mp.shuffle_btn, "shuffle"),
                       (mp.repeat_btn, "repeat")):
        assert not btn.icon().isNull(), f"{glyph}: transport button empty"

    # toggle glyph tint tracks its state: accent when checked, dim when not
    import icons as _icons
    role = "accent" if mp.shuffle_btn.isChecked() else "dim"
    acc = getattr(mp.icon_factory, f"{role}_color")
    got = mp.shuffle_btn.icon().pixmap(20, 20).toImage()
    assert not got.isNull()
    r = g = b = n = 0
    for x in range(got.width()):
        for y in range(got.height()):
            c = got.pixelColor(x, y)
            if c.alpha() > 100:
                r += c.red(); g += c.green(); b += c.blue(); n += 1
    assert n > 3, "shuffle glyph has ink"
    avg = (r / n, g / n, b / n)
    want = QColor(acc)
    dist = abs(avg[0] - want.red()) + abs(avg[1] - want.green()) \
        + abs(avg[2] - want.blue())
    assert dist < 140, f"shuffle glyph average {avg} must be accent-tinted"


def test_theme_change_retints_icons(music_player, qapp):
    import icons
    mp = music_player
    mp.icon_factory.set_colors("#8b5cf6", "#1a2233", None)
    assert mp.icon_factory.accent_color == "#8b5cf6"
    img = icons.pixmap("play", size=24,
                       color=mp.icon_factory.accent_color).toImage()
    c = img.pixelColor(img.width() * 6 // 24, img.height() // 2)
    assert c.alpha() > 150 and (c.red() > 100 or c.green() > 100), \
        "violet tint visible after retint"


def test_tray_badge_is_accent_filled_with_contrast_glyph(qapp):
    """Tray icon = accent-filled round badge (not a stock QStyle glyph) whose
    glyph is white when the fill is dark enough."""
    import icons

    ico = icons.tray_icon("pause", "#10b981")
    assert not ico.isNull()
    img = ico.pixmap(48, 48).toImage()
    assert not img.isNull()

    fill = light = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = img.pixelColor(x, y)
            if c.alpha() <= 150:
                continue
            if c.green() > 110 and c.green() > c.red() + 50 \
                    and c.green() > c.blue() + 20:
                fill += 1  # emerald accent fill
            elif c.red() > 200 and c.green() > 200 and c.blue() > 200:
                light += 1  # white glyph ink
    assert fill > 60, f"badge must be accent-filled (fill={fill})"
    assert light > 12, f"white glyph ink on the dark accent fill (light={light})"
    # round badge: corners stay transparent
    assert img.pixelColor(0, 0).alpha() < 20
    assert img.pixelColor(img.width() - 1, img.height() - 1).alpha() < 20


def test_tray_badge_glyph_darkens_on_light_accents(qapp):
    import icons

    img = icons.tray_icon("play", "#fde047").pixmap(48, 48).toImage()
    assert not img.isNull()
    dark = light = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = img.pixelColor(x, y)
            if c.alpha() <= 150:
                continue
            if c.red() < 80 and c.green() < 80 and c.blue() < 80:
                dark += 1
            if c.red() > 230 and c.green() > 230 and c.blue() > 230:
                light += 1
    assert dark > 12, "glyph must go near-black on a light accent fill"
    assert light < 5, "no white glyph ink on a light accent fill"


def test_tray_badge_cache_and_invalidate(qapp):
    import icons
    assert icons.tray_icon("no-such-glyph", "#10b981").isNull()  # honest null
    icons.invalidate()
    first = icons.tray_icon("stop", "#10b981")
    assert first is icons.tray_icon("stop", "#10b981")  # cached identity
    icons.invalidate()
    assert icons.tray_icon("stop", "#10b981") is not first


def test_tray_controller_uses_accent_badges(qapp):
    """TrayController swaps in accent badges for play/pause/stop states
    instead of stock QStyle icons, tinted from the live factory accent."""
    import icons
    from PySide6.QtWidgets import QSystemTrayIcon
    from tray import TrayController

    class _Player:
        class PlaybackState:
            PlayingState = 1
            PausedState = 2
            StoppedState = 0

    class _App:
        def __init__(self):
            self.player = _Player()
            self.icon_factory = icons.IconFactory()
            self.icon_factory.set_colors("#7c3aed", "#e6e9ef", "#9aa3b2")
            self._state = _Player.PlaybackState.PlayingState

        def effective_playback_state(self):
            return self._state

    app = _App()
    tc = TrayController(app)
    tc.tray_icon = QSystemTrayIcon()
    tc.update_tray_ui()

    img = tc.tray_icon.icon().pixmap(48, 48).toImage()
    assert not img.isNull()
    violet = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = img.pixelColor(x, y)
            if c.alpha() > 150 and c.blue() > 140 and 80 < c.red() < 180 \
                    and c.green() < 110:
                violet += 1
    assert violet > 60, "tray badge must carry the factory accent (violet)"

    app._state = _Player.PlaybackState.PausedState
    tc.update_tray_ui()
    paused_img = tc.tray_icon.icon().pixmap(48, 48).toImage()
    assert not paused_img.isNull()
    assert paused_img != img, "pause and play badges must differ"
