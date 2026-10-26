"""Project layout contract.

The application is a package (``hicloudmp/``); the repo root keeps only the
launcher, docs, tests and packaging. These tests exist so the root cannot
quietly fill up with modules again.
"""
import ast
from pathlib import Path

from sourcepaths import PKG, ROOT

PACKAGES = ("core", "audio", "cloud", "ui", "web")

# Modules that used to sit in the root; importing any of them by bare name
# means a stale flat import survived the move.
MOVED = {
    "audio_devices", "cloud_handlers", "cover_extractor", "dialogs", "dsp",
    "eq_engine", "folder_watch", "history", "icons", "library_store",
    "library_view", "metadata", "mpris", "mpris_dbus", "playback", "player",
    "playlist", "playlist_io", "playlist_widget", "playlists_manager",
    "secure_store", "single_instance", "slider", "spectrum", "theme",
    "thread_teardown", "tray", "updates_check", "utils", "visualizer",
    "web_control", "workers",
}


def _bare_local_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in MOVED:
                    yield node.lineno, alias.name
        elif (isinstance(node, ast.ImportFrom) and node.level == 0
              and node.module):
            top = node.module.split(".")[0]
            if top in MOVED:
                yield node.lineno, node.module


def test_root_has_no_application_modules():
    stray = sorted(p.name for p in ROOT.glob("*.py") if p.name != "main.py")
    assert stray == [], f"application modules must live in hicloudmp/: {stray}"


def test_launcher_is_thin():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert len(src.splitlines()) < 20, "main.py is a launcher, not the app"
    assert "from hicloudmp.app import main" in src


def test_every_package_has_an_init():
    assert (PKG / "__init__.py").is_file()
    for name in PACKAGES:
        directory = PKG / name
        assert directory.is_dir(), f"missing package hicloudmp/{name}"
        assert (directory / "__init__.py").is_file(), \
            f"hicloudmp/{name}/__init__.py missing"


def test_package_init_has_no_import_side_effects():
    """Importing hicloudmp must stay cheap; the app boots from hicloudmp.app."""
    src = (PKG / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert imports == [], "hicloudmp/__init__.py must not import anything"


def test_no_bare_flat_imports_remain():
    offenders = []
    for path in sorted(PKG.rglob("*.py")):
        for lineno, name in _bare_local_imports(path):
            offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
    assert offenders == [], "flat imports survived the move:\n" + "\n".join(offenders)


def test_resources_live_inside_the_package_and_resolve():
    from hicloudmp.resources import resource_path, resources_dir

    for name in ("icon.ico", "icon.png", "web_panel.html"):
        path = Path(resource_path(name))
        assert path.is_file(), f"bundled asset missing: {path}"
        assert path.parent == resources_dir()
        assert not (ROOT / name).exists(), f"{name} must not live in the root"


def test_web_panel_is_served_from_resources():
    src = (PKG / "web" / "web_control.py").read_text(encoding="utf-8")
    assert "resources_dir()" in src
    assert "os.path.dirname(os.path.abspath(__file__))" not in src
