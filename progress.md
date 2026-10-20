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

`8e31f61` fix: corrupt files never modal the queue; close survives broken subsystems
- Plan P4: local InvalidMedia during auto-advance popped a MODAL
  QMessageBox (queue stopped dead until click) -> now status line +
  tray toast via shared _tray_toast helper (factored from
  _engine_playback_error); cloud rows keep the retry path.
- closeEvent: player.stop / web-server stop / the three state saves
  independently guarded - one broken subsystem can no longer skip
  later saves or block close; event.accept() always reached.
- Tests tests/test_hardening.py red->green (4, incl. refactor guard);
  suite cold `302 passed, 2 skipped`. One-off faulthandler C-stack
  dump observed in an inline pytest run (killed mid-run by interrupt);
  clean runs green; exit-fatal class covered by 5ed140d subprocess
  gates.

`6adaf24` fix(test): hardening tests kept real C++ objects alive
- P6 verification exposed an intermittent 0xC0000005 (once per ~2-3
  cold runs) introduced by 8e31f61's tests: bare SimpleNamespace
  replacement of mp.player/eq_engine/meta dropped the last Python
  reference to the live objects -> PySide destroyed C++ under the
  media backend's feet. Tests now use a delegating _Facade (house
  pattern from the engine-fallback round). Suite x4 consecutive cold
  runs green (302 passed, 2 skipped each), no dumps post-fix.

P6 verification COMPLETE (2026-10-19):
- Full cold suite: 8 consecutive runs `302 passed, 2 skipped` after
  6adaf24 (one 0xC0000005 blip pre-fix, zero post-fix).
- Real-app relaunch smoke: `main.py` starts with the user's real
  settings, alive at 10 s, no fastfail, no crash-log entries; only
  stderr is the user's own enabled web-panel Flask banner. Terminated.
- Temp probes deleted (wrap_app.py, dbg_playlist_io.py,
  probe_engine_error.py, probe_cover*.py, run logs).
- Session commits on main (all UNPUSHED, tag/build gated):
  0d79189, d503437 (EQ/viz + settings), 36ab5f3 (playlist IO UI),
  b923a72 (playlist UX), 20f1a2a (perf), 8e31f61 (hardening),
  6adaf24 (test-crash fix), + ledger commits.
- User symptoms status: 0xC0000409 exit fatal FIXED (5ed140d +
  gates), EQ/viz "stopped working" root-caused and FIXED (flush +
  loud fallback), local covers FIXED (4077823/0360727).
- v1.0.3 bump/tag/build: awaiting explicit user go.


Improv round (Do it all), part 1 of ~6 (2026-10-19):
User asked for the full improvement list; executing continuously, TDD,
one commit per logical change, release gate still locked.

`1d7d1f4` fix: corrupt local file skips to next track
- P4 only removed the modal; the queue still stopped dead at the bad
  row. InvalidMedia now advances playback to the next entry (status +
  tray toast kept), tail stops with "end of playlist". Bounded: each
  skip moves the index forward, so a fully-corrupt playlist cannot
  loop. Message keeps the "Could not play" prefix the hardening test
  asserts on. tests/test_invalid_media_skip.py (3 tests).

`9493138` feat: stream URLs from imported playlists play from queue
- Import kept counting http(s) rows as skipped; they now join the
  queue as "(Stream)" rows, play() routes string URLs through the
  existing _play_stream retry path, export writes URLs verbatim (the
  old path abspath-mangled them to "https:\host\file"). Browser/m3u8
  round trip covered in tests/test_playlist_menu.py (2 new tests).

`53bc6cf` feat: Explorer drag-drop onto the playlist
- Playlist files drop-import via shared _import_playlist_file
  (extracted from the menu action); audio files append to the queue;
  junk refused; internal reorder drags untouched. Filter is installed
  on the viewport (drag events land there, not the view).
- Test-infra lesson recorded: QDropEvent stores a RAW pointer to its
  QMimeData - passing _mime(...) inline lets shiboken destroy the
  mime while the event still points at it; the next mimeData()/repr()
  access is an instant access violation. Call sites hold the mime in
  a local (tests/test_playlist_drop.py, 7 tests).
- Suite after 1d7d1f4+9493138: 307 passed, 2 skipped. After 53bc6cf:
  314 passed, 2 skipped.

Improv round, part 2 (2026-10-19):

`9f5df59` fix(test): EQ routing tests no longer feed WMF a missing file
- Root cause of the intermittent 0xC0000005 that killed full-suite runs
  (seen twice at ~22%): test_eq.py's two route tests handed a
  nonexistent path to the REAL QMediaPlayer; pytest-qt teardown then
  destroyed the player mid-async-load and the WMF backend worker thread
  tripped an access violation (pooled thread, no Python frame). Repro:
  test_eq.py alone crashed 5/10 runs; after the fix 0/20.
- Fix follows the house recording-facade pattern (_SilentPlayer keeps
  the real object alive in _real, records setSource/play, delegates
  reads). Not an app bug - real missing files go through the
  InvalidMedia path fixed in 1d7d1f4.
- Full suite 3/3 consecutive green afterwards.

`51f9512` feat: Artist/Album sort reads real tags
- The sort combo offered Artist/Album but sorted on hardcoded empty
  strings (placebo). read_sort_tags(): mutagen easy interface first,
  raw ID3 frames fallback (WAVE has no easy mapping - verified live).
  Untagged rows sort first; ties fall back to artist/title. Only read
  for those two modes; unreadable files return ("", ""). 5 tests with
  real WAV+ID3 files.

`2558040` feat: Play Next queue visibility
- Status-bar badge "Play Next: N" (hidden at zero, click clears) +
  "Clear Play Next Queue" context action (enabled only when queued);
  badge refreshes on every mutation. 4 tests.

`41b3fc9` feat: remember window geometry
- saveGeometry/restoreGeometry through QSettings; saved as an extra
  guarded step in closeEvent + settings.sync(). Note: offscreen test
  screens are 800x800, so Qt screen-fits large saved widths in tests
  (960 minimum wins) - asserted via the exact blob + height roundtrip.

Suite: 326 passed, 2 skipped.

Improv round, part 3 (2026-10-19):

`30136fb` feat: mute toggle in the main window
- The transport volume glyph was a disabled decoration; only the tray
  could mute, and tray mute only silenced the native output (mute did
  nothing while EQ/viz owned playback). The glyph is now a real toggle:
  remembers the pre-mute level, mirrors the slider at 0, swaps to a
  volume-x glyph, and zeroes the EQ-engine sink when that route runs.
  Dragging the slider up unmutes; the tray action is engine-aware too.
  5 tests.

`2c277ee` feat: playback speed control
- Playback > Speed submenu (0.5x-2x), persisted at audio/playback_rate,
  re-applied to every new native track, validated on load (garbage or
  out-of-range -> 1x). The EQ engine has no rate control: choosing a
  speed there keeps 1x and explains why instead of silently no-oping.
  7 tests.

`8627552` feat: single-instance lock
- main.py takes a QLocalServer named-pipe lock before building the
  window; a second launch connects (the only reliable probe - Qt on
  Windows lets two servers listen on one name, but connects always
  reach the first), pings activate, exits 0. The running instance
  shows/raises itself. The OS removes the pipe with the process, so no
  stale lock file. 3 tests plus a real two-process smoke: second exited
  in ~1.3 s, first stayed alive.

Suite: 341 passed, 2 skipped.


Improv round, part 4 (2026-10-19) - items 10-17:

`07d2fbf` feat: Help > Keyboard Shortcuts reference dialog
- Global keys (Space, Ctrl+arrows, Ctrl+S) and playlist keys (Del,
  Home/End, volume click) were only discoverable by accident. The dialog
  is generated from one SHORTCUT_HELP table; a test asserts the four
  transport rows match the real QAction shortcuts. 4 tests.

`e117fd2` feat: bounded stream retries with auto-skip
- A dead URL reconnected forever; EndOfMedia reconnects did not even
  count. Retries now cap at STREAM_MAX_RETRIES for every path; when the
  exhausted stream is the playing playlist row, playback advances to the
  next entry (bounded - each give-up moves forward). Unrelated failures
  report and stop. 5 tests.

`61bd83c` feat: Recently Played / Most Played
- play_history.json (atomic writes; corrupt = empty). Records existing
  local files, stream URLs and cloud rows; re-plays move to the front,
  counts accumulate, recent capped at 50. Tools submenus rebuilt on open;
  click replays in place or appends; missing files report. 9 tests.

`33ac5cc` feat: watch library folders and auto-refresh
- QFileSystemWatcher over every library root + subdirectories (bounded),
  debounced into one background rescan; watch list rebuilt afterward so
  new subfolders are picked up and removed folders dropped. 6 tests.

`b53d175` feat: web panel parity + desktop-to-panel push
- Panel gained mute, 0.5x-2x speed, Play Next queue badge (click clears).
  Status carries muted/rate/queue_count. Play/stop/pause, volume, mute,
  shuffle, repeat, speed, queue changes and metadata updates broadcast
  status+progress instead of waiting for the next poll. 7 tests.

`6dca7ea` feat: gapless hand-off on the EQ-engine path
- Sequential local tracks tore down decoder+sink between songs. The
  engine now preloads the next decoder and swaps it onto the SAME sink/EQ
  chain; the UI/position change is reported at the audible boundary, and
  a late durationChanged(-1) can no longer erase the known duration.
  Player arms only plain sequential local rows (not shuffle/Play Next/
  cloud/last); Play Next invalidates, clearing it re-arms. 11 tests plus a
  real two-track audio probe (advanced then finished, no restart).

`d803abd` refactor: extract play history and folder watching
- Bounded split: history.py (PlayHistoryMixin) and folder_watch.py
  (FolderWatchMixin + constants). MusicPlayer mixes both in; constants
  re-exported. player.py 3,959 -> 3,761 lines. Structural test prevents
  duplication back into the class.

`e53c612` fix: delete finished cloud-scan QThreads via deleteLater
- Completed scans dropped QThread wrappers from the lists, letting Python
  destroy the C++ object while queued signals could still be delivered.
  Finished threads are deleteLater()'d and retained until Qt's destroyed
  signal; running threads keep retire+quit and the 100 ms recheck; a new
  scan disposes old threads that already stopped. 4 tests incl. a real
  QThread.

Suite: 389 passed, 2 skipped. All 17 improvement items complete.
v1.0.3 bump/tag/build/push still waiting for explicit go.

Playback fixes round (2026-10-19) — user-reported regressions in v1.0.3:

`14bbe17` fix(ui): volume slider jumps to the clicked level
- Stock QSlider pages by pageStep on groove clicks: clicking at x=20 of
  a 150 px volume slider moved 70 -> 60 instead of near 13, so a level
  could only be set by dragging. ClickJumpSlider maps press/move/release
  to the groove position, keeps sliderPressed/sliderReleased and keyboard
  behaviour. 6 tests (click 25/50/75%, drag, signals, live player).

`6ec2143` fix(visualizer): real spectrum on native playback and clearer bars
- The visualizer only read the EQ engine's spectrum. Any native playback
  (engine device busy/unsupported fallback, native cloud streams) showed
  the idle baseline forever. QAudioBufferOutput now taps decoded native
  PCM with sample-rate-aware band mapping; the engine stays the post-EQ
  source when active. Bars are larger (150x36), use the saved accent at
  startup, and a 0.65 display gamma lifts quiet music without faking
  silence. Evidence: the user's real Subsonic track produced 24 bands
  (max 0.27) through the engine; a real QMediaPlayer tone produced max
  0.79 through the native tap; local music peaks averaged 0.39. 8 tests.

`ee15097` perf(library): keep folder watching off the UI's critical path
- Every refresh walked the 48 GB Downloads tree on the UI thread (391
  dirs, 160 ms) and then called addPath 391 times (~358 ms); this ran at
  startup and again after every debounced folder change. Walk is now
  breadth-first, stops at 128 dirs, and large watch sets are added in
  batches across event-loop ticks. Real-data startup probe: 717 ms before,
  454 ms after; no event-loop spikes >50 ms. 2 tests.

`c86dd0e` perf(metadata): stop probing cloud streams on the UI thread
- Subsonic scan rows have title='' and carry the title in `name`; artist
  and album are populated. The old `if not title or ...` guard therefore
  ran CoverExtractor.extract_metadata (ffprobe over the network) on the
  UI thread for every cloud track: measured 827 ms per track. Display now
  uses title/name/path + scanned artist/album and never probes the stream
  on the now-playing path. 3 tests.

Suite: 408 passed, 2 skipped.
Not pushed/tagged/released; version remains 1.0.3 until explicit go.

`edf362d` fix(metadata): resolve cloud queue metadata from scanned rows
- Library-built cloud queue rows store only cloud_idx/file_idx, so the
  now-playing labels under the cover reset to Unknown even though the
  playlist and file manager showed the scanned names. Display now
  resolves name/artist/album (and path fallback) from the in-memory
  clouds.json catalog. Resolved values are cached on the live queue row
  so repeated displays do not re-resolve the catalog; Unknown placeholders
  are not cached, so a later scan can fill them in. No ffprobe, network
  request, or rescan. 2 tests.

Suite: 410 passed, 2 skipped.
Not pushed/tagged/released; version remains 1.0.3 until explicit go.


## 2026-10-20 — fix: Recently/Most Played name cloud entries from the catalog

Landed with this commit (`6af1c35`):

- Queue rows and history entries persist only `cloud_idx`/`file_idx`, so
  `record_play` cached the raw `cloud:0:N` key as the display name and the
  Recently/Most Played menus showed keys instead of songs (user-reported,
  confirmed on v1.0.4 install data).
- Display names now resolve from the in-memory scanned cloud rows as
  `Artist – Title` (title falls back to row `name`, then basename of
  `path`). Subsonic rows carry the title in `name`, artist in `artist`.
- Legacy entries whose stored name is still the raw key are repaired at
  display time (files on disk stay untouched; names heal on next play).
- Newly recorded plays persist the resolved human name, so restarts keep
  showing real song names. 3 tests.

Suite: 413 passed, 2 skipped.
Version remains 1.0.4 until explicit go for 1.0.5.

## 2026-10-20 — fix: touching the EQ curve enables the equalizer

Landed with this commit (`7b3093b`):

- v1.0.4 user report "Equalizer dont work": install registry had
  `eq_enabled=false` with a Bass-Boost curve stored; the dialog's
  "Equalizer on" box defaults to the persisted state, and with it unticked
  slider/preset changes saved the curve but applied FLAT gains live
  (visualizer-only engine route by design), so tuning was inaudible.
- Moving a slider or picking a preset now auto-enables the EQ (VLC-style).
  Explicit unchecking still applies immediately; Cancel/X still restores
  the state captured at open. Probes confirmed the engine itself works on
  the packaged stack (PySide 6.12/FFmpeg 9): local WAV tone + real MP3 +
  cloud stream all decode, position advances, no errors. 4 dialog tests.

Suite: 417 passed, 2 skipped.
Version remains 1.0.4 until explicit go for 1.0.5.

## 2026-10-20 — fix: library double-click appends to the queue

Landed with this commit:

- Library clicks replaced `self.app.playlist = [item]` and cleared the
  playlist widget - every left-list click destroyed the queue the user
  was building. Local and cloud file clicks now APPEND a queue row and
  play it at its index; playlist/category clicks keep their load paths.
- Added `MetadataController.queue_label()` as the single shared
  'Artist – Title' formatter for queue rows (catalog-resolved, no
  probing); library insertion uses it now, next: queue table + streams.
- Palette: Subsonic rows keep the title in `name`.

Suite: 419 passed, 2 skipped.
Version remains 1.0.4 until explicit go for 1.0.5.

## 2026-10-20 — feat: queue becomes a Title/Artist/Album table

Landed with these commits:

- `b2eb0fa` Queue rows were single-column filename strings; playlist is now
  `PlaylistQueueWidget` (QTreeWidget: Title|Artist|Album) that speaks the
  QListWidget dialect (addItem/count/item/takeItem/insertItem/currentRow/
  row/itemAt/selectedItems, text(col=0) default), so the app and tests keep
  working unchanged while rows carry real metadata cells. Cells resolve from
  the scanned cloud catalog via `MetadataController.queue_cells` (Subsonic
  rows keep the title in `name`). Filter matches any column; sort re-permutes
  existing rows using artist/album cells (local rows still read tags via
  read_sort_tags, cached into cells); highlight paints all three columns;
  stream rows keep their "(Stream)" marker; the dead duplicate
  `on_library_item_clicked` in player.py (still wiping the queue) is gone.
- `4fab01f` CI pins the packaged stack to PySide6==6.10.3. Measured on the
  dev machine with identical code+data: local decode-open to first audible
  ~0.29 s on 6.10.3 vs ~0.66-0.85 s on 6.12.0; cloud streams ~0.5-0.6 s on
  both; installed-app steady state 17% of one core during playback; startup
  ~2.5 s. The 6.12/FFmpeg 9 stack is where the user's "compiled version is
  super slow" reports pointed; shipped builds now run the tuned stack
  (FFmpeg 7.1.3) instead of floating to the newest minor.

Suite: 424 passed, 2 skipped.
Version remains 1.0.4 (git) — v1.0.5 tag/push/release awaits explicit go.

## 2026-10-20 — release: v1.0.5 (user-authorized)

- `a5` (this commit) Bumps `APP_VERSION` to 1.0.5 and ships the tag. Carries
  the four user-reported fixes (history naming `6af1c35`, EQ enable-on-touch
  `7b3093b`, library click appends `efcd9a5`, queue Title/Artist/Album table
  `b2eb0fa`) plus the packaged-stack pin to PySide6 6.10.3 (`4fab01f`).
- Release step in CI fires only on `refs/tags/v*`; pushing main never publishes.

Suite: 424 passed, 2 skipped.
