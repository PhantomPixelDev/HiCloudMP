"""Canonical source locations for tests that assert on implementation text.

The application modules live inside ``hicloudmp/``; only ``main.py`` (the
launcher) stays at the repo root. Reading through these helpers means the
next layout change is a one-file edit instead of a scavenger hunt through
every test that greps source.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "hicloudmp"


def source(relative: str) -> Path:
    """Path of a file inside the ``hicloudmp`` package (``"ui/player.py"``)."""
    return PKG / relative


def read(relative: str) -> str:
    """Read a package source file as UTF-8 text."""
    return source(relative).read_text(encoding="utf-8")


def root_file(name: str) -> str:
    """Read a file that legitimately stays at the repo root (``"main.py"``)."""
    return (ROOT / name).read_text(encoding="utf-8")


def resource(name: str) -> Path:
    """Path of a bundled runtime asset (``"web_panel.html"``)."""
    return PKG / "assets" / name
