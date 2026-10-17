# HiCloudMP Codebase Review — 2026-10-17

Review of `main` @ `99fcd5e` (15 commits, last activity 2025-09-10). Verified by three
parallel deep-dives (core / UI / web-cloud-mpris) plus manual spot-checks of every
crash claim below. Stack: PySide6 6.x (Qt6) UI, `QMediaPlayer` engine (despite
`python-vlc` being pinned), Flask + SocketIO LAN panel, `mutagen`/`Pillow` metadata,
WebDAV via `webdavclient3`.

## Verified showstoppers (crash or dead feature)

| # | Issue | Evidence |
|---|-------|----------|
| 1 | Startup crash on Windows with pywin32: `create_win_proc_handler(self)` is called but does not exist anywhere (leftover of commit `2b7c88b` which removed the media-keys handler) | `player.py:205` |
| 2 | Startup import crash on Windows: `from mpris_dbus import MprisService` unconditionally imports `dbus`/`gi` (Linux-only) | `main.py:11`, `mpris_dbus.py:4-7` |
| 3 | Closing app raises AttributeError: `self.web_server.shutdown()` — `WebControlServer` defines only `stop()` | `player.py:2232` vs `web_control.py:205` |
| 4 | "Add Cloud" flow broken: dialog has no Done button (exec never returns Accepted → `get_data()` unreachable; would AttributeError anyway — no such method on `CloudAccountsDialog`), and `MusicPlayer.add_cloud` re-appends entries the dialog already added in place (double-add) | `player.py:1965-1980`, `player.py:42-98` |
| 5 | Duplicate method definition `add_file_to_specific_playlist` — the second shadows the first, clobbers `self.playlist` and never restores; plus wrong-arg call `self.add_file_to_playlist(p, d)` (signature takes only `data`) → TypeError on "Add to Playlist" context menu | `player.py:2447` + `player.py:2499`; call at `player.py:2318` |
| 6 | Tray "New Playlist with Current Track…" → AttributeError `self.app.QInputDialog` | `tray.py:186` |
| 7 | `xdg-open` used unconditionally → "Open Current Location" broken on Windows/mac | `player.py:916`, `tray.py:221` |
| 8 | Cloud streaming permanently breaks auto-advance/shuffle/repeat: `_play_stream` blanket-`disconnect()`s **all** `mediaStatusChanged` slots (including the app's own `on_media_status_changed`) and never reconnects them | `player.py:1375-1382`, connection at `player.py:213` |
| 9 | Web panel throws ReferenceError on every progress update: `setSliderBG()` never defined (`userSeeking` also undeclared global) | `web_panel.html:502,508,514` |

## Security findings (web server)

- **No authentication at all**; bound to `0.0.0.0:5000` — anyone on the LAN controls playback; port-forwarding = whole internet. `web_control.py` routes + all socket events.
- `cors_allowed_origins='*'` → any webpage you visit can connect to your player (drive-by control).
- Unvalidated `int()` casts in socket handlers → per-client crash on malformed input, no try/except.
- `DownloadWorker.requests.get` has **no timeout** (`workers.py:26`) → can hang a thread forever.
- Werkzeug dev server run in production via `allow_unsafe_werkzeug=True` (daemon thread).
- WebDAV passwords stored plaintext in `cloudfiles.json` and embedded into playback/cover URLs.

## Correctness / quality

- ~141 `except Exception` sites; bare `except:` at `player.py:1487`; silent `pass` clusters with debug `print()`s left in UI code (`player.py:644-682`).
- Non-atomic JSON saves (`save_clouds/playlists/media_folders`) — crash mid-write corrupts config incl. plaintext passwords.
- Broken light theme: clicking "Light" only clears the window stylesheet; app-level dark palette persists; saved theme/volume not applied at startup (`main.py:20-53`, `player.py:315-326`, hardcoded vol `player.py:199`).
- Threading: socketio worker threads read Qt widget `.text()` off-GUI-thread (`web_control.py:145-153`); `QApplication.processEvents()` in scan (`player.py:2015`).
- Dead code: `python-vlc` pinned but engine is `QMediaPlayer`; duplicate `CoverArtWorker` in `metadata.py:9` vs `workers.py:54`; `mpris.py` (QtDBus variant, unused, has own NameError at `:441`) vs wired `mpris_dbus.py`.
- God-file: `MusicPlayer` ≈2,450 lines / ~110 methods.
- Packaging: no tests, no `pyproject.toml`, requirements file typo (`requiments.txt`) with pinned transitive deps; `PyGObject`/`pycairo`/`dbus-python` are Linux-only yet in the same file; PySide6 6.9.2 excludes Python 3.14 (needs ≥6.10.1).

## Improvement roadmap (phases)

1. **Now (this plan):** crash fixes 1-9, web security hardening, atomic saves, timeouts, platform guards, test infra, requirements hygiene.
2. **Stability:** event-based retry unification, atomic+QSettings-backed config, QT6.10 API audit, pyinstaller/pyproject packaging, CI (pytest offscreen matrix).
3. **UI:** theme tokens module + working light mode at startup, model/view (QSortFilterProxyModel) library, drag-drop, icons, shortcuts, accessibility, i18n.
5. **Web/cloud:** local-token streaming proxy so creds never leave the machine, PROPFIND cover art, eventlet/waitress server, server-side progress push instead of 1 s polling, keyring credential storage.
6. **Core:** extract `PlaybackEngine`/`CloudPlaybackController`/`PersistenceService` from `MusicPlayer`, delete duplicate workers, delete dead `mpris.py`/`python-vlc`.
