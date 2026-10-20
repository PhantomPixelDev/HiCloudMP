"""Release packaging: GitHub Actions (Nuitka + Inno Setup) and the
installer script. These files are the contract for end-user builds."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _wf():
    wf = ROOT / ".github" / "workflows" / "windows-build.yml"
    assert wf.exists(), ".github/workflows/windows-build.yml missing"
    return wf.read_text(encoding="utf-8")


def _iss():
    iss = ROOT / "packaging" / "HiCloudMP.iss"
    assert iss.exists(), "packaging/HiCloudMP.iss missing"
    return iss.read_text(encoding="utf-8")


# ------------------------------------------------------------ workflow
def test_workflow_builds_with_nuitka_pyside6():
    wf = _wf()
    assert "nuitka" in wf.lower()
    assert "--enable-plugin=pyside6" in wf
    assert "main.py" in wf
    # real data files only: the panel html + app icon; no phantom dirs
    for data_needle in ("web_panel.html", "icon.ico"):
        assert data_needle in wf, data_needle
    assert "--include-data-dir" not in wf, \
        "include-data-dir must reference a directory that exists in-repo"


def test_workflow_bundles_ffmpeg():
    wf = _wf()
    # The binary must come from a permanent versioned release, never from
    # the floating "release-essentials" alias (its behavior changes
    # whenever Gyan publishes a new build).
    assert "ffmpeg-release-essentials.zip" not in wf
    assert "releases/download/" in wf
    assert "essentials_build.zip" in wf
    assert "main.dist\\ffmpeg.exe" in wf
    # Reproducible toolchain: multimedia stack + compiler pinned.
    assert "PySide6==" in wf
    assert "nuitka==" in wf


def test_workflow_bundles_qt_multimedia_backend():
    """v1.0.0 regression: Nuitka ships qt6multimedia.dll but NOT the
    qt-plugins\\multimedia ffmpeg backend (the only audio decoder since
    Qt 6.8) - the packaged app played nothing."""
    wf = _wf()
    assert "qt-plugins\\multimedia" in wf
    assert "ffmpegmediaplugin" in wf
    # the backend's ffmpeg libs must ride along
    for lib in ("avcodec-*.dll", "avformat-*.dll", "avutil-*.dll",
                "swresample-*.dll", "swscale-*.dll"):
        assert lib in wf, lib
    # both artifacts derive from main.dist; keep that contract explicit
    assert "plugins\\multimedia\\*.dll" in wf


def test_workflow_uploads_artifact_and_releases_on_tags():
    wf = _wf()
    assert "upload-artifact" in wf
    assert "startsWith(github.ref, 'refs/tags/v')" in wf
    assert "softprops/action-gh-release" in wf
    assert "contents: write" in wf  # release needs to push files
    assert "innosetup" in wf.lower()
    assert "ISCC" in wf


# ------------------------------------------------------------ installer
def test_iss_installer_basics():
    iss = _iss()
    assert "#ifndef AppVersion" in iss and '#define AppVersion "0.0.0"' in iss
    assert "DefaultDirName={autopf}" in iss
    assert "HiCloudMP.exe" in iss
    assert "recursesubdirs" in iss and "ignoreversion" in iss
    assert "..\\build\\main.dist\\*" in iss


def test_iss_never_deletes_user_data():
    iss = _iss()
    assert "[InstallDelete]" not in iss, "install must not wipe anything"
    assert "[UninstallDelete]" not in iss, "uninstall keeps user data"


def test_iss_optional_desktop_shortcut():
    iss = _iss()
    assert 'Flags: unchecked' in iss  # opt-in, not opt-out


# ---------------------------------------------- runtime: ffmpeg lookup
def test_find_ffmpeg_prefers_bundled_binary(tmp_path):
    import cover_extractor
    fake = tmp_path / ("ffmpeg.exe" if __import__("os").name == "nt" else "ffmpeg")
    fake.write_bytes(b"\x00")
    out = cover_extractor.find_ffmpeg(str(tmp_path))
    assert out and Path(out).is_file()


def test_find_ffmpeg_falls_back_to_path(monkeypatch, tmp_path):
    import shutil
    import cover_extractor
    monkeypatch.setattr(shutil, "which", lambda *_: None)
    out = cover_extractor.find_ffmpeg(str(tmp_path))  # empty dir
    assert out in ("ffmpeg", "ffmpeg.exe", None)


def test_extract_uses_find_ffmpeg():
    src = (ROOT / "cover_extractor.py").read_text(encoding="utf-8")
    assert "find_ffmpeg()" in src, "_extract_with_ffmpeg must resolve via helper"


def test_subprocesses_never_flash_console():
    """v1.0.0 regression: packaged GUI app flashed a console window on
    every play (ffmpeg cover extraction). All spawns must pass
    CREATE_NO_WINDOW on Windows."""
    src = (ROOT / "cover_extractor.py").read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in src
    runs = src.count("creationflags=_NO_WINDOW")
    assert runs >= 2, f"expected every ffmpeg/ffprobe spawn flagged, got {runs}"
    # the helper must be a no-op off Windows
    assert 'os.name == "nt"' in src
