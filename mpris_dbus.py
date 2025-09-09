import os
import threading
import time
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

MPRIS_PATH = "/org/mpris/MediaPlayer2"
MPRIS_SERVICE = "org.mpris.MediaPlayer2.hicloudmp"
IFACE_ROOT = "org.mpris.MediaPlayer2"
IFACE_PLAYER = "org.mpris.MediaPlayer2.Player"
IFACE_PROPERTIES = "org.freedesktop.DBus.Properties"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class _MprisObject(dbus.service.Object):
    def __init__(self, bus, app):
        super().__init__(bus, MPRIS_PATH)
        self._app = app
        self._player = app.player

    # ===== Properties interface implementation =====
    def _root_props(self):
        return {
            'CanQuit': dbus.Boolean(True),
            'CanRaise': dbus.Boolean(True),
            'HasTrackList': dbus.Boolean(False),
            'Identity': dbus.String('HiCloud MP'),
            'SupportedUriSchemes': dbus.Array(['file'], signature='s'),
            'SupportedMimeTypes': dbus.Array([
                'audio/mpeg', 'audio/flac', 'audio/ogg', 'audio/x-wav', 'audio/aac'
            ], signature='s'),
            'DesktopEntry': dbus.String('HiCloudMP'),
        }

    def _player_props(self):
        # PlaybackStatus
        try:
            st = self._player.playbackState()
        except Exception:
            st = 0
        status = {0: 'Stopped', 1: 'Playing', 2: 'Paused'}.get(st, 'Stopped')
        # Volume
        try:
            vol = float(self._app.audio_output.volume())
        except Exception:
            vol = 1.0
        # Position microseconds
        try:
            pos_us = int(self._player.position()) * 1000
        except Exception:
            pos_us = 0
        # Metadata
        meta = {}
        idx = getattr(self._app, 'current_index', -1)
        pl = getattr(self._app, 'playlist', [])
        track_id = f"/org/mpris/MediaPlayer2/track/{idx if idx >= 0 else 0}"
        meta[dbus.String('mpris:trackid')] = dbus.ObjectPath(track_id)
        try:
            duration_ms = int(self._player.duration())
        except Exception:
            duration_ms = 0
        meta[dbus.String('mpris:length')] = dbus.Int64(duration_ms * 1000)
        title = '-'
        if pl and 0 <= idx < len(pl):
            item = pl[idx]
            if isinstance(item, str):
                title = os.path.splitext(os.path.basename(item))[0]
                meta[dbus.String('xesam:url')] = dbus.String(f"file://{os.path.abspath(item)}")
            elif isinstance(item, dict):
                title = item.get('name', 'Cloud Track')
        meta[dbus.String('xesam:title')] = dbus.String(title)
        meta[dbus.String('xesam:artist')] = dbus.Array([], signature='s')
        meta[dbus.String('xesam:album')] = dbus.String('')

        # Shuffle / LoopStatus
        try:
            shuffle = bool(self._app.shuffle_btn.isChecked())
        except Exception:
            shuffle = False
        try:
            loop = 'Track' if self._app.repeat_btn.isChecked() else 'None'
        except Exception:
            loop = 'None'

        return {
            'PlaybackStatus': dbus.String(status),
            'LoopStatus': dbus.String(loop),
            'Rate': dbus.Double(1.0),
            'Shuffle': dbus.Boolean(shuffle),
            'Metadata': dbus.Dictionary(meta, signature='sv'),
            'Volume': dbus.Double(vol),
            'Position': dbus.Int64(pos_us),
            'MinimumRate': dbus.Double(1.0),
            'MaximumRate': dbus.Double(1.0),
            'CanGoNext': dbus.Boolean(True),
            'CanGoPrevious': dbus.Boolean(True),
            'CanPlay': dbus.Boolean(True),
            'CanPause': dbus.Boolean(True),
            'CanSeek': dbus.Boolean(True),
            'CanControl': dbus.Boolean(True),
        }

    @dbus.service.method(IFACE_PROPERTIES, in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        if interface == IFACE_ROOT:
            return self._root_props()[prop]
        if interface == IFACE_PLAYER:
            return self._player_props()[prop]
        raise dbus.exceptions.DBusException('org.freedesktop.DBus.Error.InvalidArgs')

    @dbus.service.method(IFACE_PROPERTIES, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface == IFACE_ROOT:
            return self._root_props()
        if interface == IFACE_PLAYER:
            return self._player_props()
        return {}

    @dbus.service.method(IFACE_PROPERTIES, in_signature='ssv')
    def Set(self, interface, prop, value):
        if interface == IFACE_PLAYER and prop == 'Volume':
            try:
                self._app.run_on_ui.emit(lambda: self._app.audio_output.setVolume(_clamp(float(value), 0.0, 1.0)))
                self.PropertiesChanged(IFACE_PLAYER, {'Volume': dbus.Double(float(value))}, [])
            except Exception:
                pass
        # Ignore other sets

    # ===== Root interface methods =====
    @dbus.service.method(IFACE_ROOT)
    def Raise(self):
        try:
            self._app.run_on_ui.emit(lambda: (self._app.showNormal(), self._app.raise_(), self._app.activateWindow()))
        except Exception:
            pass

    @dbus.service.method(IFACE_ROOT)
    def Quit(self):
        try:
            self._app.run_on_ui.emit(lambda: self._app.close())
        except Exception:
            pass

    # ===== Player methods =====
    @dbus.service.method(IFACE_PLAYER)
    def Play(self):
        self._app.run_on_ui.emit(lambda: self._player.play())
        self.PropertiesChanged(IFACE_PLAYER, {'PlaybackStatus': dbus.String('Playing')}, [])

    @dbus.service.method(IFACE_PLAYER)
    def Pause(self):
        self._app.run_on_ui.emit(lambda: self._player.pause())
        self.PropertiesChanged(IFACE_PLAYER, {'PlaybackStatus': dbus.String('Paused')}, [])

    @dbus.service.method(IFACE_PLAYER)
    def PlayPause(self):
        self._app.run_on_ui.emit(lambda: self._app.toggle_play())
        # Status will be updated on next Get; emit a generic change
        self.PropertiesChanged(IFACE_PLAYER, {'PlaybackStatus': self._player_props()['PlaybackStatus']}, [])

    @dbus.service.method(IFACE_PLAYER)
    def Stop(self):
        self._app.run_on_ui.emit(lambda: self._app.stop())
        self.PropertiesChanged(IFACE_PLAYER, {'PlaybackStatus': dbus.String('Stopped')}, [])

    @dbus.service.method(IFACE_PLAYER)
    def Next(self):
        self._app.run_on_ui.emit(lambda: self._app.next_track())
        self.PropertiesChanged(IFACE_PLAYER, {'Metadata': self._player_props()['Metadata']}, [])

    @dbus.service.method(IFACE_PLAYER)
    def Previous(self):
        self._app.run_on_ui.emit(lambda: self._app.prev_track())
        self.PropertiesChanged(IFACE_PLAYER, {'Metadata': self._player_props()['Metadata']}, [])

    @dbus.service.method(IFACE_PLAYER, in_signature='x')
    def Seek(self, offset_us):
        def _do():
            cur = int(self._player.position())
            self._player.setPosition(max(0, cur + int(offset_us // 1000)))
        self._app.run_on_ui.emit(_do)
        self.Seeked(dbus.Int64(self._player_props()['Position']))

    @dbus.service.method(IFACE_PLAYER, in_signature='ox')
    def SetPosition(self, track_id, position_us):
        def _do():
            self._player.setPosition(max(0, int(position_us // 1000)))
        self._app.run_on_ui.emit(_do)
        self.Seeked(dbus.Int64(self._player_props()['Position']))

    @dbus.service.method(IFACE_PLAYER, in_signature='s')
    def OpenUri(self, uri):
        if uri.startswith('file://'):
            from PySide6.QtCore import QUrl
            self._app.run_on_ui.emit(lambda: (self._player.setSource(QUrl(uri)), self._player.play()))
            self.PropertiesChanged(IFACE_PLAYER, {'PlaybackStatus': dbus.String('Playing'), 'Metadata': self._player_props()['Metadata']}, [])

    # ===== Signals =====
    @dbus.service.signal(IFACE_PROPERTIES, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed_properties, invalidated):
        pass

    @dbus.service.signal(IFACE_PLAYER, signature='x')
    def Seeked(self, position_us):
        pass


class MprisService:
    def __init__(self, app):
        self._app = app
        self._thread = None
        self._loop = None
        self._bus = None
        self._obj = None

    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SessionBus()
            # Try preferred name, then PID fallback
            name = None
            try:
                name = dbus.service.BusName(MPRIS_SERVICE, bus=self._bus, allow_replacement=True, replace_existing=True, do_not_queue=False)
            except Exception:
                name = dbus.service.BusName(f"{MPRIS_SERVICE}.{os.getpid()}", bus=self._bus)
            self._obj = _MprisObject(self._bus, self._app)
            # Emit initial state via PropertiesChanged
            try:
                self._obj.PropertiesChanged(IFACE_PLAYER, self._obj._player_props(), [])
            except Exception:
                pass
            self._loop = GLib.MainLoop()
            self._loop.run()
        except Exception as e:
            print(f"[MPRIS-DBUS] Failed to start: {e}")

    def stop(self):
        try:
            if self._loop:
                self._loop.quit()
        except Exception:
            pass
