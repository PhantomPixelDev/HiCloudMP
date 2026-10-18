# HiCloud MP

A modern desktop music player for your local files and your cloud libraries —
with a **real 10-band equalizer**, a **phone-friendly web remote**, cover art,
and a Windows installer built automatically by CI.

![HiCloud MP — main window, dark theme with the accent play circle and themed icons](screen.png)

| | |
|---|---|
| ![Python](https://img.shields.io/badge/Python-3.12%2B-blue) | ![PySide6](https://img.shields.io/badge/Qt-PySide6-green) |
| ![CI](https://github.com/PhantomPixelDev/HiCloudMP/actions/workflows/windows-build.yml/badge.svg) | ![License](https://img.shields.io/badge/License-MIT-lightgrey) |

## Highlights

- ☁️ **Cloud libraries** — Nextcloud/WebDAV, Ampache and Subsonic servers.
  Albums are scanned in parallel (8×) and stream directly, so a song is
  audible seconds after you press play.
- 🎚️ **Real 10-band equalizer** — decoding → FFT overlap-add DSP → audio
  sink for *every* played track (local or streamed). Presets and custom
  gains apply live; zero-gain settings are a bit-exact bypass, and any
  engine problem falls back to native playback automatically.
- 🖼️ **Cover art pipeline** — pulled from tags (ID3/Vorbis/MP4/FLAC),
  stream metadata, or extracted with ffmpeg when nothing else has it.
- 🌐 **Web remote that normal people can use** — Settings shows one
  ready-to-open link; the panel shows a live connection pill (`Connected ·
  42 ms` / `Offline`). Tokens are handled for you (embedded in the link,
  then hidden from the browser URL); LAN exposure is one checkbox.
- 🎨 **Theme system** — Dark/Light, 12 accent presets or *any* custom
  color, comfortable/compact density, and an optional background image
  ("wallpaper mode") with an adjustable darkness slider. Icons are
  rendered from code and re-tinted with the theme — no stale asset files.
- 🧰 **Full remote control from everywhere** — in-app menus, tray menu
  with transport + volume + seek, and MPRIS media keys on Linux desktops.
- 🔒 **Security by default** — the web server binds to `127.0.0.1` unless
  you explicitly allow the LAN; every route and socket requires the token;
  config files are written atomically so a crash can't corrupt them.

## Downloads (Windows)

Grab the latest release from
[**Releases**](https://github.com/PhantomPixelDev/HiCloudMP/releases):

- `HiCloudMP-Setup-x.y.z.exe` — standard installer (program files, start
  menu, optional desktop shortcut). **No Python needed** — everything is
  bundled.
- `HiCloudMP-portable.zip` — unzip anywhere and run `HiCloudMP.exe`,
  nothing is installed.

Both are built automatically on every version tag by GitHub Actions
(Nuitka standalone + Inno Setup, ffmpeg bundled for cover extraction).

Your data (settings, playlists, cloud accounts) lives in per-user app data
and is never touched by installs, upgrades or uninstall.

## Running from source

Requirements: Python 3.12+ and `pip`.

```bash
git clone https://github.com/phantompixeldev/HiCloudMP.git
cd HiCloudMP
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
# Linux desktops with MPRIS/media keys:
pip install -r requirements-linux.txt
python main.py
```

Linux desktop only: install the DBus/GLib bits if your distro doesn't have
them — `sudo pacman -S python-gobject` (Arch) or
`sudo apt-get install python3-gi gir1.2-glib-2.0` (Debian/Ubuntu).

## Using it

### Music library

- **Add Folder / Add Files** builds a local library (mp3, flac, wav, ogg,
  aac, m4a, wma) with cover art and searchable, album-grouped browsing.
- **Add Cloud** connects Nextcloud/WebDAV, Ampache or Subsonic — enter the
  server URL and credentials, then **Scan Cloud**. Status flows through
  the status bar (no blocking dialogs); a failed account can't stall the
  others.

### Playback

- Full transport (play/pause, stop, next/prev), shuffle, repeat,
  drag-seek, volume.
- **Tools → Equalizer** for the 10-band engine: pick a preset, tweak
  sliders, apply live. Close = keep; Cancel = restore.
- Tray menu mirrors everything: Now Playing, play/pause, next/prev, stop,
  seek, shuffle/repeat, mute, volume slider, show/hide, quit.
- Keyboard media keys through MPRIS on Linux desktops.

Verify MPRIS (optional, Linux):

```bash
playerctl -l
playerctl -p hicloudmp status
playerctl -p hicloudmp play-pause
playerctl -p hicloudmp metadata
```

### Web remote

1. **Settings → Web Remote**: turn it on.
2. Click **Copy link** (or **Open in browser**).
3. Open the link on your phone/tablet — same Wi-Fi, zero setup.
4. Want it from other devices on the network? Enable
   *Allow other devices on this network*.

> The panel is token-protected; the token is embedded in the link Settings
> generates and is stored only in the browser session — it's stripped from
> the visible URL so it can't leak through bookmarks or shared tabs. The
> ping endpoint affects nothing about the player (liveness only).

### Playlists

Add tracks to the queue → **New Playlist** → name it → **Save Playlist**.
Everything is stored in plain JSON in per-user app data
(`mediafolders.json`, `cloudfiles.json`, `playlists.json`).

## Building & packaging

- **Tests**: `pip install -r requirements-dev.txt` then `pytest tests/`
  from the repo root (all headless/offscreen).
- **Windows builds**: `.github/workflows/windows-build.yml` runs Nuitka
  standalone (PySide6 plugin, console-free, app icon) on every push/PR and
  attaches a portable zip artifact. Pushing a `v*` tag additionally
  compiles the Inno Setup installer (`packaging/HiCloudMP.iss`) and
  publishes both files as a GitHub Release.
- Local packaging: build with the same Nuitka flags, place `ffmpeg.exe`
  next to the exe (it is found automatically by `cover_extractor`), then
  `ISCC /DAppVersion=1.2.3 packaging/HiCloudMP.iss`.

## Troubleshooting

- **Media keys not working (Linux)** but `playerctl` works: close other
  media apps so the desktop routes the keys to HiCloud MP, and make sure
  it is the last active player. Ensure a DBus user bus exists (normal on
  desktop Linux).
- **Web remote unreachable from the phone**: enable *Allow other devices
  on this network* (Settings → Web Remote) and check that both devices
  are on the same Wi-Fi; then copy the link again — it will contain the
  desktop's LAN address.
- **A track skips or stutters**: check CPU load and that the output
  device isn't in exclusive mode. The equalizer engine keeps seconds of
  buffered audio on purpose; if something still disrupts playback the app
  falls back to the native pipeline automatically (watch the status bar).
- **Web remote fails to start**: Flask and Flask-SocketIO come from
  `requirements.txt` — reinstall them.

## Roadmap

- Visualizer view for the currently playing track
- Custom per-cloud artwork caching improvements
- Packaging for macOS / Linux (AppImage)

## Contributing

Contributions are welcome! Please open a PR — CI runs installer +
portable builds on every branch push, and `pytest tests/` must stay
green before merging.

## License

[MIT](LICENSE)
