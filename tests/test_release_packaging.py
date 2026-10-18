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
    for data_needle in ("web_panel.html", "icon.ico", "--include-data-dir"):
        assert data_needle in wf, data_needle


def test_workflow_bundles_ffmpeg():
    wf = _wf()
    assert "ffmpeg-release-essentials.zip" in wf
    assert "main.dist\\ffmpeg.exe" in wf


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
