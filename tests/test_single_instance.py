"""Single-instance guard: a second launch must not open a second window
fighting over the same settings/playlist files. Uses QLocalServer (named
pipe on Windows): the OS tears the name down with the process, so a
crash cannot leave a stale lock behind.

Detection is probe-first because Qt on Windows happily lets two servers
listen on one name - a client connect, however, always reaches the
first server. So "can I connect?" is the only reliable running test.
"""
import os

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def _name(suffix):
    return f"HiCloudMP-test-{os.getpid()}-{suffix}"


def _pump(pred, timeout_ms=3000):
    """Spin the Qt event loop until pred() or the budget runs out."""
    import time
    waited = 0
    while waited < timeout_ms:
        QCoreApplication.processEvents()
        if pred():
            return True
        time.sleep(0.01)
        waited += 10
    return False


def test_probe_detects_running_instance():
    from hicloudmp.core.single_instance import InstanceLock

    name = _name("a")
    primary = InstanceLock(name)
    assert primary.acquire() is True
    try:
        second = InstanceLock(name)
        assert second.is_running(), \
            "a live instance must be detectable before acquiring"
        assert second.acquire() is False, \
            "a second instance must not take the same lock"
    finally:
        primary.release()
        QLocalServer.removeServer(name)


def test_second_launch_activates_running_window(qapp):
    from hicloudmp.core.single_instance import InstanceLock

    name = _name("b")
    lock = InstanceLock(name)
    assert lock.acquire() is True
    try:
        activated = []
        lock.activated.connect(lambda: activated.append(True))

        client = QLocalSocket()
        client.connectToServer(name)
        assert client.waitForConnected(2000)
        client.write(b"activate")
        client.flush()
        client.waitForBytesWritten(2000)

        assert _pump(lambda: bool(activated)), \
            "a second launch must activate the running window"
    finally:
        lock.release()
        QLocalServer.removeServer(name)


def test_release_allows_reaquisition():
    from hicloudmp.core.single_instance import InstanceLock

    name = _name("c")
    first = InstanceLock(name)
    assert first.acquire()
    first.release()

    second = InstanceLock(name)
    assert second.acquire(), "after release the name is free again"
    second.release()
    QLocalServer.removeServer(name)
