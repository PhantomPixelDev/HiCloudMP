import os
from PySide6.QtWidgets import QTreeWidgetItem, QStyle, QAbstractItemView
from PySide6.QtCore import Qt

class LibraryView:
    def __init__(self, app):
        self.app = app  # MusicPlayer instance

    def on_library_item_clicked(self, item, column):
        """Double-click on a library entry. A FILE always APPENDS to the
        current queue and plays the new row (users build a queue across
        clicks; replacing it silently was reported as a bug on v1.0.4).
        Playlists/categories keep their explicit load behavior."""
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data["type"] == "local_file":
            path = data["path"]
            self.app.playlist.append(path)
            self.app.playlist_widget.addQueueRow(
                *self.app.meta.queue_cells(path))
            self.app.current_index = len(self.app.playlist) - 1
            self.app.play()
        elif data["type"] == "cloud_file":
            cloud_idx = data["cloud_index"]
            file_idx = data["file_index"]
            row = {"type": "cloud",
                   "cloud_idx": cloud_idx,
                   "file_idx": file_idx}
            self.app.playlist.append(row)
            cloud = self.app.clouds[cloud_idx]
            file_info = cloud["files"][file_idx]
            title, artist, album = self.app.meta.queue_cells(row)
            if not title:
                title = os.path.basename(file_info["path"])
            self.app.playlist_widget.addQueueRow(title, artist, album)
            self.app.current_index = len(self.app.playlist) - 1
            self.app.play()
        elif data["type"] == "playlist":
            self.app.load_playlist_by_id(data["id"])
        elif data["type"] == "new_playlist":
            self.app.new_playlist()

    def update_library_tree(self):
        tree = self.app.library_tree
        tree.clear()
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._insert_local_root(0)
        self._insert_playlists_root(1)
        self._insert_cloud_root(2)

    def refresh_local_section(self):
        """Re-render only the Local Media subtree from the store (cheap;
        called per background-scan batch)."""
        tree = self.app.library_tree
        if self._in_search_mode():
            return  # don't stomp on search results mid-typing
        for i in range(tree.topLevelItemCount()):
            data = tree.topLevelItem(i).data(0, Qt.UserRole)
            if data and data.get("type") == "local_root":
                tree.takeTopLevelItem(i)
                self._insert_local_root(i)
                return
        self.update_library_tree()

    def _in_search_mode(self):
        try:
            return bool(self.app.search_input.text().strip())
        except Exception:
            return False

    def _insert_local_root(self, position):
        tree = self.app.library_tree
        folder_icon = self.app.style().standardIcon(QStyle.SP_DirIcon)
        file_icon = self.app.style().standardIcon(QStyle.SP_FileIcon)
        local_root = QTreeWidgetItem(["Local Media"])
        local_root.setExpanded(True)
        local_root.setData(0, Qt.UserRole, {"type": "local_root"})
        tree.insertTopLevelItem(position, local_root)
        # Folders and files come from the store - never walked here
        data = self.app.library_store.local_tree_data()
        for folder in self.app.media_folders:
            folder_item = QTreeWidgetItem(local_root, [os.path.basename(folder)])
            folder_item.setData(0, Qt.UserRole, {"type": "local_folder", "path": folder})
            folder_item.setIcon(0, folder_icon)
            entry = data.get(folder, {})
            for dir_name in entry.get("subdirs", []):
                dir_path = os.path.join(folder, dir_name)
                subdir_item = QTreeWidgetItem(folder_item, [dir_name])
                subdir_item.setData(0, Qt.UserRole, {"type": "local_folder", "path": dir_path})
                subdir_item.setIcon(0, folder_icon)
            for fpath in entry.get("files", []):
                title, artist, album = self._local_cells(fpath)
                file_item = QTreeWidgetItem(
                    folder_item, [title, artist, album])
                file_item.setData(0, Qt.UserRole, {"type": "local_file", "path": fpath})
                file_item.setIcon(0, file_icon)
        open_folder_item = QTreeWidgetItem(local_root, ["Open Folder..."])
        open_folder_item.setData(0, Qt.UserRole, {"type": "open_folder"})
        open_folder_item.setIcon(0, folder_icon)

    def _local_cells(self, fpath):
        """(name, artist, album) cells for a local file row. Tags come from
        the scan cache; the Name cell falls back to the basename."""
        try:
            cached = self.app.library_store.tags(fpath)
        except Exception:
            cached = ("", "", "")
        title = cached[0] or os.path.splitext(
            os.path.basename(fpath))[0]
        return (title, cached[1], cached[2])

    def _insert_playlists_root(self, position):
        tree = self.app.library_tree
        folder_icon = self.app.style().standardIcon(QStyle.SP_DirIcon)
        file_icon = self.app.style().standardIcon(QStyle.SP_FileIcon)
        playlists_root = QTreeWidgetItem(["Playlists"])
        playlists_root.setExpanded(True)
        tree.insertTopLevelItem(position, playlists_root)
        for playlist in self.app.playlists:
            playlist_item = QTreeWidgetItem(playlists_root, [playlist.name])
            playlist_item.setData(0, Qt.UserRole, {"type": "playlist", "id": playlist.id})
            playlist_item.setIcon(0, file_icon)
        new_playlist_item = QTreeWidgetItem(playlists_root, ["+ New Playlist"])
        new_playlist_item.setData(0, Qt.UserRole, {"type": "new_playlist"})
        new_playlist_item.setIcon(0, folder_icon)

    def _insert_cloud_root(self, position):
        tree = self.app.library_tree
        folder_icon = self.app.style().standardIcon(QStyle.SP_DirIcon)
        file_icon = self.app.style().standardIcon(QStyle.SP_FileIcon)
        cloud_root = QTreeWidgetItem(["Cloud Media"])
        cloud_root.setExpanded(True)
        tree.insertTopLevelItem(position, cloud_root)
        for idx, cloud in enumerate(self.app.clouds):
            cloud_item = QTreeWidgetItem(cloud_root, [cloud["name"]])
            cloud_item.setData(0, Qt.UserRole, {"type": "cloud_account", "index": idx})
            cloud_item.setIcon(0, folder_icon)
            if "files" in cloud and cloud["files"]:
                folder_structure = {}
                for file_idx, file in enumerate(cloud["files"]):
                    path = file["path"].replace('//', '/').strip('/')
                    parts = path.split("/")
                    if len(parts) > 1:
                        folder = "/".join(parts[:-1]) or "/"
                        filename = parts[-1]
                    else:
                        folder = "/"
                        filename = path
                    if folder not in folder_structure:
                        folder_structure[folder] = []
                    folder_structure[folder].append({"name": filename, "file_index": file_idx})
                for folder, files in folder_structure.items():
                    if not folder:
                        continue
                    folder_item = QTreeWidgetItem(cloud_item, [folder])
                    folder_item.setData(0, Qt.UserRole, {
                        "type": "cloud_folder",
                        "cloud_index": idx,
                        "folder": folder,
                        "file_indices": [f["file_index"] for f in files]
                    })
                    folder_item.setIcon(0, folder_icon)
                    for f in files:
                        file_info = cloud["files"][f["file_index"]]
                        # Catalog cells: title comes from `name`
                        # (Subsonic rows carry it there), the remote
                        # filename is only the fallback cell.
                        title = str(file_info.get("name")
                                    or f["name"] or "")
                        artist = str(file_info.get("artist") or "")
                        album = str(file_info.get("album") or "")
                        file_item = QTreeWidgetItem(
                            folder_item, [title, artist, album])
                        file_item.setData(0, Qt.UserRole, {
                            "type": "cloud_file",
                            "cloud_index": idx,
                            "file_index": f["file_index"]
                        })
                        file_item.setIcon(0, file_icon)

    def search_music(self):
        """Search the in-memory index (local) + cloud file lists.
        Never walks the filesystem."""
        term = self.app.search_input.text().strip().lower()
        if not term:
            self.update_library_tree()
            return
        self.app.status_bar.showMessage(f"Searching for: {term}")
        tree = self.app.library_tree
        tree.clear()
        search_root = QTreeWidgetItem(tree, ["Search Results"])
        search_root.setExpanded(True)
        # Local: from the store index
        local_results = QTreeWidgetItem(search_root, ["Local Media"])
        local_results.setExpanded(True)
        found_local = False
        for path in self.app.library_store.search_local(term):
            title, artist, album = self._local_cells(path)
            result_item = QTreeWidgetItem(
                local_results, [os.path.basename(path), artist, album])
            result_item.setData(0, Qt.UserRole, {"type": "local_file", "path": path})
            found_local = True
        if not found_local:
            QTreeWidgetItem(local_results, ["No matches found"])
        # Cloud: already in memory
        cloud_results = QTreeWidgetItem(search_root, ["Cloud Media"])
        cloud_results.setExpanded(True)
        found_cloud = False
        for cloud_idx, cloud in enumerate(self.app.clouds):
            if "files" in cloud and cloud["files"]:
                for file_idx, file in enumerate(cloud["files"]):
                    file_name = os.path.basename(file["path"])
                    if term in file_name.lower():
                        result_item = QTreeWidgetItem(
                            cloud_results,
                            [f"{file_name} ({cloud['name']})",
                             str(file.get("artist") or ""),
                             str(file.get("album") or "")])
                        result_item.setData(0, Qt.UserRole, {"type": "cloud_file", "cloud_index": cloud_idx, "file_index": file_idx})
                        found_cloud = True
        if not found_cloud:
            QTreeWidgetItem(cloud_results, ["No matches found"])
        self.app.status_bar.showMessage(f"Search complete: {term}")
