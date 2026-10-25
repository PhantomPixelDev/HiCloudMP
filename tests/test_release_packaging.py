"""Release packaging: GitHub Actions (Nuitka + Inno Setup) and the
installer script. These files are the contract for end-user builds."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _wf():
    wf = ROOT / ".github" / "workflows" / "build.yml"
    assert wf.exists(), ".github/workflows/build.yml missing"
    return wf.read_text(encoding="utf-8")


def test_build_workflow_replaces_windows_only_workflow():
    wf_path = ROOT / ".github" / "workflows" / "build.yml"
    assert wf_path.exists(), ".github/workflows/build.yml missing"
    assert not (ROOT / ".github" / "workflows" / "windows-build.yml").exists(), \
        "windows-build.yml must be renamed, not duplicated"


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


def test_workflow_publishes_stable_named_installer_alias():
    """The README/site link a permanent direct download:
    releases/latest/download/HiCloudMP-Setup.exe. The build must publish
    that unversioned copy next to the versioned installer every tag."""
    wf = _wf()
    assert "HiCloudMP-Setup-$ver.exe" in wf, \
        "installer copy step must derive the alias from the tag version"
    assert "packaging/Output/HiCloudMP-Setup.exe" in wf, \
        "release files must include the stable-named installer"


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
    # Exactly one spawn remains: the ffmpeg cover extraction (the ffprobe
    # metadata spawn was deleted — dead code, and ffprobe.exe never shipped).
    assert runs >= 1, f"expected the ffmpeg spawn flagged, got {runs}"
    # the helper must be a no-op off Windows
    assert 'os.name == "nt"' in src
# ------------------------------------------------------------ workflow: linux job

def test_workflow_has_linux_job():
    wf = _wf()
    assert "build-linux:" in wf
    assert "runs-on: ubuntu-latest" in wf
    assert "--enable-plugin=pyside6" in wf
    assert "requirements-linux.txt" in wf, "MPRIS deps must ride along"
    assert "imageio-ffmpeg==" in wf, "linux ffmpeg must come from a pinned PyPI build"
    assert "get_ffmpeg_exe" in wf
    assert "chmod +x" in wf


def test_workflow_bundles_linux_qt_multimedia():
    wf = _wf()
    assert "plugins/multimedia" in wf
    assert "libavcodec" in wf and "libswresample" in wf


def test_workflow_builds_appimage():
    wf = _wf()
    assert "appimagetool" in wf
    assert "--appimage-extract-and-run" in wf
    assert "appimagetool/releases/download/" in wf  # versioned release, not continuous
    assert "HiCloudMP.desktop" in wf


def test_linux_artifacts_and_stable_alias():
    wf = _wf()
    assert "HiCloudMP-linux-x86_64.AppImage" in wf  # stable alias name
    assert "linux-x86_64.tar.gz" in wf
