<p align="center">
  <img src="icon.png" width="104" alt="HiCloud MP app icon — a white music note and play triangle on a purple circle">
</p>

<h1 align="center">HiCloud MP</h1>

<p align="center">
  <strong>Your music, local and cloud, in one quiet player.</strong><br>
  A friendly Windows music player with a real 10-band equalizer,
  playlists, cover art and a remote for your phone.
</p>

<p align="center">
  <a href="https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-Setup.exe"><img src="https://img.shields.io/badge/Download_for_Windows-Installer-ab45ed?style=for-the-badge&logo=windows&logoColor=white" alt="Download the Windows installer"></a>
  <a href="https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-portable.zip"><img src="https://img.shields.io/badge/Portable_version-ZIP-334155?style=for-the-badge&logo=files&logoColor=white" alt="Download the portable ZIP"></a>
</p>

<p align="center">
  <sub>Windows 10 / 11 &nbsp;·&nbsp; free and open source (MIT) &nbsp;·&nbsp; no account, no telemetry</sub>
</p>

![HiCloud MP — library, queue and now-playing card in the dark theme](screen.png)

## Download

Both buttons always download the newest release — no version hunting.

| | |
|---|---|
| **Installer** <br><sub>recommended</sub> | [**HiCloudMP-Setup.exe**](https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-Setup.exe) — about 75 MB. Adds HiCloud MP to the Start menu and installs an uninstaller. No Python or extra codecs needed. |
| **Portable** | [**HiCloudMP-portable.zip**](https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/HiCloudMP-portable.zip) — about 112 MB. Unzip it anywhere, run `HiCloudMP.exe`, and take your player with you. |

> **First launch and SmartScreen.** The app isn't code-signed yet, so Windows
> may show *"Windows protected your PC"*. Click **More info → Run anyway** —
> the builds come straight from this repository's GitHub Actions.
>
> Want release notes or an older version? See
> [all releases](https://github.com/PhantomPixelDev/HiCloudMP/releases).

## What you can do

- **Bring your library together.** Add your music folders once, then browse
  by name, artist and album — with instant search and a queue you can filter
  and sort.
- **Stream from your cloud.** Connect Nextcloud or any WebDAV server, a
  Subsonic-compatible server, or Ampache. Albums scan in the background and
  play directly — nothing to sync, nothing to download twice.
- **Shape the sound.** A real 10-band equalizer with presets and custom
  curves. Changes apply while the music plays, and flat settings are a
  bit-exact bypass.
- **Keep the queue moving.** Title / artist / album columns, drag to reorder,
  Play Next, shuffle, repeat — and the queue remembers its sort and filter
  between sessions.
- **Use your phone as the remote.** Settings → Web Remote gives you a link
  that works on the same Wi-Fi, with no app to install. It's token protected
  and stays local unless you allow other devices.
- **Stay private.** No account, no telemetry. Settings and playlists stay on
  your PC, and saved cloud passwords are encrypted with Windows DPAPI (locked
  to your Windows user).

## Get started in three steps

1. **Install** the app — or unzip the portable build.
2. **Add your music** — `Add Folder` for local files, or `Add Cloud` →
   `Scan Cloud` for a server.
3. **Press play.** `Tools → Equalizer` and `Settings → Web Remote` are one
   click away.

<img src="docs/assets/equalizer.png" width="430" alt="The 10-band equalizer with the Rock preset">

Works with **WebDAV** servers (Nextcloud, ownCloud), **Subsonic-compatible**
servers (Subsonic, Navidrome, Airsonic, Nextcloud Music) and
**Ampache-compatible** servers. You'll need the server address and your login;
an app password is fine.

Your data lives in `%LOCALAPPDATA%\HiCloudMP\HiCloudMP`. Installing,
upgrading or uninstalling never touches your settings, playlists or music.

## Good to know

- **Requirements:** Windows 10 or 11, 64-bit.
- **Updates:** *Settings → Check for updates* compares your version with the
  latest GitHub release.
- **Uninstall:** *Settings → Apps → HiCloud MP*. Your music and settings stay
  untouched.
- **Linux:** the source runs on Linux (with MPRIS media keys); packaged
  builds are Windows-only for now.

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

**Tests** (headless/offscreen, no audio device required):

```bash
pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

**Packaging:** `.github/workflows/build.yml` builds the standalone app
with Nuitka on every push. Pushing a `v*` tag additionally compiles the Inno
Setup installer and publishes the release with `HiCloudMP-portable.zip`, the
versioned installer, and the stable `HiCloudMP-Setup.exe` alias used by the
download buttons above.

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
