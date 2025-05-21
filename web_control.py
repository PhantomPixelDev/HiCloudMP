import threading
import os
from flask import Flask, request, render_template_string, send_from_directory
from flask_socketio import SocketIO, emit

class WebControlServer:
    def __init__(self, player, host='0.0.0.0', port=5000):
        self.player = player
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins='*', async_mode='threading')
        self._thread = None
        self._running = False
        self._setup_routes()
        self._setup_socketio()

    def _setup_routes(self):
        @self.app.route('/')
        def index():
            return send_from_directory('.', 'web_panel.html')
        @self.app.route('/static/<path:path>')
        def static_files(path):
            return send_from_directory('static', path)

    def _setup_socketio(self):
        @self.socketio.on('connect')
        def handle_connect():
            emit('status', self._get_status())
            emit('playlist', self._get_playlist())
            emit('progress', self._get_progress())
            emit('all_playlists', self._get_all_playlists())

        @self.socketio.on('play')
        def handle_play():
            self.player.play()
            self._broadcast_status()
            self._broadcast_progress()

        @self.socketio.on('pause')
        def handle_pause():
            self.player.toggle_play()
            self._broadcast_status()
            self._broadcast_progress()

        @self.socketio.on('next')
        def handle_next():
            self.player.next_track()
            self._broadcast_status()
            self._broadcast_progress()
            self._broadcast_playlist()

        @self.socketio.on('prev')
        def handle_prev():
            self.player.prev_track()
            self._broadcast_status()
            self._broadcast_progress()
            self._broadcast_playlist()

        @self.socketio.on('stop')
        def handle_stop():
            self.player.stop()
            self._broadcast_status()
            self._broadcast_progress()

        @self.socketio.on('set_volume')
        def handle_set_volume(data):
            vol = int(data.get('volume', 70))
            self.player.set_volume(vol)
            if hasattr(self.player, 'volume_slider'):
                self.player.volume_slider.setValue(vol)
            self._broadcast_status()

        @self.socketio.on('get_playlist')
        def handle_get_playlist():
            emit('playlist', self._get_playlist())

        @self.socketio.on('play_index')
        def handle_play_index(data):
            idx = int(data.get('index', 0))
            if 0 <= idx < len(self.player.playlist):
                self.player.current_index = idx
                self.player.play()
                self._broadcast_status()
                self._broadcast_progress()
                self._broadcast_playlist()

        @self.socketio.on('get_progress')
        def handle_get_progress():
            emit('progress', self._get_progress())

        @self.socketio.on('seek')
        def handle_seek(data):
            pos = int(data.get('position', 0))
            self.player.player.setPosition(pos)
            self._broadcast_progress()

        @self.socketio.on('toggle_shuffle')
        def handle_toggle_shuffle():
            if hasattr(self.player, 'shuffle_btn'):
                self.player.shuffle_btn.setChecked(not self.player.shuffle_btn.isChecked())
                self.player.toggle_shuffle(self.player.shuffle_btn.isChecked())
            self._broadcast_status()

        @self.socketio.on('toggle_repeat')
        def handle_toggle_repeat():
            if hasattr(self.player, 'repeat_btn'):
                self.player.repeat_btn.setChecked(not self.player.repeat_btn.isChecked())
                self.player.toggle_repeat(self.player.repeat_btn.isChecked())
            self._broadcast_status()

        @self.socketio.on('get_all_playlists')
        def handle_get_all_playlists():
            emit('all_playlists', self._get_all_playlists())

        @self.socketio.on('switch_playlist')
        def handle_switch_playlist(data):
            pid = data.get('playlist_id')
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

    def _get_status(self):
        return {
            'track': getattr(self.player, 'track_title_label', None).text() if hasattr(self.player, 'track_title_label') else '-',
            'artist': getattr(self.player, 'track_artist_label', None).text() if hasattr(self.player, 'track_artist_label') else '-',
            'album': getattr(self.player, 'track_album_label', None).text() if hasattr(self.player, 'track_album_label') else '-',
            'state': str(self.player.player.playbackState()),
            'volume': int(self.player.volume_slider.value()) if hasattr(self.player, 'volume_slider') else 70,
            'current_index': getattr(self.player, 'current_index', -1),
            'shuffle': self.player.shuffle_btn.isChecked() if hasattr(self.player, 'shuffle_btn') else False,
            'repeat': self.player.repeat_btn.isChecked() if hasattr(self.player, 'repeat_btn') else False,
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
        # Flask does not provide a built-in way to stop, so this is a placeholder
        self._running = False
        # In production, use a more robust server or signal 