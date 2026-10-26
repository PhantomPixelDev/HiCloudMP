"""Website copy contract (docs/index.html, GitHub Pages).

The landing page is the first thing a downloader reads, so it must match
what the app actually does and where it actually runs. These tests keep
stale claims ("Windows-only") and feature inflation (a dedicated equalizer
section) from creeping back.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _site():
    path = ROOT / "docs" / "index.html"
    assert path.exists(), "docs/index.html missing"
    return path.read_text(encoding="utf-8")


def test_site_is_not_windows_only():
    site = _site()
    assert "Windows-only" not in site
    assert "Windows music player" not in site
    for platform in ("Windows", "macOS", "Linux"):
        assert platform in site, platform


def test_site_downloads_cover_every_shipped_artifact():
    site = _site()
    for asset in ("HiCloudMP-Setup.exe", "HiCloudMP-portable.zip",
                  "HiCloudMP-macOS.dmg", "HiCloudMP-macOS-intel.dmg",
                  "HiCloudMP-linux-x86_64.AppImage"):
        assert asset in site, asset


def test_site_does_not_lead_with_the_equalizer():
    """A 10-band EQ is table stakes in 2026, not a headline feature."""
    site = _site()
    head = site.split("</head>", 1)[0]
    assert "equalizer" not in head.lower(), \
        "title/meta description must not sell the equalizer"
    assert 'id="screens-title">Equalizer' not in site, \
        "no dedicated equalizer section"
    assert 'href="#screens">Equalizer' not in site, \
        "no equalizer item in the nav"


def test_site_sells_cloud_and_lightweight_runtime():
    site = _site()
    # the cloud story names the real protocols/servers the app speaks
    for needle in ("Nextcloud", "WebDAV", "Subsonic", "Navidrome", "Ampache"):
        assert needle in site, needle
    # and the resource story is explicit about what it is not
    assert "Electron" in site
    assert "no account" in site.lower()
