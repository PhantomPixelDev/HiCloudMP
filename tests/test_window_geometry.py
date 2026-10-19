"""Window size/position was never remembered (every launch re-opened at
the 1120x720 default). Geometry now round-trips through QSettings; the
first run keeps the default and the save runs inside closeEvent's
guarded save steps.
"""
from PySide6.QtGui import QCloseEvent


def test_first_run_uses_default_size(music_player):
    mp = music_player
    assert (mp.width(), mp.height()) == (1120, 720)


def test_geometry_roundtrip(music_player):
    mp = music_player
    mp.resize(1010, 660)
    blob = mp.saveGeometry()
    mp._save_window_geometry()
    assert mp.settings.value("ui/window_geometry") == blob, \
        "the exact saveGeometry blob must be persisted"

    mp.resize(1000, 645)
    mp._restore_window_geometry()
    # The offscreen screen is 800x800: Qt fits the saved 1010 px width and
    # the 960 px minimum wins there. Height has room and must round-trip.
    assert mp.height() == 660
    assert mp.width() >= mp.minimumWidth()


def test_close_persists_geometry(music_player):
    mp = music_player
    mp.resize(1010, 660)
    mp.closeEvent(QCloseEvent())
    stored = mp.settings.value("ui/window_geometry")
    assert stored is not None, "close must save window geometry"
