"""Library folder watching (mixin).

Watches every media-library root and its subdirectories; a burst of Explorer
writes debounces into one background rescan. The watch list is rebuilt after
the debounce, so new subfolders are picked up and removed folders dropped.

Walking a 48 GB Downloads tree on the UI thread used to freeze startup for
~0.5 s (391 dirs walked, then ~1 ms per addPath). The walk is now
breadth-first with an early stop at the cap, and additions are queued across
event-loop ticks so no single tick pays for the whole watch set.
"""
import os
from collections import deque

from PySide6.QtCore import QFileSystemWatcher, QTimer

# Debounce bursts of file operations into one rescan; cap watch handles.
FOLDER_WATCH_DEBOUNCE_MS = 1200
FOLDER_WATCH_MAX_DIRS = 128
# addPath() costs ~1 ms per directory on Windows: spread large sets out.
FOLDER_WATCH_ADD_BATCH = 16
FOLDER_WATCH_ADD_INTERVAL_MS = 10


def walk_watch_dirs(roots, limit):
    """Existing directories under `roots`, breadth-first, at most `limit`.

    Breadth-first keeps shallow album folders watched even when one deep
    tree (Downloads) has hundreds of nested directories. os.scandir stops
    as soon as the candidate budget is full, so a huge tree is never walked
    in full just to pick a handful of watch paths.
    """
    limit = max(0, int(limit))
    if not limit:
        return []
    dirs = []
    queue = deque()
    seen = set()
    for root in roots or []:
        try:
            if os.path.isdir(root) and root not in seen:
                seen.add(root)
                queue.append(root)
        except OSError:
            continue
    while queue and len(dirs) < limit:
        path = queue.popleft()
        dirs.append(path)
        if len(dirs) >= limit:
            break
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if len(dirs) + len(queue) >= limit:
                        break
                    try:
                        if (entry.is_dir(follow_symlinks=False)
                                and not entry.name.startswith(".")):
                            queue.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return dirs[:limit]


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
        self._pending_watch_paths = []
        self._watch_add_timer = QTimer(self)
        self._watch_add_timer.setSingleShot(True)
        self._watch_add_timer.setInterval(FOLDER_WATCH_ADD_INTERVAL_MS)
        self._watch_add_timer.timeout.connect(self._drain_watch_queue)

    def _watch_directories(self):
        """Existing directories under the library roots, bounded, shallow first."""
        return walk_watch_dirs(getattr(self, "media_folders", None) or [],
                               FOLDER_WATCH_MAX_DIRS)

    def _refresh_folder_watcher(self):
        """Point the watcher at the current library directory set.

        Removals are cheap and applied at once; additions are queued and
        drained a batch per tick so a large library never freezes the UI.
        """
        try:
            watcher = self._folder_watcher
            current = self._watch_directories()
            current_set = set(current)
            for path in watcher.directories():
                if path not in current_set:
                    watcher.removePath(path)
            watched = set(watcher.directories())
            self._pending_watch_paths = [
                path for path in current if path not in watched]
            if len(self._pending_watch_paths) <= FOLDER_WATCH_ADD_BATCH:
                self._drain_watch_queue()
            else:
                self._watch_add_timer.start()
        except Exception:
            pass

    def _drain_watch_queue(self):
        """Add the next small batch of watch paths, then yield to the event loop."""
        try:
            batch = self._pending_watch_paths[:FOLDER_WATCH_ADD_BATCH]
            self._pending_watch_paths = self._pending_watch_paths[
                FOLDER_WATCH_ADD_BATCH:]
            for path in batch:
                try:
                    if os.path.isdir(path):
                        self._folder_watcher.addPath(path)
                except Exception:
                    continue
            if self._pending_watch_paths:
                self._watch_add_timer.start()
            else:
                self._watch_add_timer.stop()
        except Exception:
            self._pending_watch_paths = []

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
