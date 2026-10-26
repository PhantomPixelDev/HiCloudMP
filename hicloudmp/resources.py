"""Bundled runtime assets (icons, web panel) for source and Nuitka builds."""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def resources_dir() -> Path:
    """Directory holding the data files shipped with the app.

    In a source checkout this is ``hicloudmp/resources``. Nuitka sets module
    ``__file__`` values inside the standalone dist, so the same relative path
    resolves there too; the executable-directory fallback covers layouts that
    flatten ``__file__``.
    """
    candidate = _HERE / "resources"
    if candidate.is_dir():
        return candidate
    return Path(sys.argv[0]).resolve().parent / "hicloudmp" / "resources"


def resource_path(name: str) -> str:
    """Absolute path of a bundled asset, ready for Qt/Flask."""
    return str(resources_dir() / name)
