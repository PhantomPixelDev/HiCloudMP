"""In-memory library model.

The library tree renders from this store; the store is filled by
LibraryScanWorker (background thread). Nothing here touches the
filesystem on the UI thread, and search reads the index, never the disk.
"""


class LibraryStore:
    """Local library data: tree-shaped (per media folder) + a flat search
    index of every music file found recursively."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._folders = {}   # folder path -> {"subdirs": [names], "files": [paths]}
        self._all = []       # every music file path found recursively

    # -------------------------------------------------- worker callbacks
    def add_folder(self, folder, subdirs):
        """(Re)register a media folder; a rescan replaces its entry."""
        self._folders[folder] = {"subdirs": list(subdirs or []), "files": []}

    def add_tree_files(self, folder, chunk):
        entry = self._folders.get(folder)
        if entry is not None and chunk:
            entry["files"].extend(chunk)

    def add_indexed(self, paths):
        if paths:
            self._all.extend(paths)

    # ------------------------------------------------------------- reads
    def local_tree_data(self):
        return {f: {"subdirs": list(v["subdirs"]), "files": list(v["files"])}
                for f, v in self._folders.items()}

    def local_count(self):
        return len(self._all)

    def search_local(self, term):
        """Case-insensitive basename substring match over the index."""
        term = (term or "").strip().lower()
        if not term:
            return []
        import os
        return [p for p in self._all if term in os.path.basename(p).lower()]
