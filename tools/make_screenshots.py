"""Regenerate the README / website screenshots from the real UI.

Runs the actual Qt app headlessly (offscreen platform) against a throwaway
demo library: fake user-data dirs, an ini-file QSettings, no audio device,
no registry writes. Nothing in this script touches the user's real
HiCloudMP data.

Usage (from the repo root):

    .venv\\Scripts\\python tools\\make_screenshots.py

Outputs:
    screen.png                  main window (README hero)
    docs/assets/main.png        same, for the GitHub Pages site
    docs/assets/equalizer.png   equalizer dialog

Requires ffmpeg on PATH (used only to synthesize short demo tracks).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES = os.path.join(ROOT, "docs", "assets")
SANDBOX = tempfile.mkdtemp(prefix="hicloudmp-shots-")

# --- Isolate the app BEFORE anything imports utils/player -----------------
# tests/conftest.py does the same: platformdirs is stubbed in sys.modules so
# utils.data_dir resolves inside the sandbox, and QSettings is redirected to
# an ini file below (Windows would otherwise use HKCU).
_stub = types.ModuleType("platformdirs")


def _user_data_dir(app_name=None, app_author=None, ensure_exists=True,
                   **_ignored):
    target = os.path.join(SANDBOX, "data", app_author or app_name or "app",
                          app_name or "app")
    if ensure_exists:
        os.makedirs(target, exist_ok=True)
    return target


def _user_cache_dir(*_args, **_kwargs):
    target = os.path.join(SANDBOX, "cache")
    os.makedirs(target, exist_ok=True)
    return target


_stub.user_data_dir = _user_data_dir
_stub.user_cache_dir = _user_cache_dir
sys.modules["platformdirs"] = _stub

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_SCALE_FACTOR", "2")
os.environ["QT_LOGGING_RULES"] = "qt.multimedia.*=false"

sys.path.insert(0, ROOT)

from PySide6.QtCore import QSettings as QtQSettings, Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import theme  # noqa: E402
import utils  # noqa: E402

# Fictional demo catalog: title, artist, album, displayed length, tone (Hz)
TRACKS = [
    ("Midnight Drive", "Neon Harbour", "Night Circuit", 214, 196.00),
    ("Rooftop Lights", "Neon Harbour", "Night Circuit", 231, 220.00),
    ("After Hours", "Neon Harbour", "Night Circuit", 198, 246.94),
    ("Paper Planes", "Elara Vane", "Quiet Machinery", 242, 261.63),
    ("Glasshouse", "Elara Vane", "Quiet Machinery", 205, 293.66),
    ("Slow Machines", "Elara Vane", "Quiet Machinery", 227, 329.63),
    ("Golden Hour", "Marlowe & Finch", "Lantern Rooms", 188, 349.23),
    ("Afterglow", "Marlowe & Finch", "Lantern Rooms", 219, 392.00),
    ("Lantern Rooms", "Marlowe & Finch", "Lantern Rooms", 236, 440.00),
    ("Slow Tide", "Juniper Row", "Salt & Static", 203, 493.88),
    ("Static Bloom", "Juniper Row", "Salt & Static", 224, 523.25),
    ("Salt & Static", "Juniper Row", "Salt & Static", 247, 587.33),
]


def _settings_factory(*_args, **_kwargs):
    return QtQSettings(os.path.join(SANDBOX, "settings.ini"),
                       QtQSettings.IniFormat)


def load_ui_fonts(app):
    """The offscreen platform ships an empty font database; register the
    app's theme font (theme.py asks for Segoe UI) so text renders."""
    win_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf",
                 "seguisb.ttf"):
        path = os.path.join(win_fonts, name)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)
    app.setFont(QFont("Segoe UI", 10))


def build_demo_library():
    """Synthesize tagged MP3s with embedded cover art. Returns paths."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required on PATH to synthesize demo tracks")

    media_root = os.path.join(SANDBOX, "media", "Demo Library")
    os.makedirs(media_root, exist_ok=True)
    cover_src = os.path.join(ROOT, "cover.png")

    from mutagen.id3 import (APIC, ID3, TALB, TDRC, TIT2, TPE1)
    from PIL import Image

    cover_png = os.path.join(SANDBOX, "cover-512.png")
    with Image.open(cover_src) as im:
        im = im.convert("RGB").resize((512, 512))
        im.save(cover_png, "PNG")
    with open(cover_png, "rb") as fh:
        cover_bytes = fh.read()

    paths = []
    for idx, (title, artist, album, _secs, freq) in enumerate(TRACKS, 1):
        # Files live directly in the scanned root: the library tree renders
        # root-level tracks (subdirs show as folders only).
        safe = "".join(c if c not in '<>:"/\\|?*' else "-" for c in title)
        path = os.path.join(media_root, f"{idx:02d} {safe}.mp3")
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"sine=frequency={freq}:sample_rate=44100:duration=3",
             "-af", "volume=0.04", "-ac", "2", "-b:a", "128k", path],
            check=True, capture_output=True,
        )
        tags = ID3()
        tags.add(TIT2(encoding=3, text=title))
        tags.add(TPE1(encoding=3, text=artist))
        tags.add(TALB(encoding=3, text=album))
        tags.add(TDRC(encoding=3, text="2026"))
        tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover",
                      data=cover_bytes))
        tags.save(path)
        paths.append(path)

    with open(utils.MEDIA_FOLDERS_FILE, "w", encoding="utf-8") as fh:
        json.dump([media_root], fh)
    return paths


def pump(app, seconds=0.05):
    """Deliver queued scan callbacks (the app's UI-thread bridge)."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def wait_for_scan(app, player, paths, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
        cached = all(player.library_store.tags(p)[0] for p in paths)
        if cached and player.library_store.local_count() >= len(paths):
            # Let the tree repaint queued batches land too.
            pump(app, 0.4)
            return
    raise SystemExit("demo library scan did not finish")


def save(widget, *paths):
    pm = widget.grab()
    for path in paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not pm.save(path, "PNG"):
            raise SystemExit(f"could not write {path}")
    print(f"saved {os.path.relpath(paths[0], ROOT)} "
          f"({pm.width()}x{pm.height()})")


def main():
    os.makedirs(SITES, exist_ok=True)
    paths = build_demo_library()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    load_ui_fonts(app)
    settings = _settings_factory()
    theme.apply_app_theme(app, settings=settings)

    import player as player_mod
    player_mod.QSettings = _settings_factory

    mp = player_mod.MusicPlayer()
    mp.resize(1280, 880)
    mp.sidebar.setFixedWidth(330)   # staging: show name + artist columns
    mp.show()
    pump(app, 0.3)
    wait_for_scan(app, mp, paths)

    # Stage a playing state using the app's own rendering paths.
    from playlist import Playlist
    evening = Playlist("Evening Drive", list(paths))
    focus = Playlist("Focus", list(paths[:4]))
    mp.playlists = [evening, focus]
    mp.active_playlist = evening
    mp.update_playlist_selector()

    mp.playlist = list(paths)
    mp.current_index = 0
    mp.playlist_widget.clear()
    for path in paths:
        mp.playlist_widget.addQueueRow(*mp.meta.queue_cells(path))
    mp.playlist_widget.setCurrentRow(0)
    mp.highlight_current_track()
    mp.update_metadata_display()

    # Cover art extraction runs on a worker: wait for the real pixmap.
    deadline = time.time() + 5
    while time.time() < deadline:
        pump(app, 0.1)
        if not mp.cover_art_label.pixmap().isNull():
            break

    mp.seek_slider.setRange(0, TRACKS[0][3] * 1000)
    mp.seek_slider.setValue(78 * 1000)
    mp.position_label.setText("1:18")
    mp.duration_label.setText(f"{TRACKS[0][3] // 60}:{TRACKS[0][3] % 60:02d}")
    mp.play_btn.setIcon(mp._icon_pause())

    mp.update_library_tree()
    mp.library_tree.expandAll()
    mp.library_tree.setColumnHidden(2, True)   # staging: sidebar is narrow
    mp.library_tree.setIndentation(12)
    mp.library_tree.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    mp.library_tree.header().resizeSection(0, 195)
    mp.library_tree.header().resizeSection(1, 105)
    mp.playlist_widget.header().resizeSection(0, 320)
    mp.playlist_widget.header().setStretchLastSection(True)
    mp.playlist_widget.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    pump(app, 0.3)

    # Static spectrum snapshot (the timer would overwrite it on idle).
    spectrum = [0.12, 0.24, 0.38, 0.61, 0.83, 0.94, 0.72, 0.55,
                0.41, 0.33, 0.29, 0.35, 0.47, 0.63, 0.78, 0.66,
                0.52, 0.44, 0.37, 0.31, 0.26, 0.21, 0.16, 0.11]
    mp._viz_timer.stop()
    mp.visualizer.set_spectrum(spectrum)

    save(mp, os.path.join(ROOT, "screen.png"),
        os.path.join(SITES, "main.png"))

    from dsp import PRESETS
    from dialogs import EqualizerDialog
    dlg = EqualizerDialog(mp, PRESETS["Rock"], True, "Rock",
                          mp.make_eq_apply_cb())
    dlg.show()
    pump(app, 0.2)
    save(dlg, os.path.join(SITES, "equalizer.png"))
    dlg.close()

    mp._viz_timer.stop()
    mp.close()
    pump(app, 0.2)
    print(f"sandbox: {SANDBOX}")


if __name__ == "__main__":
    main()
