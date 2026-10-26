"""Single-instance guard.

A second HiCloud MP launch must not open a second window fighting over
the same settings and playlist files. The lock is a QLocalServer named
pipe (Windows) - the OS tears the name down with the process, so a
crash can never leave a stale lock behind.

Detection is probe-first: Qt on Windows lets two servers listen on the
same name, but a client connect always routes to the first one. So
"can I connect?" is the reliable "is an instance already running?"
test; only when the probe fails with ServerNotFound do we take the name.
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

DEFAULT_LOCK_NAME = "HiCloudMP-single-instance"


class InstanceLock(QObject):
    """Owns the primary-instance name and reports activation pings."""

    activated = Signal()

    def __init__(self, name=DEFAULT_LOCK_NAME, parent=None):
        super().__init__(parent)
        self.name = name
        self._server = None

    # -- probing -----------------------------------------------------
    def is_running(self):
        """True when another instance already owns the name. Also pokes
        that instance so it can raise its window (second-launch UX)."""
        probe = QLocalSocket()
        probe.connectToServer(self.name)
        if probe.waitForConnected(300):
            try:
                probe.write(b"activate")
                probe.flush()
                probe.waitForBytesWritten(300)
            except Exception:
                pass
            probe.disconnectFromServer()
            return True
        try:
            probe.abort()
        except Exception:
            pass
        return False

    # -- acquiring ---------------------------------------------------
    def acquire(self):
        """Take the primary-instance name. False when another instance
        is already running (its window has been pinged)."""
        if self.is_running():
            return False
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self.name):
            # A leftover name from a killed process: clear and retry once.
            QLocalServer.removeServer(self.name)
            if not server.listen(self.name):
                server.deleteLater()
                return False
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def _on_new_connection(self):
        """A second launch connected: drain the socket and ask the app
        to show/raise its window."""
        try:
            while self._server.hasPendingConnections():
                sock = self._server.nextPendingConnection()
                if sock is None:
                    break
                try:
                    sock.readAll()
                except Exception:
                    pass
                try:
                    sock.disconnectFromServer()
                    sock.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.activated.emit()
        except Exception:
            pass

    def release(self):
        if self._server is not None:
            try:
                self._server.close()
                self._server.deleteLater()
            except Exception:
                pass
            self._server = None
        try:
            QLocalServer.removeServer(self.name)
        except Exception:
            pass
