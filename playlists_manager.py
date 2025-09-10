import os
import json
from datetime import datetime
from PySide6.QtWidgets import QInputDialog, QMessageBox
from PySide6.QtCore import Qt
from playlist import Playlist

class PlaylistsManager:
    def __init__(self, app):
        self.app = app  # MusicPlayer instance

    def add_current_to_named_playlist(self, name: str):
        if not name:
            return
        item = self._get_current_item()
        if item is None:
            self.app.status_bar.showMessage("No current track to add")
            return
        target = None
        for p in self.app.playlists:
            if p.name == name:
                target = p
                break
        if not target:
            self.app.status_bar.showMessage(f"Playlist not found: {name}")
            return
        try:
            if isinstance(item, str):
                if item not in target.items:
                    target.items.append(item)
            else:
                target.items.append(item)
        except Exception:
            target.items.append(item)
        target.modified = datetime.now().isoformat()
        self.app.save_playlists()
        if getattr(self.app, 'active_playlist', None) and self.app.active_playlist.id == target.id:
            self.app.playlist.append(item)
            if isinstance(item, dict):
                display = "(Cloud)"
                try:
                    cloud_idx = item.get('cloud_idx')
                    file_idx = item.get('file_idx')
                    if isinstance(cloud_idx, int) and isinstance(file_idx, int):
                        cloud = self.app.clouds[cloud_idx]
                        file_info = cloud.get('files', [])[file_idx]
                        display = os.path.basename(file_info.get('path', 'Cloud File')) + " (Cloud)"
                except Exception:
                    pass
                self.app.playlist_widget.addItem(display)
            else:
                self.app.playlist_widget.addItem(os.path.basename(item))
        self.app.status_bar.showMessage(f"Added current track to playlist: {name}")

    def new_playlist(self):
        name, ok = QInputDialog.getText(self.app, "New Playlist", "Playlist name:")
        if ok and name:
            playlist = Playlist(name)
            if self.app.playlist:
                playlist.items = self.app.playlist.copy()
            self.app.playlists.append(playlist)
            self.app.active_playlist = playlist
            self.app.save_playlists()
            self.app.update_library_tree()
            self.app.update_playlist_selector()
            self.app.status_bar.showMessage(f"Created new playlist: {name}")

    def save_current_playlist(self):
        if not self.app.active_playlist:
            self.new_playlist()
            return
        self.app.active_playlist.items = self.app.playlist.copy()
        self.app.active_playlist.modified = datetime.now().isoformat()
        self.app.save_playlists()
        self.app.status_bar.showMessage(f"Saved playlist: {self.app.active_playlist.name}")

    def delete_current_playlist(self):
        if not self.app.active_playlist:
            return
        confirm = QMessageBox.question(
            self.app,
            "Delete Playlist",
            f"Are you sure you want to delete the playlist '{self.app.active_playlist.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.delete_playlist(self.app.active_playlist.id)

    def load_playlist(self, playlist: Playlist):
        self.app.active_playlist = playlist
        self.app.playlist = self.app.active_playlist.items
        self.app.playlist_widget.clear()
        for item in self.app.playlist:
            if isinstance(item, dict):
                if item.get("type") == "cloud":
                    cloud_idx = item.get("cloud_idx")
                    file_idx = item.get("file_idx")
                    if cloud_idx < 0 or cloud_idx >= len(self.app.clouds):
                        continue
                    cloud = self.app.clouds[cloud_idx]
                    files = cloud.get("files", [])
                    if file_idx < 0 or file_idx >= len(files):
                        continue
                    file_info = files[file_idx]
                    file_name = os.path.basename(file_info["path"])
                    self.app.playlist_widget.addItem(f"{file_name} (Cloud)")
            else:
                if os.path.exists(item):
                    self.app.playlist_widget.addItem(os.path.basename(item))
        if self.app.playlist:
            self.app.current_index = 0
            self.app.status_bar.showMessage(f"Loaded playlist: {playlist.name}")

    def load_playlist_by_id(self, playlist_id: str):
        for playlist in self.app.playlists:
            if playlist.id == playlist_id:
                self.load_playlist(playlist)
                self.app.update_playlist_selector()
                return

    def delete_playlist(self, playlist_id: str):
        for i, playlist in enumerate(self.app.playlists):
            if playlist.id == playlist_id:
                del self.app.playlists[i]
                if self.app.active_playlist and self.app.active_playlist.id == playlist_id:
                    self.app.active_playlist = None
                self.app.save_playlists()
                self.app.update_library_tree()
                self.app.update_playlist_selector()
                self.app.status_bar.showMessage(f"Deleted playlist: {playlist.name}")
                return

    # Helpers
    def _get_current_item(self):
        try:
            if not self.app.playlist or self.app.current_index < 0 or self.app.current_index >= len(self.app.playlist):
                return None
            return self.app.playlist[self.app.current_index]
        except Exception:
            return None
