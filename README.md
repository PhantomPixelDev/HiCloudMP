# HiCloud MP - Cross-Platform Music Player

A personal project born from the need for a lightweight music player with robust WebDAV integration, designed to seamlessly sync with cloud storage services.

A powerful, modern music player with support for local and cloud-based music libraries.

![Python](https://img.shields.io/badge/Python-3.x-blue)
![Qt](https://img.shields.io/badge/Qt-PySide6-green)

## Screenshot

![HiCloud MP Screenshot](screen.png)

## Features

✨ **Unified Music Library**
- 🎵 Local files and folders
- ☁️ Cloud storage via WebDAV (Nextcloud, OwnCloud, etc.)
- 🔍 Search across local and cloud

🎧 **Playback & Control**
- 📋 Playlists (create, save, load, edit)
- 🔀 Shuffle and 🔁 Repeat
- 🎚️ Volume, mute, seeking with progress
- ⌨️ System media keys via MPRIS (Play/Pause, Next, Previous, Stop)
- 🧰 Enhanced tray menu: Now Playing, Play/Pause, Next/Prev, Stop, Shuffle, Repeat, Mute, inline Volume slider, Seek ±10s, Show/Hide Window, Open Current Location, Settings, Web Panel, Quit
- 🌐 Web Interface (LAN): real-time remote control from any device

☁️ **Cloud Integration**
- 🌐 WebDAV (Nextcloud, OwnCloud, etc.) with folder scanning and cover art

🎨 **Modern UI**
- 🌙 Dark theme with sleek purple-blue accents
- 📱 Responsive layout

## Installation

### Requirements
- Python 3.12+ (3.14 supported; the PySide6 pin adapts automatically)
- System media library (`python-vlc` is not used — playback is Qt `QMediaPlayer`)
- Linux only: see `requirements-linux.txt` for the MPRIS/media-key extras

### Setup

1. Clone the repository:
```bash
git clone https://github.com/phantompixeldev/HiCloudMP.git
cd HiCloudMP
```

2. (Recommended) Create and activate a virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
# Linux desktops with MPRIS/media keys:
pip install -r requirements-linux.txt
```

4. Linux desktop (for MPRIS/media keys): install system packages if missing
- Arch/Endeavour/Manjaro:
  ```bash
  sudo pacman -S python-gobject
  ```
- Debian/Ubuntu:
  ```bash
  sudo apt-get install python3-gi gir1.2-glib-2.0
  ```

5. Run the player:
```bash
python main.py
```

## Web Interface (LAN Remote Control)

HiCloud MP includes a web interface for remote control from any device on your network.

> **Security:** the panel is protected by an access **token**. It binds to
> `127.0.0.1` by default; enabling **Expose on LAN** in Settings binds to
> `0.0.0.0` and the token stays mandatory for every route and socket.
> Any HTTP/WSS client without the token gets rejected.

### Features
- 🎛️ **Full playback control** (play, pause, next, previous, stop)
- 🔊 **Volume control**
- 📋 **Playlist view** (see and play any track)
- ⏩ **Seek bar** (see and seek track progress)
- 🔀 **Shuffle** and 🔁 **Repeat** toggles
- ⚡ **Real-time updates** (instant sync between desktop and all web clients)
- 📱 **Multi-device**: Control from your phone, tablet, or another PC

### How to use
1. Open HiCloud MP and go to **Settings**
2. Enable **Web Interface (LAN control)** and expose on LAN if desired
3. The update loop shows a short-lived token path: the built-in **Web Panel** menu action opens the panel URL with its token pre-attached (copied automatically to the browser session); from other devices open
   `http://<desktop-ip>:5000/?token=<token>`
   (the token is shown read-only in Settings)
4. The page moves the token into browser session storage and strips it from the visible URL automatically.

## Usage

### Adding Local Media
1. Click "Add Folder" or "Add Files" to add music to your library
2. Browse to select your music files or folders
3. Choose whether to add to your library or directly to a playlist

### Adding Cloud Accounts
1. Click "Add Cloud" to add a WebDAV storage account
2. Enter your WebDAV server details (URL, username, password)
3. Click "Scan Cloud" to discover your music files

### Creating Playlists
1. Add tracks to the current queue
2. Click "New Playlist" or use the dropdown menu
3. Enter a name for your playlist
4. Click "Save Playlist"

### Playback Controls
- Use the transport controls (Play/Pause, Next, Previous, Stop)
- Adjust volume with the slider or the tray menu
- Use your keyboard's media keys (via MPRIS) on supported desktops

### Tray Menu
- Right-click the tray icon to access controls and actions:
  - Now Playing, Show/Hide Window
  - Play/Pause, Previous, Next, Stop, Seek ±10s
  - Shuffle, Repeat, Mute, Volume slider
  - Open Current Location, Settings, Web Panel, Quit

### Verify MPRIS (optional)
With the app running:
```bash
playerctl -l                 # list detected players
playerctl -p hicloudmp status
playerctl -p hicloudmp play-pause
playerctl -p hicloudmp next
playerctl -p hicloudmp metadata
```

## Configuration Files

The player stores settings in the following files:
- `mediafolders.json` - List of local media folders
- `cloudfiles.json` - Cloud account settings and cached file lists
- `playlists.json` - Saved playlists

## Supported Formats

- MP3 (.mp3)
- FLAC (.flac)
- WAV (.wav)
- OGG (.ogg)
- AAC (.aac)
- M4A (.m4a)
- WMA (.wma)

## Troubleshooting

- Media keys not working but playerctl works:
  - Close other media apps (e.g., Firefox, Spotify) so your desktop routes keys to HiCloud MP.
  - Ensure the player is active/playing. Some desktops send keys to the last active MPRIS player.
  - A desktop file can help desktops prefer your player (request one if you need it installed).

- playerctl cannot find the player:
  - Start the app and re-run `playerctl -l`. Look for `hicloudmp`.
  - Check that your session has a DBus user bus (normal on desktop Linux).

- Missing DBus/PyGObject on Linux:
  - Install `python-gobject` (Arch) or `python3-gi` (Debian/Ubuntu) as shown above.

- Web interface not starting:
  - Ensure Flask and Flask-SocketIO are installed (`pip install -r requirements.txt`).
  - Enable it in Settings, then open the Web Panel from the menu.

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

Run the test suite before opening a PR:
```bash
pip install -r requirements-dev.txt
pytest tests/
```

## Project status & roadmap

A full codebase review (verified crash list, security findings, deferred roadmap) lives at
[`docs/superpowers/specs/2026-10-17-codebase-review.md`](docs/superpowers/specs/2026-10-17-codebase-review.md).
Known deferred items include: theme centralization, model/view library, native Windows media keys
(regression tests exist for the removed win32 handler), streaming credentials not embedded in URLs,
and a full `MusicPlayer` decomposition.
