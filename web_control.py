import threading
import os
import secrets
import time
from flask import Flask, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit

DEFAULT_HOST = "127.0.0.1"


def lan_ip():
    """Best-effort LAN address for user-facing remote links (never raises).
    Falls back to 127.0.0.1 when the machine is offline/isolated."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("192.168.255.255", 9))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and ip not in ("127.0.0.1", "0.0.0.0"):
            return str(ip)
    except Exception:
        pass
    try:
        return str(socket.gethostbyname(socket.gethostname()))
    except Exception:
        return "127.0.0.1"


def panel_url(port=5000, token="", lan_ip=None):
    """Full ready-to-open remote link. The access key is embedded — people
    copy this one link; nothing to configure."""
    host = lan_ip or "127.0.0.1"
    return f"http://{host}:{port}" + (f"/?token={token}" if token else "")


class WebControlServer:
    """LAN web remote. Security model:
    - binds loopback by default (opt-in exposes on LAN by passing host='0.0.0.0')
    - every HTTP route requiring auth accepts Authorization: Bearer <token> or ?token=...
    - socket.io connects must pass auth={"token": ...}; unauthenticated connects refused
    - /health stays intentionally unauthenticated (liveness only, no player data)
    """

    def __init__(self, player, host=DEFAULT_HOST, port=5000, token=None):
        self.player = player
        self.host = host
        self.port = port
        self.token = token or secrets.token_hex(16)
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, async_mode='threading')
        self._thread = None
        self._running = False
        self._setup_routes()
        self._setup_socketio()

    def _check_auth(self):
        """Return True if the request carries the valid token (header or query)."""
        supplied = request.args.get("token", "")
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            supplied = supplied or auth_header[7:].strip()
        try:
            return supplied and secrets.compare_digest(supplied, self.token)
        except Exception:
            return False

    @staticmethod
    def _safe_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _unauthorized(self):
        return jsonify({"error": "unauthorized"}), 401

    def _setup_routes(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(base_dir, 'static')

        @self.app.route('/')
        def index():
            if not self._check_auth():
                return self._unauthorized()
            return send_from_directory(base_dir, 'web_panel.html')

        @self.app.route('/static/<path:path>')
        def static_files(path):
            return send_from_directory(static_dir, path)

        @self.app.route('/health')
        def health():
            return {'status': 'ok'}

        @self.app.route('/api/ping')
        def ping():
            """Public liveness probe for the panel's connection indicator.
            Deliberately exposes nothing about the player — same contract as
            /health plus a clock so the browser can show latency."""
            return {'ok': True, 'app': 'HiCloudMP',
                    'server_ms': int(time.time() * 1000)}

    def _setup_socketio(self):
        @self.socketio.on('connect')
        def handle_connect(*args):
            # flask_socketio delivers the socket.io `auth` payload as the third
            # positional arg when present: (sid, environ, auth)
            auth = args[2] if len(args) > 2 and isinstance(args[2], dict) else {}
            supplied = str(auth.get("token", ""))
            if not supplied:
                for a in args:  # some transports pass auth differently; ignore silently
                    if isinstance(a, dict) and a.get("token"):
                        supplied = str(a.get("token"))
            try:
                ok = bool(supplied) and secrets.compare_digest(supplied, self.token)
            except Exception:
                ok = False
            if not ok:
                return False  # reject the connection
            emit('status', self._get_status())
            emit('playlist', self._get_playlist())
            emit('progress', self._get_progress())
            emit('all_playlists', self._get_all_playlists())

        @self.socketio.on('play')
        def handle_play():
            def _do():
                # If no current index, default to first track
                if (not hasattr(self.player, 'playlist') or not self.player.playlist):
                    return
                if not hasattr(self.player, 'current_index') or self.player.current_index < 0 or self.player.current_index >= len(self.player.playlist):
                    self.player.current_index = 0
                self.player.play()
                self._broadcast_status()
                self._broadcast_progress()
            self.player.run_on_ui.emit(_do)

        @self.socketio.on('pause')
        def handle_pause():
            self.player.run_on_ui.emit(lambda: (self.player.toggle_play(), self._broadcast_status(), self._broadcast_progress()))

        @self.socketio.on('next')
        def handle_next():
            self.player.run_on_ui.emit(lambda: (self.player.next_track(), self._broadcast_status(), self._broadcast_progress(), self._broadcast_playlist()))

        @self.socketio.on('prev')
        def handle_prev():
            self.player.run_on_ui.emit(lambda: (self.player.prev_track(), self._broadcast_status(), self._broadcast_progress(), self._broadcast_playlist()))

        @self.socketio.on('stop')
        def handle_stop():
            self.player.run_on_ui.emit(lambda: (self.player.stop(), self._broadcast_status(), self._broadcast_progress()))

        @self.socketio.on('set_volume')
        def handle_set_volume(data):
            if not isinstance(data, dict):
                return
            vol = self._safe_int(data.get('volume', 70), None)
            if vol is None or not (0 <= vol <= 100):
                return
            def _do():
                self.player.set_volume(vol)
                if hasattr(self.player, 'volume_slider'):
                    self.player.volume_slider.setValue(vol)
                self._broadcast_status()
            self.player.run_on_ui.emit(_do)

        @self.socketio.on('get_playlist')
        def handle_get_playlist():
            emit('playlist', self._get_playlist())

        @self.socketio.on('play_index')
        def handle_play_index(data):
            if not isinstance(data, dict):
                return
            idx = self._safe_int(data.get('index', 0), -1)
            if idx < 0:
                return
            def _do():
                if 0 <= idx < len(self.player.playlist):
                    self.player.current_index = idx
                    self.player.play()
                    self._broadcast_status()
                    self._broadcast_progress()
                    self._broadcast_playlist()
            self.player.run_on_ui.emit(_do)

        @self.socketio.on('get_progress')
        def handle_get_progress():
            emit('progress', self._get_progress())

        @self.socketio.on('seek')
        def handle_seek(data):
            if not isinstance(data, dict):
                return
            pos = self._safe_int(data.get('position', 0), None)
            if pos is None or pos < 0:
                return
            self.player.run_on_ui.emit(lambda: (self.player.seek_position(pos),
                                                    self._broadcast_progress(),
                                                    self._broadcast_status()))

        @self.socketio.on('toggle_shuffle')
        def handle_toggle_shuffle():
            def _do():
                if hasattr(self.player, 'shuffle_btn'):
                    self.player.shuffle_btn.setChecked(not self.player.shuffle_btn.isChecked())
                    self.player.toggle_shuffle(self.player.shuffle_btn.isChecked())
                self._broadcast_status()
            self.player.run_on_ui.emit(_do)

        @self.socketio.on('toggle_repeat')
        def handle_toggle_repeat():
            def _do():
                if hasattr(self.player, 'repeat_btn'):
                    self.player.repeat_btn.setChecked(not self.player.repeat_btn.isChecked())
                    self.player.toggle_repeat(self.player.repeat_btn.isChecked())
                self._broadcast_status()
            self.player.run_on_ui.emit(_do)

        @self.socketio.on('toggle_mute')
        def handle_toggle_mute():
            def _do():
                self.player.toggle_mute()
                self._broadcast_status()
            self.player.run_on_ui.emit(_do)

        @self.socketio.on('set_rate')
        def handle_set_rate(data):
            if not isinstance(data, dict):
                return
            try:
                rate = float(data.get('rate'))
            except (TypeError, ValueError):
                return
            if not (0.5 <= rate <= 2.0):
                return
            def _do():
                apply_rate = getattr(self.player, '_apply_playback_rate', None)
                if callable(apply_rate):
                    apply_rate(int(round(rate * 100)), announce=False)
                self._broadcast_status()
            self.player.run_on_ui.emit(_do)

        @self.socketio.on('clear_queue')
        def handle_clear_queue():
            def _do():
                clear = getattr(self.player, 'clear_play_next_queue', None)
                if callable(clear):
                    clear()
                self._broadcast_status()
            self.player.run_on_ui.emit(_do)

        @self.socketio.on('get_all_playlists')
        def handle_get_all_playlists():
            emit('all_playlists', self._get_all_playlists())

        @self.socketio.on('switch_playlist')
        def handle_switch_playlist(data):
            if not isinstance(data, dict):
                return
            pid = data.get('playlist_id')
            def _do():
                if pid == '__queue__':
                    # Switch to current queue
                    self.player.active_playlist = None
                    # Keep current playlist as is
                else:
                    for p in self.player.playlists:
                        if getattr(p, 'id', None) == pid:
                            self.player.load_playlist(p)
                            break
                self._broadcast_status()
                self._broadcast_playlist()
                self._broadcast_progress()
            self.player.run_on_ui.emit(_do)

    def _get_status(self):
        try:
            state = str(self.player.effective_playback_state())
        except AttributeError:
            state = str(self.player.player.playbackState())
        return {
            'track': getattr(self.player, 'track_title_label', None).text() if hasattr(self.player, 'track_title_label') else '-',
            'artist': getattr(self.player, 'track_artist_label', None).text() if hasattr(self.player, 'track_artist_label') else '-',
            'album': getattr(self.player, 'track_album_label', None).text() if hasattr(self.player, 'track_album_label') else '-',
            'state': state,
            'volume': int(self.player.volume_slider.value()) if hasattr(self.player, 'volume_slider') else 70,
            'current_index': getattr(self.player, 'current_index', -1),
            'shuffle': self.player.shuffle_btn.isChecked() if hasattr(self.player, 'shuffle_btn') else False,
            'repeat': self.player.repeat_btn.isChecked() if hasattr(self.player, 'repeat_btn') else False,
            'muted': bool(self.player.audio_output.isMuted()) if hasattr(self.player, 'audio_output') else False,
            'rate': float(self.player._playback_rate()) if hasattr(self.player, '_playback_rate') else 1.0,
            'queue_count': len(getattr(self.player, '_play_next_queue', None) or []),
            'playlist_name': self.player.active_playlist.name if getattr(self.player, 'active_playlist', None) else 'Current Queue',
            'playlist_id': self.player.active_playlist.id if getattr(self.player, 'active_playlist', None) else '__queue__'
        }

    def _get_playlist(self):
        playlist = []
        for i, item in enumerate(self.player.playlist):
            if isinstance(item, dict) and item.get('type') == 'cloud':
                cloud_idx = item.get('cloud_idx')
                file_idx = item.get('file_idx')
                cloud = self.player.clouds[cloud_idx] if 0 <= cloud_idx < len(self.player.clouds) else None
                file_info = cloud['files'][file_idx] if cloud and 'files' in cloud and 0 <= file_idx < len(cloud['files']) else None
                name = os.path.basename(file_info['path']) if file_info else f'Cloud Track {i+1}'
            else:
                name = os.path.basename(item) if isinstance(item, str) else f'Track {i+1}'
            playlist.append({'index': i, 'name': name})
        return playlist

    def _get_progress(self):
        # In engine mode (EQ active) the native player sits idle - report
        # the engine's real position/duration so the panel keeps moving.
        if getattr(self.player, '_using_engine', False):
            try:
                eng = self.player.eq_engine
                pos = int(eng.position_ms())
                dur = int(eng.duration_ms())
                if dur <= 0:
                    dur = int(self.player.player.duration())
                return {'position': pos, 'duration': dur}
            except Exception:
                pass
        pos = int(self.player.player.position())
        dur = int(self.player.player.duration())
        return {'position': pos, 'duration': dur}

    def _get_all_playlists(self):
        # Returns a list of {id, name}
        playlists = [{'id': '__queue__', 'name': 'Current Queue'}]
        for p in self.player.playlists:
            playlists.append({'id': getattr(p, 'id', ''), 'name': getattr(p, 'name', 'Unnamed')})
        return playlists

    def _broadcast_status(self):
        self.socketio.emit('status', self._get_status())

    def _broadcast_playlist(self):
        self.socketio.emit('playlist', self._get_playlist())

    def _broadcast_progress(self):
        self.socketio.emit('progress', self._get_progress())

    def broadcast_state(self):
        """Push desktop-side changes to every connected panel (call on the
        UI thread; failures must never disturb playback)."""
        try:
            self._broadcast_status()
            self._broadcast_progress()
        except Exception:
            pass

    def _html(self):
        # No longer used, but kept for reference
        return """(moved to web_panel.html)"""

    def start(self):
        if self._running:
            return
        self._running = True
        def run_socketio():
            self.socketio.run(self.app, host=self.host, port=self.port, allow_unsafe_werkzeug=True)
        self._thread = threading.Thread(target=run_socketio, daemon=True)
        self._thread.start()

    def stop(self):
        """Best-effort shutdown of the web server (idempotent, safe from any thread)."""
        self._running = False
        try:
            # flask_socketio.SocketIO has no shutdown(); the underlying
            # socketio.Server does (python-socketio >= 5.10).
            self.socketio.server.shutdown()
        except Exception:
            pass  # no controlled shutdown handle in threading mode — the daemon
        # server thread dies with the process; joining it would only add a
        # multi-second close delay when the server ignores the shutdown signal. 