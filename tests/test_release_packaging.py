"""Release packaging: GitHub Actions (Nuitka + Inno Setup) and the
installer script. These files are the contract for end-user builds."""
from pathlib import Path

from sourcepaths import read

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


def test_workflow_name_is_platform_neutral():
    """The workflow builds Windows, Linux and two macOS arches; a name
    that still says 'windows-build' misleads every Actions run list."""
    import re
    wf = _wf()
    name = re.search(r"^name:\s*(.+)$", wf, re.MULTILINE).group(1).strip()
    assert name != "windows-build"
    assert name == "CI", f"expected 'name: CI', got {name!r}"


def test_pull_request_builds_are_scoped():
    """A bare `pull_request:` runs a full three-platform Nuitka build on
    every PR. Scope it to main and skip doc-only PRs (no code to compile)."""
    wf = _wf()
    block = wf.split("pull_request:", 1)[1].split("workflow_dispatch:", 1)[0]
    assert "branches: [main]" in block, "PR trigger must be scoped to main"
    assert "paths-ignore:" in block
    assert "'**.md'" in block and "'docs/**'" in block


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
    # Runtime assets live inside the package now: one package-data rule
    # replaces per-file --include-data-file lines, and the icon paths
    # point at hicloudmp/assets.
    assert "--include-package-data=hicloudmp" in wf
    assert "--include-data-file" not in wf, \
        "package data is covered by --include-package-data=hicloudmp"
    for data_needle in ("hicloudmp/assets/icon.ico",
                        "hicloudmp/assets/icon.png"):
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
    from hicloudmp.core import cover_extractor
    fake = tmp_path / ("ffmpeg.exe" if __import__("os").name == "nt" else "ffmpeg")
    fake.write_bytes(b"\x00")
    out = cover_extractor.find_ffmpeg(str(tmp_path))
    assert out and Path(out).is_file()


def test_find_ffmpeg_falls_back_to_path(monkeypatch, tmp_path):
    import shutil
    from hicloudmp.core import cover_extractor
    monkeypatch.setattr(shutil, "which", lambda *_: None)
    out = cover_extractor.find_ffmpeg(str(tmp_path))  # empty dir
    assert out in ("ffmpeg", "ffmpeg.exe", None)


def test_extract_uses_find_ffmpeg():
    src = read("core/cover_extractor.py")
    assert "find_ffmpeg()" in src, "_extract_with_ffmpeg must resolve via helper"


def test_subprocesses_never_flash_console():
    """v1.0.0 regression: packaged GUI app flashed a console window on
    every play (ffmpeg cover extraction). All spawns must pass
    CREATE_NO_WINDOW on Windows."""
    src = read("core/cover_extractor.py")
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
    assert "requirements-dev.txt" in wf, "pre-build test suite needs dev deps"
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
# ------------------------------------------------------------ workflow: macos job

def test_workflow_has_macos_job():
    wf = _wf()
    assert "build-macos:" in wf
    # Both Mac arches, built natively: Nuitka has no universal2 output, so
    # a real Intel DMG needs the x64 runner (PySide6 itself is universal2).
    assert "runner: macos-15" in wf, "Apple Silicon leg missing"
    assert "runner: macos-15-intel" in wf, "Intel leg missing"
    assert "runs-on: ${{ matrix.runner }}" in wf
    assert "--macos-create-app-bundle" in wf
    assert '--macos-app-name="HiCloudMP"' in wf
    assert "make-icns.sh" in wf


def test_workflow_adhoc_signs_app_bundle():
    wf = _wf()
    assert "codesign --force --deep --sign -" in wf


def test_workflow_bundles_macos_qt_multimedia():
    wf = _wf()
    assert "*.dylib" in wf
    assert "Contents/MacOS" in wf


def test_macos_dmg_and_stable_alias():
    wf = _wf()
    assert "hdiutil create" in wf and "UDZO" in wf
    # One versioned DMG per arch plus one stable alias each.
    assert "macos-${ARCH}.dmg" in wf
    assert "HiCloudMP-macOS.dmg" in wf
    assert "HiCloudMP-macOS-intel.dmg" in wf
def test_macos_bundle_executable_avoids_case_insensitive_collision():
    """macOS APFS is case-insensitive: Contents/MacOS/HiCloudMP and the
    hicloudmp package data directory are the same path, so Nuitka fails with
    NotADirectoryError while copying package data. The executable must have a
    different name, and the bundle users see must stay HiCloudMP.app."""
    wf = _wf()
    macos = wf.split("build-macos:", 1)[1].split("release:", 1)[0]
    assert "--output-filename=HiCloudMPApp" in macos
    assert "--output-filename=HiCloudMP " not in macos, \
        "HiCloudMP collides with hicloudmp/ on a case-insensitive filesystem"
    assert "--output-folder-name=HiCloudMP" in macos
    assert 'test "$(basename "$appdir")" = "HiCloudMP.app"' in macos
# ------------------------------------------------------------ workflow: release

def test_release_publishes_all_platform_assets():
    wf = _wf()
    # all-or-nothing: every platform must pass before anything publishes
    assert "release:" in wf
    for need in ("build-windows", "build-linux", "build-macos"):
        assert need in wf
    assert "download-artifact" in wf
    assert "softprops/action-gh-release" in wf
    for asset in ("HiCloudMP-portable.zip", "HiCloudMP-Setup", "HiCloudMP-Setup.exe",
                  "HiCloudMP-linux-x86_64.AppImage", "linux-x86_64.tar.gz",
                  "HiCloudMP-macOS.dmg", "macos-arm64.dmg",
                  "HiCloudMP-macOS-intel.dmg", "macos-x86_64.dmg"):
        assert asset in wf, asset
    assert "prerelease: ${{ contains(github.ref_name, 'rc') }}" in wf
# ------------------------------------------------------------ README

def test_readme_documents_all_platform_downloads():
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "releases/latest/download/HiCloudMP-macOS.dmg" in src
    assert "releases/latest/download/HiCloudMP-linux-x86_64.AppImage" in src


def test_readme_documents_linux_platform_notes():
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "libfuse2" in src.lower()


def test_readme_documents_macos_platform_notes():
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Apple Silicon" in src
    assert "xattr -dr com.apple.quarantine" in src
    assert ("Right-click" in src or "right-click" in src)


def test_readme_documents_both_macos_arches():
    """Nuitka cannot emit a universal2 binary, so Intel Macs get a native
    x86_64 DMG instead of being told they are unsupported."""
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "releases/latest/download/HiCloudMP-macOS-intel.dmg" in src
    assert "Intel" in src
    assert "runners for Intel macOS have\nbeen retired" not in src


def test_readme_no_longer_claims_packaged_builds_are_windows_only():
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "packaged\nbuilds are Windows-only" not in src
    assert "packaged builds are Windows-only" not in src
    # the docs must name every shipped platform somewhere
    for platform in ("Windows", "macOS", "Linux"):
        assert platform in src, platform
