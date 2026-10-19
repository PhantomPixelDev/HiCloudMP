"""Cloud scan threads were only dropped from the scan lists, leaving their
QThread wrappers to be destroyed by Python at an arbitrary moment (queued
signals may still be delivered). Finished threads are now deleteLater()'d,
with the wrapper kept alive until Qt confirms the C++ object is gone.
Running threads still get the existing retire path and a 100 ms recheck.
"""
import pytest

import player as player_mod


class _Destroyed:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def emit(self):
        for fn in list(self.slots):
            fn(None)


class _FakeThread:
    def __init__(self, running=False):
        self.running = running
        self.deleted = 0
        self.destroyed = _Destroyed()

    def isRunning(self):
        return self.running

    def deleteLater(self):
        self.deleted += 1


def _set_scan_state(mp, thread):
    mp.scan_threads = [thread]
    mp.scan_workers = [object()]
    mp._scan_errors = []


def test_completed_threads_are_deleted_and_held_until_destroyed(music_player):
    mp = music_player
    thread = _FakeThread(running=False)
    _set_scan_state(mp, thread)

    mp._check_all_scans_complete()

    assert thread.deleted == 1
    assert mp.scan_threads == [] and mp.scan_workers == []
    assert any(pair[0] is thread for pair in mp._retired_qthreads), \
        "the wrapper must outlive deleteLater"

    thread.destroyed.emit()

    assert not any(pair[0] is thread for pair in mp._retired_qthreads)


def test_running_threads_are_kept_and_rechecked(music_player, monkeypatch):
    mp = music_player
    thread = _FakeThread(running=True)
    _set_scan_state(mp, thread)
    calls = []

    class _TimerSpy:
        @staticmethod
        def singleShot(ms, fn):
            calls.append((ms, fn))

    monkeypatch.setattr(player_mod, "QTimer", _TimerSpy)
    mp.scan_cloud_btn.setEnabled(False)

    mp._check_all_scans_complete()

    assert thread.deleted == 0
    assert mp.scan_threads == [thread]
    assert calls and calls[0][0] == 100
    assert not mp.scan_cloud_btn.isEnabled(), "still scanning"


def test_dispose_helper_is_idempotent(music_player):
    mp = music_player
    thread = _FakeThread(running=False)

    mp._dispose_finished_scan_threads([thread])
    mp._dispose_finished_scan_threads([thread])

    assert thread.deleted == 2
    pairs = [p for p in mp._retired_qthreads if p[0] is thread]
    assert len(pairs) == 1, "one retained wrapper per thread"


def test_real_finished_qthread_survives_delete_later(music_player, qtbot):
    from PySide6.QtCore import QThread

    mp = music_player

    class _QuickThread(QThread):
        def run(self):   # returns immediately: no event loop to quit
            return

    thread = _QuickThread()
    thread.start()
    assert thread.wait(2000)
    _set_scan_state(mp, thread)
    mp.scan_cloud_btn.setEnabled(False)

    mp._check_all_scans_complete()

    assert mp.scan_threads == []
    qtbot.waitUntil(
        lambda: not any(p[0] is thread
                        for p in getattr(mp, "_retired_qthreads", [])),
        timeout=2000)
    with pytest.raises(RuntimeError):
        thread.isRunning()   # the C++ object is gone
