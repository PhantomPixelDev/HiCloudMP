import os
import threading
import requests
from PySide6.QtCore import QObject, Signal
from io import BytesIO
from hicloudmp.core.cover_extractor import CoverExtractor
from hicloudmp.cloud.cloud_handlers import CLOUD_TYPES
from hicloudmp.utils import is_music_file

class LibraryScanWorker:
    """Walks media folders and hands every result to `dispatch`.

    Deliberately NOT a QObject on a QThread: results reach the UI thread
    through MusicPlayer.run_on_ui (a queued callable bridge), so there is
    no Qt object affinity on a second thread and none of the
    deleteLater/destroy-while-running races that abort native processes.
    Runs as a plain daemon thread; abort() is checked per folder/chunk.
    """

    CHUNK = 500

    def __init__(self, folders, dispatch):
        self.folders = list(folders or [])
        self._dispatch = dispatch    # fn(callable) -> run on the UI thread
        self._abort = False
        self._indexed_total = 0
        self.on_folder = None        # fn(folder, subdirs)
        self.on_files = None         # fn(folder, tree_chunk)
        self.on_indexed = None       # fn(paths)
        self.on_tags = None          # fn([(path, title, artist, album)])
        self.on_finished = None      # fn(total)

    def run(self):
        self._indexed_total = 0
        try:
            for folder in self.folders:
                if self._abort:
                    break
                try:
                    self._walk_folder(folder)
                except Exception as e:
                    print(f"Library scan error in {folder}: {e}")
        finally:
            self._emit(self.on_finished, self._indexed_total)

    def _walk_folder(self, folder):
        subdirs = []
        top_files = []
        for root, dirs, files in os.walk(folder):
            if self._abort:
                return
            if root == folder:
                subdirs = list(dirs)
                top_files = [os.path.join(folder, f) for f in files
                             if is_music_file(f)]
            else:
                # deeper levels only feed the search index
                chunk = [os.path.join(root, f) for f in files if is_music_file(f)]
                if chunk:
                    self._indexed_total += len(chunk)
                    self._emit(self.on_indexed, chunk)
                    self._emit_tags(chunk)
        self._emit(self.on_folder, folder, subdirs)
        self._indexed_total += len(top_files)
        if top_files:
            self._emit(self.on_indexed, list(top_files))
            self._emit_tags(top_files)
        for i in range(0, len(top_files), self.CHUNK):
            if self._abort:
                return
            self._emit(self.on_files, folder, top_files[i:i + self.CHUNK])

    def _emit_tags(self, paths):
        """Read embedded tags for a chunk of files (worker thread) and hand
        (path, title, artist, album) pairs to the UI thread. Per-file errors
        are swallowed into neutral cells; a broken file must never break the
        scan."""
        pairs = []
        for path in paths:
            title, artist, album = self._read_tags(path)
            pairs.append((path, title, artist, album))
        if pairs:
            self._emit(self.on_tags, pairs)

    @staticmethod
    def _read_tags(path):
        try:
            import mutagen
            audio = mutagen.File(path, easy=True)
            if audio is None:
                return ("", "", "")

            def first(*keys):
                # easy=True maps keys for most formats, but not for WAVE +
                # embedded ID3 (frames stay raw TIT2/TPE1/TALB there). A
                # raw frame has no len(); index it instead.
                for key in keys:
                    value = audio.get(key)
                    if value is None:
                        continue
                    try:
                        text = value[0]
                    except (IndexError, KeyError, TypeError):
                        continue
                    if text:
                        return str(text)
                return ""

            return (first("title", "TIT2"),
                    first("artist", "TPE1"),
                    first("album", "TALB"))
        except Exception:
            return ("", "", "")

    def _emit(self, cb, *args):
        if cb is not None:
            self._dispatch(lambda cb=cb, a=args: cb(*a))

    def abort(self):
        self._abort = True


class DownloadWorker(QObject):
    """Worker for downloading files from cloud storage"""
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int)
    
    def __init__(self, url, path, auth=None):
        super().__init__()
        self.url = url
        self.path = path
        self.auth = auth
        self._abort = False

    def run(self):
        try:
            with requests.get(self.url, stream=True, auth=self.auth, timeout=(10, 30)) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(self.path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._abort:
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                # Calculate percentage if content-length is available
                                progress = int(100 * downloaded / total_size)
                                self.progress.emit(progress)
                            else:
                                # Otherwise just show how many kilobytes downloaded
                                self.progress.emit(downloaded // 1024)
            
            self.finished.emit(self.path)
        except Exception as e:
            self.error.emit(str(e))

    def abort(self):
        self._abort = True


class CoverArtWorker(QObject):
    """Worker to extract cover art in the background.
    Emits finished with PNG bytes or None on error.
    """
    finished = Signal(object)  # bytes or None
    error = Signal(str)

    def __init__(self, source, is_url=False):
        super().__init__()
        self.source = source
        self.is_url = is_url
        self._abort = False

    def run(self):
        try:
            if self._abort:
                return
            img = CoverExtractor.extract_cover(self.source, is_url=self.is_url)
            if img is None:
                self.finished.emit(None)
                return
            # Convert PIL Image to PNG bytes
            try:
                if hasattr(img, 'mode') and img.mode != 'RGB':
                    img = img.convert('RGB')
                bio = BytesIO()
                img.save(bio, format='PNG')
                self.finished.emit(bio.getvalue())
            except Exception as e:
                self.error.emit(str(e))
                self.finished.emit(None)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(None)

    def abort(self):
        self._abort = True


class ScanCloudWorker(QObject):
    """Worker for scanning cloud storages in background"""
    progress_updated = Signal(int, str, str)  # progress %, status message, cloud name
    scan_finished = Signal(int, list)  # cloud index, files list
    scan_error = Signal(int, str)  # cloud index, error message
    
    def __init__(self, cloud_index, cloud_data):
        super().__init__()
        self.cloud_index = cloud_index
        self.cloud_data = cloud_data
        self._abort = False
    
    def run(self):
        try:
            cloud_type = self.cloud_data["type"]
            handler_cls = CLOUD_TYPES.get(cloud_type)
            
            if not handler_cls:
                self.scan_error.emit(self.cloud_index, f"Unsupported cloud type: {cloud_type}")
                return
            
            handler = handler_cls(self.cloud_data["config"])
            
            # Patch handler to emit progress for every file found
            orig_scan_dir = getattr(handler, '_scan_directory', None)
            orig_scan_path = getattr(handler, '_scan_path', None)
            worker_self = self
            def scan_dir_with_emit(client, path):
                files = orig_scan_dir(client, path)
                for f in files:
                    if worker_self._abort:
                        break
                    worker_self.progress_updated.emit(int(handler.get_progress()), f"File: {f.get('path', f)}", self.cloud_data["name"])
                return files
            def scan_path_with_emit(dbx, path):
                files = orig_scan_path(dbx, path)
                for f in files:
                    if worker_self._abort:
                        break
                    worker_self.progress_updated.emit(int(handler.get_progress()), f"File: {f.get('path', f)}", self.cloud_data["name"])
                return files
            if orig_scan_dir:
                handler._scan_directory = scan_dir_with_emit
            if orig_scan_path:
                handler._scan_path = scan_path_with_emit
            
            # Start a monitoring thread
            self._abort = False
            monitor_thread = threading.Thread(target=self._monitor_progress, args=(handler,))
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Run the scan
            handler.scan()
            
            # Signal we're done
            self._abort = True
            # Wait for monitor thread to exit, but don't block forever
            for _ in range(50):  # Wait up to 1 second total (50 x 0.02)
                if not monitor_thread.is_alive():
                    break
                threading.Event().wait(0.02)
            # Only emit if we haven't aborted
            self.scan_finished.emit(self.cloud_index, handler.get_links())
        
        except Exception as e:
            self.scan_error.emit(self.cloud_index, str(e))
    
    def _monitor_progress(self, handler):
        """Monitor and report progress of the scan operation"""
        last_progress = -1
        last_status = ""
        
        while not self._abort:
            try:
                # Get current progress
                progress = handler.get_progress()
                status = handler.get_status()
                
                # Always emit progress updates at regular intervals
                current_progress = int(progress)
                
                # Only emit if there's a change or every 5 ticks (1 sec)
                if current_progress != last_progress or status != last_status:
                    self.progress_updated.emit(current_progress, status, self.cloud_data["name"])
                    last_progress = current_progress
                    last_status = status
            except Exception as e:
                print(f"Error in progress monitoring: {e}")
            
            # Very short sleep to make UI more responsive
            threading.Event().wait(0.02)  # Faster UI updates
    
    def abort(self):
        self._abort = True 