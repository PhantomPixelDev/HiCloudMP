"""Library folder watching (mixin).

Watches every media-library root and its subdirectories; a burst of Explorer
writes debounces into one background rescan. The watch list is rebuilt after
the debounce, so new subfolders are picked up and removed folders dropped.
Bounded to keep the OS watch-handle budget sane.
"""
import os

from PySide6.QtCore import QFileSystemWatcher, QTimer

# Debounce bursts of file operations into one rescan; cap watch handles.
FOLDER_WATCH_DEBOUNCE_MS = 1200
FOLDER_WATCH_MAX_DIRS = 500


class FolderWatchMixin:
    """Requires on the mixing class: media_folders, status_bar,
    _start_local_scan()."""

    def _init_folder_watch(self):
        """Create the watcher + debounce timer (called from __init__)."""
        self._folder_watcher = QFileSystemWatcher(self)
        self._folder_watcher.directoryChanged.connect(
            self._on_watched_folder_changed)
        self._folder_watch_timer = QTimer(self)
        self._folder_watch_timer.setSingleShot(True)
        self._folder_watch_timer.setInterval(FOLDER_WATCH_DEBOUNCE_MS)
        self._folder_watch_timer.timeout.connect(
            self._apply_watched_folder_refresh)

    def _watch_directories(self):
        """Existing directories under the library roots, bounded."""
        dirs = []
        for root in list(getattr(self, "media_folders", None) or []):
            try:
                if not os.path.isdir(root):
                    continue
                dirs.append(root)
                for dirpath, dirnames, _files in os.walk(root):
                    dirnames[:] = [d for d in dirnames
                                   if not d.startswith(".")]
                    for d in dirnames:
                        dirs.append(os.path.join(dirpath, d))
                        if len(dirs) >= FOLDER_WATCH_MAX_DIRS:
                            return dirs[:FOLDER_WATCH_MAX_DIRS]
            except Exception:
                continue
        return dirs[:FOLDER_WATCH_MAX_DIRS]

    def _refresh_folder_watcher(self):
        """Point the watcher at the current library directory set."""
        try:
            watcher = self._folder_watcher
            current = self._watch_directories()
            for path in watcher.directories():
                if path not in current:
                    watcher.removePath(path)
            watched = set(watcher.directories())
            for path in current:
                if path not in watched:
                    watcher.addPath(path)
        except Exception:
            pass

    def _on_watched_folder_changed(self, path):
        """A watched directory changed: restart the debounce timer."""
        try:
            self._folder_watch_timer.start()
        except Exception:
            pass

    def _apply_watched_folder_refresh(self):
        """Debounce elapsed: rebuild the watch list and rescan the library."""
        self._refresh_folder_watcher()
        try:
            self._start_local_scan()
        except Exception:
            pass
        self.status_bar.showMessage(
            "Library folder changed - refreshing…", 3000)
