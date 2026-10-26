<p align="center">
  <img src="hicloudmp/assets/icon.png" width="104" alt="HiCloud MP app icon - a white music note and play triangle on a purple circle">
</p>

<h1 align="center">HiCloud MP</h1>

<p align="center">
  <strong>Your music, local and cloud, in one quiet player.</strong><br>
  A fast desktop music player for Windows, macOS and Linux. Your own files,
  your own servers, no account — and no browser engine inside.
</p>

<p align="center">
  <a href="https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-Setup.exe"><img src="https://img.shields.io/badge/Download_for_Windows-Installer-ab45ed?style=for-the-badge&logo=windows&logoColor=white" alt="Download the Windows installer"></a>
  <a href="https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-portable.zip"><img src="https://img.shields.io/badge/Portable_version-ZIP-334155?style=for-the-badge&logo=files&logoColor=white" alt="Download the portable ZIP"></a>
  <a href="https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-macOS.dmg"><img src="https://img.shields.io/badge/Download_for_macOS-Apple_Silicon-ab45ed?style=for-the-badge&logo=apple&logoColor=white" alt="Download the macOS build for Apple Silicon"></a>
  <a href="https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-linux-x86_64.AppImage"><img src="https://img.shields.io/badge/Download_for_Linux-AppImage-ab45ed?style=for-the-badge&logo=linux&logoColor=white" alt="Download the Linux AppImage"></a>
</p>

<p align="center">
  <sub>Windows 10 / 11 &nbsp;·&nbsp; macOS 13+ (Apple Silicon &amp; Intel) &nbsp;·&nbsp; Linux x86_64 &nbsp;·&nbsp; free and open source (MIT) &nbsp;·&nbsp; no account, no telemetry</sub>
</p>

![HiCloud MP — library, queue and now-playing card in the dark theme](screen.png)

## Light by design

HiCloud MP is a native Qt application compiled to a standalone binary with
Nuitka. There is no Electron, no bundled Chromium and no second browser engine
pretending to be a music player:

- **One process.** The packaged Linux build idles at about **180 MB resident**
  in our own measurement — the kind of footprint a desktop app should have.
- **A small download.** The Windows installer is about **75 MB** and already
  contains Qt, the FFmpeg multimedia backend and a static FFmpeg for cover art.
- **No background services.** No account, no updater daemon, no telemetry
  agent. It talks to your servers and, when you ask, to GitHub for updates.

## Download

Every button downloads the newest release — no version hunting.

| | |
|---|---|
| **Installer** <br><sub>recommended</sub> | [**HiCloudMP-Setup.exe**](https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-Setup.exe) — about 75 MB. Adds HiCloud MP to the Start menu and installs an uninstaller. No Python or extra codecs needed. |
| **Portable (Windows)** | [**HiCloudMP-portable.zip**](https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-portable.zip) — about 112 MB. Unzip it anywhere, run `HiCloudMP.exe`, and take your player with you. |
| **macOS — Apple Silicon** | [**HiCloudMP-macOS.dmg**](https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-macOS.dmg) — native arm64 build, ad-hoc signed. |
| **macOS — Intel** | [**HiCloudMP-macOS-intel.dmg**](https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-macOS-intel.dmg) — native x86_64 build for Intel Macs, ad-hoc signed. |
| **Linux x86_64** | [**HiCloudMP-linux-x86_64.AppImage**](https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-linux-x86_64.AppImage) — runs on most distributions; libfuse2 needed for direct double-click. |
| **Versioned files** | `HiCloudMP-<version>-macos-arm64.dmg`, `-macos-x86_64.dmg`, `-linux-x86_64.AppImage` and `-linux-x86_64.tar.gz` ship alongside the stable aliases on every release. |

> **First launch and SmartScreen.** The app isn't code-signed yet, so Windows
> may show *"Windows protected your PC"*. Click **More info → Run anyway** —
> the builds come straight from this repository's GitHub Actions.
>
> Want release notes or an older version? See
> [all releases](https://github.com/PhantomPixelDev/HiCloudMP/releases).

## First launch notes by platform

**macOS (Apple Silicon and Intel).** Both DMGs are ad-hoc signed but not
notarized yet (notarization requires a paid Apple Developer account), so macOS
may warn *"HiCloudMP can't be opened"* or *"can't verify the developer"*.
Either:

- **Right-click** `HiCloudMP.app` in the mounted DMG and choose **Open**, then
  confirm **Open** in the warning dialog - the one-time approval persists; or
- clear the quarantine flag entirely: run
  `xattr -dr com.apple.quarantine HiCloudMP.app` in a terminal.

Pick the DMG that matches your Mac: `HiCloudMP-macOS.dmg` for Apple Silicon,
`HiCloudMP-macOS-intel.dmg` for Intel. (There is no universal binary: Nuitka
compiles one architecture per build, so each Mac arch is built natively on its
own runner.)

**Linux (x86_64).** Every release ships an AppImage and a tarball:

- `HiCloudMP-linux-x86_64.AppImage` - make it executable once
  (`chmod +x HiCloudMP-linux-x86_64.AppImage`) and run it. Double-clicking
  directly on desktops additionally needs libfuse2
  (`sudo apt install libfuse2` on Ubuntu/Debian, `fuse2` on Arch).
- `HiCloudMP-<version>-linux-x86_64.tar.gz` - unpack anywhere and run
  `./HiCloudMP` from the folder; no fuse requirement.

## What you can do

- **Stream your own cloud.** Connect Nextcloud or any WebDAV server
  (ownCloud included), a Subsonic-compatible server (Subsonic, Navidrome,
  Airsonic, Nextcloud Music) or Ampache. The library scans in the background
  and tracks play straight from the server — nothing to sync, nothing to
  download twice.
- **Keep a local library that keeps up.** Add your folders once and browse by
  name, artist and album with instant search. The scanner runs off the UI
  thread, and folder watching rescans automatically when files appear.
- **Playlists that travel.** Import and export M3U/M3U8, PLS and XSPF, so
  playlists move between players instead of being trapped in one.
- **A queue that behaves.** Title / artist / album columns, drag to reorder,
  Play Next, shuffle and repeat — with the sort and filter remembered between
  sessions.
- **Pick up where you left off.** Recently Played and Most Played are one
  click away.
- **Use your phone as the remote.** Settings → Web Remote gives you a link
  that works on the same Wi-Fi, with no app to install. It's token protected
  and stays local unless you allow other devices.
- **Real desktop integration.** System tray controls, an audio output picker,
  playback speed, and media keys (MPRIS on Linux).
- **Cover art and tags.** Covers are extracted from the files themselves with
  the bundled FFmpeg — no online metadata service required.
- **Shape the sound when you want to.** A 10-band equalizer with presets and
  custom curves, applied live, with a bit-exact bypass at flat settings.
- **Stay private.** No account, no telemetry. Settings and playlists stay on
  your machine, and saved cloud passwords are encrypted with Windows DPAPI
  (locked to your Windows user) on Windows.
- **Plays your files.** MP3, FLAC, WAV, OGG, Opus, AAC, M4A, WMA and more,
  decoded by the bundled FFmpeg backend. No conversion.

## Get started in three steps

1. **Install** the app — or unzip the portable build.
2. **Add your music** — `Add Folder` for local files, or `Add Cloud` →
   `Scan Cloud` for a server.
3. **Press play.** The queue, the phone remote and the settings you need are
   one click away.

Works with **WebDAV** servers (Nextcloud, ownCloud), **Subsonic-compatible**
servers (Subsonic, Navidrome, Airsonic, Nextcloud Music) and
**Ampache-compatible** servers. You'll need the server address and your login;
an app password is fine.

Your data lives in the platform's standard per-user location:

| Platform | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\HiCloudMP\HiCloudMP` |
| macOS | `~/Library/Application Support/HiCloudMP` |
| Linux | `~/.local/share/HiCloudMP` |

Installing, upgrading or uninstalling never touches your settings, playlists
or music.

## Good to know

- **Requirements:** Windows 10 or 11 (64-bit); macOS 13 or newer (Apple
  Silicon or Intel); Linux x86_64 (built on Ubuntu 24.04).
- **Updates:** *Settings → Check for updates* compares your version with the
  latest GitHub release.
- **Uninstall:** Windows — *Settings → Apps → HiCloud MP*; macOS — drag the app
  to the Trash; Linux — delete the AppImage or the unpacked folder. Your music
  and settings stay untouched.
- **Cloud passwords off Windows:** the DPAPI vault is Windows-only. On macOS
  and Linux the cloud settings file is plain JSON for now — use an app password
  rather than your main account password.
- **Media keys:** MPRIS is available when the app runs from source with
  `requirements-linux.txt`; the packaged Linux build ships without PyGObject.

## For developers

<details>
<summary><strong>Run from source, tests and packaging</strong></summary>

**Run from source** (Python 3.12+):

```bash
git clone https://github.com/PhantomPixelDev/HiCloudMP.git
cd HiCloudMP
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
python main.py
```

On Linux, also install `requirements-linux.txt` (MPRIS/media keys) and the
PyGObject packages your distro needs.

**Repository layout.** `main.py` is a thin launcher (the Nuitka entry point).
The application is the `hicloudmp/` package: `core/` (library, metadata,
playlists, workers), `audio/` (playback, DSP/EQ, MPRIS), `cloud/` (WebDAV,
Subsonic, Ampache handlers), `ui/` (window, dialogs, theme, tray) and `web/`
(the phone remote). Bundled assets live in `hicloudmp/assets/` and are
resolved through `hicloudmp.resources.resource_path()`, so they work from a
checkout and inside a Nuitka build alike. Tests and packaging stay outside the
package.

**Tests** (headless/offscreen, no audio device required):

```bash
pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

**Packaging:** `.github/workflows/build.yml` builds the standalone app with
Nuitka on every platform job — Windows, Linux x86_64, macOS arm64 and macOS
x86_64 — and runs the test suite on Linux and both macOS arches before burning
Nuitka minutes. The macOS job is a two-leg matrix (`macos-15` for Apple
Silicon, `macos-15-intel` for Intel) because Nuitka emits one architecture per
build; there is no universal2 output. Pushing a `v*` tag additionally compiles
the Inno Setup installer, then a single all-or-nothing `release` job publishes
one release with `HiCloudMP-portable.zip`, the versioned installer plus the
stable `HiCloudMP-Setup.exe` alias, the Linux AppImage + tarball, and both
macOS DMGs (stable aliases `HiCloudMP-macOS.dmg` and
`HiCloudMP-macOS-intel.dmg`) - the links used by the download buttons above.
Tags containing `rc` publish as prereleases.

**Screenshots:** `tools/make_screenshots.py` renders the real UI headlessly
against a throwaway demo library, so `screen.png` and the site images can be
regenerated after UI changes.

Contributions are welcome — keep the suite green and open a PR.

[![CI](https://github.com/PhantomPixelDev/HiCloudMP/actions/workflows/build.yml/badge.svg)](https://github.com/PhantomPixelDev/HiCloudMP/actions/workflows/build.yml)

</details>

## Links

[Website](https://PhantomPixelDev.github.io/HiCloudMP/) ·
[Releases](https://github.com/PhantomPixelDev/HiCloudMP/releases) ·
[Issues](https://github.com/PhantomPixelDev/HiCloudMP/issues) ·
[MIT license](LICENSE)
