"""Process-exit guard for retained QThreads.

Root cause of the 0xC0000409 fatal at app close: Python interpreter
finalization clears the module-global retention lists (_ORPHAN_THREADS /
_ORPHAN_QTHREADS) while a retired, uninterruptibly-blocked QThread is
still running - the pair's last Python reference drops, C++ ~QThread()
sees running==true and calls qFatal, which fastfails the whole process.

atexit handlers run BEFORE module globals are cleared (proven in the
crash investigation), so each owner module registers a guard here over
its own retention lists: near-finished threads get a bounded wait to
complete; if any thread is still unstoppable at exit, the process
hard-exits 0 (os._exit) so the OS reclaims the running threads and
teardown never destroys a live QThread.
"""
import atexit
import os


def pair_is_running(pair):
    try:
        thread = pair[0]
        return bool(thread is not None and thread.isRunning())
    except RuntimeError:
        return False  # underlying C++ object already gone
    except Exception:
        return False


def register_exit_guard(get_retained_pairs, wait_ms=1000):
    """Register an atexit guard over the lists returned by
    ``get_retained_pairs()``. Multiple registrations are fine: each guard
    only inspects its own lists and acts only when something still runs."""

    def _exit_guard():
        try:
            pairs = [p for p in list(get_retained_pairs() or [])
                     if pair_is_running(p)]
        except Exception:
            return
        if not pairs:
            return
        for pair in pairs:
            try:
                pair[0].wait(wait_ms)
            except Exception:
                pass
        if any(pair_is_running(pair) for pair in pairs):
            # Teardown is about to reach these references. Let the OS
            # reclaim the running threads instead of destroying them.
            os._exit(0)

    atexit.register(_exit_guard)
