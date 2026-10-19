import io
import os
from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QPixmap, QPainter

from cover_extractor import CoverExtractor

# Cover-art QThreads that are still running when the app closes must keep a
# strong reference until they finish: destroying a running QThread from
# Python (refcount drop -> C++ ~QThread) calls qFatal and fastfails the
# process with 0xC0000409.
_ORPHAN_THREADS = []

# Same fatal has a second, subtler trigger at PROCESS EXIT: interpreter
# finalization clears this list while a retired thread still runs. The exit
# guard runs before module globals are cleared; see thread_teardown.
from thread_teardown import register_exit_guard as _register_exit_guard  # noqa: E402

_register_exit_guard(lambda: list(_ORPHAN_THREADS))


class CoverArtWorker(QThread):
    finished = Signal(bytes)  # PNG-encoded image payload (may be empty)
    error = Signal(str)

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
            img = CoverExtractor.extract_cover(self.source, is_url=self.is_url)
            data = b""
            if img is not None and not self._abort:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="PNG")
                data = buf.getvalue()
            if self._abort:
                self.finished.emit(b"")
                return
            self.finished.emit(data)
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
                # A dedicated cover URL (Subsonic getCoverArt / Ampache get_art)
                # beats re-parsing full audio streams; fall back to the
                # stream/credential-embedded URL.
                cov = item.get('cover_url')
                if cov:
                    source, is_url = cov, True
                else:
                    url = item.get('url')
                    try:
                        if (not url or "@" not in url) and "cloud_idx" in item and "file_idx" in item:
                            cloud_idx = item.get('cloud_idx')
                            file_idx = item.get('file_idx')
                            if isinstance(cloud_idx, int) and 0 <= cloud_idx < len(self.app.clouds):
                                cloud = self.app.clouds[cloud_idx]
                                files = cloud.get('files', [])
                                if isinstance(file_idx, int) and 0 <= file_idx < len(files):
                                    row = files[file_idx]
                                    base_url = row.get('url')
                                    row_cov = row.get('cover_url')
                                    if isinstance(row_cov, str) and row_cov.strip():
                                        url = row_cov
                                    elif base_url:
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

    def _cloud_row_for(self, item):
        """Return the scanned catalog row backing a queue entry, if any.

        Playlist entries intentionally store only (cloud_idx, file_idx):
        artist/album/name live in the catalog loaded from clouds.json, so
        resolving a row is free and never touches the network.
        """
        try:
            if not isinstance(item, dict):
                return None
            cloud_idx = item.get('cloud_idx')
            file_idx = item.get('file_idx')
            if not isinstance(cloud_idx, int) or not isinstance(file_idx, int):
                return None
            clouds = getattr(self.app, 'clouds', None) or []
            if not (0 <= cloud_idx < len(clouds)):
                return None
            cloud = clouds[cloud_idx]
            if not isinstance(cloud, dict):
                return None
            files = cloud.get('files') or []
            if not (0 <= file_idx < len(files)):
                return None
            row = files[file_idx]
            return row if isinstance(row, dict) else None
        except Exception:
            return None

    def queue_label(self, item):
        """Human label for a queue row: 'Artist – Title', title only when no
        artist is known, basename for plain paths. Resolves cloud rows from
        the in-memory catalog (cloud rows only carry indices); never a
        network/probe call."""
        try:
            row = {}
            if isinstance(item, dict):
                resolved = self._cloud_row_for(item)
                if resolved:
                    row = resolved
                title = item.get('title') or row.get('title')
            else:
                title = None
            if not title:
                title = row.get('name')
            if not title:
                path = (item.get('path')
                        if isinstance(item, dict) else None) \
                    or row.get('path') \
                    or (item if isinstance(item, str) else None)
                if path:
                    title = os.path.splitext(os.path.basename(
                        str(path)))[0]
            artist = (item.get('artist')
                      if isinstance(item, dict) else None) \
                or row.get('artist') or ''
            if title and artist:
                return f"{artist} – {title}"
            return str(title) if title else ''
        except Exception:
            return ''

    def update_metadata_display(self):
        try:
            # Reset labels
            self.app.track_title_label.setText("Title: -")
            self.app.track_artist_label.setText("Artist: -")
            self.app.track_album_label.setText("Album: -")

            if not hasattr(self.app, 'current_index') or self.app.current_index < 0 or self.app.current_index >= len(self.app.playlist):
                self.set_default_cover()
                self._push_web_state()
                return

            current_item = self.app.playlist[self.app.current_index]

            if isinstance(current_item, dict):
                # Queue rows built by the library store only account/file
                # indices. The scanned cloud row (already in memory and
                # persisted in clouds.json) is the metadata cache: resolve
                # from it instead of probing the stream or forcing a rescan.
                row = self._cloud_row_for(current_item) or {}
                title = (current_item.get('title')
                         or current_item.get('name')
                         or row.get('title')
                         or row.get('name')
                         or '')
                artist = current_item.get('artist') or row.get('artist') or ''
                album = current_item.get('album') or row.get('album') or ''
                if not title:
                    path = current_item.get('path') or row.get('path')
                    if path:
                        title = os.path.splitext(
                            os.path.basename(str(path)))[0]
                    else:
                        title = 'Unknown'

                # Cache resolved display values on the live queue row so
                # repeated displays (track changes, tray/web pushes) never
                # need to resolve the catalog again. Placeholder values are
                # not cached, so a later scan can fill them in.
                for key, value in (('title', title),
                                   ('artist', artist),
                                   ('album', album)):
                    if (value
                            and value not in ('Unknown', 'Unknown Artist',
                                              'Unknown Album')
                            and not current_item.get(key)):
                        current_item[key] = value

                if not artist: artist = 'Unknown Artist'
                if not album: album = 'Unknown Album'

                self.app.track_title_label.setText(f"Title: {title}")
                self.app.track_artist_label.setText(f"Artist: {artist}")
                self.app.track_album_label.setText(f"Album: {album}")

                self.update_cover_art(current_item)
                # Tray tooltip only — no per-track "Now Playing" balloon popups
                # (they spam Windows notifications on streaming metadata updates).
                try:
                    if hasattr(self.app, 'tray'):
                        self.app.tray.update_tray_ui()
                except Exception:
                    pass
                self._push_web_state()
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
                        if hasattr(self.app, 'tray'):
                            self.app.tray.update_tray_ui()
                    except Exception:
                        pass
                    self._push_web_state()
                    return

            # Fallback
            self.app.track_title_label.setText(f"Title: {os.path.basename(str(current_item))}" if isinstance(current_item, str) else "Title: Unknown")
            self.app.track_artist_label.setText("Artist: Unknown")
            self.app.track_album_label.setText("Album: Unknown")
            self.set_default_cover()
            self._push_web_state()
        except Exception:
            self.set_default_cover()

    def _push_web_state(self):
        """Mirror metadata changes to the web panel (safe no-op when off)."""
        try:
            push = getattr(self.app, '_push_web_state', None)
            if callable(push):
                push()
        except Exception:
            pass

    # --- Internal ---
    def _post_to_ui(self, fn):
        """Execute fn on the UI thread; safe to call from worker threads.

        Completion handlers for cover fetches run in the emitting context
        (the cover QThread, see on_finished), so every QPixmap/widget
        operation must be marshalled back to the UI thread - touching Qt GUI
        objects from a worker thread corrupts Qt state and later kills the
        process with an access violation (0xC0000005) while the UI thread
        processes events.
        """
        try:
            signal = getattr(self.app, "run_on_ui", None)
        except Exception:
            signal = None
        if signal is not None:
            try:
                signal.emit(fn)
                return
            except Exception:
                pass
        try:
            fn()
        except Exception:
            pass

    def _apply_cover_result(self, png_bytes):
        """Apply an extracted cover payload on the UI thread."""
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
        except Exception:
            try:
                self.set_default_cover()
            except Exception:
                pass

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
            self._cover_thread = thread = QThread(self.app)
            thread.setObjectName("cover-art")  # fatal forensics
            self._cover_worker = worker = CoverArtWorker(source, is_url=is_url)
            worker.setObjectName("cover-art-worker")  # fatal forensics
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            def _cleanup(thread=thread, worker=worker):
                # Do NOT deleteLater() the worker or thread here: the worker's
                # deferred delete would be posted into the cover thread's
                # (already dead) event queue, and stale deferred-delete events
                # referencing destroyed objects crash Qt's event dispatch
                # (0xC0000005 in Qt6Core while the UI thread pumps events).
                # The thread is parented to the widget tree and both objects
                # are owned by their Python wrappers, so dropping every
                # reference here is enough: the worker wrapper frees the
                # never-started QThread safely, and the finished thread is
                # destroyed with its parent.
                # Release only THIS fetch's state; a stale cleanup from an
                # older thread must never clobber a newer fetch's objects.
                if self._cover_thread is thread:
                    self._cover_thread = None
                if self._cover_worker is worker:
                    self._cover_worker = None
                self._cover_inflight_source = None
                if self._pending_cover:
                    src, pending_is_url = self._pending_cover
                    self._pending_cover = None
                    # Create the replacement fetch on the UI thread only, so
                    # the QThread it spawns is parented to a main-thread object.
                    self._post_to_ui(lambda: self._start_cover_art_fetch(src, pending_is_url))
            thread.finished.connect(_cleanup)
            def on_finished(png_bytes):
                # This handler runs in the cover QThread's context (plain
                # callable connection); GUI work must be marshalled back to
                # the UI thread.
                self._cover_inflight_source = None
                self._post_to_ui(lambda: self._apply_cover_result(png_bytes))
            def on_error(msg):
                self._cover_inflight_source = None
            try:
                worker.finished.connect(thread.quit)
            except Exception:
                pass
            worker.finished.connect(on_finished)
            try:
                worker.error.connect(on_error)
            except Exception:
                pass
            self._cover_inflight_source = source
            thread.start()
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
                if self._cover_thread.isRunning():
                    # A running extraction cannot be interrupted. Detach the
                    # thread from the widget tree and keep a strong reference
                    # until it finishes: destroying a running QThread aborts
                    # the process (qFatal in ~QThread).
                    thread, worker = self._cover_thread, self._cover_worker
                    try:
                        thread.setParent(None)
                    except Exception:
                        pass
                    pair = (thread, worker)
                    if pair not in _ORPHAN_THREADS:
                        _ORPHAN_THREADS.append(pair)

                    def _done(pair=pair):
                        # Runs as a queued delivery while thread.finished is
                        # being dispatched. Never release the references
                        # synchronously here: the last reference drop can
                        # destroy the detached thread and the wrapper-owned
                        # worker, and destroying signal machinery while that
                        # very delivery frame is still on the C++ stack
                        # corrupts Qt state - later event processing then
                        # crashes (0xC0000005 in Qt6Core). Defer the release
                        # to a fresh event-loop step instead.
                        def _release(pair=pair):
                            try:
                                if pair[0].isRunning():
                                    # The thread is in its final teardown;
                                    # retry on a later step. Destroying a
                                    # still-running QThread aborts the
                                    # process (qFatal -> 0xC0000409).
                                    QTimer.singleShot(50, lambda p=pair: _release(p))
                                    return
                            except RuntimeError:
                                pass  # underlying C++ object already gone
                            try:
                                pair[0].finished.disconnect()
                            except Exception:
                                pass
                            try:
                                _ORPHAN_THREADS.remove(pair)
                            except ValueError:
                                pass
                        QTimer.singleShot(0, _release)
                    try:
                        thread.finished.connect(_done)
                    except Exception:
                        pass
            self._pending_cover = None
            self._cover_inflight_source = None
        except Exception:
            pass
