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

Next in line: EQ/visualizer + QThread-fatal fixes (investigations running),
then performance round.

