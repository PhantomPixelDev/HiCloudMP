from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidgetAction, QSlider
from PySide6.QtWidgets import QStyle
import os
import subprocess


class TrayController:
    def __init__(self, app):
        self.app = app  # MusicPlayer instance
        self.tray_icon = None
        self.tray_add_menu = None
        self.tray_now_playing = None
        self.tray_shuffle_action = None
        self.tray_repeat_action = None
        self.tray_mute_action = None

    def init_tray(self):
        if self.tray_icon:
            return
        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.setIcon(self.app.style().standardIcon(QStyle.SP_MediaPlay))
        self.tray_icon.setToolTip("HiCloud MP")

        tray_menu = QMenu()

        # Now Playing (disabled informational action)
        self.tray_now_playing = tray_menu.addAction("Now Playing: -")
        self.tray_now_playing.setEnabled(False)

        tray_menu.addSeparator()

        # Window actions
        show_action = tray_menu.addAction("Show Window")
        show_action.triggered.connect(self.app.showNormal)
        hide_action = tray_menu.addAction("Hide Window")
        hide_action.triggered.connect(self.app.hide)

        tray_menu.addSeparator()

        # Media controls
        play_action = tray_menu.addAction("Play/Pause")
        play_action.triggered.connect(self.app.toggle_play)

        prev_action = tray_menu.addAction("Previous")
        prev_action.triggered.connect(self.app.prev_track)

        next_action = tray_menu.addAction("Next")
        next_action.triggered.connect(self.app.next_track)

        stop_action = tray_menu.addAction("Stop")
        stop_action.triggered.connect(self.app.stop)

        # Seek controls
        seek_back_action = tray_menu.addAction("Seek -10s")
        seek_back_action.triggered.connect(lambda: self.app.seek_position(max(0, self.app.player.position() - 10000)))
        seek_fwd_action = tray_menu.addAction("Seek +10s")
        seek_fwd_action.triggered.connect(lambda: self.app.seek_position(self.app.player.position() + 10000))

        # Toggles
        tray_menu.addSeparator()
        self.tray_shuffle_action = tray_menu.addAction("Shuffle")
        self.tray_shuffle_action.setCheckable(True)
        self.tray_shuffle_action.toggled.connect(self.app.toggle_shuffle)

        self.tray_repeat_action = tray_menu.addAction("Repeat")
        self.tray_repeat_action.setCheckable(True)
        self.tray_repeat_action.toggled.connect(self.app.toggle_repeat)

        # Volume controls
        tray_menu.addSeparator()
        self.tray_mute_action = tray_menu.addAction("Mute")
        self.tray_mute_action.setCheckable(True)
        self.tray_mute_action.toggled.connect(lambda m: self.app.audio_output.setMuted(m))

        # Inline volume slider
        vol_widget_action = QWidgetAction(tray_menu)
        vol_slider = QSlider(Qt.Horizontal)
        vol_slider.setRange(0, 100)
        try:
            vol_slider.setValue(int(self.app.audio_output.volume() * 100))
        except Exception:
            vol_slider.setValue(self.app.volume_slider.value())
        vol_slider.valueChanged.connect(self.app.set_volume)
        vol_widget_action.setDefaultWidget(vol_slider)
        tray_menu.addAction(vol_widget_action)

        # App shortcuts
        tray_menu.addSeparator()
        open_web_action = tray_menu.addAction("Open Web Panel")
        open_web_action.triggered.connect(self.app.open_web_panel)

        # Add to Playlist submenu (dynamic)
        self.tray_add_menu = tray_menu.addMenu("Add Current to Playlist")
        self.tray_add_menu.addAction("No saved playlists").setEnabled(False)
        tray_menu.aboutToShow.connect(self._rebuild_tray_playlist_menu)

        open_loc_action = tray_menu.addAction("Open Current Location")
        open_loc_action.triggered.connect(self.open_current_location)

        settings_action = tray_menu.addAction("Settings")
        settings_action.triggered.connect(self.app.open_settings_dialog)

        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self.app.close)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(lambda reason: self.app.toggle_play() if reason == QSystemTrayIcon.Trigger else None)
        self.tray_icon.show()
        self.update_tray_ui()

    def update_tray_ui(self):
        if not self.tray_icon:
            return
        # Icon based on playing/paused
        try:
            state = self.app.player.playbackState()
        except Exception:
            state = self.app.player.PlaybackState.StoppedState
        if state == self.app.player.PlaybackState.PlayingState:
            self.tray_icon.setIcon(self.app.style().standardIcon(QStyle.SP_MediaPause))
        elif state == self.app.player.PlaybackState.PausedState:
            self.tray_icon.setIcon(self.app.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            self.tray_icon.setIcon(self.app.style().standardIcon(QStyle.SP_MediaStop))

        # Now Playing text and tooltip
        title = "-"
        try:
            if hasattr(self.app, 'track_title_label') and self.app.track_title_label.text():
                t = self.app.track_title_label.text()
                if ":" in t:
                    title = t.split(":", 1)[1].strip() or title
        except Exception:
            pass
        artist = "-"
        try:
            if hasattr(self.app, 'track_artist_label') and self.app.track_artist_label.text():
                a = self.app.track_artist_label.text()
                if ":" in a:
                    artist = a.split(":", 1)[1].strip() or artist
        except Exception:
            pass
        if self.tray_now_playing:
            self.tray_now_playing.setText(f"Now Playing: {title} — {artist}")
        self.tray_icon.setToolTip(f"HiCloud MP\n{title} — {artist}")

        # Toggle states
        if self.tray_shuffle_action and hasattr(self.app, 'shuffle_btn'):
            self.tray_shuffle_action.blockSignals(True)
            self.tray_shuffle_action.setChecked(self.app.shuffle_btn.isChecked())
            self.tray_shuffle_action.blockSignals(False)
        if self.tray_repeat_action and hasattr(self.app, 'repeat_btn'):
            self.tray_repeat_action.blockSignals(True)
            self.tray_repeat_action.setChecked(self.app.repeat_btn.isChecked())
            self.tray_repeat_action.blockSignals(False)
        if self.tray_mute_action:
            try:
                self.tray_mute_action.blockSignals(True)
                self.tray_mute_action.setChecked(self.app.audio_output.isMuted())
                self.tray_mute_action.blockSignals(False)
            except Exception:
                pass

    def _rebuild_tray_playlist_menu(self):
        if not self.tray_add_menu:
            return
        self.tray_add_menu.clear()
        # Add to Active
        if getattr(self.app, 'active_playlist', None):
            act = self.tray_add_menu.addAction(f"Add to Active: {self.app.active_playlist.name}")
            act.triggered.connect(lambda checked=False, n=self.app.active_playlist.name: self.app.add_current_to_named_playlist(n))
            self.tray_add_menu.addSeparator()
        # Saved playlists
        if getattr(self.app, 'playlists', None):
            for pl in self.app.playlists:
                act = self.tray_add_menu.addAction(pl.name)
                act.triggered.connect(lambda checked=False, n=pl.name: self.app.add_current_to_named_playlist(n))
        else:
            self.tray_add_menu.addAction("No saved playlists").setEnabled(False)
        # New with current
        self.tray_add_menu.addSeparator()
        new_pl_act = self.tray_add_menu.addAction("New Playlist with Current Track…")
        def _new_with_current():
            name, ok = self.app.QInputDialog.getText(self.app, "New Playlist", "Playlist name:")
            if ok and name:
                from playlist import Playlist as _P
                pl = _P(name)
                item = self._get_current_item()
                if item is not None:
                    pl.items.append(item)
                self.app.playlists.append(pl)
                self.app.active_playlist = pl
                self.app.save_playlists()
                self.app.update_playlist_selector()
                self.app.status_bar.showMessage(f"Created playlist '{name}' and added current track")
        new_pl_act.triggered.connect(_new_with_current)

    def _get_current_item(self):
        try:
            if not self.app.playlist or self.app.current_index < 0 or self.app.current_index >= len(self.app.playlist):
                return None
            return self.app.playlist[self.app.current_index]
        except Exception:
            return None

    def open_current_location(self):
        try:
            if not self.app.playlist or self.app.current_index < 0 or self.app.current_index >= len(self.app.playlist):
                return
            item = self.app.playlist[self.app.current_index]
            path = None
            if isinstance(item, str):
                path = os.path.abspath(item)
            elif isinstance(item, dict) and 'path' in item and isinstance(item['path'], str) and os.path.exists(item['path']):
                path = os.path.abspath(item['path'])
            if path and os.path.exists(path):
                folder = os.path.dirname(path)
                try:
                    subprocess.Popen(["xdg-open", folder])
                except Exception:
                    pass
        except Exception:
            pass
