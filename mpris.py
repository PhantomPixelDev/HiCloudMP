from PySide6.QtCore import QObject, Slot, Property, QByteArray, QTimer
from PySide6.QtDBus import (
    QDBusAbstractAdaptor,
    QDBusConnection,
    QDBusMessage,
    QDBusObjectPath,
)
import os

MPRIS_PATH = "/org/mpris/MediaPlayer2"
# Prefer lowercase per MPRIS recommendation; we'll attempt both
MPRIS_SERVICE_PRIMARY = "org.mpris.MediaPlayer2.hicloudmp"
MPRIS_SERVICE_ALT = "org.mpris.MediaPlayer2.HiCloudMP"
IFACE_ROOT = "org.mpris.MediaPlayer2"
IFACE_PLAYER = "org.mpris.MediaPlayer2.Player"


class _MprisRootAdaptor(QDBusAbstractAdaptor):
    # Declare D-Bus interface for adaptor
    Q_CLASSINFO = [("D-Bus Interface", IFACE_ROOT)]
    """
    org.mpris.MediaPlayer2 root interface adaptor
    """

    def __init__(self, parent, app_identity: str = "HiCloud MP"):
        super().__init__(parent)
        self._identity = app_identity

    # Interface name (helper)
    def interface(self) -> str:
        return IFACE_ROOT

    @Property(bool, constant=True)
    def CanQuit(self) -> bool:  # noqa: N802 (DBus property name)
        return True

    @Property(bool, constant=True)
    def CanRaise(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def HasTrackList(self) -> bool:  # noqa: N802
        return False

    @Property(str, constant=True)
    def Identity(self) -> str:  # noqa: N802
        return self._identity

    @Property('QStringList', constant=True)
    def SupportedUriSchemes(self):  # noqa: N802
        return ["file"]

    @Property('QStringList', constant=True)
    def SupportedMimeTypes(self):  # noqa: N802
        return [
            "audio/mpeg", "audio/flac", "audio/ogg", "audio/x-wav", "audio/aac",
        ]

    @Property(str, constant=True)
    def DesktopEntry(self) -> str:  # noqa: N802
        # If you have a HiCloudMP.desktop installed, set its basename without extension
        return "HiCloudMP"

    @Slot()
    def Raise(self):
        # Show and raise the main window
        try:
            w = self.parent().parent()
            if hasattr(w, 'showNormal'):
                w.showNormal()
            if hasattr(w, 'raise_'):
                w.raise_()
            if hasattr(w, 'activateWindow'):
                w.activateWindow()
        except Exception:
            pass

    @Slot()
    def Quit(self):
        # Ask the application to quit
        self.parent().close()


class _MprisPlayerAdaptor(QDBusAbstractAdaptor):
    # Declare D-Bus interface for adaptor
    Q_CLASSINFO = [("D-Bus Interface", IFACE_PLAYER)]
    """
    org.mpris.MediaPlayer2.Player interface adaptor
    """

    def __init__(self, parent, player_obj, app_window):
        super().__init__(parent)
        # Reference to the actual application window (for UI methods/state)
        self._app = app_window
        self._player = player_obj  # QMediaPlayer
        # Periodically emit Seeked to keep some clients updated with position
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._emit_seeked)
        self._timer.start()

        # Hook into state changes to notify clients via PropertiesChanged
        try:
            self._player.playbackStateChanged.connect(self._emit_props_changed)
            self._player.mediaStatusChanged.connect(self._emit_props_changed)
            self._player.durationChanged.connect(self._emit_props_changed)
            self._player.positionChanged.connect(self._maybe_emit_seeked)
        except Exception:
            # Older PySide6 may have slightly different signals; ignore if missing
            pass

    # Interface name
    def interface(self) -> str:
        return IFACE_PLAYER

    # ----- Properties -----
    @Property(str)
    def PlaybackStatus(self) -> str:  # noqa: N802
        state = getattr(self._player, 'playbackState', None)
        if callable(state):
            st = self._player.playbackState()
        else:
            # Fallback using mediaStatus if older API
            st = getattr(self._player, 'playbackState', 0)
        # QMediaPlayer.PlaybackState.{StoppedState=0, PlayingState=1, PausedState=2}
        if st == 1:
            return "Playing"
        if st == 2:
            return "Paused"
        return "Stopped"

    @Property(str)
    def LoopStatus(self) -> str:  # noqa: N802
        # Use the repeat button state if present
        repeat = getattr(self._app, 'repeat_btn', None)
        if repeat and repeat.isChecked():
            return "Track"
        return "None"

    @Property(float)
    def Rate(self) -> float:  # noqa: N802
        return 1.0

    @Property(bool)
    def Shuffle(self) -> bool:  # noqa: N802
        shuffle = getattr(self._app, 'shuffle_btn', None)
        return bool(shuffle and shuffle.isChecked())

    @Property('QVariantMap')
    def Metadata(self):  # noqa: N802
        meta = {}
        # Track ID must be a D-Bus object path and unique per track
        track_id = "/org/mpris/MediaPlayer2/track/{}".format(self._app.current_index if hasattr(self._app, 'current_index') else 0)
        meta["mpris:trackid"] = QDBusObjectPath(track_id)
        # Length in microseconds
        duration_ms = int(getattr(self._player, 'duration', lambda: 0)() or 0)
        meta["mpris:length"] = int(duration_ms) * 1000

        # Determine current path
        title = "-"
        album = ""
        artist = []
        art_url = None
        try:
            pl = getattr(self._app, 'playlist', [])
            idx = getattr(self._app, 'current_index', -1)
            if pl and 0 <= idx < len(pl):
                item = pl[idx]
                if isinstance(item, str):
                    title = os.path.splitext(os.path.basename(item))[0]
                    # Provide URL for local files
                    from PySide6.QtCore import QUrl
                    meta["xesam:url"] = QUrl.fromLocalFile(os.path.abspath(item)).toString()
                    art_url = None
                elif isinstance(item, dict) and item.get('type') == 'cloud':
                    title = item.get('name', 'Cloud Track')
        except Exception:
            pass

        # If the UI labels have more info, use them
        try:
            lbl = getattr(self._app, 'track_title_label', None)
            if lbl and lbl.text():
                # Expected format: "Title: <name>"
                t = lbl.text()
                if ":" in t:
                    title = t.split(":", 1)[1].strip() or title
        except Exception:
            pass

        meta["xesam:title"] = title
        meta["xesam:album"] = album
        meta["xesam:artist"] = artist
        if art_url:
            meta["mpris:artUrl"] = art_url
        return meta

    @Property(float)
    def Volume(self) -> float:  # noqa: N802
        ao = getattr(self._app, 'audio_output', None)
        if ao:
            try:
                return float(ao.volume())
            except Exception:
                pass
        return 1.0

    @Volume.setter
    def Volume(self, value: float):  # noqa: N802
        ao = getattr(self._app, 'audio_output', None)
        if ao:
            try:
                ao.setVolume(max(0.0, min(1.0, float(value))))
            except Exception:
                pass

    @Property(int)
    def Position(self) -> int:  # noqa: N802
        # In microseconds
        pos_ms = int(getattr(self._player, 'position', lambda: 0)() or 0)
        return pos_ms * 1000

    @Property(float, constant=True)
    def MinimumRate(self) -> float:  # noqa: N802
        return 1.0

    @Property(float, constant=True)
    def MaximumRate(self) -> float:  # noqa: N802
        return 1.0

    @Property(bool, constant=True)
    def CanGoNext(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def CanGoPrevious(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def CanPlay(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def CanPause(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def CanSeek(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def CanControl(self) -> bool:  # noqa: N802
        return True

    # ----- Methods -----
    @Slot()
    def Play(self):
        # Ensure playing
        try:
            if self._player.playbackState() != 1:
                self._player.play()
        except Exception:
            self._player.play()
        self._emit_props_changed()

    @Slot()
    def Pause(self):
        try:
            if self._player.playbackState() == 1:
                self._player.pause()
        except Exception:
            self._player.pause()
        self._emit_props_changed()

    @Slot()
    def PlayPause(self):
        try:
            # Use application's toggle if available for UI sync
            toggle = getattr(self._app, 'toggle_play', None)
            if callable(toggle):
                toggle()
                self._emit_props_changed()
                return
        except Exception:
            pass
        # Fallback
        if self.PlaybackStatus == "Playing":
            self.Pause()
        else:
            self.Play()

    @Slot()
    def Stop(self):
        stop = getattr(self._app, 'stop', None)
        if callable(stop):
            stop()
        else:
            self._player.stop()
        self._emit_props_changed()

    @Slot()
    def Next(self):
        nxt = getattr(self._app, 'next_track', None)
        if callable(nxt):
            nxt()
        self._emit_props_changed()

    @Slot()
    def Previous(self):
        prev = getattr(self._app, 'prev_track', None)
        if callable(prev):
            prev()
        self._emit_props_changed()

    @Slot(int)
    def Seek(self, offset_us: int):
        # offset in microseconds relative to current pos
        cur = int(getattr(self._player, 'position', lambda: 0)() or 0)
        new_ms = max(0, cur + int(offset_us // 1000))
        try:
            self._player.setPosition(new_ms)
        except Exception:
            pass
        self._emit_seeked()

    @Slot(str, int)
    def SetPosition(self, track_id: str, position_us: int):
        # Set absolute position in microseconds
        new_ms = max(0, int(position_us // 1000))
        try:
            self._player.setPosition(new_ms)
        except Exception:
            pass
        self._emit_seeked()

    @Slot(str)
    def OpenUri(self, uri: str):
        # Simple support for file:// URIs
        try:
            if uri.startswith('file://'):
                from PySide6.QtCore import QUrl
                self._player.setSource(QUrl(uri))
                self._player.play()
                self._emit_props_changed()
        except Exception:
            pass

    # ----- Helpers to emit signals -----
    def _emit_props_changed(self):
        # Emit org.freedesktop.DBus.Properties.PropertiesChanged
        conn = QDBusConnection.sessionBus()
        msg = QDBusMessage.createSignal(
            MPRIS_PATH,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
        )
        # Arguments: interface_name, changed_properties (dict), invalidated (array)
        changed = {
            "PlaybackStatus": self.PlaybackStatus,
            "Metadata": self.Metadata,
            "Volume": self.Volume,
        }
        msg.setArguments([
            IFACE_PLAYER,
            changed,
            [],
        ])
        conn.send(msg)

    def _emit_seeked(self):
        # Emit Seeked signal with current position
        conn = QDBusConnection.sessionBus()
        msg = QDBusMessage.createSignal(
            MPRIS_PATH,
            IFACE_PLAYER,
            "Seeked",
        )
        msg.setArguments([self.Position])
        conn.send(msg)

    def _maybe_emit_seeked(self, _pos_ms: int):
        self._emit_seeked()


class Mpris(QObject):
    """Sets up MPRIS service on the session bus and binds to an existing MusicPlayer instance."""

    def __init__(self, app_window):
        super().__init__(app_window)
        self._app = app_window
        self._player = getattr(self._app, 'player')  # QMediaPlayer instance

        # Register service and object
        self._conn = QDBusConnection.sessionBus()
        if not self._conn.isConnected():
            print("[MPRIS] No DBus session bus available. MPRIS disabled.")
            return
        # Try preferred lowercase name, then alt (legacy), then PID-suffixed fallback
        service_candidates = [MPRIS_SERVICE_PRIMARY, MPRIS_SERVICE_ALT]
        ok = False
        service_name = None
        for name in service_candidates:
            if self._conn.registerService(name):
                ok = True
                service_name = name
                break
        if not ok:
            # Fallback: append PID to stay spec-compliant and unique
            pid = os.getpid()
            # Try PID suffix on primary
            service_name = f"{MPRIS_SERVICE_PRIMARY}.{pid}"
            ok = self._conn.registerService(service_name)
        if not ok:
            print(f"[MPRIS] Failed to register service name(s). Tried: {service_candidates + [service_name]}.")
        else:
            print(f"[MPRIS] Registered service: {service_name}")

        # Create exported QObject and attach adaptors BEFORE registering the object
        self._export_obj = QObject(self)
        print("[MPRIS] Creating DBus adaptors...")
        self._root = _MprisRootAdaptor(self._export_obj, app_identity="HiCloud MP")
        self._player_adaptor = _MprisPlayerAdaptor(self._export_obj, self._player, self._app)
        obj_ok = self._conn.registerObject(MPRIS_PATH, self._export_obj, QDBusConnection.ExportAdaptors)
        if not obj_ok:
            print(f"[MPRIS] Failed to register DBus object at {MPRIS_PATH}")
        else:
            print(f"[MPRIS] Exported object at {MPRIS_PATH} with adaptors")
            # Emit initial state so desktops pick us up immediately
            try:
                self._player_adaptor._emit_props_changed()
                self._player_adaptor._emit_seeked()
            except Exception:
                pass

    def teardown(self):
        try:
            self._conn.unregisterObject(MPRIS_PATH)
        except Exception:
            pass
        try:
            self._conn.unregisterService(MPRIS_SERVICE)
        except Exception:
            pass
