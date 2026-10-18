# HiCloudMP Stability & Security Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate every verified startup/close/route crash, close the web-panel security holes, and put a green pytest suite under the project so future work has a gate.

**Architecture:** No new framework. Bug-for-bug fixes in-place plus small `utils.py` helpers (`open_folder`, `atomic_write_text`, pywin32-optional note). Tests are pytest + pytest-qt running the real widgets offscreen (`QT_QPA_PLATFORM=offscreen`), with the Flask-SocketIO test client for the server, and conftest redirecting config state (`APPDATA`) to a session temp dir before any project import.

**Tech Stack:** Python ≥3.12 (3.14 installed locally), PySide6 6.10.3 (first line supporting 3.14; the repo's 6.9.2 pin excludes it), Flask-SocketIO 5.5.1, pytest 9 + pytest-qt 4.5, pywin32 (dev-only, for Windows-path regression coverage).

**Spec:** `docs/superpowers/specs/2026-10-17-codebase-review.md`

## Global Constraints

- Python floor stays 3.12 (PEP 701 f-strings used at `cloud_handlers.py:244`); tests run on 3.14.
- No module splits, no `MusicPlayer` restructuring in this plan — bug-for-bug only. Refactors belong to the next plan.
- The app must stay runnable after every task; each task ends with the full suite green.
- Tests never touch real user data: conftest sets `QT_QPA_PLATFORM=offscreen` and redirects `APPDATA` to a session temp dir **before** importing `utils`/`player`.
- New runtime dependencies: none. Dev/test-only: `pytest`, `pytest-qt`, `pywin32` (Windows-only coverage).
- Commit style follows repo history: `fix:`, `test:`, `chore:` prefixes, plain messages, no Co-Authored-By lines.

## Review Focus

- A user **with** pywin32 must start and close the app on Windows without exceptions → `tests/test_smoke.py::test_player_constructs_offscreen` (win32-active) and `tests/test_close.py::test_close_event_runs_web_stop`.
- A user **without** pywin32/dbus/gi must start the app → `tests/test_main_import.py::test_main_imports_without_linux_backends`.
- A malformed web-panel event (e.g. `set_volume` value `"abc"`) must not kill the server → `tests/test_web_security.py::test_socket_bad_payload_is_ignored`.
- A LAN client without the access token gets 401 on routes and a refused socket connect → `tests/test_web_security.py`.
- A simulated crash mid-save must lose no previous config → `tests/test_atomic_save.py::test_failed_replace_keeps_previous_file`.
- After one cloud-stream attempt, EndOfMedia on a later local track still auto-advances → `tests/test_stream_autosadvance.py`.

---

### Task 1: Test infrastructure (pytest + offscreen Qt + isolated APPDATA)

**Files:**
- Create: `tests/conftest.py`, `tests/test_config_paths.py`, `pytest.ini`

**Interfaces:**
- Produces: pytest-qt fixtures for all later tasks; `SESSION_APPDATA` temp dir; rule: **every test module imports `utils`/`player` only inside test functions** (import order matters because `utils.py` reads `APPDATA` at module import).

- [ ] **Step 1: Write the test**

```python
# tests/test_config_paths.py
def test_config_paths_under_session_appdata(session_appdata):
    import utils
    assert str(utils.data_dir).replace("\\", "/").lower().startswith(str(session_appdata).replace("\\", "/").lower())
    assert str(utils.CLOUD_FILES_FILE).replace("\\", "/").lower().startswith(str(session_appdata).replace("\\", "/").lower())
```

```python
# tests/conftest.py (shape)
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APPDATA", str(Path(tempfile.mkdtemp(prefix="hicloudmp-tests-"))))
os.environ.setdefault("HOME", str(Path(tempfile.mkdtemp(prefix="hicloudmp-tests-home-"))))
```

`session_appdata` fixture returns `Path(os.environ["APPDATA"])`.
Note: this must land **before** first `import utils`, which is why config-path policy (env vars) lives in conftest at collection time.

- [ ] **Step 2: Run to verify it passes** (infra has no red phase) — `.venv\Scripts\python -m pytest tests/ -q` → `1 passed`, zero collection errors.
- [ ] **Step 3: Commit** — `test: pytest infra with offscreen Qt and APPDATA isolation`

### Task 2: Startup crash with pywin32 (`create_win_proc_handler`)

**Files:**
- Modify: `player.py:203-205` (delete block: comment + `if HAS_WIN32: self.win_proc = create_win_proc_handler(self)`)
- Modify: `utils.py:19-32` (drop the win32 import try/except block; replace with `HAS_WIN32 = (sys.platform == "win32")` — pywin32 is not used at all today)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing (removal).
- Produces: `MusicPlayer()` constructs with and without pywin32 present; media keys use only `setup_system_media_controls()` (wired at `player.py:208`). The name `create_win_proc_handler` must have zero callers and zero definitions after this task.

- [ ] **Step 1: Install pywin32 dev-only and write the failing test**

```bash
.venv\Scripts\python -m pip install pywin32
```

```python
# tests/test_smoke.py
def test_player_constructs_offscreen(qtbot, capsys):
    from player import MusicPlayer
    mp = MusicPlayer()
    qtbot.addWidget(mp)
    assert mp.player is not None
```

With pywin32 installed, `utils.HAS_WIN32` is True at import, __init__ hits the dead `create_win_proc_handler` call.

- [ ] **Step 2: Run to verify failure** — `.venv\Scripts\python -m pytest tests/test_smoke.py -q` → `NameError: create_win_proc_handler`.
- [ ] **Step 3: Implement** — delete `player.py:202-205` (four lines: comment, blank, `if HAS_WIN32:` and the call — keep `setup_system_media_controls()` call at 208); replace `utils.py` lines 19-32 with `HAS_WIN32 = (sys.platform == "win32")`.
- [ ] **Step 4: Run to verify it passes** — `pytest tests/ -q` → all green.
- [ ] **Step 5: Commit** — `fix: remove dangling create_win_proc_handler call that crashed startup with pywin32`

### Task 3: MPRIS import guard + FULL app smoke

**Files:**
- Modify: `main.py:11` (import guard) and `main.py:56-59` (usage guard)
- Create: `tests/test_main_import.py`

**Interfaces:**
- Produces: `main.MprisService` is the real class on Linux-with-dbus, otherwise `None`; startup block starts MPRIS only when non-None. No other module imports `main`, so both branches are compile-time safe.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_import.py
def test_main_imports_without_linux_backends():
    import main
    assert main.MprisService is None or hasattr(main.MprisService, "start")
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_main_import.py -q` → `ImportError` (`No module named 'dbus'`).
- [ ] **Step 3: Implement** —

```python
try:
    from mpris_dbus import MprisService
except Exception:
    MprisService = None
```

and in `__main__`: `if MprisService is not None: try/except-start` (preserving the existing try/except around start, moving import-only failure to silence).
- [ ] **Step 4: Run to verify it passes** — plus `test_player_constructs_offscreen` from Task 2 becomes a full-construct smoke (UI built offscreen).
- [ ] **Step 5: Commit** — `fix: tolerate missing dbus/gi so Windows can import main`

### Task 4: closeEvent web-server stop (AttributeError)

**Files:**
- Modify: `player.py:2230-2232` (delete the redundant block calling nonexistent `shutdown()` — the real `stop()` call already happens at `player.py:2213-2214`)
- Modify: `web_control.py` (`stop()` gains real best-effort shutdown + thread join)
- Create: `tests/test_close.py`

**Interfaces:**
- Consumes: `WebControlServer` attributes `self.socketio`, `self.thread`.
- Produces: `WebControlServer.stop()` — idempotent (safe to call twice), safe from any thread, joins its server thread (≤2 s) if the join target is not the calling thread, best-effort `self.socketio.shutdown()` swallowing `Exception`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_close.py
def test_close_event_runs_without_exceptions(qtbot):
    from player import MusicPlayer
    mp = MusicPlayer()
    qtbot.addWidget(mp)
    mp.start_web_server_if_enabled() if hasattr(mp, "start_web_server_if_enabled") else None  # read-first: locate actual enable path via grep "WebControlServer(" before writing
    mp.close()  #ucceeded only if closeEvent raises never
```

(Action: figure out where the server gets enabled at startup (`player.py:254-255` per review) and force-enable it in test before close.)

- [ ] **Step 2: Run to verify failure** — AttributeError inside closeEvent.
- [ ] **Step 3: Implement** — delete `player.py:2230-2232`; implement `stop()` per Interfaces.
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `fix: remove closeEvent shutdown() call that raised AttributeError`

### Task 5: Add-Cloud flow (Done button, no ghost `get_data`, no double-append)

**Files:**
- Modify: `player.py:42-98` (`CloudAccountsDialog`: add a `Done` QDialogButtonBox -> `accept`)
- Modify: `player.py:1965-1980` (`MusicPlayer.add_cloud`)
- Create: `tests/test_cloud_flow.py`

**Interfaces:**
- Produces: contract — `MusicPlayer.add_cloud()`: open `CloudAccountsDialog(self, self.clouds)`; `exec()`; if the serialized clouds snapshot changed after close → `save_clouds()` then `update_library_tree()`. Mutations happen solely via the dialog's in-place edits on the shared list; `MusicPlayer` never appends its own entries.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cloud_flow.py
from PySide6.QtWidgets import QDialog

class _StubDialog(QDialog):  # kills three birds: mutates shared list, no get_data, accept-close
    def __init__(self, parent, clouds):
        super().__init__(parent)
        self._clouds = clouds
    def exec(self):
        self._clouds.append({"type": "webdav", "name": "T", "config": {},
                             "files": [], "last_sync": "Never"})
        return QDialog.Accepted

def test_add_cloud_saves_once_without_double_append(qtbot, monkeypatch):
    import player as player_mod
    monkeypatch.setattr(player_mod, "CloudAccountsDialog", _StubDialog)
    mp = player_mod.MusicPlayer()
    qtbot.addWidget(mp)
    saved = []
    monkeypatch.setattr(mp, "save_clouds", lambda: saved.append("x") or None)
    mp.clouds.clear()
    mp.add_cloud()
    assert len(mp.clouds) == 1
    assert len(saved) == 1
```

- [ ] **Step 2: Run to verify failure** — AttributeError at `dlg.get_data()` (or double-append when stubbed without the guard) — either way the flow is broken today.
- [ ] **Step 3: Implement** — dialog gets `QDialogButtonBox(QDialogButtonBox.Ok)` labeled Done wired to `accept`; `add_cloud` becomes:

```python
def add_cloud(self):
    """Add or manage cloud storage accounts."""
    dlg = CloudAccountsDialog(self, self.clouds)
    snapshot = sorted((c.get("name", ""), c.get("type", "")) for c in self.clouds)
    dlg.exec()
    if sorted((c.get("name", ""), c.get("type", "")) for c in self.clouds) != snapshot:
        self.save_clouds()
        self.update_library_tree()
```

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `fix: Done button for CloudAccountsDialog; add_cloud saves changed clouds exactly once`

### Task 6: Playlist helpers (duplicate method shadow + TypeError call-site)

**Files:**
- Modify: `player.py:2499-2516` (delete the second `add_file_to_specific_playlist`; keep the first at 2447-2474)
- Modify: `player.py:~2318` — **read-first mandate:** read `player.py:2300-2340` and its helper `add_file_to_playlist(self, data)` (2428) before choosing the correction (likely `add_file_to_specific_playlist(playlist_obj, item_data)` or dropping an extraneous arg)
- Create: `tests/test_playlist_helpers.py`

**Interfaces:**
- Produces: exactly one `add_file_to_specific_playlist(self, playlist, data)` (the 2447 variant, which never clobbers `self.playlist`); all call sites compile to either `add_file_to_playlist(data)` or `add_file_to_specific_playlist(playlist, data)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_playlist_helpers.py
import ast, pathlib

def test_no_duplicate_method_names_in_musicplayer():
    tree = ast.parse(pathlib.Path("player.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MusicPlayer":
            names = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
            dupes = {n for n in names if names.count(n) > 1}
            assert not dupes, f"duplicate methods: {sorted(dupes)}"
```

plus behavioral test: monkeypatch `_add_file_to_playlist_internal` to return "TrackX" (and record calls with `update_ui` kwarg), call `add_file_to_specific_playlist(pl, data)`, assert `pl.items` gained the item and `mp.playlist` length unchanged.

- [ ] **Step 2: Run to verify failure** — duplicate detected.
- [ ] **Step 3: Implement** — delete the 2499 copy; fix the 2318-region call per read.
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `fix: drop shadowed add_file_to_specific_playlist copy; repair wrong-arg context-menu call`

### Task 7: Platform-safe folder open + tray QInputDialog

**Files:**
- Modify: `utils.py` (append `open_folder`)
- Modify: `player.py:916` and `tray.py:221` (call `utils.open_folder`)
- Modify: `tray.py` (import `QInputDialog` from QtWidgets; fix `self.app.QInputDialog.getText` → imported name)
- Create: `tests/test_platform_open.py`

**Interfaces:**
- Produces: `utils.open_folder(path) -> None`, never raises: Windows `os.startfile(str(path))`; macOS `subprocess.Popen(["open", str(path)])`; else `subprocess.Popen(["xdg-open", str(path)])`; any exception swallowed after a `print`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_platform_open.py
def test_open_folder_uses_right_backend(monkeypatch, tmp_path):
    import utils
    called = {}
    monkeypatch.setattr(os, "startfile", lambda p: called.setdefault("startfile", p) or None, raising=False)
    utils.open_folder(tmp_path)
    assert "startfile" in called  # on Windows CI/user machine
```

(macOS/xdg branches verified via monkeypatching `utils.subprocess.Popen` in companion tests marked skip-if-not-applicable — keep them in the same file, `skipif` on platform.)

- [ ] **Step 2: Run to verify failure** — AttributeError: no `open_folder`.
- [ ] **Step 3: Implement; update both call sites and the tray fix.**
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `fix: cross-platform folder-open and broken tray QInputDialog reference`

### Task 8: Atomic config saves + download timeout

**Files:**
- Modify: `utils.py` (append `atomic_write_text`)
- Modify: `player.py:2185-2208` (three `save_*` methods use it)
- Modify: `workers.py:26` (`requests.get(...)` gains `timeout=(10, 30)`)
- Create: `tests/test_atomic_save.py`

**Interfaces:**
- Produces: `utils.atomic_write_text(path: str, text: str) -> None` — writes `path.tmp`, `os.replace(path.tmp, path)`, cleans the tmp file on failure, re-raises hard failures.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_atomic_save.py
def test_write_and_no_leftovers(tmp_path):
    target = tmp_path / "clouds.json"
    utils.atomic_write_text(str(target), '{"a": 1}')
    assert target.read_text() == '{"a": 1}'
    assert [p.name for p in tmp_path.iterdir()] == ["clouds.json"]

def test_failed_replace_keeps_previous_file(tmp_path, monkeypatch):
    target = tmp_path / "playlists.json"
    target.write_text("OLD", encoding="utf-8")
    def boom(a): raise OSError("disk full")
    monkeypatch.setattr(utils.os, "replace", boom)
    with pytest.raises(OSError):
        utils.atomic_write_text(str(target), "NEW")
    assert target.read_text() == "OLD"
    assert list(tmp_path.glob('*.tmp')) == []
```

plus a source-grep test pinning `timeout=` inside `workers.py` `DownloadWorker.run`.

- [ ] **Step 2: Run to verify failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `fix: atomic JSON config writes and request timeout for downloads`

### Task 9: Web security (loopback default, token auth HTTP + Socket IO, locked CORS, hardened casts)

**Files:**
- Modify: `web_control.py` (default host `127.0.0.0.1`*, token, `@auth_required` wrapper on routes, connect-handler auth check, `cors_allowed_origins` from env `HICLOUDMP_WEB_ORIGINS` or same-origin, `_safe_int` helper)
- Modify: `player.py` (web settings: persist token QSettings key `web/token`, generated first enable with `secrets.token_hex(16)`; expose in Settings dialog near the web checkbox)
- Modify: `web_panel.html` (token transport: `#token` from URL is forbidden; use `localStorage` write + auto-inject via the "Open Web Panel" flow or query param consumed once — decide per read: read-first `web_control.py` top + `player.py:250-360` before editing)
- Create: `tests/test_web_security.py`

**Interfaces:**
- Produces:
  - HTTP: `Authorization: Bearer <token>` **or** `?token=<token>` → 401 otherwise.
  - Socket.IO: `ClientSDK send auth={"token": t}` — server disconnects unauthenticated connects.
  - `WebControlServer.token: str`; QSettings `web/token`.
  - `Host` is configurable via QSettings (`web/host`), default `127.0.0.1`.

- [ ] **Step 1: Write the failing tests** (Flask `test_client()` + `socketio.test_client(app)` — no real port bound):

```python
def test_routes_401_without_token(): ...
def test_routes_200_with_bearer_token(client_with_token): ...
def test_socket_connect_rejected_without_token(): ...
def test_socket_connect_ok_with_token(): ...
def test_socket_bad_payload_is_ignored(): ...   # emit set_volume "abc" → no reopened errors, server up
def test_cors_not_wildcard(): ...
def test_default_host_is_loopback(): ...
```

- [ ] **Step 2: Run to verify failures (currently everything is 200/no-auth).**
- [ ] **Step 3: Implement.** reach-through: read `web_control.py` fully (208 lines) before editing; change `player.py:344` to a configurable host default 127.0.0.1; keep dev-loop LAN workability documented in README note (Task 12).
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `feat: token auth for web panel, loopback default, locked CORS, hardened inputs`

### Task 10: Web panel JS correctness (`setSliderBG`, `userSeeking`)

**Files:**
- Modify: `web_panel.html:497-515`
- Create: `tests/test_web_assets.py`

**Interfaces:**
- Produces: zero references to undefined `setSliderBG` in the served file; `let userSeeking = false` declared (no implicit global); one `updateSliderBG(el)` helper defined if backgrounds still need painting.

- [ ] **Step 1: Write the failing test** — plain `regex` over `web_panel.html` bytes:

```python
def test_no_undefined_slider_helpers():
    html = pathlib.Path("web_panel.html").read_text(encoding="utf-8")
    uses = len(re.findall(r"setSliderBG\(", html))
    defines = len(re.findall(r"(function\s+setSliderBG|const\s+setSliderBG|let\s+setSliderBG)", html))
    assert uses <= defines, f"{uses} uses vs {defines} definitions"
    assert re.search(r"\b(let|var)\s+userSeeking\s*=", html)
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** — delete the three bare `setSliderBG()` calls (502/508/514) and replace with the existing styling mechanism visible in file (read around 460-520 first); declare `userSeeking`.
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `fix(web-panel): remove undefined setSliderBG calls, declare userSeeking`

### Task 11: Auto-advance survives a cloud-stream attempt

**Files:**
- Modify: `player.py:1368-1437` (`_play_stream` — targeted disconnect of stored stream handlers only; never blanket-disconnects `mediaStatusChanged`/`errorOccurred`)
- Create: `tests/test_stream_autosadvance.py`

**Interfaces:**
- Produces: `MusicPlayer` attributes `self._stream_status_handler = None`, `self._stream_error_handler = None` (init at `__init__`); `_play_stream` stores its new closures there and disconnects only those stored refs (guarded try/except).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stream_autosadvance.py
def test_end_of_media_advances_after_stream_attempt(qtbot, tmp_path, monkeypatch):
    mp = MusicPlayer(); qtbot.addWidget(mp)
    wav = _make_wav(tmp_path / "t1.wav", seconds=0.4)   # real wave-file bytes via `wave` module
    wav2 = _make_wav(tmp_path / "t2.wav", seconds=0.4)
    mp._play_stream(QUrl("http://127.0.0.1:9/404").toString(), "x")   # local, unreachable → retry path
    # wait until the first stream attempt settles (status invalid or retry scheduled)
    mp.playlist = [str(wav), str(wav2)]
    mp.play_index?  # read-first: actually available local-play entrypoint; or drive via mp.player.setSource(QUrl.fromLocalFile(wav)) + mp.player.play()
    qtbot.waitSignal(mp.player.mediaStatusChanged, timeout=15_000)  # whatever fires — then assert final state
    with qtbot.waitSignal(mp.player.mediaStatusChanged, timeout=15_000, check_params_cb=lambda status: status == QMediaPlayer.MediaStatus.EndOfMedia):
        pass
    assert mp.current_index == 1
```

(The concrete API names for local playback need a read-first pass: `play_index`, `play_downloaded_file` internals at `player.py:805-...` — the test must drive the real auto-advance code path, not reimplement it.)

- [ ] **Step 2: Run to verify failure** — pre-fix, after `_play_stream`, EndOfMedia does nothing (all slots disconnected) → `current_index == 0`.
- [ ] **Step 3: Implement** — targeted disconnect:

```python
if getattr(self, "_stream_status_handler", None) is not None:
    try:
        self.player.mediaStatusChanged.disconnect(self._stream_status_handler)
    except Exception:
        pass
self._stream_status_handler = handle_media_status
```

mirror for `errorOccurred` (replacing `player.py:1375-1382`).
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `fix: keep mediaStatusChanged/:errorOccurred subscriptions when streaming reconnect helpers churn`

### Task 12: Requirements hygiene + README + full gate + push

**Files:**
- Rename: `requiments.txt` → `requirements.txt` (runtime only — Flask family, requests, Pillow, mutagen, PySide6 with a ≥6.10 comment for Python 3.14, platformdirs)
- Create: `requirements-linux.txt` (PyGObject, pycairo, dbus-python + comment), `requirements-dev.txt` (pytest, pytest-qt, pywin32 with win-only note)
- Modify: `README.md` — install section: venv + `pip install -r requirements.txt` (+ Linux extras line), Python ≥3.12, PySide6 6.10.3 note for 3.14, web-panel token mention + loopback default, link to the review doc for deferred roadmap.

- [ ] **Step 1: Verify dead-dep claim** — `grep -ci python-vlc *.py` → zero hits.
- [ ] **Step 2: Write files.**
- [ ] **Step 3: Full gate** — `.venv\Scripts\python -m pytest tests\ -q` all green; fresh-interpreter `python -c "import main"` clean; manual interactive checklist (start app, add folder, play, web panel with token, close) with the human partner before push.
- [ ] **Step 4: Commit** — `chore: split requirements, drop dead python-vlc pin, document setup and web token`
- [ ] **Step 5: Push** — `git push origin main` (origin = PhantomPixelDev/HiCloudMP; pushing directly with the user's verified auth) only after full gate + manual check.

---

## Self-review notes

- Spec coverage: every showstopper 1-9 from the review doc maps to Tasks 2-5, 6(+7), 11, 9, 10. Security findings → Task 8 (timeout), 9 (auth/CORS/host). Atomicity → Task 8. Trailing quality items (theme centralization, big-file splits, model/view rewrite) are explicitly out of scope (next plan).
- Type consistency: `open_folder`/`atomic_write_text`/`token`/`_stream_status_handler`/`_stream_error_handler` used identically across tasks.
- Proportion: code blocks appear only for contracts the executor cannot infer (save-on-change logic, targeted-disconnect pattern, auth contract, helper behavior). Everything else is deletion plus a read-first mandate.
