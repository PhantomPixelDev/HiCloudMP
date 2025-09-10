import os
from PySide6.QtCore import Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import QSystemTrayIcon

from cover_extractor import CoverExtractor


class CoverArtWorker(QThread):
    def __init__(self, source, is_url=False):
        super().__init__()
        self.source = source
        self.is_url = is_url
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        try:
            if self._abort:
                self.finished.emit(b"")
                return
            if self.is_url:
                png_bytes = CoverExtractor.extract_cover(url=self.source)
            else:
                png_bytes = CoverExtractor.extract_cover(file_path=self.source)
            if self._abort:
                self.finished.emit(b"")
                return
            self.finished.emit(png_bytes or b"")
        except Exception as e:
            try:
                # Emit empty on error
                self.finished.emit(b"")
            except Exception:
                pass


class MetadataController:
    def __init__(self, app):
        self.app = app
        # Worker state
        self._cover_thread = None
        self._cover_worker = None
        self._pending_cover = None
        self._cover_inflight_source = None
        self._last_cover_source = None
        self._last_cover_time = 0.0

    # --- Public API used by MusicPlayer ---
    def set_default_cover(self):
        try:
            pm = QPixmap(200, 200)
            pm.fill(Qt.darkGray)
            painter = QPainter(pm)
            painter.setPen(Qt.white)
            f = painter.font()
            f.setBold(True)
            f.setPointSize(12)
            painter.setFont(f)
            painter.drawText(pm.rect(), Qt.AlignCenter, "No Cover")
            painter.end()
            self.app.cover_art_label.setPixmap(pm)
            self.app.cover_art_label.setAlignment(Qt.AlignCenter)
        except Exception:
            try:
                pm = QPixmap(200, 200)
                pm.fill(Qt.darkGray)
                self.app.cover_art_label.setPixmap(pm)
                self.app.cover_art_label.setAlignment(Qt.AlignCenter)
            except Exception:
                pass

    def update_cover_art(self, item):
        try:
            source = None
            is_url = False
            if isinstance(item, dict):
                url = item.get('url')
                try:
                    if (not url or "@" not in url) and "cloud_idx" in item and "file_idx" in item:
                        cloud_idx = item.get('cloud_idx')
                        file_idx = item.get('file_idx')
                        if isinstance(cloud_idx, int) and 0 <= cloud_idx < len(self.app.clouds):
                            cloud = self.app.clouds[cloud_idx]
                            files = cloud.get('files', [])
                            if isinstance(file_idx, int) and 0 <= file_idx < len(files):
                                base_url = files[file_idx].get('url')
                                if base_url:
                                    cfg = cloud.get('config', {})
                                    user = cfg.get('webdav_login', '')
                                    pwd = cfg.get('webdav_password', '')
                                    parsed = QUrl(base_url)
                                    if user and pwd and not parsed.userName():
                                        parsed.setUserName(user)
                                        parsed.setPassword(pwd)
                                    try:
                                        url = parsed.toString(QUrl.UrlFormattingOption.FullyEncoded)
                                    except Exception:
                                        url = parsed.toString()
                except Exception:
                    pass
                if url:
                    source = url
                    is_url = True
            elif isinstance(item, str) and os.path.exists(item):
                source = item
                is_url = False

            if source:
                try:
                    import time as _time
                    if self._last_cover_source == source and (_time.time() - self._last_cover_time) < 3.0:
                        return
                    if self._cover_inflight_source == source:
                        return
                    self._last_cover_source = source
                    self._last_cover_time = _time.time()
                except Exception:
                    pass
                self._start_cover_art_fetch(source, is_url)
            else:
                self.set_default_cover()
        except Exception:
            self.set_default_cover()

    def update_metadata_display(self):
        try:
            # Reset labels
            self.app.track_title_label.setText("Title: -")
            self.app.track_artist_label.setText("Artist: -")
            self.app.track_album_label.setText("Album: -")

            if not hasattr(self.app, 'current_index') or self.app.current_index < 0 or self.app.current_index >= len(self.app.playlist):
                self.set_default_cover()
                return

            current_item = self.app.playlist[self.app.current_index]

            if isinstance(current_item, dict):
                title = current_item.get('title', '')
                artist = current_item.get('artist', '')
                album = current_item.get('album', '')
                is_cloud = current_item.get('is_cloud', False) or current_item.get('type') == 'cloud'
                url = current_item.get('url')
                if is_cloud:
                    try:
                        if (not url or "@" not in url) and "cloud_idx" in current_item and "file_idx" in current_item:
                            cloud_idx = current_item.get('cloud_idx')
                            file_idx = current_item.get('file_idx')
                            if isinstance(cloud_idx, int) and 0 <= cloud_idx < len(self.app.clouds):
                                cloud = self.app.clouds[cloud_idx]
                                files = cloud.get('files', [])
                                if isinstance(file_idx, int) and 0 <= file_idx < len(files):
                                    base_url = files[file_idx].get('url')
                                    if base_url:
                                        cfg = cloud.get('config', {})
                                        user = cfg.get('webdav_login', '')
                                        pwd = cfg.get('webdav_password', '')
                                        parsed = QUrl(base_url)
                                        if user and pwd and not parsed.userName():
                                            parsed.setUserName(user)
                                            parsed.setPassword(pwd)
                                        try:
                                            url = parsed.toString(QUrl.UrlFormattingOption.FullyEncoded)
                                        except Exception:
                                            url = parsed.toString()
                    except Exception:
                        pass
                    try:
                        md = CoverExtractor.extract_metadata(url or '', is_url=True)
                        if md.get('title'): title = md['title']
                        if md.get('artist'): artist = md['artist']
                        if md.get('album'): album = md['album']
                    except Exception:
                        pass
                if not title:
                    if 'name' in current_item:
                        title = os.path.splitext(str(current_item['name']))[0]
                    elif 'path' in current_item:
                        title = os.path.splitext(os.path.basename(str(current_item['path'])))[0]
                    else:
                        title = 'Unknown'
                if not artist: artist = 'Unknown Artist'
                if not album: album = 'Unknown Album'

                self.app.track_title_label.setText(f"Title: {title}")
                self.app.track_artist_label.setText(f"Artist: {artist}")
                self.app.track_album_label.setText(f"Album: {album}")

                self.update_cover_art(current_item)
                try:
                    if hasattr(self.app, 'tray'): self.app.tray.update_tray_ui()
                    if hasattr(self.app, 'tray') and self.app.tray.tray_icon:
                        self.app.tray.tray_icon.showMessage("Now Playing", f"{title} — {artist}", QSystemTrayIcon.Information, 3000)
                except Exception:
                    pass
                return

            elif isinstance(current_item, str) and os.path.exists(current_item):
                import mutagen
                audio = mutagen.File(current_item, easy=True)
                if audio:
                    title = audio.get('title', [os.path.basename(current_item)])[0]
                    artist = audio.get('artist', ['Unknown Artist'])[0]
                    album = audio.get('album', ['Unknown Album'])[0]
                    self.app.track_title_label.setText(f"Title: {title}")
                    self.app.track_artist_label.setText(f"Artist: {artist}")
                    self.app.track_album_label.setText(f"Album: {album}")
                    self.update_cover_art(current_item)
                    try:
                        if hasattr(self.app, 'tray'): self.app.tray.update_tray_ui()
                        if hasattr(self.app, 'tray') and self.app.tray.tray_icon:
                            self.app.tray.tray_icon.showMessage("Now Playing", f"{title} — {artist}", QSystemTrayIcon.Information, 3000)
                    except Exception:
                        pass
                    return

            # Fallback
            self.app.track_title_label.setText(f"Title: {os.path.basename(str(current_item))}" if isinstance(current_item, str) else "Title: Unknown")
            self.app.track_artist_label.setText("Artist: Unknown")
            self.app.track_album_label.setText("Album: Unknown")
            self.set_default_cover()
        except Exception:
            self.set_default_cover()

    # --- Internal ---
    def _start_cover_art_fetch(self, source, is_url):
        try:
            # Stop existing
            if self._cover_thread and self._cover_thread.isRunning():
                self._pending_cover = (source, is_url)
                try:
                    if self._cover_worker:
                        self._cover_worker.abort()
                except Exception:
                    pass
                try:
                    self._cover_thread.requestInterruption() if hasattr(self._cover_thread, 'requestInterruption') else None
                    self._cover_thread.quit()
                except Exception:
                    pass
                return
            self._cover_thread = QThread(self.app)
            self._cover_worker = CoverArtWorker(source, is_url=is_url)
            self._cover_worker.moveToThread(self._cover_thread)
            self._cover_thread.started.connect(self._cover_worker.run)
            def _cleanup():
                try:
                    self._cover_worker.deleteLater()
                except Exception:
                    pass
                try:
                    self._cover_thread.deleteLater()
                except Exception:
                    pass
                self._cover_thread = None
                self._cover_worker = None
                self._cover_inflight_source = None
                if self._pending_cover:
                    src, pending_is_url = self._pending_cover
                    self._pending_cover = None
                    QTimer.singleShot(0, lambda: self._start_cover_art_fetch(src, pending_is_url))
            self._cover_thread.finished.connect(_cleanup)
            def on_finished(png_bytes):
                try:
                    if png_bytes:
                        pm = QPixmap()
                        if pm.loadFromData(png_bytes):
                            scaled = pm.scaled(self.app.cover_art_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            self.app.cover_art_label.setPixmap(scaled)
                            self.app.cover_art_label.setAlignment(Qt.AlignCenter)
                        else:
                            self.set_default_cover()
                    else:
                        self.set_default_cover()
                finally:
                    self._cover_inflight_source = None
            def on_error(msg):
                self._cover_inflight_source = None
            try:
                self._cover_worker.finished.connect(self._cover_thread.quit)
            except Exception:
                pass
            self._cover_worker.finished.connect(on_finished)
            try:
                self._cover_worker.error.connect(on_error)
            except Exception:
                pass
            self._cover_inflight_source = source
            self._cover_thread.start()
        except Exception:
            self.set_default_cover()

    def stop(self):
        """Stop any running worker thread (called from MusicPlayer.closeEvent)."""
        try:
            if self._cover_thread and self._cover_thread.isRunning():
                try:
                    if self._cover_worker:
                        self._cover_worker.abort()
                except Exception:
                    pass
                try:
                    self._cover_thread.quit()
                except Exception:
                    pass
                try:
                    self._cover_thread.wait(100)
                except Exception:
                    pass
            self._pending_cover = None
            self._cover_inflight_source = None
        except Exception:
            pass
