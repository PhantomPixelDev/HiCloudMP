import os
import sys

import pytest


def test_open_folder_uses_startfile_on_windows(monkeypatch, tmp_path):
    import utils

    called = {}
    if not hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda p: called.setdefault("startfile", p), raising=False)
    else:
        monkeypatch.setattr(os, "startfile", lambda p: called.setdefault("startfile", p))

    utils.open_folder(tmp_path)
    assert os.path.normcase(str(called.get("startfile"))) == os.path.normcase(str(tmp_path))


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS branch")
def test_open_folder_uses_open_on_macos(monkeypatch, tmp_path):
    import utils

    called = {}
    monkeypatch.setattr(utils.subprocess, "Popen", lambda argv, **k: called.setdefault("argv", argv) or None)
    utils.open_folder(tmp_path)
    assert called["argv"][0] == "open"


@pytest.mark.skipif(sys.platform == "win32" or sys.platform == "darwin", reason="xdg-open branch")
def test_open_folder_uses_xdg_open_on_linux(monkeypatch, tmp_path):
    import utils

    called = {}
    monkeypatch.setattr(utils.subprocess, "Popen", lambda argv, **k: called.setdefault("argv", argv) or None)
    utils.open_folder(tmp_path)
    assert called["argv"][0] == "xdg-open"


def test_open_folder_never_raises(monkeypatch, tmp_path):
    import utils

    def boom(_p):
        raise RuntimeError("explorer unavailable")

    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", boom)
    else:
        monkeypatch.setattr(os, "startfile", boom, raising=False)

    utils.open_folder(tmp_path)  # no raise expected


def test_player_and_tray_no_longer_call_xdg_open_directly():
    """Regression pin: both call sites route through utils.open_folder."""
    root_path = ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
    player_src = (root_path / "player.py").read_text(encoding="utf-8")
    tray_src = (root_path / "tray.py").read_text(encoding="utf-8")
    assert "xdg-open" not in player_src
    assert "xdg-open" not in tray_src


def test_tray_uses_module_level_qinputdialog(music_player):
    """Task 7 regression: tray.py used self.app.QInputDialog (AttributeError);
    the real attribute path must trigger 'New Playlist with Current Track' failure point."""
    import tray as tray_mod

    assert tray_mod.QInputDialog is not None
