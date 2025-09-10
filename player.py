import os
import io
import json
import time
import random
import tempfile
from urllib.parse import urlparse
from platformdirs import user_data_dir, user_cache_dir
from cover_extractor import CoverExtractor
import subprocess
from tray import TrayController
from metadata import MetadataController
from playlists_manager import PlaylistsManager
from library_view import LibraryView

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSlider, QListWidget, QFileDialog, QMessageBox, QTreeWidget, 
    QTreeWidgetItem, QSplitter, QLineEdit, QDialog, QFormLayout, QTabWidget, 
    QToolButton, QStatusBar, QStyle, QFrame, QMenu, QProgressBar, QSystemTrayIcon,
    QComboBox, QInputDialog, QListWidgetItem, QRadioButton, QDialogButtonBox, QProgressDialog,
    QCheckBox, QWidgetAction
)
from PySide6.QtGui import QPainter
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QUrl, QSize, QEvent, QSettings
from PySide6.QtGui import QIcon, QAction, QKeySequence, QKeyEvent, QPalette, QColor, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaFormat

# Import custom modules
from utils import (
    is_music_file, scan_music_files, format_time, 
    MEDIA_FOLDERS_FILE, CLOUD_FILES_FILE, PLAYLISTS_FILE,
    HAS_WIN32
)
from cloud_handlers import CLOUD_TYPES
from playlist import Playlist
from dialogs import AddCloudDialog, EditCloudDialog
from workers import DownloadWorker, ScanCloudWorker, CoverArtWorker

from web_control import WebControlServer

class CloudAccountsDialog(QDialog):
    def __init__(self, parent, clouds):
        super().__init__(parent)
        self.setWindowTitle("Cloud Accounts")
        self.resize(500, 350)
        self.clouds = clouds
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.refresh_list()
        layout.addWidget(self.list_widget)
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        remove_btn = QPushButton("Remove")
        add_btn.clicked.connect(self.add_cloud)
        edit_btn.clicked.connect(self.edit_cloud)
        remove_btn.clicked.connect(self.remove_cloud)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(remove_btn)
        layout.addLayout(btn_layout)
    def refresh_list(self):
        self.list_widget.clear()
        for cloud in self.clouds:
            status = "Connected" if cloud.get("files") else "Not Synced"
            last_sync = cloud.get("last_sync", "Never")
            self.list_widget.addItem(f"{cloud['name']} ({cloud['type']}) - {status} | Last Sync: {last_sync}")
    def add_cloud(self):
        dlg = AddCloudDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if data["type"] != "unknown":
                self.clouds.append({
                    "type": data["type"],
                    "name": data["name"],
                    "config": data["config"],
                    "files": [],
                    "last_sync": "Never"
                })
                self.refresh_list()
    def edit_cloud(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.clouds):
            return
        cloud = self.clouds[row]
        dlg = EditCloudDialog(cloud, self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            cloud["name"] = data["name"]
            cloud["config"] = data["config"]
            self.refresh_list()
    def remove_cloud(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.clouds):
            return
        del self.clouds[row]
        self.refresh_list()

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(400, 300)
        self.settings = QSettings("HiCloudMP", "HiCloudMP")
        layout = QVBoxLayout(self)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.settings.value("volume", 70, int))
        layout.addWidget(QLabel("Default Volume"))
        layout.addWidget(self.volume_slider)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText(self.settings.value("theme", "Dark"))
        layout.addWidget(QLabel("Theme"))
        layout.addWidget(self.theme_combo)
        self.download_folder_edit = QLineEdit(self.settings.value("download_folder", ""))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_folder)
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.download_folder_edit)
        folder_layout.addWidget(browse_btn)
        layout.addWidget(QLabel("Download Folder"))
        layout.addLayout(folder_layout)
        # Cloud account management
        cloud_btn = QPushButton("Manage Cloud Accounts")
        cloud_btn.clicked.connect(self.open_cloud_accounts)
        layout.addWidget(cloud_btn)
        # Add web interface toggle
        self.web_checkbox = QCheckBox("Enable Web Interface (LAN control)")
        self.web_checkbox.setChecked(self.settings.value("web_interface", False, bool))
        layout.addWidget(self.web_checkbox)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        self.parent = parent
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.download_folder_edit.setText(folder)
    def save_settings(self):
        self.settings.setValue("volume", self.volume_slider.value())
        self.settings.setValue("theme", self.theme_combo.currentText())
        self.settings.setValue("download_folder", self.download_folder_edit.text())
        self.settings.setValue("web_interface", self.web_checkbox.isChecked())
    def open_cloud_accounts(self):
        if self.parent:
            dlg = CloudAccountsDialog(self, self.parent.clouds)
            dlg.exec()

    pass


class MusicPlayer(QMainWindow):
    cloud_file_downloaded = Signal(str)
    run_on_ui = Signal(object)  # pass a callable to execute on UI thread
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HiCloud MP")
        self.resize(1000, 600)
        self.setWindowIcon(QIcon("icon.ico"))
        
        # Set up application directories
        self.app_name = "HiCloudMP"
        self.app_author = "HiCloudMP"
        self.data_dir = user_data_dir(self.app_name, self.app_author, ensure_exists=True)
        self.cache_dir = user_cache_dir(self.app_name, self.app_author, ensure_exists=True)
        
        # Create directories if they don't exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Initialize settings
        self.settings = QSettings("HiCloudMP", "HiCloudMP")
        
        # Set up temporary directory for downloads
        self.temp_dir = os.path.join(self.cache_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Clean up old temp files on startup
        self.cleanup_temp_files()
        
        # State
        self.media_folders = []
        self.playlist = []  # Current active playlist contents
        self.playlists = []  # List of all playlists
        self.active_playlist = None  # Currently active playlist
        self.current_index = -1
        self.temp_files_to_cleanup = set()
        self.clouds = []
        self.original_playlist_order = []
        
        # Media player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.7)  # 70% volume default
        # Metadata/Cover controller
        self.meta = MetadataController(self)
        
        # Set up Windows message handler for media keys
        if HAS_WIN32:
            self.win_proc = create_win_proc_handler(self)
            
        # Enable system media control (media keys)
        self.setup_system_media_controls()
        
        # Connect signals
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.cloud_file_downloaded.connect(self.play_downloaded_file)
        self.run_on_ui.connect(self._run_on_ui)
        
        # UI
        self.setup_ui()
        
        # Load saved data
        self.load_media_folders()
        self.load_clouds()
        self.load_playlists()
        
        # Playlists manager (delegate playlist operations)
        try:
            self.playlists_mgr = PlaylistsManager(self)
            # Rebind common playlist APIs to manager to gradually slim this class
            self.add_current_to_named_playlist = self.playlists_mgr.add_current_to_named_playlist
            self.new_playlist = self.playlists_mgr.new_playlist
            self.save_current_playlist = self.playlists_mgr.save_current_playlist
            self.delete_current_playlist = self.playlists_mgr.delete_current_playlist
            self.load_playlist = self.playlists_mgr.load_playlist
            self.load_playlist_by_id = self.playlists_mgr.load_playlist_by_id
            self.delete_playlist = self.playlists_mgr.delete_playlist
        except Exception as e:
            print(f"Warning: PlaylistsManager init failed: {e}")
        
        # Library view (delegate library tree and search)
        try:
            self.library_mgr = LibraryView(self)
            self.update_library_tree = self.library_mgr.update_library_tree
            self.on_library_item_clicked = self.library_mgr.on_library_item_clicked
            self.search_music = self.library_mgr.search_music
        except Exception as e:
            print(f"Warning: LibraryView init failed: {e}")
        
        self.web_server = None
        self.web_port = 5000
        
        # Async cover fetch state now handled by MetadataController
        
        # Auto-start web interface if enabled in settings
        if self.settings.value("web_interface", False, bool):
            self.start_web_interface()
        
        # Create menu bar
        menubar = self.menuBar()
        
        # Add Web Panel action
        web_panel_action = QAction("Web Panel", self)
        web_panel_action.triggered.connect(self.open_web_panel)
        menubar.addAction(web_panel_action)
        
        # Add Settings action
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        menubar.addAction(settings_action)
        
        # (autostart handled above once)
        
    def set_dark_theme(self):
        """Apply dark theme to the application"""
        self.setStyleSheet("""
            QMainWindow, QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QLabel, QPushButton, QCheckBox, QRadioButton, QLineEdit, QListWidget, QComboBox {
                color: #ffffff;
            }
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                padding: 5px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
            QListWidget, QLineEdit, QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555;
                padding: 5px;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                background: #3a3a3a;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def open_settings_dialog(self):
        """Open the settings dialog and apply any changes"""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            dialog.save_settings()
            # Apply theme
            theme = dialog.settings.value("theme", "Dark")
            if theme == "Dark":
                self.set_dark_theme()
            else:
                # Reset to default light theme
                self.setStyleSheet("")
            # Apply volume
            volume = dialog.settings.value("volume", 70, int)
            self.audio_output.setVolume(volume / 100.0)
            self.volume_slider.setValue(volume)
            # Update web interface setting
            if hasattr(self, 'web_server'):
                if dialog.settings.value("web_interface", False, bool):
                    self.start_web_interface()
                else:
                    self.stop_web_interface()

    def start_web_interface(self):
        """Start the web interface server using WebControlServer"""
        if getattr(self, 'web_server', None):
            return True  # Already running
        try:
            from web_control import WebControlServer
            self.web_server = WebControlServer(self, host='0.0.0.0', port=self.web_port)
            self.web_server.start()
            self.status_bar.showMessage(f"Web interface started on http://localhost:{self.web_port}")
            return True
        except Exception as e:
            print(f"Failed to start web interface: {e}")
            QMessageBox.warning(self, "Web Interface",
                                "Failed to start web interface. Make sure Flask and Flask-SocketIO are installed.")
            self.web_server = None
            return False
    
    def stop_web_interface(self):
        """Stop the web interface server"""
        if getattr(self, 'web_server', None):
            try:
                self.web_server.stop()
            except Exception:
                pass
            self.web_server = None
            self.status_bar.showMessage("Web interface stopped")
    
    def open_web_panel(self):
        """Open the web control panel in the default browser"""
        import webbrowser
        if getattr(self, 'web_server', None):
            url = f"http://localhost:{self.web_port}"
            webbrowser.open(url)
        else:
            # If setting is enabled, try to start it automatically
            if self.settings.value("web_interface", False, bool):
                if self.start_web_interface():
                    url = f"http://localhost:{self.web_port}"
                    webbrowser.open(url)
                    return
            QMessageBox.warning(self, "Web Panel", "Web interface is not enabled in settings.")
        
    def setup_system_media_controls(self):
        """Setup system-wide media controls (keyboard, taskbar, etc.)"""
        try:
            # Register for system-level media player notifications
            self.player.setProperty("playbackRate", 1.0)
            
            # Set up actions for all the usual media controls
            self.play_action = QAction("Play/Pause", self)
            self.play_action.setShortcut(QKeySequence("Space"))
            self.play_action.triggered.connect(self.toggle_play)
            
            self.next_action = QAction("Next", self)
            self.next_action.setShortcut(QKeySequence("Ctrl+Right"))
            self.next_action.triggered.connect(self.next_track)
            
            self.prev_action = QAction("Previous", self)
            self.prev_action.setShortcut(QKeySequence("Ctrl+Left"))
            self.prev_action.triggered.connect(self.prev_track)
            
            self.stop_action = QAction("Stop", self)
            self.stop_action.setShortcut(QKeySequence("Ctrl+S"))
            self.stop_action.triggered.connect(self.stop)
            
            # Add to window for shortcut handling
            self.addAction(self.play_action)
            self.addAction(self.next_action)
            self.addAction(self.prev_action)
            self.addAction(self.stop_action)
            
            # Create system tray icon if supported
            if QSystemTrayIcon.isSystemTrayAvailable():
                # Initialize external tray controller (modularized)
                try:
                    self.tray = TrayController(self)
                    self.tray.init_tray()
                except Exception as e:
                    print(f"Warning: Tray init failed: {e}")
                
        except Exception as e:
            print(f"Warning: Could not set up system media controls: {e}")
    
    def setup_system_tray(self):
        """Deprecated: Use TrayController. Kept for backward compatibility."""
        try:
            if not hasattr(self, 'tray'):
                self.tray = TrayController(self)
            self.tray.init_tray()
        except Exception as e:
            print(f"Warning: setup_system_tray proxy failed: {e}")

    def _rebuild_tray_playlist_menu(self):
        """Proxy to TrayController implementation."""
        try:
            if hasattr(self, 'tray'):
                self.tray._rebuild_tray_playlist_menu()
        except Exception:
            pass

    def _get_current_item(self):
        """Return the currently playing/selected item (str path or dict for cloud), or None."""
        try:
            if not self.playlist or self.current_index < 0 or self.current_index >= len(self.playlist):
                return None
            return self.playlist[self.current_index]
        except Exception:
            return None

    def add_current_to_named_playlist(self, name: str):
        """Add the current item to the saved playlist with the given name."""
        if not name:
            return
        item = self._get_current_item()
        if item is None:
            self.status_bar.showMessage("No current track to add")
            return
        target = None
        for p in self.playlists:
            if p.name == name:
                target = p
                break
        if not target:
            self.status_bar.showMessage(f"Playlist not found: {name}")
            return
        # Append item; optionally prevent exact duplicates for local files
        try:
            if isinstance(item, str):
                if item not in target.items:
                    target.items.append(item)
            else:
                target.items.append(item)
        except Exception:
            target.items.append(item)
        target.modified = datetime.now().isoformat()
        self.save_playlists()
        # If the active playlist is the same, reflect in UI
        if getattr(self, 'active_playlist', None) and self.active_playlist.id == target.id:
            self.playlist.append(item)
            if isinstance(item, dict):
                display = "(Cloud)"
                try:
                    cloud_idx = item.get('cloud_idx')
                    file_idx = item.get('file_idx')
                    if isinstance(cloud_idx, int) and isinstance(file_idx, int):
                        cloud = self.clouds[cloud_idx]
                        file_info = cloud.get('files', [])[file_idx]
                        display = os.path.basename(file_info.get('path', 'Cloud File')) + " (Cloud)"
                except Exception:
                    pass
                self.playlist_widget.addItem(display)
            else:
                self.playlist_widget.addItem(os.path.basename(item))
        self.status_bar.showMessage(f"Added current track to playlist: {name}")

    def update_tray_ui(self):
        """Proxy to TrayController implementation."""
        try:
            if hasattr(self, 'tray'):
                self.tray.update_tray_ui()
        except Exception:
            pass
    
    def setup_ui(self):
        """Set up the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel - library
        library_panel = QWidget()
        library_layout = QVBoxLayout(library_panel)
        
        # Search box
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search music...")
        self.search_input.returnPressed.connect(self.search_music)
        self.search_btn = QToolButton()
        self.search_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.search_btn.clicked.connect(self.search_music)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        library_layout.addLayout(search_layout)
        
        # Library tree
        self.library_tree = QTreeWidget()
        self.library_tree.setHeaderHidden(True)
        self.library_tree.itemDoubleClicked.connect(self.on_library_item_clicked)
        self.library_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.library_tree.customContextMenuRequested.connect(self.show_library_context_menu)
        library_layout.addWidget(self.library_tree)
        
        # Library buttons
        lib_buttons_layout = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_files_btn = QPushButton("Add Files")
        self.add_cloud_btn = QPushButton("Add Cloud")
        self.scan_cloud_btn = QPushButton("Scan Cloud")
        
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.add_files_btn.clicked.connect(self.add_files)
        self.add_cloud_btn.clicked.connect(self.add_cloud)
        self.scan_cloud_btn.clicked.connect(self.scan_clouds)
        
        lib_buttons_layout.addWidget(self.add_folder_btn)
        lib_buttons_layout.addWidget(self.add_files_btn)
        lib_buttons_layout.addWidget(self.add_cloud_btn)
        lib_buttons_layout.addWidget(self.scan_cloud_btn)
        
        library_layout.addLayout(lib_buttons_layout)
        
        # Right panel - player
        player_panel = QWidget()
        player_layout = QVBoxLayout(player_panel)
        
        # Playlist management
        playlist_header = QHBoxLayout()
        
        # Playlist selector
        self.playlist_selector = QComboBox()
        self.playlist_selector.currentIndexChanged.connect(self.on_playlist_changed)
        playlist_header.addWidget(self.playlist_selector, 1)
        
        # Playlist buttons
        playlist_new_btn = QToolButton()
        playlist_new_btn.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        playlist_new_btn.setToolTip("New Playlist")
        playlist_new_btn.clicked.connect(self.new_playlist)
        
        playlist_save_btn = QToolButton()
        playlist_save_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        playlist_save_btn.setToolTip("Save Playlist")
        playlist_save_btn.clicked.connect(self.save_current_playlist)
        
        playlist_delete_btn = QToolButton()
        playlist_delete_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        playlist_delete_btn.setToolTip("Delete Playlist")
        playlist_delete_btn.clicked.connect(self.delete_current_playlist)
        
        playlist_header.addWidget(playlist_new_btn)
        playlist_header.addWidget(playlist_save_btn)
        playlist_header.addWidget(playlist_delete_btn)
        
        player_layout.addLayout(playlist_header)
        
        # Playlist search/filter/sort controls
        playlist_controls_layout = QHBoxLayout()
        self.playlist_search_input = QLineEdit()
        self.playlist_search_input.setPlaceholderText("Search playlist...")
        self.playlist_search_input.textChanged.connect(self.filter_playlist)
        self.playlist_sort_combo = QComboBox()
        self.playlist_sort_combo.addItems(["Original", "Title", "Artist", "Album"])
        self.playlist_sort_combo.currentIndexChanged.connect(self.sort_playlist)
        playlist_controls_layout.addWidget(QLabel("Playlist:"))
        playlist_controls_layout.addWidget(self.playlist_search_input)
        playlist_controls_layout.addWidget(self.playlist_sort_combo)
        player_layout.addLayout(playlist_controls_layout)
        
        # Playlist
        self.playlist_widget = QListWidget()
        self.playlist_widget.itemDoubleClicked.connect(self.play_selected)
        self.playlist_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(self.show_playlist_context_menu)
        # Enable drag-and-drop reordering and multi-select
        self.playlist_widget.setDragDropMode(QListWidget.InternalMove)
        self.playlist_widget.setSelectionMode(QListWidget.ExtendedSelection)
        player_layout.addWidget(self.playlist_widget)
        
        # Cover art and metadata display
        meta_container = QWidget()
        meta_layout = QHBoxLayout(meta_container)
        
        # Cover art with frame
        cover_frame = QFrame()
        cover_frame.setFixedSize(220, 220)  # Slightly larger to accommodate the frame
        cover_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 2px solid #444;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        
        # Create a layout for the cover art
        cover_layout = QVBoxLayout(cover_frame)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setSpacing(0)
        
        # Cover art label
        self.cover_art_label = QLabel()
        self.cover_art_label.setFixedSize(200, 200)  # Fixed size for cover art
        self.cover_art_label.setAlignment(Qt.AlignCenter)
        self.cover_art_label.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 4px;
            }
        """)
        
        # Add cover art to its frame
        cover_layout.addWidget(self.cover_art_label)
        
        # Debug: Print cover art label info
        print("\n=== Cover Art Label Info ===")
        print(f"Size: {self.cover_art_label.size().width()}x{self.cover_art_label.size().height()}")
        print(f"Is visible: {self.cover_art_label.isVisible()}")
        print(f"Is enabled: {self.cover_art_label.isEnabled()}")
        
        # Set default cover art
        self.set_default_cover()
        
        # Metadata text
        meta_text_layout = QVBoxLayout()
        self.track_title_label = QLabel("Title: -")
        self.track_artist_label = QLabel("Artist: -")
        self.track_album_label = QLabel("Album: -")
        
        # Style metadata labels
        for label in [self.track_title_label, self.track_artist_label, self.track_album_label]:
            label.setStyleSheet("font-size: 12px; margin: 2px;")
        
        meta_text_layout.addWidget(self.track_title_label)
        meta_text_layout.addWidget(self.track_artist_label)
        meta_text_layout.addWidget(self.track_album_label)
        meta_text_layout.addStretch(1)
        
        # Add widgets to layout with proper spacing and alignment
        meta_layout.addWidget(cover_frame, 0, Qt.AlignTop | Qt.AlignLeft)  # Add the framed cover art
        meta_layout.addLayout(meta_text_layout)
        meta_layout.setStretch(0, 0)  # Don't stretch cover art
        meta_layout.setStretch(1, 1)  # Stretch metadata text
        meta_layout.setSpacing(20)  # Add some spacing between cover art and text
        
        # Force update the layout
        meta_layout.update()
        meta_layout.activate()
        
        # Debug: Print layout info
        print("\n=== Cover Art Layout Info ===")
        print(f"Cover art in layout: {meta_layout.itemAt(0).widget() is self.cover_art_label}")
        print(f"Layout contents rect: {meta_layout.contentsRect()}")
        
        # Create a container widget for metadata
        meta_widget = QWidget()
        meta_widget.setLayout(meta_layout)
        meta_widget.setMinimumHeight(240)  # Increased to fit the cover art
        meta_widget.setMaximumHeight(240)  # Fixed height to prevent layout jumps
        player_layout.addWidget(meta_widget)
        
        # Force a style refresh
        meta_widget.style().unpolish(meta_widget)
        meta_widget.style().polish(meta_widget)
        meta_widget.update()
        
        # Playback controls
        controls_frame = QFrame()
        controls_frame.setFrameShape(QFrame.StyledPanel)
        controls_layout = QVBoxLayout(controls_frame)
        
        # Time and seek
        seek_layout = QHBoxLayout()
        self.position_label = QLabel("00:00")
        self.duration_label = QLabel("00:00")
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setTracking(True)  # Enable tracking for smooth updates
        self.seek_slider.sliderMoved.connect(self.seek_position)
        self.seek_slider.sliderPressed.connect(self.on_slider_pressed)
        self.seek_slider.sliderReleased.connect(self.on_slider_released)
        self.seek_slider.mousePressEvent = self.seek_slider_mouse_press
        self.seek_slider.mouseMoveEvent = self.seek_slider_mouse_move
        self.seek_slider.setSingleStep(1000)  # 1 second step
        self.seek_slider.setPageStep(10000)   # 10 second step
        
        seek_layout.addWidget(self.position_label)
        seek_layout.addWidget(self.seek_slider)
        seek_layout.addWidget(self.duration_label)
        controls_layout.addLayout(seek_layout)
        
        # Control buttons
        buttons_layout = QHBoxLayout()
        
        # Use QToolButton with icons from QStyle
        self.prev_btn = QToolButton()
        self.prev_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipBackward))
        self.prev_btn.setIconSize(QSize(32, 32))
        self.prev_btn.clicked.connect(self.prev_track)
        
        self.play_btn = QToolButton()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_btn.setIconSize(QSize(48, 48))
        self.play_btn.clicked.connect(self.toggle_play)
        
        self.stop_btn = QToolButton()
        self.stop_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_btn.setIconSize(QSize(32, 32))
        self.stop_btn.clicked.connect(self.stop)
        
        self.next_btn = QToolButton()
        self.next_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipForward))
        self.next_btn.setIconSize(QSize(32, 32))
        self.next_btn.clicked.connect(self.next_track)
        
        self.shuffle_btn = QToolButton()
        self.shuffle_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaSeekForward))
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setToolTip("Shuffle: Play random song each time")
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        
        self.repeat_btn = QToolButton()
        self.repeat_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        
        buttons_layout.addWidget(self.shuffle_btn)
        buttons_layout.addWidget(self.prev_btn)
        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addWidget(self.next_btn)
        buttons_layout.addWidget(self.repeat_btn)
        
        # Volume
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Volume:")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.set_volume)
        
        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_slider)
        
        buttons_layout.addLayout(volume_layout)
        controls_layout.addLayout(buttons_layout)
        
        player_layout.addWidget(controls_frame)
        
        # Add panels to main layout with splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(library_panel)
        splitter.addWidget(player_panel)
        splitter.setSizes([300, 700])  # Set initial sizes
        
        main_layout.addWidget(splitter)
        
        # Status bar with progress bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.hide()
        
        self.status_bar.addPermanentWidget(self.progress_bar)

    def _run_on_ui(self, fn):
        try:
            if callable(fn):
                fn()
        except Exception as e:
            print(f"run_on_ui error: {e}")

    # === Playback Controls ===
    def play(self):
        if not self.playlist or self.current_index < 0 or self.current_index >= len(self.playlist):
            return
        current_item = self.playlist[self.current_index]
        if isinstance(current_item, dict) and current_item.get("type") == "cloud":
            cloud_idx = current_item.get("cloud_idx")
            file_idx = current_item.get("file_idx")
            self.play_cloud_file(cloud_idx, file_idx)
        else:
            path = self.playlist[self.current_index]
            # Set up and play the media
            url = QUrl.fromLocalFile(os.path.abspath(path))
            self.player.setSource(url)
            self.player.play()
            
            # Update UI elements
            self.playlist_widget.setCurrentRow(self.current_index)
            item = self.playlist_widget.item(self.current_index)
            if item:
                self.playlist_widget.scrollToItem(item)
            self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            
            # Force an immediate metadata update
            QTimer.singleShot(100, self.update_metadata_display)
        self.highlight_current_track()
        # Update tray UI
        if hasattr(self, 'update_tray_ui'):
            self.update_tray_ui()
    
    def play_selected(self, item):
        self.current_index = self.playlist_widget.row(item)
        self.play()
    
    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia and self.current_index >= 0:
                self.play()
            else:
                self.player.play()
                self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        # Update tray UI
        if hasattr(self, 'update_tray_ui'):
            self.update_tray_ui()
    
    def stop(self):
        self.player.stop()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        # Update tray UI
        if hasattr(self, 'update_tray_ui'):
            self.update_tray_ui()
    
    def next_track(self):
        if self.shuffle_btn.isChecked() and len(self.playlist) > 1:
            import random
            next_index = self.current_index
            while next_index == self.current_index:
                next_index = random.randint(0, len(self.playlist) - 1)
            self.current_index = next_index
            self.play()
        elif self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            self.play()
        # Update tray UI
        if hasattr(self, 'update_tray_ui'):
            self.update_tray_ui()
    
    def prev_track(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.play()
        # Update tray UI
        if hasattr(self, 'update_tray_ui'):
            self.update_tray_ui()
    
    # --- Metadata/Cover delegation wrappers ---
    def set_default_cover(self):
        """Set the default cover art (delegated to MetadataController)."""
        return self.meta.set_default_cover()

    def update_cover_art(self, item):
        """Update the cover art display for the current track (delegated)."""
        return self.meta.update_cover_art(item)

    def update_metadata_display(self):
        """Update the metadata display (delegated)."""
        return self.meta.update_metadata_display()

    def _start_cover_art_fetch(self, source, is_url):
        """Compatibility wrapper (delegates to MetadataController)."""
        return self.meta._start_cover_art_fetch(source, is_url)

    # --- Convenience ---
    def open_current_location(self):
        """Open the folder of the currently selected track (local files)."""
        try:
            if not self.playlist or self.current_index < 0 or self.current_index >= len(self.playlist):
                return
            item = self.playlist[self.current_index]
            path = None
            if isinstance(item, str):
                path = os.path.abspath(item)
            elif isinstance(item, dict):
                # Try local path field if present
                if 'path' in item and isinstance(item['path'], str) and os.path.exists(item['path']):
                    path = os.path.abspath(item['path'])
            if path and os.path.exists(path):
                folder = os.path.dirname(path)
                try:
                    subprocess.Popen(["xdg-open", folder])
                except Exception:
                    pass
        except Exception:
            pass

            
    def update_position(self, position):
        self.seek_slider.blockSignals(True)
        self.seek_slider.setValue(position)
        self.seek_slider.blockSignals(False)
        self.position_label.setText(format_time(position))
    
    def update_duration(self, duration):
        self.seek_slider.setRange(0, duration)
        self.duration_label.setText(format_time(duration))
    
    def on_slider_pressed(self):
        # Store the current state to restore if needed
        self.was_playing = self.player.playbackState() == QMediaPlayer.PlayingState
        if self.was_playing:
            self.player.pause()
    
    def on_slider_released(self):
        # Restore playback state if it was playing
        if hasattr(self, 'was_playing') and self.was_playing:
            self.player.play()
    
    def seek_slider_mouse_press(self, event):
        # Handle mouse press on the slider
        if event.button() == Qt.LeftButton:
            # Calculate the position based on the mouse click
            pos = event.pos().x()
            max_ = self.seek_slider.maximum()
            min_ = self.seek_slider.minimum()
            width = self.seek_slider.width()
            value = min_ + ((max_ - min_) * pos) // width
            self.seek_position(value)
        # Call the original mouse press event
        QSlider.mousePressEvent(self.seek_slider, event)
    
    def seek_slider_mouse_move(self, event):
        # Handle mouse move with left button pressed (dragging)
        if event.buttons() & Qt.LeftButton:
            pos = event.pos().x()
            max_ = self.seek_slider.maximum()
            min_ = self.seek_slider.minimum()
            width = self.seek_slider.width()
            value = min_ + ((max_ - min_) * pos) // width
            self.seek_position(value)
        # Call the original mouse move event
        QSlider.mouseMoveEvent(self.seek_slider, event)
    
    def seek_position(self, position):
        # Make sure position is within valid range
        if position < 0:
            position = 0
        max_pos = self.player.duration()
        if position > max_pos and max_pos > 0:
            position = max_pos
            
        # Update the slider position
        self.seek_slider.setValue(position)
        
        # Only update the player position if the change is significant
        # (to avoid excessive updates during drag)
        if abs(self.player.position() - position) > 100:  # 100ms threshold
            self.player.setPosition(position)
    
    def set_volume(self, volume):
        self.audio_output.setVolume(volume / 100.0)
    
    def toggle_shuffle(self, enabled):
        # Only update the button style and state
        if enabled:
            self.shuffle_btn.setStyleSheet("background-color: #007bff; color: white;")
            self.status_bar.showMessage("Shuffle mode enabled: random song will play after each track.")
        else:
            self.shuffle_btn.setStyleSheet("")
            self.status_bar.showMessage("Shuffle mode disabled: normal order.")
        self.highlight_current_track()
    
    def toggle_repeat(self, enabled):
        self.repeat_btn.setStyleSheet(
            "background-color: #007bff; color: white;" if enabled else ""
        )
    
    def on_media_status_changed(self, status):
        # Update status bar with current media status
        status_messages = {
            QMediaPlayer.MediaStatus.NoMedia: "No media loaded",
            QMediaPlayer.MediaStatus.LoadingMedia: "Loading media...",
            QMediaPlayer.MediaStatus.LoadedMedia: "Media loaded",
            QMediaPlayer.MediaStatus.StalledMedia: "Buffering...",
            QMediaPlayer.MediaStatus.BufferingMedia: "Buffering...",
            QMediaPlayer.MediaStatus.BufferedMedia: "Ready to play",
            QMediaPlayer.MediaStatus.EndOfMedia: "End of media",
            QMediaPlayer.MediaStatus.InvalidMedia: "Error: Invalid or corrupted media"
        }
        
        # Track the last media status for error recovery
        if not hasattr(self, '_last_media_status'):
            self._last_media_status = None
        self._last_media_status = status
        
        # Show status message if we have one for this status
        if status in status_messages:
            self.status_bar.showMessage(status_messages[status], 3000)  # Show for 3 seconds
        
        # Handle specific status changes
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            # Media is loaded, but not yet playing
            current_item = self.playlist[self.current_index] if self.playlist and 0 <= self.current_index < len(self.playlist) else None
            if current_item:
                if isinstance(current_item, dict):
                    name = os.path.basename(current_item.get('path', 'Unknown'))
                else:
                    name = os.path.basename(str(current_item))
                # Update labels once media is ready
                try:
                    self.update_metadata_display()
                except Exception as e:
                    print(f"Metadata update on LoadedMedia failed: {e}")
            
        elif status == QMediaPlayer.MediaStatus.BufferedMedia:
            # Media is buffered and ready to play
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                current_item = self.playlist[self.current_index] if self.playlist and 0 <= self.current_index < len(self.playlist) else None
                if current_item:
                    if isinstance(current_item, dict):
                        name = os.path.basename(current_item.get('path', 'Unknown'))
                    else:
                        name = os.path.basename(str(current_item))
                    # Ensure metadata labels are accurate when buffered
                    try:
                        self.update_metadata_display()
                    except Exception as e:
                        print(f"Metadata update on BufferedMedia failed: {e}")
        
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.repeat_btn.isChecked():
                # Repeat current track
                self.player.setPosition(0)
                self.player.play()
            elif self.shuffle_btn.isChecked() and len(self.playlist) > 1:
                # Play a random track (not the same as current)
                import random
                if len(self.playlist) > 1:
                    next_index = self.current_index
                    while next_index == self.current_index and len(self.playlist) > 1:
                        next_index = random.randint(0, len(self.playlist) - 1)
                    self.current_index = next_index
                    self.play()
            elif self.current_index < len(self.playlist) - 1:
                # Play next track
                self.next_track()
                
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            current_item = self.playlist[self.current_index] if self.playlist and 0 <= self.current_index < len(self.playlist) else None
            
            # Check if this is a network-related error
            is_network_issue = False
            if isinstance(current_item, dict) and 'url' in current_item:
                is_network_issue = True
                error_msg = f"Network error playing {os.path.basename(current_item.get('path', 'media'))}. Retrying..."
                self.status_bar.showMessage(error_msg, 5000)
                
                # Retry playing the current item after a short delay
                QTimer.singleShot(2000, self.retry_current_playback)
            else:
                error_msg = "Error: Could not play media (invalid or unsupported format)"
                self.status_bar.showMessage(error_msg, 5000)
                QMessageBox.critical(self, "Playback Error", error_msg)
            
        # Update play/pause button based on playback state
        if status in [QMediaPlayer.MediaStatus.LoadedMedia, 
                     QMediaPlayer.MediaStatus.BufferedMedia,
                     QMediaPlayer.MediaStatus.BufferingMedia]:
            self.play_btn.setIcon(self.style().standardIcon(
                QStyle.SP_MediaPause if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState 
                else QStyle.SP_MediaPlay
            ))

    def retry_current_playback(self):
        """Retry playing the current track, with a maximum number of retries."""
        if not hasattr(self, '_playback_retry_count'):
            self._playback_retry_count = 0
        
        max_retries = 3
        
        if self._playback_retry_count < max_retries and self.playlist and 0 <= self.current_index < len(self.playlist):
            current_item = self.playlist[self.current_index]
            if isinstance(current_item, dict) and 'url' in current_item:
                self._playback_retry_count += 1
                self.status_bar.showMessage(
                    f"Retry {self._playback_retry_count}/{max_retries} for {os.path.basename(current_item.get('path', 'media'))}"
                )
                # Reset the player before retrying
                self.player.stop()
                self.player.setSource(QUrl())
                
                # Small delay before retry to allow network recovery
                QTimer.singleShot(1000, lambda: self.play_item_at_index(self.current_index))
            else:
                self._playback_retry_count = 0
        else:
            # Max retries reached, try playing next track
            self._playback_retry_count = 0
            if self.playlist and 0 <= self.current_index < len(self.playlist):
                current_item = self.playlist[self.current_index]
                error_msg = f"Failed to play {os.path.basename(current_item.get('path', 'media'))} after {max_retries} attempts. Moving to next track..."
                self.status_bar.showMessage(error_msg, 5000)
                
                # Try to play next track if available
                if self.current_index < len(self.playlist) - 1:
                    QTimer.singleShot(1500, self.next_track)
                else:
                    # If this was the last track, just stop
                    self.stop()
    
    # === Cloud Methods ===
    def play_cloud_file(self, cloud_idx, file_idx):
        try:
            if cloud_idx < 0 or cloud_idx >= len(self.clouds):
                raise ValueError("Invalid cloud account")
                
            cloud = self.clouds[cloud_idx]
            if file_idx < 0 or file_idx >= len(cloud.get("files", [])):
                raise ValueError("Invalid file index")
                
            file_info = cloud["files"][file_idx]
            url = file_info["url"]
            cloud_type = cloud["type"]
            file_name = os.path.basename(file_info["path"])
            
            self.status_bar.showMessage(f"Preparing to stream: {file_name}...")
            QApplication.processEvents()  # Update UI
            
            # Handle different cloud types
            if cloud_type == "webdav":
                auth_user = cloud["config"].get("webdav_login", "")
                auth_pass = cloud["config"].get("webdav_password", "")
                media_url = QUrl(url)
                # If credentials not present in URL, set via QUrl to safely encode
                if auth_user and auth_pass and not media_url.userName():
                    media_url.setUserName(auth_user)
                    media_url.setPassword(auth_pass)
            else:
                media_url = QUrl(url)
            
            # Stop current playback asynchronously
            self.player.stop()
            self.player.setSource(QUrl())
            QApplication.processEvents()  # Process events to ensure clean state

            # Stream directly using the resilient streaming helper (with retry)
            stream_url = str(media_url.toString())
            self._play_stream(stream_url, os.path.basename(file_name))

            # Update UI with track information
            base_name = os.path.splitext(file_name)[0]
            self.track_title_label.setText(f"Title: {base_name}")
            self.track_artist_label.setText("Artist: -")
            self.track_album_label.setText("Album: -")
            
            
            self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            # Update metadata shortly after starting stream
            QTimer.singleShot(200, self.update_metadata_display)
            
            if hasattr(self, 'current_index') and 0 <= self.current_index < len(self.playlist):
                self.playlist_widget.setCurrentRow(self.current_index)
                
                # Try to update metadata from the current playlist item
                current_item = self.playlist[self.current_index]
                if isinstance(current_item, dict):
                    # If we have metadata in the playlist item, use it
                    if 'title' in current_item:
                        self.track_title_label.setText(f"Title: {current_item['title']}")
                    if 'artist' in current_item:
                        self.track_artist_label.setText(f"Artist: {current_item['artist']}")
                    if 'album' in current_item:
                        self.track_album_label.setText(f"Album: {current_item['album']}")
                    # Also refresh cover art for this cloud item
                    self.update_cover_art(current_item)
                
        except Exception as e:
            error_msg = f"Failed to start streaming: {str(e)}"
            self.status_bar.showMessage(error_msg)
            QMessageBox.critical(self, "Streaming Error", error_msg)
    
    def _download_and_play(self, url, cloud_type, config, display_name, auth=None):
        """Download the cloud track to a temporary file then play locally.
        This avoids intermittent TLS resets that can break streaming demux.
        """
        try:
            # Ensure previous downloads are stopped
            if hasattr(self, 'download_worker') and self.download_worker:
                try:
                    self.download_worker.abort()
                except Exception:
                    pass
            # Prepare temp file path
            safe_name = os.path.basename(display_name) or 'track'
            fd, temp_path = tempfile.mkstemp(prefix='hicloud_', suffix='_' + safe_name, dir=self.temp_dir)
            os.close(fd)
            # Track for later cleanup on failures
            self.temp_files_to_cleanup.add(temp_path)

            # Setup worker in its own thread
            self.download_thread = QThread()
            self.download_worker = DownloadWorker(url, temp_path, auth=auth)
            self.download_worker.moveToThread(self.download_thread)

            # UI: show progress
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            self.status_bar.showMessage(f"Downloading: {display_name}")

            # Connect signals
            self.download_thread.started.connect(self.download_worker.run)
            self.download_worker.progress.connect(lambda p: self.progress_bar.setValue(max(0, min(100, p))))
            def on_finished(path):
                try:
                    self.progress_bar.hide()
                    self.status_bar.showMessage(f"Download complete: {display_name}")
                    # Remove from cleanup set now that it's a valid file
                    if path in self.temp_files_to_cleanup:
                        self.temp_files_to_cleanup.remove(path)
                    # Play on UI thread
                    self.run_on_ui.emit(lambda: self.play_downloaded_file(path))
                finally:
                    try:
                        self.download_thread.quit()
                        self.download_thread.wait(1000)
                    except Exception:
                        pass
            self.download_worker.finished.connect(on_finished)
            def on_error(err):
                try:
                    self.progress_bar.hide()
                    self.status_bar.showMessage(f"Download failed: {err}")
                    QMessageBox.warning(self, "Download Error", f"Failed to download: {err}\nAttempting to stream directly…")
                    # Fallback to stream
                    self._play_stream(url, display_name)
                finally:
                    try:
                        self.download_thread.quit()
                        self.download_thread.wait(1000)
                    except Exception:
                        pass
            self.download_worker.error.connect(on_error)

            self.download_thread.start()
        except Exception as e:
            # As a last resort, try to stream directly
            self.status_bar.showMessage(f"Download setup failed: {e}. Streaming instead…")
            self._play_stream(url, display_name)
    def _on_stream_media_status(self, status):
        if getattr(self, '_pending_stream_play', False):
            if status in (QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.LoadedMedia):
                self.player.play()
                self._pending_stream_play = False
                try:
                    self.player.mediaStatusChanged.disconnect(self._on_stream_media_status)
                except Exception:
                    pass
    
    def _reset_stream_retry(self):
        """Reset stream retry state."""
        self._stream_retry = {
            'attempts': 0,
            'url': None,
            'name': None,
        }

    def _schedule_stream_retry(self, url, display_name, immediate=False):
        """Schedule a reconnect with exponential backoff and jitter."""
        try:
            if not hasattr(self, '_stream_retry'):
                self._reset_stream_retry()
            # Update latest target
            self._stream_retry['url'] = url
            self._stream_retry['name'] = display_name
            # Compute delay
            if immediate:
                delay_ms = 250
            else:
                attempts = int(self._stream_retry.get('attempts', 0)) + 1
                self._stream_retry['attempts'] = attempts
                base = min(30000, 1000 * (2 ** (attempts - 1)))  # cap at 30s
                jitter = random.randint(0, 500)
                delay_ms = base + jitter
            # Inform user
            self.status_bar.showMessage(f"Network issue. Reconnecting to stream in {delay_ms//1000}.{(delay_ms%1000)//100}s…")
            QTimer.singleShot(delay_ms, lambda: self._play_stream(self._stream_retry['url'], self._stream_retry['name']))
        except Exception as e:
            print(f"schedule_stream_retry error: {e}")

    def cleanup_temp_files(self):
        """Clean up old temporary files on startup"""
        try:
            # Clean up any files older than 1 day
            now = time.time()
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                try:
                    # Delete files older than 1 day
                    if os.path.isfile(file_path):
                        if now - os.path.getmtime(file_path) > 86400:  # 1 day in seconds
                            os.unlink(file_path)
                except Exception as e:
                    print(f"Error cleaning up {file_path}: {e}")
        except Exception as e:
            print(f"Error in cleanup_temp_files: {e}")
    
    def stream_cloud_file(self, url, cloud_type="webdav", config=None):
        try:
            # For WebDAV, we can stream directly with authentication
            if cloud_type == "webdav" and config:
                from urllib.parse import quote_plus
                from base64 import b64encode
                
                # Get credentials
                username = config.get("webdav_login", "")
                password = config.get("webdav_password", "")
                
                if username and password:
                    # Create authenticated URL
                    auth_string = f"{username}:{password}"
                    encoded_auth = b64encode(auth_string.encode()).decode('utf-8')
                    
                    # Create the streaming URL with basic auth
                    parsed_url = url.split('://', 1)
                    if len(parsed_url) == 2:
                        scheme, path = parsed_url
                        streaming_url = f"{scheme}://{username}:{password}@{path}"
                        
                        # Play the stream directly
                        self._play_stream(streaming_url, os.path.basename(url))
                        return
            
            # Fall back to progressive download for other cloud types or if auth fails
            self._download_and_play(url, cloud_type, config)
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to start streaming: {str(e)}"
            )
    
    def _play_stream(self, url, display_name):
        try:
            # Ensure retry state exists
            if not hasattr(self, '_stream_retry'):
                self._reset_stream_retry()

            # Clear any existing media and handlers
            try:
                self.player.errorOccurred.disconnect()
            except Exception:
                pass
            try:
                self.player.mediaStatusChanged.disconnect()
            except Exception:
                pass

            # Stop and reset source first to avoid race conditions
            self.player.stop()
            self.player.setSource(QUrl())

            # Set up the media content correctly for Qt6
            self.player.setSource(QUrl(url))

            # Error handling with retry
            def handle_error(error, error_string):
                try:
                    # Qt6 emits (error, errorString)
                    if getattr(QMediaPlayer, 'NoError', None) is not None and error == QMediaPlayer.NoError:
                        return
                except Exception:
                    pass
                # Schedule retry with backoff
                self._schedule_stream_retry(url, display_name)

            try:
                # Connect with the two-arg signature if available; PySide will adapt as needed
                self.player.errorOccurred.connect(handle_error)
            except Exception:
                # Fallback: if signature mismatch, still attempt reconnect on media status
                pass

            # Media status handling for stalled/invalid/end
            def handle_media_status(status):
                if status == QMediaPlayer.MediaStatus.BufferedMedia:
                    # Success path: reset retry counter
                    self._reset_stream_retry()
                    self.status_bar.showMessage(f"Playing stream: {display_name}")
                elif status == QMediaPlayer.MediaStatus.StalledMedia:
                    # Network hiccup; schedule retry soon
                    self.status_bar.showMessage("Stream stalled. Reconnecting…")
                    self._schedule_stream_retry(url, display_name)
                elif status == QMediaPlayer.MediaStatus.InvalidMedia:
                    self.status_bar.showMessage("Invalid media. Reconnecting…")
                    self._schedule_stream_retry(url, display_name)
                elif status == QMediaPlayer.MediaStatus.EndOfMedia:
                    # Some streams end unexpectedly; try to resume quickly
                    self._schedule_stream_retry(url, display_name, immediate=True)

            self.player.mediaStatusChanged.connect(handle_media_status)

            # Start playback
            self.player.play()
            self.status_bar.showMessage(f"Connecting to stream: {display_name}…")

        except Exception as e:
            error_msg = f"Failed to start stream: {str(e)}"
            self.status_bar.showMessage(error_msg)
            # Try again with backoff
            self._schedule_stream_retry(url, display_name)

    def cancel_download(self):
        if hasattr(self, 'download_worker') and hasattr(self.download_worker, 'abort'):
            self.download_worker.abort()
        self.status_bar.showMessage("Download canceled")
        if hasattr(self, 'download_progress_dialog') and self.download_progress_dialog:
            self.download_progress_dialog.close()
    
    def play_downloaded_file(self, path):
        """
        Called when a cloud file has been downloaded and is ready to play.
        Handles the actual playback of the downloaded file.
        """
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Downloaded file not found: {path}")
                
            file_name = os.path.basename(path)
            self.status_bar.showMessage(f"Playing: {file_name}")
            QApplication.processEvents()  # Ensure UI updates
            
            try:
                # Stop any currently playing media
                self.player.stop()
                self.player.setSource(QUrl())
                QApplication.processEvents()  # Process events to ensure clean state
                
                # Set the new media source with absolute path
                abs_path = os.path.abspath(path)
                if not os.path.exists(abs_path):
                    raise FileNotFoundError(f"File not found at absolute path: {abs_path}")
                    
                url = QUrl.fromLocalFile(abs_path)
                self.player.setSource(url)
                
                # Update UI
                self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
                
                # Start playback with a small delay to prevent race conditions
                QTimer.singleShot(100, self.player.play)
                
                # Update the current track in the playlist if it exists
                if self.playlist_widget and hasattr(self, 'current_index') and 0 <= self.current_index < self.playlist_widget.count():
                    self.playlist_widget.setCurrentRow(self.current_index)
                
            except Exception as inner_e:
                # If playback fails, clean up and re-raise
                try:
                    self.player.stop()
                    self.player.setSource(QUrl())
                except:
                    pass
                raise inner_e
            
        except Exception as e:
            error_msg = f"Failed to play {os.path.basename(path)}: {str(e)}"
            self.status_bar.showMessage(error_msg)
            QMessageBox.critical(self, "Playback Error", error_msg)
            
            # Clean up the temporary file if it exists
            if path in self.temp_files_to_cleanup:
                try:
                    os.unlink(path)
                    self.temp_files_to_cleanup.remove(path)
                except Exception as cleanup_error:
                    print(f"Error cleaning up file {path}: {cleanup_error}")

    # === Playlist Management ===
    def load_cloud_folder_playlist(self, cloud_idx, file_indices):
        """Load cloud files from a folder into the current playlist"""
        if cloud_idx < 0 or cloud_idx >= len(self.clouds):
            self.status_bar.showMessage("Invalid cloud account")
            return
            
        cloud = self.clouds[cloud_idx]
        files = cloud.get("files", [])
        
        # Clear current playlist
        self.playlist = []
        self.playlist_widget.clear()
        
        # Add all files to playlist
        added = 0
        for idx in file_indices:
            if idx < 0 or idx >= len(files):
                continue
                
            file_info = files[idx]
            file_name = os.path.basename(file_info["path"])
            
            # Add to playlist widget
            self.playlist_widget.addItem(f"{file_name} (Cloud)")
            
            # Add to playlist data
            self.playlist.append({
                "type": "cloud",
                "cloud_idx": cloud_idx,
                "file_idx": idx
            })
            added += 1
        
        # Reset active playlist
        self.active_playlist = None
        self.update_playlist_selector()
        
        # Set current index if we have items
        if self.playlist:
            self.current_index = 0
            self.status_bar.showMessage(f"Loaded {added} tracks from cloud folder")
        else:
            self.status_bar.showMessage("No music files found in cloud folder")

    def load_media_folders(self):
        """Load saved media folders from file"""
        if os.path.exists(MEDIA_FOLDERS_FILE):
            try:
                with open(MEDIA_FOLDERS_FILE, "r") as f:
                    self.media_folders = json.load(f)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not load media folders: {e}")
                self.media_folders = []
        self.update_library_tree()
        
    def load_clouds(self):
        """Load saved cloud accounts from file"""
        if os.path.exists(CLOUD_FILES_FILE):
            try:
                with open(CLOUD_FILES_FILE, "r") as f:
                    self.clouds = json.load(f)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not load cloud accounts: {e}")
                self.clouds = []
        self.update_library_tree()
        
    def load_playlists(self):
        """Load saved playlists from file"""
        try:
            if os.path.exists(PLAYLISTS_FILE):
                with open(PLAYLISTS_FILE, "r") as f:
                    playlists_data = json.load(f)
                    
                self.playlists = [Playlist.from_dict(p) for p in playlists_data]
                
                # Update playlist selector
                self.update_playlist_selector()
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load playlists: {e}")
            self.playlists = []
    
    def on_playlist_changed(self, index):
        """Handle playlist selection change"""
        if index == 0:  # Current Queue
            self.active_playlist = None
            # Keep current playlist, no changes
            return
            
        playlist_index = index - 1  # Adjust for "Current Queue" item
        if 0 <= playlist_index < len(self.playlists):
            self.load_playlist(self.playlists[playlist_index])
    
    def update_playlist_selector(self):
        """Update the playlist selector dropdown"""
        if not hasattr(self, 'playlist_selector'):
            return
            
        self.playlist_selector.blockSignals(True)
        self.playlist_selector.clear()
        
        # Add "Current Queue" option
        self.playlist_selector.addItem("Current Queue")
        
        # Add all playlists
        for playlist in self.playlists:
            self.playlist_selector.addItem(playlist.name)
            
        # If there's an active playlist, select it
        if self.active_playlist:
            index = 1  # Start after "Current Queue"
            for i, playlist in enumerate(self.playlists):
                if playlist.id == self.active_playlist.id:
                    self.playlist_selector.setCurrentIndex(index)
                    break
                index += 1
        else:
            self.playlist_selector.setCurrentIndex(0)  # Select "Current Queue"
            
        self.playlist_selector.blockSignals(False)
    
    def show_playlist_context_menu(self, position):
        selected_items = self.playlist_widget.selectedItems()
        item = self.playlist_widget.itemAt(position)
        if not item:
            return
        index = self.playlist_widget.row(item)
        context_menu = QMenu()
        play_action = context_menu.addAction("Play")
        play_action.triggered.connect(lambda: self.play_item_at_index(index))
        remove_action = context_menu.addAction("Remove from Playlist")
        remove_action.triggered.connect(lambda: self.remove_from_playlist(index))
        if len(selected_items) > 1:
            remove_selected_action = context_menu.addAction("Remove Selected")
            remove_selected_action.triggered.connect(self.remove_selected_from_playlist)
            move_up_action = context_menu.addAction("Move Selected Up")
            move_up_action.triggered.connect(lambda: self.move_selected_in_playlist(-1))
            move_down_action = context_menu.addAction("Move Selected Down")
            move_down_action.triggered.connect(lambda: self.move_selected_in_playlist(1))
        if self.active_playlist:
            save_action = context_menu.addAction("Save Playlist")
            save_action.triggered.connect(self.save_current_playlist)
        context_menu.exec(self.playlist_widget.viewport().mapToGlobal(position))
    
    def remove_selected_from_playlist(self):
        selected_rows = sorted([self.playlist_widget.row(item) for item in self.playlist_widget.selectedItems()], reverse=True)
        for row in selected_rows:
            self.playlist_widget.takeItem(row)
            del self.playlist[row]
        if self.active_playlist:
            self.active_playlist.modified = datetime.now().isoformat()
    
    def move_selected_in_playlist(self, direction):
        selected_rows = sorted([self.playlist_widget.row(item) for item in self.playlist_widget.selectedItems()])
        if direction < 0:
            for row in selected_rows:
                if row > 0:
                    self.playlist[row-1], self.playlist[row] = self.playlist[row], self.playlist[row-1]
                    item = self.playlist_widget.takeItem(row)
                    self.playlist_widget.insertItem(row-1, item)
                    item.setSelected(True)
        else:
            for row in reversed(selected_rows):
                if row < self.playlist_widget.count()-1:
                    self.playlist[row+1], self.playlist[row] = self.playlist[row], self.playlist[row+1]
                    item = self.playlist_widget.takeItem(row)
                    self.playlist_widget.insertItem(row+1, item)
                    item.setSelected(True)
    
    def on_library_item_clicked(self, item, column):
        """Handle double-click on library tree items"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        # Only play or add to playlist for files, not folders
        if data["type"] == "local_file":
            # Play single file
            path = data["path"]
            self.playlist = [path]
            self.playlist_widget.clear()
            self.playlist_widget.addItem(os.path.basename(path))
            self.current_index = 0
            self.play()
        elif data["type"] == "cloud_file":
            cloud_idx = data["cloud_index"]
            file_idx = data["file_index"]
            # Set playlist to just this cloud file
            self.playlist = [{
                "type": "cloud",
                "cloud_idx": cloud_idx,
                "file_idx": file_idx
            }]
            self.playlist_widget.clear()
            cloud = self.clouds[cloud_idx]
            file_info = cloud["files"][file_idx]
            file_name = os.path.basename(file_info["path"])
            self.playlist_widget.addItem(f"{file_name} (Cloud)")
            self.current_index = 0
            self.play()
        elif data["type"] == "playlist":
            self.load_playlist_by_id(data["id"])
        elif data["type"] == "new_playlist":
            self.new_playlist()
        # For folders, just expand/collapse (default QTreeWidget behavior)
    
    def update_library_tree(self):
        """Update the library tree with current data"""
        self.library_tree.clear()
        self.library_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        file_icon = self.style().standardIcon(QStyle.SP_FileIcon)
        # Local folders section
        local_root = QTreeWidgetItem(self.library_tree, ["Local Media"])
        local_root.setExpanded(True)
        local_root.setData(0, Qt.UserRole, {"type": "local_root"})
        # Add playlists section
        playlists_root = QTreeWidgetItem(self.library_tree, ["Playlists"])
        playlists_root.setExpanded(True)
        for playlist in self.playlists:
            playlist_item = QTreeWidgetItem(playlists_root, [playlist.name])
            playlist_item.setData(0, Qt.UserRole, {"type": "playlist", "id": playlist.id})
            playlist_item.setIcon(0, file_icon)
        new_playlist_item = QTreeWidgetItem(playlists_root, ["+ New Playlist"])
        new_playlist_item.setData(0, Qt.UserRole, {"type": "new_playlist"})
        new_playlist_item.setIcon(0, folder_icon)
        # Local folders and files
        for folder in self.media_folders:
            folder_item = QTreeWidgetItem(local_root, [os.path.basename(folder)])
            folder_item.setData(0, Qt.UserRole, {"type": "local_folder", "path": folder})
            folder_item.setIcon(0, folder_icon)
            try:
                for root, dirs, files in os.walk(folder):
                    if root == folder:
                        # Add subfolders
                        for dir_name in dirs:
                            dir_path = os.path.join(root, dir_name)
                            subdir_item = QTreeWidgetItem(folder_item, [dir_name])
                            subdir_item.setData(0, Qt.UserRole, {"type": "local_folder", "path": dir_path})
                            subdir_item.setIcon(0, folder_icon)
                        # Add files
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
        cloud_root = QTreeWidgetItem(self.library_tree, ["Cloud Media"])
        cloud_root.setExpanded(True)
        for idx, cloud in enumerate(self.clouds):
            cloud_item = QTreeWidgetItem(cloud_root, [cloud["name"]])
            cloud_item.setData(0, Qt.UserRole, {"type": "cloud_account", "index": idx})
            cloud_item.setIcon(0, folder_icon)
            if "files" in cloud and cloud["files"]:
                # Group files by folder structure
                folder_structure = {}
                for file_idx, file in enumerate(cloud["files"]):
                    path = file["path"]
                    path = path.replace('//', '/').strip('/')
                    parts = path.split("/")
                    if len(parts) > 1:
                        folder = "/".join(parts[:-1]) or "/"
                        filename = parts[-1]
                    else:
                        folder = "/"
                        filename = path
                    if folder not in folder_structure:
                        folder_structure[folder] = []
                    folder_structure[folder].append({
                        "name": filename,
                        "file_index": file_idx
                    })
                # Add folders and files to tree
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
                    # Add files in this folder
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
        """Search for music in local and cloud libraries"""
        search_term = self.search_input.text().strip().lower()
        if not search_term:
            # If search is empty, restore original tree
            self.update_library_tree()
            return
            
        self.status_bar.showMessage(f"Searching for: {search_term}")
        
        # Clear and setup search results tree
        self.library_tree.clear()
        search_root = QTreeWidgetItem(self.library_tree, ["Search Results"])
        search_root.setExpanded(True)
        
        # Search local folders
        local_results = QTreeWidgetItem(search_root, ["Local Media"])
        local_results.setExpanded(True)
        
        found_local = False
        for folder in self.media_folders:
            for root, _, files in os.walk(folder):
                for file in files:
                    if is_music_file(file) and search_term in file.lower():
                        full_path = os.path.join(root, file)
                        result_item = QTreeWidgetItem(local_results, [file])
                        result_item.setData(0, Qt.UserRole, {"type": "local_file", "path": full_path})
                        found_local = True
        
        if not found_local:
            QTreeWidgetItem(local_results, ["No matches found"])
        
        # Search cloud files
        cloud_results = QTreeWidgetItem(search_root, ["Cloud Media"])
        cloud_results.setExpanded(True)
        
        found_cloud = False
        for cloud_idx, cloud in enumerate(self.clouds):
            if "files" in cloud and cloud["files"]:
                for file_idx, file in enumerate(cloud["files"]):
                    file_name = os.path.basename(file["path"])
                    if search_term in file_name.lower():
                        result_item = QTreeWidgetItem(cloud_results, [f"{file_name} ({cloud['name']})"])
                        result_item.setData(0, Qt.UserRole, {
                            "type": "cloud_file", 
                            "cloud_index": cloud_idx, 
                            "file_index": file_idx
                        })
                        found_cloud = True
        
        if not found_cloud:
            QTreeWidgetItem(cloud_results, ["No matches found"])
            
        self.status_bar.showMessage(f"Search complete: {search_term}")
    
    def add_folder(self):
        """Add a folder to the media library"""
        folder = QFileDialog.getExistingDirectory(self, "Add Media Folder")
        if folder and folder not in self.media_folders:
            self.media_folders.append(folder)
            self.save_media_folders()
            self.update_library_tree()
    
    def add_files(self):
        """Add individual music files to the library or playlist"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Music Files",
            "",
            "Music Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.wma);;All Files (*.*)"
        )
        
        if not files:
            return
            
        # Ask user whether to add to library or current playlist
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Files")
        layout = QVBoxLayout(dialog)
        
        label = QLabel("Where would you like to add these files?")
        layout.addWidget(label)
        
        add_to_library = QRadioButton("Add to Media Library")
        add_to_library.setChecked(True)
        layout.addWidget(add_to_library)
        
        add_to_playlist = QRadioButton("Add to Current Playlist")
        layout.addWidget(add_to_playlist)
        
        if self.playlists:
            add_to_saved_playlist = QRadioButton("Add to Saved Playlist")
            layout.addWidget(add_to_saved_playlist)
        else:
            add_to_saved_playlist = None
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() != QDialog.Accepted:
            return
        
        # Handle based on user selection
        if add_to_library.isChecked():
            # Add files to library by adding their parent folder
            unique_folders = set()
            for file in files:
                folder = os.path.dirname(file)
                if folder not in self.media_folders:
                    unique_folders.add(folder)
            
            if unique_folders:
                self.media_folders.extend(unique_folders)
                self.save_media_folders()
                self.update_library_tree()
                self.status_bar.showMessage(f"Added {len(files)} files to library")
            else:
                self.status_bar.showMessage("Files already in library")
                
        elif add_to_playlist.isChecked():
            # Add files to current playlist
            for file in files:
                self.playlist.append(file)
                self.playlist_widget.addItem(os.path.basename(file))
            
            # Set current index if this is the first item
            if len(self.playlist) == len(files) and self.current_index < 0:
                self.current_index = 0
                
            self.status_bar.showMessage(f"Added {len(files)} files to current playlist")
            
        elif add_to_saved_playlist and add_to_saved_playlist.isChecked():
            # Let user select which playlist to add to
            playlists = [p.name for p in self.playlists]
            playlist_name, ok = QInputDialog.getItem(
                self, "Select Playlist", "Add to playlist:", playlists, 0, False
            )
            
            if ok and playlist_name:
                # Find the playlist
                target_playlist = None
                for p in self.playlists:
                    if p.name == playlist_name:
                        target_playlist = p
                        break
                
                if target_playlist:
                    # Add files to the playlist
                    for file in files:
                        if file not in target_playlist.items:
                            target_playlist.items.append(file)
                    
                    # Save changes
                    target_playlist.modified = datetime.now().isoformat()
                    self.save_playlists()
                    
                    self.status_bar.showMessage(f"Added {len(files)} files to playlist: {playlist_name}")
    
    def add_cloud(self):
        """Add or manage cloud storage accounts"""
        dlg = CloudAccountsDialog(self, self.clouds)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if data["type"] != "unknown":
                self.clouds.append({
                    "type": data["type"], 
                    "name": data["name"], 
                    "config": data["config"], 
                    "files": [],
                    "last_sync": "Never"
                })
                self.save_clouds()
                self.update_library_tree()
                self.status_bar.showMessage(f"Added {data['type']} account: {data['name']}")
    
    def scan_clouds(self):
        if not self.clouds:
            self.status_bar.showMessage("No cloud accounts configured")
            return
        self.scan_cloud_btn.setEnabled(False)
        self.scan_threads = []
        self.scan_workers = []
        self.progress_dialog = QProgressDialog("Scanning cloud accounts...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Cloud Scan Progress")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setValue(0)
        self.progress_dialog.canceled.connect(self.cancel_cloud_scan)
        for idx, cloud in enumerate(self.clouds):
            thread = QThread()
            worker = ScanCloudWorker(idx, cloud)
            self.scan_workers.append(worker)
            worker.progress_updated.connect(self.update_scan_progress)
            worker.scan_finished.connect(self.handle_scan_complete)
            worker.scan_error.connect(self.handle_scan_error)
            worker.scan_finished.connect(thread.quit)
            worker.scan_error.connect(thread.quit)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            thread.finished.connect(lambda w=worker: w.deleteLater())
            thread.finished.connect(thread.deleteLater)
            self.scan_threads.append(thread)
        self.status_bar.showMessage("Starting cloud scan...")
        for thread in self.scan_threads:
            thread.start()
    def update_scan_progress(self, progress, status, cloud_name):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.setValue(progress)
            self.progress_dialog.setLabelText(f"{cloud_name}: {status}")
        QApplication.processEvents()
    def handle_scan_complete(self, cloud_idx, files):
        if cloud_idx >= 0 and cloud_idx < len(self.clouds):
            self.clouds[cloud_idx]["files"] = files
            self.save_clouds()
            self.update_library_tree()
        self._check_all_scans_complete()
    def handle_scan_error(self, cloud_idx, error_msg):
        if cloud_idx >= 0 and cloud_idx < len(self.clouds):
            cloud_name = self.clouds[cloud_idx]["name"]
            QMessageBox.critical(self, "Cloud Scan Error", f"{cloud_name}:\n\n{error_msg}")
        self._check_all_scans_complete()
    def cancel_cloud_scan(self):
        for worker in getattr(self, 'scan_workers', []):
            if hasattr(worker, 'abort'):
                worker.abort()
        self.status_bar.showMessage("Cloud scan canceled")
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
    
    def new_playlist(self):
        """Create a new playlist"""
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")
        if ok and name:
            playlist = Playlist(name)
            
            # Add current items to the new playlist if there are any
            if self.playlist:
                playlist.items = self.playlist.copy()
                
            self.playlists.append(playlist)
            self.active_playlist = playlist
            
            # Update UI
            self.save_playlists()
            self.update_library_tree()
            self.update_playlist_selector()
            
            self.status_bar.showMessage(f"Created new playlist: {name}")
    
    def save_current_playlist(self):
        """Save the current playlist"""
        if not self.active_playlist:
            # Create a new playlist if none is active
            self.new_playlist()
            return
            
        # Update the active playlist with current items
        self.active_playlist.items = self.playlist.copy()
        self.active_playlist.modified = datetime.now().isoformat()
        
        # Save to disk
        self.save_playlists()
        self.status_bar.showMessage(f"Saved playlist: {self.active_playlist.name}")
    
    def delete_current_playlist(self):
        """Delete the current playlist"""
        if not self.active_playlist:
            return
            
        confirm = QMessageBox.question(
            self,
            "Delete Playlist",
            f"Are you sure you want to delete the playlist '{self.active_playlist.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            self.delete_playlist(self.active_playlist.id)
    
    def load_playlist(self, playlist):
        """Load a playlist into the player"""
        self.active_playlist = playlist
        self.playlist = self.active_playlist.items  # Use reference, not copy
        self.playlist_widget.clear()
        # Load all items from the playlist
        for item in self.playlist:
            if isinstance(item, dict):
                # This is a cloud item
                if item.get("type") == "cloud":
                    cloud_idx = item.get("cloud_idx")
                    file_idx = item.get("file_idx")
                    # Verify the cloud and file still exist
                    if cloud_idx < 0 or cloud_idx >= len(self.clouds):
                        continue
                    cloud = self.clouds[cloud_idx]
                    files = cloud.get("files", [])
                    if file_idx < 0 or file_idx >= len(files):
                        continue
                    file_info = files[file_idx]
                    file_name = os.path.basename(file_info["path"])
                    # Add to playlist
                    self.playlist_widget.addItem(f"{file_name} (Cloud)")
            else:
                # This is a local file
                if os.path.exists(item):
                    self.playlist_widget.addItem(os.path.basename(item))
        if self.playlist:
            self.current_index = 0
            self.status_bar.showMessage(f"Loaded playlist: {playlist.name}")
    
    def load_playlist_by_id(self, playlist_id):
        """Load a playlist by its ID"""
        for playlist in self.playlists:
            if playlist.id == playlist_id:
                self.load_playlist(playlist)
                
                # Update selector to match
                self.update_playlist_selector()
                return
    
    def delete_playlist(self, playlist_id):
        """Delete a playlist by its ID"""
        # Find and remove the playlist
        for i, playlist in enumerate(self.playlists):
            if playlist.id == playlist_id:
                del self.playlists[i]
                
                # If this was the active playlist, clear it
                if self.active_playlist and self.active_playlist.id == playlist_id:
                    self.active_playlist = None
                
                # Update UI
                self.save_playlists()
                self.update_library_tree()
                self.update_playlist_selector()
                self.status_bar.showMessage(f"Deleted playlist: {playlist.name}")
                return
    
    def play_item_at_index(self, index):
        # Reset retry counter when starting a new track
        if hasattr(self, '_playback_retry_count'):
            self._playback_retry_count = 0
        """Play a specific item from the playlist"""
        if 0 <= index < len(self.playlist):
            self.current_index = index
            self.play()
    
    def remove_from_playlist(self, index):
        """Remove an item from the current playlist"""
        if 0 <= index < len(self.playlist):
            self.playlist_widget.takeItem(index)
            del self.playlist[index]
            if self.active_playlist:
                self.active_playlist.modified = datetime.now().isoformat()
                self.save_playlists()
    
    def load_folder_playlist(self, folder):
        """Load music files from a folder into the playlist"""
        self.playlist = scan_music_files(folder)
        self.playlist_widget.clear()
        for f in self.playlist:
            self.playlist_widget.addItem(os.path.basename(f))
        
        # Reset active playlist
        self.active_playlist = None
        self.update_playlist_selector()
        
        if self.playlist:
            self.current_index = 0
            self.status_bar.showMessage(f"Loaded {len(self.playlist)} tracks from {folder}")
        else:
            self.status_bar.showMessage("No music files found in folder")
    
    def open_folder(self):
        """Open a folder dialog and load music files"""
        folder = QFileDialog.getExistingDirectory(self, "Open Music Folder")
        if folder:
            self.load_folder_playlist(folder)
    
    def save_media_folders(self):
        """Save media folders to file"""
        try:
            with open(MEDIA_FOLDERS_FILE, "w") as f:
                json.dump(self.media_folders, f)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save media folders: {e}")
    
    def save_clouds(self):
        """Save cloud accounts to file"""
        try:
            with open(CLOUD_FILES_FILE, "w") as f:
                json.dump(self.clouds, f)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save cloud accounts: {e}")
    
    def save_playlists(self):
        """Save all playlists to file"""
        try:
            playlists_data = [p.to_dict() for p in self.playlists]
            with open(PLAYLISTS_FILE, "w") as f:
                json.dump(playlists_data, f)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save playlists: {e}")

    def closeEvent(self, event):
        self.player.stop()
        # Stop web server if running
        if self.web_server:
            self.web_server.stop()
            self.web_server = None
        # Clean up temporary files
        for temp_file in list(self.temp_files_to_cleanup):
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    self.temp_files_to_cleanup.remove(temp_file)
            except Exception as e:
                print(f"Error deleting temp file {temp_file}: {e}")
        
        # Save state
        self.save_media_folders()
        self.save_clouds()
        self.save_playlists()
        
        # Clean up web server if running
        if hasattr(self, 'web_server') and self.web_server:
            self.web_server.shutdown()
        
        # Clean up any remaining temp files in the temp directory
        try:
            if os.path.exists(self.temp_dir):
                for filename in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        print(f"Error cleaning up {file_path}: {e}")
        except Exception as e:
            print(f"Error during final cleanup: {e}")
        
        event.accept()

    def show_library_context_menu(self, position):
        """Show context menu for library tree items"""
        item = self.library_tree.itemAt(position)
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        context_menu = QMenu()
        # Remove local folder option
        if data.get("type") == "local_folder":
            remove_action = context_menu.addAction("Remove Folder")
            remove_action.triggered.connect(lambda: self.remove_media_folder(data["path"]))
        # Improved: cloud_account context menu (add ALL files from all folders)
        if data["type"] == "cloud_account":
            cloud_idx = data["index"]
            if 0 <= cloud_idx < len(self.clouds):
                cloud = self.clouds[cloud_idx]
                # Gather all file indices from all folders
                file_indices = [i for i, f in enumerate(cloud.get("files", []))]
                if file_indices:
                    # Add to current playlist
                    add_to_queue_action = context_menu.addAction("Add ALL Files to Current Queue")
                    add_to_queue_action.triggered.connect(
                        lambda: self.add_folder_to_playlist({
                            "type": "cloud_folder",
                            "cloud_index": cloud_idx,
                            "folder": None,  # Not used, just for compatibility
                            "file_indices": file_indices
                        })
                    )
                    # Add to specific playlist
                    if self.playlists:
                        add_to_menu = QMenu("Add ALL Files to Playlist", context_menu)
                        context_menu.addMenu(add_to_menu)
                        for playlist in self.playlists:
                            playlist_action = add_to_menu.addAction(playlist.name)
                            playlist_action.triggered.connect(
                                lambda checked, p=playlist: self.add_folder_to_specific_playlist(
                                    p,
                                    {
                                        "type": "cloud_folder",
                                        "cloud_index": cloud_idx,
                                        "folder": None,
                                        "file_indices": file_indices
                                    }
                                )
                            )
        # Existing context menu logic...
        if data["type"] in ["local_folder", "cloud_folder"]:
            add_to_playlist_action = context_menu.addAction("Add to Current Playlist")
            add_to_playlist_action.triggered.connect(lambda: self.add_folder_to_playlist(data))
            if self.playlists:
                add_to_menu = QMenu("Add to Playlist", context_menu)
                context_menu.addMenu(add_to_menu)
                for playlist in self.playlists:
                    playlist_action = add_to_menu.addAction(playlist.name)
                    playlist_action.triggered.connect(
                        lambda checked, p=playlist, d=data: self.add_folder_to_specific_playlist(p, d)
                    )
        elif data["type"] == "local_file" or data["type"] == "cloud_file":
            add_to_playlist_action = context_menu.addAction("Add to Current Playlist")
            add_to_playlist_action.triggered.connect(lambda: self.add_file_to_playlist(data))
            if self.playlists:
                add_to_menu = QMenu("Add to Playlist", context_menu)
                context_menu.addMenu(add_to_menu)
                for playlist in self.playlists:
                    playlist_action = add_to_menu.addAction(playlist.name)
                    playlist_action.triggered.connect(
                        lambda checked, p=playlist, d=data: self.add_file_to_playlist(p, d)
                    )
        if not context_menu.isEmpty():
            context_menu.exec(self.library_tree.viewport().mapToGlobal(position))

    def add_folder_to_playlist(self, data):
        """Add all music files from a folder to the current playlist"""
        if data["type"] == "local_folder":
            # Local folder
            path = data["path"]
            files = scan_music_files(path)
            
            # Add files to playlist
            if files:
                for file_path in files:
                    self.playlist.append(file_path)
                    self.playlist_widget.addItem(os.path.basename(file_path))
                
                self.status_bar.showMessage(f"Added {len(files)} tracks from {os.path.basename(path)}")
                
                # If this is the first item, set the current index
                if len(self.playlist) == len(files) and self.current_index < 0:
                    self.current_index = 0
                    
        elif data["type"] == "cloud_folder":
            # Cloud folder
            cloud_idx = data["cloud_index"]
            file_indices = data["file_indices"]
            
            if cloud_idx < 0 or cloud_idx >= len(self.clouds):
                return
                
            cloud = self.clouds[cloud_idx]
            files = cloud.get("files", [])
            
            # Add files to playlist
            added = 0
            for idx in file_indices:
                if idx < 0 or idx >= len(files):
                    continue
                    
                file_info = files[idx]
                file_name = os.path.basename(file_info["path"])
                
                # Add to playlist widget
                self.playlist_widget.addItem(f"{file_name} (Cloud)")
                
                # Add to playlist data
                self.playlist.append({
                    "type": "cloud",
                    "cloud_idx": cloud_idx,
                    "file_idx": idx
                })
                added += 1
            
            self.status_bar.showMessage(f"Added {added} tracks from cloud folder")
            
            # If this is the first item, set the current index
            if len(self.playlist) == added and self.current_index < 0:
                self.current_index = 0
    
    def _add_file_to_playlist_internal(self, data, target_list, update_ui=True):
        """Internal method to add a file to a playlist
        
        Args:
            data (dict): File data containing type and path/index information
            target_list (list): The playlist to add the file to
            update_ui (bool): Whether to update the UI (default: True)
            
        Returns:
            str: The name of the file that was added, or None if failed
        """
        if data["type"] == "local_file":
            path = data["path"]
            target_list.append(path)
            if update_ui:
                self.playlist_widget.addItem(os.path.basename(path))
            if len(target_list) == 1 and self.current_index < 0:
                self.current_index = 0
            return os.path.basename(path)
            
        elif data["type"] == "cloud_file":
            cloud_idx = data["cloud_index"]
            file_idx = data["file_index"]
            if cloud_idx < 0 or cloud_idx >= len(self.clouds):
                return None
                
            cloud = self.clouds[cloud_idx]
            files = cloud.get("files", [])
            if file_idx < 0 or file_idx >= len(files):
                return None
                
            file_info = files[file_idx]
            file_name = os.path.basename(file_info["path"])
            
            target_list.append({
                "type": "cloud",
                "cloud_idx": cloud_idx,
                "file_idx": file_idx
            })
            
            if update_ui:
                self.playlist_widget.addItem(f"{file_name} (Cloud)")
                
            if len(target_list) == 1 and self.current_index < 0:
                self.current_index = 0
                
            return file_name
        
        return None
    def add_file_to_playlist(self, data):
        """Add a single file to the current playlist
        
        Args:
            data (dict): File data containing type and path/index information
        """
        target_list = self.playlist
        if self.active_playlist:
            target_list = self.active_playlist.items
            
        file_name = self._add_file_to_playlist_internal(data, target_list)
        
        if file_name:
            self.status_bar.showMessage(f"Added {file_name} to playlist")
        
        if self.active_playlist:
            self.active_playlist.modified = datetime.now().isoformat()
            self.save_playlists()
            
    def add_file_to_specific_playlist(self, playlist, data):
        """Add a file to a specific playlist
        
        Args:
            playlist: The playlist to add the file to
            data (dict): File data containing type and path/index information
        """
        if not playlist or not hasattr(playlist, 'items'):
            return
            
        # Create a temporary list to hold the file
        temp_list = []
        file_name = self._add_file_to_playlist_internal(data, temp_list, update_ui=False)
        
        if not file_name or not temp_list:
            return
            
        # Add to the target playlist if not already present
        if temp_list[0] not in playlist.items:
            playlist.items.append(temp_list[0])
            playlist.modified = datetime.now().isoformat()
            self.save_playlists()
            self.status_bar.showMessage(f"Added {file_name} to playlist: {playlist.name}")
        else:
            self.status_bar.showMessage(f"{file_name} is already in playlist: {playlist.name}")
        
        # Restore original playlist

    def add_folder_to_specific_playlist(self, playlist, data):
        """Add folder contents to a specific playlist"""
        original_playlist = self.playlist.copy()
        original_index = self.current_index
        
        # Temporarily clear playlist to collect the folder items
        self.playlist = []
        self.add_folder_to_playlist(data)
        
        # Add the files to the specific playlist
        for item in self.playlist:
            if item not in playlist.items:
                playlist.items.append(item)
        
        # Save playlists
        playlist.modified = datetime.now().isoformat()
        self.save_playlists()
        
        # Restore original playlist
        self.playlist = original_playlist
        self.current_index = original_index
        
        self.status_bar.showMessage(f"Added folder to playlist: {playlist.name}")
    
    def add_file_to_specific_playlist(self, playlist, data):
        """Add a file to a specific playlist"""
        original_playlist = self.playlist.copy()
        original_index = self.current_index
        
        # Temporarily clear playlist to collect the file
        self.playlist = []
        self.add_file_to_playlist(data)
        
        # Add the file to the specific playlist
        if self.playlist and self.playlist[0] not in playlist.items:
            playlist.items.append(self.playlist[0])
        
        # Save playlists
        playlist.modified = datetime.now().isoformat()
        self.save_playlists()
        
        # Restore original playlist

    def highlight_current_track(self):
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            if i == self.current_index:
                item.setBackground(QColor(0, 80, 0))  # dark green
                item.setForeground(QColor(255, 255, 255))
            else:
                item.setBackground(QColor(0, 0, 0, 0))
                item.setForeground(QColor(240, 240, 255))

    def filter_playlist(self):
        text = self.playlist_search_input.text().strip().lower()
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            if text in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    def sort_playlist(self):
        mode = self.playlist_sort_combo.currentText()
        if mode == "Original":
            # TODO: restore original order if needed
            return
        # Build a list of (playlist_entry, display_text, meta) for sorting
        items = []
        for i in range(self.playlist_widget.count()):
            entry = self.playlist[i] if i < len(self.playlist) else None
            item = self.playlist_widget.item(i)
            display_text = item.text() if item else ""
            meta = {"title": display_text, "artist": "", "album": ""}
            if isinstance(entry, str) and os.path.exists(entry):
                meta["title"] = os.path.basename(entry)
            items.append((entry, display_text, meta))
        if mode == "Title":
            items.sort(key=lambda x: x[2]["title"].lower())
        elif mode == "Artist":
            items.sort(key=lambda x: x[2]["artist"].lower())
        elif mode == "Album":
            items.sort(key=lambda x: x[2]["album"].lower())
        self.playlist_widget.clear()
        new_playlist = []
        for entry, display_text, _ in items:
            self.playlist_widget.addItem(display_text)
            new_playlist.append(entry)
        # Update the underlying playlist data
        if self.active_playlist:
            self.active_playlist.items[:] = new_playlist
            self.active_playlist.modified = datetime.now().isoformat()
            self.save_playlists()
            self.playlist = self.active_playlist.items
        else:
            self.playlist = new_playlist

    
    def _check_all_scans_complete(self):
        all_done = all(not thread.isRunning() for thread in getattr(self, 'scan_threads', []))
        if all_done:
            self.scan_cloud_btn.setEnabled(True)
            self.status_bar.showMessage("Cloud scan complete")
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()
            # Clear references
            self.scan_threads = []
            self.scan_workers = []

    def get_all_playlists(self):
        # Returns a list of dicts: {id, name}
        playlists = [{'id': '__queue__', 'name': 'Current Queue'}]
        for p in self.playlists:
            playlists.append({'id': getattr(p, 'id', ''), 'name': getattr(p, 'name', 'Unnamed')})
        return playlists