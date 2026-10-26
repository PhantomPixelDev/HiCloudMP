"""Regression tests for the QThread-destroyed-while-running abort crash.

Crash signature (user sessions, Oct 18): exit code 0xC0000409
(STATUS_STACK_BUFFER_OVERRUN). Minidump forensics showed the fault inside
QtCore's qAbort() reached from QMessageLogger::fatal, with the return address
inside QThread::~QThread(). The fatal message is::

    QThread: Destroyed while thread '%ls' is still running

Producer: replacing (or clearing) the last Python reference to a QThread
object whose thread is still running makes PySide destroy the C++ QThread;
~QThread() then calls qFatal(), which fastfails the whole process.

Three production sites could drop a still-running thread reference:
  * MusicPlayer._download_and_play() started a new download while the
    previous DownloadWorker/thread was still running (cloud tracks),
  * MusicPlayer.scan_clouds() reset self.scan_threads/self.scan_workers while
    a previous scan was still running,
  * MetadataController stop()/teardown of a cover-art thread that is still
    running (and its stale _cleanup handler could delete a NEWER thread).

The contract pinned here: references to a running QThread are RETIRED (kept
alive until the thread actually finishes) and completion handlers act on
THEIR OWN thread/worker, never on a newer one.

NOTE: on the unfixed code the in-process tests below would abort the entire
pytest process with 0xC0000409, which is why the end-to-end scenario runs in
a subprocess (tests/_qthread_crash_child.py).
"""

import gc
import os
import subprocess
import sys
import time
import weakref
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from hicloudmp.ui import player as player_mod

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _SleepyDownloadWorker(QObject):
    """DownloadWorker stand-in: pseudo-work in small polling steps so abort()
    lets run() return promptly, while still outliving the replacement steps."""

    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int)

    delay = 3.0  # seconds of pseudo-download work

    def __init__(self, url, path, auth=None):
        super().__init__()
        self.path = path
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        deadline = time.monotonic() + type(self).delay
        while time.monotonic() < deadline:
            if self._abort:
                return
            time.sleep(0.05)
        self.finished.emit(self.path)


class _SleepyScanWorker(QObject):
    """ScanCloudWorker stand-in: run() outlives the first test steps."""

    progress_updated = Signal(int, str, str)
    scan_finished = Signal(int, list)
    scan_error = Signal(int, str)

    def __init__(self, cloud_index, cloud_data):
        super().__init__()
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if self._abort:
                return
            time.sleep(0.05)
        self.scan_finished.emit(0, [])


class _RecordingThread(QThread):
    """QThread that counts Python-side quit()/wait() calls, so a stale handler
    touching the WRONG thread is detectable even when the wrong-thread effects
    would otherwise be invisible (the thread stops soon anyway)."""

    def __init__(self):
        super().__init__()
        self.quit_calls = 0
        self.wait_calls = 0

    def quit(self):
        self.quit_calls += 1
        super().quit()

    def wait(self, *args, **kwargs):
        self.wait_calls += 1
        return super().wait(*args, **kwargs)


def _no_dialogs(monkeypatch):
    class _Box:
        @staticmethod
        def warning(*a, **k):
            return None

        @staticmethod
        def critical(*a, **k):
            return None

        @staticmethod
        def information(*a, **k):
            return None

    monkeypatch.setattr(player_mod, "QMessageBox", _Box)


# ---------------------------------------------------------------------------
# end-to-end: the exact user-facing sequence must not abort the process
# ---------------------------------------------------------------------------

def test_download_replace_while_running_survives_subprocess():
    """Replacing an in-flight cloud download must not fastfail the process.

    Runs in a CHILD process: on the old code the child dies with exit code
    0xC0000409 (STATUS_STACK_BUFFER_OVERRUN), which would take the whole
    pytest process with it if run in-process.
    """
    child = Path(__file__).parent / "_qthread_crash_child.py"
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, str(child)],
        capture_output=True, text=True, timeout=240, env=env, cwd=str(ROOT),
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        "child died: exit={} (0x{:08X})\n{}".format(
            proc.returncode, proc.returncode & 0xFFFFFFFF, out)
    )
    assert "SURVIVED" in out, out


def test_retired_running_thread_survives_interpreter_teardown():
    """The 0xC0000409 fatal AT PROCESS EXIT: interpreter finalization clears
    the module-global retention lists (_ORPHAN_THREADS / _ORPHAN_QTHREADS)
    while a retired, uninterruptibly-blocked thread still runs; the pair's
    last reference drops -> C++ ~QThread -> qFatal -> fastfail. Pinned
    contract: a registered exit guard (runs before module globals are
    cleared) lets near-finished threads complete and hard-exits 0 while any
    retained thread still runs, so teardown can never destroy a live QThread."""
    child = Path(__file__).parent / "_qthread_teardown_child.py"
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, str(child)],
        capture_output=True, text=True, timeout=240, env=env, cwd=str(ROOT),
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        "child died: exit={} (0x{:08X})\n{}".format(
            proc.returncode, proc.returncode & 0xFFFFFFFF, out)
    )
    assert "orphans=1" in out, out


# ---------------------------------------------------------------------------
# in-process lifecycle contract
# ---------------------------------------------------------------------------

def test_download_replacement_retires_old_thread_and_starts_new(music_player, monkeypatch, qtbot):
    """Starting a new download while the previous one still runs must keep the
    old thread referenced (retire it) and quit/wait only the OLD thread -
    never the new download's thread."""
    mp = music_player
    _no_dialogs(monkeypatch)
    monkeypatch.setattr(player_mod, "QThread", _RecordingThread)
    monkeypatch.setattr(player_mod, "DownloadWorker", _SleepyDownloadWorker)
    monkeypatch.setattr(mp, "play_downloaded_file", lambda path: None)

    mp._download_and_play("http://x/one.mp3", "webdav", {}, "one.mp3")
    qtbot.waitUntil(lambda: mp.download_thread.isRunning(), timeout=3000)
    thread1 = mp.download_thread
    ref = weakref.ref(thread1)

    # Replace while the first download's thread is still running.
    mp._download_and_play("http://x/two.mp3", "webdav", {}, "two.mp3")
    thread2 = mp.download_thread
    assert thread2 is not thread1
    assert thread1.quit_calls == 1, "replacement must quit the OLD thread"
    assert thread2.quit_calls == 0 and thread2.wait_calls == 0, (
        "replacement must never touch the NEW download's thread"
    )
    assert any(t is thread1 for t, _w in mp._retired_qthreads), (
        "replaced running thread must be on the retire list"
    )

    # Dropping the test's own reference must NOT destroy the running QThread.
    del thread1
    gc.collect()
    assert ref() is not None

    # The retired thread stops (its worker polls the abort flag) and is
    # released from the retire list.
    qtbot.waitUntil(
        lambda: not any(t is ref() for t, _w in mp._retired_qthreads),
        timeout=8000,
    )

    # The new download is unaffected.
    assert mp.download_thread is thread2
    assert thread2.quit_calls == 0 and thread2.wait_calls == 0
    assert thread2.isRunning()

    # Cleanup: end the second download's thread deterministically.
    thread2.quit()
    qtbot.waitUntil(lambda: not thread2.isRunning(), timeout=8000)


def test_scan_restart_keeps_running_threads_alive(music_player, monkeypatch, qtbot):
    """Re-scanning while the previous scan still runs must not destroy the
    old QThreads (menu action bypasses the disabled button)."""
    mp = music_player
    _no_dialogs(monkeypatch)
    monkeypatch.setattr(player_mod, "ScanCloudWorker", _SleepyScanWorker)
    monkeypatch.setattr(mp, "save_clouds", lambda: None)
    monkeypatch.setattr(mp, "update_library_tree", lambda: None)
    mp.clouds = [{"name": "cli", "type": "subsonic", "config": {}, "files": []}]

    mp.scan_clouds()
    qtbot.waitUntil(
        lambda: mp.scan_threads and mp.scan_threads[0].isRunning(), timeout=3000
    )
    first = mp.scan_threads[0]
    ref = weakref.ref(first)

    mp.scan_clouds()  # re-scan while the first is still running
    assert mp.scan_threads and mp.scan_threads[0] is not first
    assert any(t is first for t, _w in mp._retired_qthreads), (
        "replaced running scan thread must be on the retire list"
    )

    del first
    gc.collect()
    assert ref() is not None  # kept alive by the retire list while it stops

    qtbot.waitUntil(
        lambda: not any(t is ref() for t, _w in mp._retired_qthreads),
        timeout=8000,
    )


def test_metadata_stop_detaches_running_cover_thread(music_player, monkeypatch, qtbot):
    """stop() must never leave a RUNNING cover thread destructible by widget
    teardown; it detaches and keeps a reference until the worker finishes."""
    import threading

    from hicloudmp.core import metadata as md_mod

    extraction_started = threading.Event()

    class _SlowExtractor:
        @staticmethod
        def extract_cover(source, is_url=False):
            extraction_started.set()
            time.sleep(1.5)
            return None

    monkeypatch.setattr(md_mod, "CoverExtractor", _SlowExtractor)
    mp = music_player

    mp.meta._start_cover_art_fetch("coversrc", False)
    thread = mp.meta._cover_thread
    assert thread is not None
    # Wait until the worker is provably inside the (uninterruptible)
    # extraction, so abort() cannot make run() return during stop()'s wait.
    qtbot.waitUntil(extraction_started.is_set, timeout=3000)
    assert thread.isRunning()

    mp.meta.stop()

    # Extraction cannot be interrupted; the thread lives on, but it must be
    # detached from the widget tree so teardown can never destroy it.
    assert thread.isRunning()
    assert thread.parent() is None

    # Its cleanup releases the tracker when the fetch actually finishes.
    # (The QThread wrapper itself is deleteLater'd by _cleanup, so poll the
    # controller's state instead of touching the deleted C++ object.)
    qtbot.waitUntil(lambda: mp.meta._cover_thread is None, timeout=8000)


def test_cover_fetch_sequencing_tracks_refs(music_player, monkeypatch, qtbot):
    """Sequential cover fetches must each clean up their own thread/worker and
    never clobber the newer fetch's state (identity-guarded _cleanup)."""
    from hicloudmp.core import metadata as md_mod

    class _SlowExtractor:
        @staticmethod
        def extract_cover(source, is_url=False):
            time.sleep(0.4)
            return None

    monkeypatch.setattr(md_mod, "CoverExtractor", _SlowExtractor)
    mp = music_player

    mp.meta._start_cover_art_fetch("first", False)
    qtbot.waitUntil(
        lambda: mp.meta._cover_thread is not None and mp.meta._cover_thread.isRunning(),
        timeout=3000,
    )

    # The first fetch must finish and release its refs cleanly.
    qtbot.waitUntil(lambda: mp.meta._cover_thread is None, timeout=8000)

    # A second fetch starts fresh and completes normally.
    mp.meta._start_cover_art_fetch("second", False)
    second_thread = mp.meta._cover_thread
    assert second_thread is not None
    qtbot.waitUntil(lambda: second_thread.isRunning(), timeout=3000)
    qtbot.waitUntil(lambda: mp.meta._cover_thread is None, timeout=8000)


def test_cover_application_marshals_to_ui_thread(music_player, monkeypatch, qtbot):
    """Cover results must be APPLIED on the UI thread.

    The worker.finished connection is a plain Python callable, so PySide runs
    it in the emitting (cover QThread) context.  Touching QPixmap/widgets from
    there corrupts Qt state and later kills the process with an access
    violation (0xC0000005) while the UI thread processes events.
    """
    import threading

    from hicloudmp.core import metadata as md_mod

    class _SlowExtractor:
        @staticmethod
        def extract_cover(source, is_url=False):
            time.sleep(0.2)
            return None

    monkeypatch.setattr(md_mod, "CoverExtractor", _SlowExtractor)
    mp = music_player

    names = []
    real = mp.meta.set_default_cover

    def record():
        names.append(threading.current_thread().name)
        real()

    monkeypatch.setattr(mp.meta, "set_default_cover", record)

    mp.meta._start_cover_art_fetch("threadcheck", False)
    qtbot.waitUntil(lambda: mp.meta._cover_thread is None, timeout=8000)
    qtbot.waitUntil(lambda: bool(names), timeout=8000)

    assert all(name == "MainThread" for name in names), (
        "cover application must run on the UI thread, got threads: %r" % (names,)
    )


def test_pending_cover_restart_runs_after_replacement(music_player, monkeypatch, qtbot):
    """A fetch requested while another is still running must run next.

    _cleanup may execute on the cover QThread whose event loop is already
    gone; a QTimer created there never fires, so the pending restart has to be
    marshalled to the UI thread.
    """
    from hicloudmp.core import metadata as md_mod

    started = []

    class _Extractor:
        @staticmethod
        def extract_cover(source, is_url=False):
            started.append(source)
            time.sleep(0.3)
            return None

    monkeypatch.setattr(md_mod, "CoverExtractor", _Extractor)
    mp = music_player

    mp.meta._start_cover_art_fetch("first", False)
    qtbot.waitUntil(lambda: "first" in started, timeout=3000)

    # Requested while the first fetch still runs: queued as the pending fetch.
    mp.meta._start_cover_art_fetch("second", False)
    assert mp.meta._pending_cover is not None

    # Once the first thread finishes, the pending fetch must actually run.
    qtbot.waitUntil(lambda: "second" in started, timeout=8000)
    qtbot.waitUntil(lambda: mp.meta._cover_thread is None, timeout=8000)


# ---------------------------------------------------------------------------
# worker -> UI marshalling: status bar and friends
# ---------------------------------------------------------------------------

class _QuickDownloadWorker(QObject):
    """DownloadWorker stand-in that finishes (or fails) in ~0.1 s."""

    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int)

    fail = False  # set True on subclasses to emit error() instead

    def __init__(self, url, path, auth=None):
        super().__init__()
        self.path = path
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline:
            if self._abort:
                return
            time.sleep(0.01)
        self.progress.emit(100)
        if type(self).fail:
            self.error.emit("boom")
        else:
            self.finished.emit(self.path)


class _FailingDownloadWorker(_QuickDownloadWorker):
    fail = True


def _arm_status_message_timer(mp):
    """Arm a RUNNING 5 s status message timer (the deletion target).

    QStatusBar creates this QTimer lazily on the first timed showMessage().
    The timeout-less showMessage() calls in the download completion handlers
    delete it right where they run; Qt only warns when that happens off the
    UI thread and skips the timer deregistration, leaving a stale 5 s timer
    registration in the main dispatcher.

    Must be called AFTER _download_and_play() starts: its "Downloading: …"
    message uses the timeout-less path too and would delete a pre-armed
    timer (on the UI thread, cleanly).
    """
    mp.status_bar.showMessage("hold", 5000)


def test_download_completion_marshals_status_update_to_ui_thread(music_player, monkeypatch, qtbot):
    """Download completion must touch Qt objects only on the UI thread.

    on_finished is a plain-callable connection, so PySide runs it inside the
    download QThread.  QStatusBar.showMessage(msg) with NO timeout deletes the
    status bar's running message QTimer right there; destroying a running
    main-thread-affine QTimer from a foreign thread makes ~QObject skip the
    timer deregistration (it only warns), leaving a stale timer in the main
    dispatcher whose next fire sends a QTimerEvent to freed memory
    (0xC0000005) while the UI thread pumps events.
    """
    import threading

    from PySide6.QtCore import qInstallMessageHandler

    mp = music_player
    _no_dialogs(monkeypatch)

    threads = []
    monkeypatch.setattr(player_mod, "DownloadWorker", _QuickDownloadWorker)
    monkeypatch.setattr(
        mp, "play_downloaded_file",
        lambda path: threads.append(threading.current_thread().name),
    )

    messages = []
    previous = qInstallMessageHandler(lambda mode, ctx, msg: messages.append(msg))
    try:
        mp._download_and_play("http://x/one.mp3", "webdav", {}, "one.mp3")

        # Arm the trap AFTER the download starts: the "Downloading: …"
        # message itself uses the timeout-less showMessage() path and would
        # delete a pre-armed timer on the UI thread (cleanly - no bug).
        _arm_status_message_timer(mp)

        def completed():
            return bool(threads) and "Download complete" in mp.status_bar.currentMessage()

        qtbot.waitUntil(completed, timeout=8000)
    finally:
        qInstallMessageHandler(previous)

    assert all(name == "MainThread" for name in threads), threads
    offenders = [m for m in messages if "another thread" in m]
    assert not offenders, (
        "download completion touched Qt objects from a worker thread: %r" % (offenders,)
    )


def test_download_error_marshals_status_update_to_ui_thread(music_player, monkeypatch, qtbot):
    """Download failure handling (status bar, error dialog, stream fallback)
    must run on the UI thread, not inside the download QThread."""
    import threading

    from PySide6.QtCore import qInstallMessageHandler

    mp = music_player
    _no_dialogs(monkeypatch)

    threads = []
    monkeypatch.setattr(player_mod, "DownloadWorker", _FailingDownloadWorker)
    monkeypatch.setattr(
        mp, "_play_stream",
        lambda url, name: threads.append(threading.current_thread().name),
    )

    messages = []
    previous = qInstallMessageHandler(lambda mode, ctx, msg: messages.append(msg))
    try:
        mp._download_and_play("http://x/one.mp3", "webdav", {}, "one.mp3")

        # Arm the trap AFTER the download starts (see the completed test).
        _arm_status_message_timer(mp)

        def failed():
            return bool(threads) and "Download failed" in mp.status_bar.currentMessage()

        qtbot.waitUntil(failed, timeout=8000)
    finally:
        qInstallMessageHandler(previous)

    assert all(name == "MainThread" for name in threads), threads
    offenders = [m for m in messages if "another thread" in m]
    assert not offenders, (
        "download failure handling touched Qt objects from a worker thread: %r"
        % (offenders,)
    )
