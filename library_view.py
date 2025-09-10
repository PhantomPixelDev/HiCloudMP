import os
from PySide6.QtWidgets import QMenu, QTreeWidgetItem, QMessageBox, QStyle
from PySide6.QtCore import Qt
from utils import is_music_file, scan_music_files

class LibraryView:
    def __init__(self, app):
        self.app = app  # MusicPlayer instance

    def on_library_item_clicked(self, item, column):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data["type"] == "local_file":
            path = data["path"]
            self.app.playlist = [path]
            self.app.playlist_widget.clear()
            self.app.playlist_widget.addItem(os.path.basename(path))
            self.app.current_index = 0
            self.app.play()
        elif data["type"] == "cloud_file":
            cloud_idx = data["cloud_index"]
            file_idx = data["file_index"]
            self.app.playlist = [{
                "type": "cloud",
                "cloud_idx": cloud_idx,
                "file_idx": file_idx
            }]
            self.app.playlist_widget.clear()
            cloud = self.app.clouds[cloud_idx]
            file_info = cloud["files"][file_idx]
            file_name = os.path.basename(file_info["path"])
            self.app.playlist_widget.addItem(f"{file_name} (Cloud)")
            self.app.current_index = 0
            self.app.play()
        elif data["type"] == "playlist":
            self.app.load_playlist_by_id(data["id"])
        elif data["type"] == "new_playlist":
            self.app.new_playlist()

    def update_library_tree(self):
        self.app.library_tree.clear()
        self.app.library_tree.setSelectionMode(self.app.library_tree.ExtendedSelection)
        folder_icon = self.app.style().standardIcon(QStyle.SP_DirIcon)
        file_icon = self.app.style().standardIcon(QStyle.SP_FileIcon)
        # Local folders
        local_root = QTreeWidgetItem(self.app.library_tree, ["Local Media"])
        local_root.setExpanded(True)
        local_root.setData(0, Qt.UserRole, {"type": "local_root"})
        # Playlists
        playlists_root = QTreeWidgetItem(self.app.library_tree, ["Playlists"])
        playlists_root.setExpanded(True)
        for playlist in self.app.playlists:
            playlist_item = QTreeWidgetItem(playlists_root, [playlist.name])
            playlist_item.setData(0, Qt.UserRole, {"type": "playlist", "id": playlist.id})
            playlist_item.setIcon(0, file_icon)
        new_playlist_item = QTreeWidgetItem(playlists_root, ["+ New Playlist"])
        new_playlist_item.setData(0, Qt.UserRole, {"type": "new_playlist"})
        new_playlist_item.setIcon(0, folder_icon)
        # Local folders and files
        for folder in self.app.media_folders:
            folder_item = QTreeWidgetItem(local_root, [os.path.basename(folder)])
            folder_item.setData(0, Qt.UserRole, {"type": "local_folder", "path": folder})
            folder_item.setIcon(0, folder_icon)
            try:
                for root, dirs, files in os.walk(folder):
                    if root == folder:
                        for dir_name in dirs:
                            dir_path = os.path.join(root, dir_name)
                            subdir_item = QTreeWidgetItem(folder_item, [dir_name])
                            subdir_item.setData(0, Qt.UserRole, {"type": "local_folder", "path": dir_path})
                            subdir_item.setIcon(0, folder_icon)
                        for file in files:
                            if is_music_file(file):
                                file_path = os.path.join(root, file)
                                file_item = QTreeWidgetItem(folder_item, [file])
                                file_item.setData(0, Qt.UserRole, {"type": "local_file", "path": file_path})
                                file_item.setIcon(0, file_icon)
            except Exception as e:
                print(f"Error scanning subfolders: {e}")
        open_folder_item = QTreeWidgetItem(local_root, ["Open Folder..."])
        open_folder_item.setData(0, Qt.UserRole, {"type": "open_folder"})
        open_folder_item.setIcon(0, folder_icon)
        # Cloud section
        cloud_root = QTreeWidgetItem(self.app.library_tree, ["Cloud Media"])
        cloud_root.setExpanded(True)
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
                        file_item = QTreeWidgetItem(folder_item, [f["name"]])
                        file_item.setData(0, Qt.UserRole, {
                            "type": "cloud_file",
                            "cloud_index": idx,
                            "file_index": f["file_index"]
                        })
                        file_item.setIcon(0, file_icon)

    def search_music(self):
        term = self.app.search_input.text().strip().lower()
        if not term:
            self.update_library_tree()
            return
        self.app.status_bar.showMessage(f"Searching for: {term}")
        self.app.library_tree.clear()
        search_root = QTreeWidgetItem(self.app.library_tree, ["Search Results"])
        search_root.setExpanded(True)
        # Local search
        local_results = QTreeWidgetItem(search_root, ["Local Media"])
        local_results.setExpanded(True)
        found_local = False
        for folder in self.app.media_folders:
            for root, _, files in os.walk(folder):
                for file in files:
                    if is_music_file(file) and term in file.lower():
                        full_path = os.path.join(root, file)
                        result_item = QTreeWidgetItem(local_results, [file])
                        result_item.setData(0, Qt.UserRole, {"type": "local_file", "path": full_path})
                        found_local = True
        if not found_local:
            QTreeWidgetItem(local_results, ["No matches found"])
        # Cloud search
        cloud_results = QTreeWidgetItem(search_root, ["Cloud Media"])
        cloud_results.setExpanded(True)
        found_cloud = False
        for cloud_idx, cloud in enumerate(self.app.clouds):
            if "files" in cloud and cloud["files"]:
                for file_idx, file in enumerate(cloud["files"]):
                    file_name = os.path.basename(file["path"])
                    if term in file_name.lower():
                        result_item = QTreeWidgetItem(cloud_results, [f"{file_name} ({cloud['name']})"])
                        result_item.setData(0, Qt.UserRole, {"type": "cloud_file", "cloud_index": cloud_idx, "file_index": file_idx})
                        found_cloud = True
        if not found_cloud:
            QTreeWidgetItem(cloud_results, ["No matches found"])
        self.app.status_bar.showMessage(f"Search complete: {term}")
