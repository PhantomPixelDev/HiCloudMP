# HiCloud MP progress ledger

Append-only log of landed work, one entry per commit.

## 2026-10-18 — fix: download callbacks touched the status bar off the UI thread (0xC0000005)

Landed with this commit (`fix: stop touching the status bar ...`):

- **Root cause (0xC0000005):** `_download_and_play`'s `on_finished`/`on_error`
  handlers are plain-callable connections, so PySide ran them inside the
  download QThread. `QStatusBar.showMessage(msg)` with no timeout deletes the
  status bar's running message QTimer right there; destroying a running
  main-thread-affine QTimer from a foreign thread makes Qt skip the timer
  deregistration (it only warns), leaving a stale 5000 ms timer registration
  in the main dispatcher. Its next fire delivers a QTimerEvent to the freed
  QTimer → access violation in main event dispatch. Forensics: interval=5000,
  Coarse timer, garbage d_ptr; deterministically reproduced in isolation.
- **Fix:** progress/finished/error all marshal through `run_on_ui`; widget
  access, status messages, the modal error dialog and the stream fallback run
  on the UI thread.
- **0xC0000409 (same commit):** `_retire_qthread()` + orphan lists keep
  (thread, worker) references until `finished`; `MetadataController.stop()`
  detaches cover threads the same way and now releases orphans only once the
  thread is provably finished (the experiment leak is gone). `closeEvent`
  retires stalled download/scan threads instead of dropping running refs.
- **Evidence:** module `tests/test_qthread_lifecycle.py` 9 passed ×3; 7-file
  subset (35 tests) `33 passed, 2 skipped` ×3; full suite `223 passed,
  2 skipped` ×3 cold (~28 s each). Before: ≈80 % crash rate at subset test #29.

## 2026-10-18 — feat: crash-forensics logger pinned with tests

Landed with this commit (`feat: keep the crash-forensics logger ...`):

- main.py opens a per-user `crashlog.txt` (session header), enables
  faulthandler into it and installs a severity-labelled Qt message handler,
  all before PySide6 imports. This block produced the dbg forensics that
  root-caused both crash signatures.
- Pinned by tests: import opens the log; `_qt_message` labels and writes;
  and a clean-interpreter child (no pytest-qt handler swaps) proves a Qt
  warning emitted after `import main` lands in the crash log.
- Finding while pinning: pytest-qt replaces the Qt message handler for the
  duration of each test — that is why test-run crashlogs never contained the
  Qt-side warnings seen during the investigation.

Next in line: tray icon color fix, performance round.

## 2026-10-18 — feat: accent-badged tray icon (contrast-safe)

Landed with this commit (`feat: tray icon is an accent badge ...`):

- `icons.py`: `tray_icon()` renders a round accent-filled badge with a
  play/pause/stop glyph; the glyph flips white/near-black by the fill's
  relative luminance (contrast-safe on every accent) with a hairline rim so
  the badge reads on light and dark taskbars; rendered at 2x, size ladder
  16/24/32/48, cached per (glyph, accent), cleared by `invalidate()`.
- `tray.py`: `_tray_badge()` uses the live factory accent with one honest
  stock-icon fallback; init and every state update go through it;
  `_apply_icons()` re-tints the tray on theme/accent changes.
- Tests: 4 new in `tests/test_icons.py` (fill + contrast glyph, dark glyph on
  light accents, cache identity + honest null, TrayController state badges).
- Evidence: full suite `227 passed, 2 skipped` ×3.

`4077823` fix: local covers fall back to artwork stored next to the audio
- User report: "local cover not loading". Real-library forensics: the
  archive.org album "Tede – Ścieżka Dźwiękowa" was playing
  (02. 22 Gibony...mp3) and the extractor logged "Unsupported image
  format" for its MP3s. Hard facts from the folder: FLACs embed a
  410x410 cover and extract fine; the MP3s have NO embedded art at all
  (mutagen pictures=0, no attached_pic stream); the album ships
  Cover.jpg + per-track 800x200 banner renders on disk; the local path
  of extract_cover() tried only embedded art and ended at
  Image.open(<the mp3>) -> UnidentifiedImageError -> default cover.
- Fix: for local files, after embedded attempts fail,
  `_open_sidecar_artwork()` now uses artwork next to the audio,
  case-insensitive: `<track>.<img>` first, then cover/folder/front/
  album/albumart/artwork (.jpg/.jpeg/.png/.webp/.bmp). Cover-shaped
  (aspect 0.45-2.2) beats wide/tall renders (banner-like archive.org
  per-track displays defer to square Cover.jpg, last resort otherwise);
  corrupt candidates fall through; embedded art keeps priority;
  *_spectrogram.png never matches; URLs untouched.
- Tests: `tests/test_cover_sidecar.py` 6 tests red->green; cover files
  combined 13 passed; full suite cold `233 passed, 2 skipped`; real-album
  probe: 01/02/03 .mp3 -> 410x410 RGB (Cover.jpg).

`a016783` feat: playlist import/export engine (M3U/M3U8, PLS, XSPF)
- Plan P2 core as a new-file island (agents were auditing player.py/
  metadata.py read-only; no overlap). PlaylistIO: import m3u/m3u8
  (EXTINF, utf-8 w/ cp1252 legacy fallback), pls (indexed File/Title/
  Length, holes tolerated), xspf (ns-agnostic track walk - findall sees
  only direct children, tracks live under trackList; file: URI decode);
  export keyed by output ext, m3u relativizes inside base_dir with
  forward slashes, pls spec-shaped, xspf v1; utf-8->cp1252 fallback.
- Errors: FileNotFoundError / ValueError(unknown ext); order kept;
  unknown duration = None; URLs verbatim.
- Tests: tests/test_playlist_io.py 10 (collection RED - module missing
  -> 7 passed first cut -> fix trackList walk + legacy test content ->
  10/10); full suite cold `243 passed, 2 skipped`.
- Ruling: executing-plans wants an SDD workspace/ledger; this session's
  standing convention is repo-root progress.md as the ledger and direct
  work on main per owner's explicit "go" - keeping that.

`62bf01e` feat: one supported-formats list + embedded art for wma/aiff/wav/oga
- Plan P1. SUPPORTED_EXTS was a third opinion vs the add-files dialog
  (mp3/flac/wav/ogg vs +aac/m4a/wma): ffmpeg-decodable formats invisible
  to scan/cloud rows. Now one list adding .oga .opus .m4a .mp4 .aac .wma
  .aiff .aif .mka; scan/is_music_file/cloud filter read it.
- Cover fallback for the new containers: _extract_asf_cover (WM/Picture),
  _extract_aiff_cover/_extract_wav_cover (ID3 APIC chunks in AIFF/WAVE),
  .oga -> ogg branch; mutagen imported function-locally (broken installs
  degrade to the ffmpeg layer instead of killing module import).
- Tests: tests/test_supported_formats.py + tests/test_cover_formats.py
  red->green (fixture fixes: mutagen.wave is the module, wma/aiff branch
  tests had not created target files); full suite cold `265 passed,
  2 skipped`.

`1afdfc8` perf(web): panel progress poll skips remaining fetches while hidden
- Plan P5a: the web remote emitted socket get_progress at 1000 ms
  forever - background tabs kept the single-threaded server busy for
  nothing; emit is now gated on document.hidden.
- Test: tests/test_web_assets.py::test_progress_poll_skips_while_hidden
  (anchored on the last get_progress emit site) red->green.

`5ed140d` fix: 0xC0000409 was interpreter exit destroying a retired running QThread
- Root cause from the probe investigation (deterministic, headless):
  the fatal fired at PROCESS EXIT. closeEvent retires still-running
  uninterruptible threads (download requests.get 30s / ffmpeg cover /
  scan clouds) into module-global retention lists and the app just
  exits; interpreter finalization then CLEARS those globals - the
  pair's last reference drops, ~QThread sees running==true, qFatal,
  fastfail 0xC0000409. Existing gates never saw it: they ended with
  os._exit(0), skipping exactly this teardown.
- Fix: each owner module registers an exit guard
  (thread_teardown.register_exit_guard) over its retention lists -
  atexit runs BEFORE globals are cleared (proven); near-finished
  threads get 1 s grace; still-unstoppable at exit -> os._exit(0).
- Forensics: setObjectName at every QThread creation site (download,
  scan-cloud-{idx}, cover-art/worker) - fatals carry names now.
- Defense-in-depth: _retire_qthread._done mirrors metadata._release
  (deferred, isRunning-guarded retry, disconnect).
- Tests: tests/_qthread_teardown_child.py drives the real closeEvent
  detach path through normal finalization; unfixed -> exit 0xC0000409
  watched red, fixed -> 0; full suite cold `266 passed, 2 skipped`.
- Ruled out by the investigation (kept for the record):
  _retire_qthread._done sync-removal and metadata._cleanup pointer
  clears are delivered queued on finished with isRunning()==False on
  PySide6 6.10.3 - not the crash trigger (now hardened anyway).
- Deferred minor: player.py scan thread deleteLater-on-own-finished
  posts to a finished thread's queue (leak class, not fatal) - left
  untouched, tracked here.

`0d79189` fix: preferences survive hard process deaths (flush on change)
- EQ/viz mystery RESOLVED inline (its investigation agent died without
  a report): all preference writes were buffered QSettings setValue
  with no sync; the app's repeated 0xC0000409 fastfatal deaths ran no
  destructors, so the user's enabled EQ/viz reverted to defaults after
  every crash - matching their recorded settings snapshot (eq=false,
  viz unset). Exit-fatal already fixed (5ed140d); now the writes
  themselves flush immediately: MusicPlayer._flush_settings() +
  guarded sync after setValue in apply_eq_toggle, make_eq_apply_cb
  gain moves, open_eq_dialog accept, SettingsDialog.save_settings.
- Tests tests/test_settings_persist.py red->green (4).
- Method-level notes: monkeypatched shiboken QMediaPlayer method
  shadowing is NOT reliably intercepted (class-level descriptors win);
  whole-object replacement is the working pattern.

`d503437` fix: EQ-engine failure is loud (status wording + tray toast)
- When the decoder->EQ->sink route fails, EQ AND viz die together
  silently; only a 4 s status line mentioned "Equalizer". Now:
  engine-general wording + QSystemTrayIcon toast (6 s, sanitized
  detail), tray-less installs degrade to status only.
- Tests tests/test_engine_fallback_ux.py red->green (3) with a
  recording-facade native player (no WMF probing of empty files -
  flaky under pytest).
- Deferred to P4: closeEvent error trails when a subsystem raises
  mid-teardown (seen via stub-teardown errors); also local
  undecodable-file playback error UX (modal QMessageBox risk noted
  during probing).

`36ab5f3` feat: playlist import/export wired into the File menu
- Plan P2b: the a016783 format engine got its UI. File menu gains
  Import Playlist… / Export Playlist….
- Import: m3u/m3u8/pls/xspf; relatives resolve vs the playlist's own
  folder; only supported local audio appended (is_music_file+isfile);
  first-ever import readies track 0; missing rows + stream URLs
  skipped-with-count (URL queue entries -> P3); failures -> status.
- Export: selection or whole queue; cloud rows excluded with explicit
  count; format by save dialog, M3U8 first (default decision); writer
  relativizes entries under the export folder.
- P1 followup: Add Files dialog filter stale ( fourth opinion) -> built
  from SUPPORTED_EXTS so dialog/scan/cloud agree.
- Tests tests/test_playlist_menu.py red->green (6); suite cold
  `279 passed, 2 skipped` (test-content fixes: m3u fixtures resolve
  relative to the playlist's own folder).

`b923a72` feat: playlist UX - Play Next queue, dedupe, keyboard ops, context menu
- Plan P3: queue_play_next parks selected rows; BOTH auto-advance sites
  (native EndOfMedia + engine finish) consume the queue before
  repeat/shuffle/sequence; stale rows vanish silently.
- remove_duplicates_from_playlist: normcase-path + cloud-row key,
  first occurrence kept, widget mirrored, index clamp, no-dup run
  says so.
- Keyboard via filter on playlist_widget: Del/Space/Home/End; other
  keys pass through (guard pins it).
- Context menu refactored to _build_playlist_context_menu; adds Play
  Selected, Queue Next, Remove Duplicates, import/export shortcuts.
- Tests tests/test_playlist_ux.py red->green (12); suite cold
  `291 passed, 2 skipped`.

`20f1a2a` perf: viz repaint gate + playlist filter/sort repaint brackets
- visualizer.set_spectrum skips identical/idle-to-idle frames; 20 Hz
  timer pin and paint-content tests stay green.
- filter_playlist/sort_playlist wrapped in setUpdatesEnabled brackets;
  behavior parity asserted; driven via the real signals.
- Test-writing lessons pinned in the ledger: fixture names ended
  ".mp3" so a "3" search matched everything (test bug, fixed); spy on
  QListWidget methods via instance setattr is honored for plain calls.
- Tests red->green (4+3); suite cold `298 passed, 2 skipped`.

Next in line: P4 hardening pack (closeEvent trail guard, InvalidMedia
modal demotion to status+toast, undecodable-file UX), P6 release
(verification x3 + real-app relaunch; tag only on explicit user go).

