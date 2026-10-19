import os
import io
import json
import time
import random
import tempfile
from datetime import datetime
from urllib.parse import urlparse
from platformdirs import user_data_dir, user_cache_dir
from cover_extractor import CoverExtractor
import subprocess
from tray import TrayController
from metadata import MetadataController
from playlists_manager import PlaylistsManager
from library_view import LibraryView
# dialogs live in dialogs.py; re-export so existing imports/patches
# (player.SettingsDialog, monkeypatched player.CloudAccountsDialog) keep working
from dialogs import CloudAccountsDialog, SettingsDialog  # noqa: F401
from playback import PlaybackEngineMixin
from visualizer import SFVisualizer
import icons

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSlider, QListWidget, QFileDialog, QMessageBox, QTreeWidget, 
    QTreeWidgetItem, QSplitter, QLineEdit, QDialog, QFormLayout, QTabWidget, 
    QToolButton, QStatusBar, QStyle, QFrame, QMenu, QProgressBar, QSystemTrayIcon,
    QComboBox, QInputDialog, QListWidgetItem, QRadioButton, QDialogButtonBox, QProgressDialog,
    QCheckBox, QWidgetAction, QGroupBox, QGridLayout, QStackedWidget, QColorDialog,
    QScrollArea
)
from PySide6.QtGui import QPainter
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QUrl, QSize, QEvent, QSettings
from PySide6.QtGui import QIcon, QAction, QKeySequence, QKeyEvent, QPalette, QColor, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaFormat

# Import custom modules
from utils import (
    SUPPORTED_EXTS, is_music_file, scan_music_files, format_time, 
    MEDIA_FOLDERS_FILE, CLOUD_FILES_FILE, PLAYLISTS_FILE,
    open_folder, atomic_write_text
)
from cloud_handlers import CLOUD_TYPES
from playlist import Playlist
from dialogs import AddCloudDialog, EditCloudDialog
from workers import DownloadWorker, ScanCloudWorker, CoverArtWorker

from web_control import WebControlServer

# Playlist files that can be dropped onto the queue (they get imported);
# audio rows are decided by utils.is_music_file.
PLAYLIST_DROP_EXTS = (".m3u", ".m3u8", ".pls", ".xspf")


def _first_text(value):
    """First text out of a tag value (list / ID3 frame / plain)."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", "replace")
        except Exception:
            return ""
    return str(value).strip()


def read_sort_tags(path):
    """Best-effort (artist, album) for playlist sorting; ("", "") when
    the file has no readable tags. The mutagen easy interface covers
    MP3/FLAC/MP4/Vorbis; raw ID3 frames are the fallback (WAV/AIFF
    containers carry ID3 but have no easy mapping)."""
    try:
        import mutagen
        artist = album = ""
        audio = mutagen.File(path, easy=True)
        if audio is not None:
            tags = getattr(audio, "tags", None) or {}
            artist = _first_text(tags.get("artist"))
            album = _first_text(tags.get("album"))
        if not (artist and album):
            raw = mutagen.File(path)
            rtags = getattr(raw, "tags", None) if raw is not None else None
            if rtags:
                if not artist:
                    artist = _first_text(rtags.get("TPE1")
                                         or rtags.get("ARTIST")
                                         or rtags.get("artist"))
                if not album:
                    album = _first_text(rtags.get("TALB")
                                        or rtags.get("ALBUM")
                                        or rtags.get("album"))
        return artist, album
    except Exception:
        return "", ""

# QThread objects whose threads outlive the code path that owned them must
# keep a strong reference, otherwise PySide destroys the C++ QThread while it
# is still running; ~QThread() then calls qFatal("QThread: Destroyed while
# thread ... is still running") which fastfails the process with
# STATUS_STACK_BUFFER_OVERRUN (0xC0000409). Entries are added by
# MusicPlayer._retire_qthread() and dropped on the thread's finished signal.
_ORPHAN_QTHREADS = []

# 0xC0000409 fix, part 2: interpreter finalization would clear this list
# while a retired thread still runs, dropping the pair's last reference
# (-> ~QThread -> qFatal). The exit guard runs before those globals are
# cleared; see thread_teardown.
from thread_teardown import register_exit_guard as _register_exit_guard  # noqa: E402

_register_exit_guard(lambda: list(_ORPHAN_QTHREADS))


class MusicPlayer(QMainWindow, PlaybackEngineMixin):
    cloud_file_downloaded = Signal(str)
    run_on_ui = Signal(object)  # pass a callable to execute on UI thread
    
    def __init__(self, startup_paths=None):
        super().__init__()
        self.setWindowTitle("HiCloud MP")
        self.resize(1120, 720)
        self.setMinimumSize(960, 640)
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
        # Remember window size/position across launches (first run keeps
        # the default 1120x720 set above).
        self._restore_window_geometry()

        # Themed icon factory (accent-tinted Feather glyphs; stock QStyle
        # icons are fully replaced). Colors refresh with every theme change.
        self.icon_factory = icons.IconFactory()
        self._refresh_icon_colors()

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
        # (thread, worker) pairs kept alive until their thread finishes; see
        # _retire_qthread(). Destroying a running QThread aborts the process.
        self._retired_qthreads = []
        
        # Media player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.7)  # 70% volume default
        # Metadata/Cover controller
        self.meta = MetadataController(self)
        # Stream-specific retry handlers (see _play_stream/_disconnect_stream_handlers)
        self._stream_status_handler = None
        self._stream_error_handler = None
        
        # Enable system media control (media keys)
        self.setup_system_media_controls()
        
        # Connect signals
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.cloud_file_downloaded.connect(self.play_downloaded_file)
        self.run_on_ui.connect(self._run_on_ui)

        # Equalizer engine (decoder -> 10-band EQ -> audio sink). Routed per
        # track when the equalizer is enabled; engine errors fall back to the
        # native QMediaPlayer path (see _engine_playback_error).
        self._using_engine = False
        self._engine_source = ('', '', '')
        from eq_engine import EQEngine
        self.eq_engine = EQEngine(self)
        self.eq_engine.position_changed.connect(self.update_position)
        self.eq_engine.duration_changed.connect(self.update_duration)
        self.eq_engine.track_finished.connect(self._on_engine_track_finished)
        self.eq_engine.error_occurred.connect(self._engine_playback_error)
        self.eq_engine.state_changed.connect(self._on_engine_state)
        
        # Library data model + background scanner (no os.walk on the UI
        # thread) and the LibraryView delegate that renders from it. These
        # must exist before setup_ui() connects search/tree signals.
        try:
            self.library_mgr = LibraryView(self)
            self.update_library_tree = self.library_mgr.update_library_tree
            self.on_library_item_clicked = self.library_mgr.on_library_item_clicked
            self.search_music = self.library_mgr.search_music
        except Exception as e:
            print(f"Warning: LibraryView init failed: {e}")
        from library_store import LibraryStore
        self.library_store = LibraryStore()
        self._local_scan_worker = None
        self._local_scan_thread = None

        # UI
        self.setup_ui()

        # Visualizer polling (~20 Hz): engine spectrum or idle baseline.
        self._viz_timer = QTimer(self)
        self._viz_timer.setInterval(50)
        self._viz_timer.timeout.connect(self._update_visualizer)
        self._viz_timer.start()
        
        # Load saved data
        self.load_media_folders()
        self.load_clouds()
        self.load_playlists()
        self.apply_output_device_setting()
        self._start_local_scan()
        
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
        
        self.web_server = None
        self.web_port = 5000
        
        # Async cover fetch state now handled by MetadataController
        
        # Auto-start web interface if enabled in settings
        if self.settings.value("web_interface", False, bool):
            self.start_web_interface()

        # Real top menu bar (moved here from the old sidebar footer buttons)
        self._create_menubar()

        # Files passed on the command line (also Windows 'open with'):
        # enqueue and preselect, never auto-play, never persist.
        self._apply_startup_paths(startup_paths)

    def _apply_startup_paths(self, paths):
        """Enqueue paths given on the command line. Missing paths are
        skipped; an empty/no-op call leaves the queue untouched."""
        paths = [p for p in (paths or []) if p and os.path.exists(p)]
        if not paths:
            return
        for p in paths:
            if p not in self.playlist:
                self.playlist.append(p)
                self.playlist_widget.addItem(os.path.basename(p))
        self.current_index = self.playlist.index(paths[0])
        
    def _create_menubar(self):
        """Standard top menu bar: File / Playback / Tools / Help."""
        mb = self.menuBar()
        # Widget-backed bar: native bars on Windows are handled out-of-process,
        # which makes Python-side wrappers transient and hides QSS styling.
        mb.setNativeMenuBar(False)

        # --- File ---
        file_menu = QMenu(self)
        file_menu.setTitle("File")
        file_menu.addAction("Add Folder", self.add_folder)
        file_menu.addAction("Add Files", self.add_files)
        file_menu.addAction("Import Playlist…", self.import_playlist)
        file_menu.addAction("Export Playlist…", self.export_playlist)
        file_menu.addAction("Rescan Library", self.rescan_library)
        file_menu.addAction("Add Cloud Account...", self.add_cloud)
        file_menu.addAction("Scan Cloud Library", self.scan_clouds)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        mb.addMenu(file_menu)

        # --- Playback ---
        playback_menu = QMenu(self)
        playback_menu.setTitle("Playback")
        playback_menu.addAction("Play / Pause", self.toggle_play)
        playback_menu.addAction("Stop", self.stop)
        playback_menu.addAction("Previous", self.prev_track)
        playback_menu.addAction("Next", self.next_track)
        playback_menu.addSeparator()
        self.shuffle_action = playback_menu.addAction("Shuffle")
        self.shuffle_action.setCheckable(True)
        self.shuffle_action.toggled.connect(self.toggle_shuffle)
        self.repeat_action = playback_menu.addAction("Repeat")
        self.repeat_action.setCheckable(True)
        self.repeat_action.toggled.connect(self.toggle_repeat)
        mb.addMenu(playback_menu)

        # --- Tools ---
        tools_menu = QMenu(self)
        tools_menu.setTitle("Tools")
        tools_menu.addAction("Equalizer…", self.open_eq_dialog)
        tools_menu.addSeparator()
        tools_menu.addAction("Web Panel", self.open_web_panel)
        tools_menu.addSeparator()
        tools_menu.addAction("Settings", self.open_settings_dialog)
        mb.addMenu(tools_menu)

        # --- Help ---
        help_menu = QMenu(self)
        help_menu.setTitle("Help")
        help_menu.addAction("About HiCloud MP", self._show_about)
        mb.addMenu(help_menu)

        # Ownership debugging vestige from the PySide wrapper-invalidation
        # investigation: keep strong refs so no transient GC can reclaim them.
        self._menu_holder = [file_menu, playback_menu, tools_menu, help_menu]

    def _show_about(self):
        QMessageBox.information(
            self, "About HiCloud MP",
            "HiCloud MP — local & cloud music player\n\n"
            "WebDAV / Ampache / Subsonic cloud streaming, web remote panel,\n"
            "playlists and library in one desktop app.\n\n"
            "Repository: github.com/PhantomPixelDev/HiCloudMP")

    def set_dark_theme(self):
        """Apply the unified theme (theme/accent/density resolved from QSettings)."""
        import theme as _theme
        _theme.apply_theme(self)
        try:
            accent = _theme.icon_colors(self.settings)[0]
            self.visualizer.set_palette(accent)
        except Exception:
            pass
        self._refresh_icon_colors()

    # === Accent icon helpers ===
    def _refresh_icon_colors(self):
        """Bind the icon factory to the live theme (accent/text/dim) and
        re-render every themed icon."""
        if not hasattr(self, 'icon_factory'):
            return
        try:
            import theme as _theme
            accent, text, dim = _theme.icon_colors(self.settings)
            self.icon_factory.set_colors(accent, text, dim)
        except Exception:
            pass
        self._apply_icons()

    def _icon(self, name, role="text", size=20):
        return self.icon_factory.icon(name, size=size, role=role)

    def _icon_play(self):
        return self._icon("play", role="onaccent", size=28)

    def _icon_pause(self):
        return self._icon("pause", role="onaccent", size=28)

    def _apply_icons(self):
        """Set themed glyph icons on every button (font-size independent)."""
        f = getattr(self, 'icon_factory', None)
        if f is None:
            return
        try:
            self.play_btn.setIcon(self._icon_play())
            self.play_btn.setIconSize(QSize(28, 28))
            self.stop_btn.setIcon(self._icon("stop", size=20))
            self.prev_btn.setIcon(self._icon("skip-back", size=20))
            self.next_btn.setIcon(self._icon("skip-forward", size=20))
            for btn, glyph in ((self.stop_btn, "stop"),
                               (self.prev_btn, "skip-back"),
                               (self.next_btn, "skip-forward")):
                btn.setIconSize(QSize(20, 20))
            self._apply_toggle_icons()
            vbtn = getattr(self, 'volume_icon', None)
            if vbtn is not None:
                glyph = "volume"
                try:
                    if self.audio_output.isMuted():
                        glyph = "volume-x"
                except Exception:
                    pass
                vbtn.setIcon(self._icon(glyph, size=20))
                vbtn.setIconSize(QSize(20, 20))
        except AttributeError:
            pass  # setup_ui() still building; icons apply once others land
        # The tray badge follows the accent color too (theme changes).
        try:
            tray = getattr(self, 'tray', None)
            if tray is not None:
                tray.update_tray_ui()
        except Exception:
            pass

    def _apply_toggle_icons(self):
        """Shuffle/Repeat glyphs follow their accentActive toggle state."""
        self.shuffle_btn.setIcon(self._icon(
            "shuffle", role="accent" if self.shuffle_btn.isChecked() else "dim"))
        self.shuffle_btn.setIconSize(QSize(20, 20))
        self.repeat_btn.setIcon(self._icon(
            "repeat", role="accent" if self.repeat_btn.isChecked() else "dim"))
        self.repeat_btn.setIconSize(QSize(20, 20))

    def open_settings_dialog(self):
        """Open the settings dialog and apply any changes"""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            dialog.save_settings()
            # Apply the unified theme (Dark/Light, accent color, density)
            import theme as _theme
            _theme.apply_theme(self)
            try:
                accent = _theme.icon_colors(dialog.settings)[0]
                self.visualizer.set_palette(accent)
            except Exception:
                pass
            self._refresh_icon_colors()
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
            from web_control import WebControlServer, panel_url, lan_ip
            token = self.ensure_web_token()
            host = self.settings.value("web/host", "127.0.0.1")
            self.web_server = WebControlServer(self, host=host, port=self.web_port, token=token)
            self.web_server.start()
            visible_ip = lan_ip() if host == "0.0.0.0" else None
            url = panel_url(self.web_port, token, lan_ip=visible_ip)
            self.status_bar.showMessage(
                f"Web remote ready: {url} — open this link from any "
                f"device on the same network.")
            return True
        except Exception as e:
            print(f"Failed to start web interface: {e}")
            QMessageBox.warning(self, "Web Interface",
                                "Failed to start web interface. Make sure Flask and Flask-SocketIO are installed.")
            self.web_server = None
            return False

    def ensure_web_token(self):
        """Return the web panel access token, generating one on first use."""
        token = self.settings.value("web/token", "")
        if not token:
            import secrets
            token = secrets.token_hex(16)
            self.settings.setValue("web/token", token)
        return token
    
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
            token = getattr(self.web_server, 'token', '') or self.ensure_web_token()
            url = f"http://localhost:{self.web_port}/?token={token}"
            webbrowser.open(url)
        else:
            # If setting is enabled, try to start it automatically
            if self.settings.value("web_interface", False, bool):
                if self.start_web_interface():
                    token = getattr(self.web_server, 'token', '') or self.ensure_web_token()
                    url = f"http://localhost:{self.web_port}/?token={token}"
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
        """Modern two-zone layout: navigation sidebar + content stage with
        transport bar. All widget attribute names are preserved (tests and the
        web-control bridge depend on them)."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setObjectName("central")
        root = QHBoxLayout(central_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ================= Sidebar =================
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(250)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 14, 14, 10)
        side.setSpacing(10)

        self.nav_brand = QLabel("HiCloud")
        self.nav_brand.setObjectName("brandTitle")
        side.addWidget(self.nav_brand)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search music...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self._search_now)
        # Live search: the index lookup is instant, so fire per keystroke,
        # coalesced into one query per 150 ms typing pause. Enter = instant.
        # Both routes go through _search_now (a stable class method doing
        # dynamic lookup) so LibraryView delegation rebinds keep working.
        self._search_debounce = QTimer(self)
        self._search_debounce.setInterval(150)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.timeout.connect(self._search_now)
        self.search_input.textChanged.connect(self._on_search_input_changed)
        side.addWidget(self.search_input)

        self.library_tree = QTreeWidget()
        self.library_tree.setHeaderHidden(True)
        self.library_tree.itemDoubleClicked.connect(self.on_library_item_clicked)
        self.library_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.library_tree.customContextMenuRequested.connect(self.show_library_context_menu)
        side.addWidget(self.library_tree, 1)

        # Library actions (2x2 grid)
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_files_btn = QPushButton("Add Files")
        self.add_cloud_btn = QPushButton("Add Cloud")
        self.scan_cloud_btn = QPushButton("Scan Cloud")

        self.add_folder_btn.clicked.connect(self.add_folder)
        self.add_files_btn.clicked.connect(self.add_files)
        self.add_cloud_btn.clicked.connect(self.add_cloud)
        self.scan_cloud_btn.clicked.connect(self.scan_clouds)

        actions_grid = QGridLayout()
        actions_grid.setSpacing(6)
        actions_grid.addWidget(self.add_folder_btn, 0, 0)
        actions_grid.addWidget(self.add_files_btn, 0, 1)
        actions_grid.addWidget(self.add_cloud_btn, 1, 0)
        actions_grid.addWidget(self.scan_cloud_btn, 1, 1)
        side.addLayout(actions_grid)

        root.addWidget(self.sidebar)

        # ================= Stage =================
        stage = QWidget()
        stage_col = QVBoxLayout(stage)
        stage_col.setContentsMargins(12, 12, 12, 8)
        stage_col.setSpacing(10)

        # Top bar: playlist selector + manage buttons
        playlist_header = QHBoxLayout()
        self.playlist_selector = QComboBox()
        self.playlist_selector.currentIndexChanged.connect(self.on_playlist_changed)
        playlist_header.addWidget(self.playlist_selector, 1)

        playlist_new_btn = QToolButton()
        playlist_new_btn.setIcon(self._icon("plus", size=16))
        playlist_new_btn.setToolTip("New Playlist")
        playlist_new_btn.clicked.connect(self.new_playlist)

        playlist_save_btn = QToolButton()
        playlist_save_btn.setIcon(self._icon("save", size=16))
        playlist_save_btn.setToolTip("Save Playlist")
        playlist_save_btn.clicked.connect(self.save_current_playlist)

        playlist_delete_btn = QToolButton()
        playlist_delete_btn.setIcon(self._icon("trash", size=16))
        playlist_delete_btn.setToolTip("Delete Playlist")
        playlist_delete_btn.clicked.connect(self.delete_current_playlist)

        playlist_header.addWidget(playlist_new_btn)
        playlist_header.addWidget(playlist_save_btn)
        playlist_header.addWidget(playlist_delete_btn)
        stage_col.addLayout(playlist_header)

        # Filter / sort row
        playlist_controls = QHBoxLayout()
        self.playlist_search_input = QLineEdit()
        self.playlist_search_input.setPlaceholderText("Filter playlist...")
        self.playlist_search_input.setClearButtonEnabled(True)
        self.playlist_search_input.textChanged.connect(self.filter_playlist)
        self.playlist_sort_combo = QComboBox()
        self.playlist_sort_combo.addItems(["Original", "Title", "Artist", "Album"])
        self.playlist_sort_combo.currentIndexChanged.connect(self.sort_playlist)
        playlist_controls.addWidget(self.playlist_search_input, 1)
        playlist_controls.addWidget(self.playlist_sort_combo)
        stage_col.addLayout(playlist_controls)

        # Content row: now-playing card + playlist
        content_row = QHBoxLayout()
        content_row.setSpacing(12)

        now_card = QFrame()
        now_card.setObjectName("nowCard")
        now_card.setFixedWidth(300)
        card_col = QVBoxLayout(now_card)
        card_col.setContentsMargins(16, 16, 16, 16)
        card_col.setSpacing(8)

        self.cover_art_label = QLabel()
        self.cover_art_label.setObjectName("coverCard")
        self.cover_art_label.setAlignment(Qt.AlignCenter)
        self.cover_art_label.setFixedSize(256, 256)
        card_col.addWidget(self.cover_art_label, 0, Qt.AlignHCenter)

        self.track_title_label = QLabel("Title: -")
        self.track_title_label.setObjectName("trackTitle")
        self.track_artist_label = QLabel("Artist: -")
        self.track_artist_label.setObjectName("trackDim")
        self.track_album_label = QLabel("Album: -")
        self.track_album_label.setObjectName("trackDim")
        card_col.addWidget(self.track_title_label)
        card_col.addWidget(self.track_artist_label)
        card_col.addWidget(self.track_album_label)
        card_col.addStretch(1)

        self.set_default_cover()

        content_row.addWidget(now_card)

        self.playlist_widget = QListWidget()
        self.playlist_widget.itemDoubleClicked.connect(self.play_selected)
        self.playlist_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(self.show_playlist_context_menu)
        # Enable drag-and-drop reordering and multi-select
        self.playlist_widget.setDragDropMode(QListWidget.InternalMove)
        self.playlist_widget.setSelectionMode(QListWidget.ExtendedSelection)
        # Keyboard driving (P3): Del = remove, Space = play, Home/End jump
        self.playlist_widget.installEventFilter(self)
        # Explorer drops land on the viewport (not the view itself), so the
        # drag/drop filter must watch both.
        self.playlist_widget.viewport().installEventFilter(self)
        content_row.addWidget(self.playlist_widget, 1)
        stage_col.addLayout(content_row, 1)

        # Transport bar
        self.transport_bar = QFrame()
        self.transport_bar.setObjectName("transportBar")
        transport_col = QVBoxLayout(self.transport_bar)
        transport_col.setContentsMargins(16, 10, 16, 12)
        transport_col.setSpacing(6)

        seek_layout = QHBoxLayout()
        seek_layout.setSpacing(10)
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
        seek_layout.addWidget(self.seek_slider, 1)
        seek_layout.addWidget(self.duration_label)
        transport_col.addLayout(seek_layout)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch(1)

        self.prev_btn = QToolButton()
        self.prev_btn.setIcon(self._icon("skip-back", size=24))
        self.prev_btn.setIconSize(QSize(24, 24))
        self.prev_btn.setFixedSize(44, 44)
        self.prev_btn.clicked.connect(self.prev_track)

        self.play_btn = QToolButton()
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setIcon(self._icon_play())
        self.play_btn.setIconSize(QSize(28, 28))
        self.play_btn.setFixedSize(56, 56)
        self.play_btn.clicked.connect(self.toggle_play)

        self.stop_btn = QToolButton()
        self.stop_btn.setIcon(self._icon("stop", size=20))
        self.stop_btn.setIconSize(QSize(20, 20))
        self.stop_btn.setFixedSize(40, 40)
        self.stop_btn.clicked.connect(self.stop)

        self.next_btn = QToolButton()
        self.next_btn.setIcon(self._icon("skip-forward", size=24))
        self.next_btn.setIconSize(QSize(24, 24))
        self.next_btn.setFixedSize(44, 44)
        self.next_btn.clicked.connect(self.next_track)

        self.shuffle_btn = QToolButton()
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setIconSize(QSize(20, 20))
        self.shuffle_btn.setFixedSize(40, 40)
        self.shuffle_btn.setToolTip("Shuffle: Play random song each time")
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)

        self.repeat_btn = QToolButton()
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.setIconSize(QSize(20, 20))
        self.repeat_btn.setFixedSize(40, 40)
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        self._apply_toggle_icons()

        buttons_layout.addWidget(self.shuffle_btn)
        buttons_layout.addWidget(self.prev_btn)
        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addWidget(self.next_btn)
        buttons_layout.addWidget(self.repeat_btn)
        buttons_layout.addStretch(1)

        # Spectrum visualizer (EQ-engine tap; calm baseline when EQ is off)
        self.visualizer = SFVisualizer()
        self.visualizer.setFixedSize(120, 32)
        buttons_layout.addWidget(self.visualizer)

        # Volume (icon = mute toggle + compact slider in the transport bar)
        self.volume_icon = QToolButton()
        self.volume_icon.setIcon(self._icon("volume", size=18))
        self.volume_icon.setIconSize(QSize(18, 18))
        self.volume_icon.setFixedSize(32, 32)
        self.volume_icon.setCursor(Qt.PointingHandCursor)
        self.volume_icon.setToolTip("Mute / unmute (click)")
        self.volume_icon.setAutoRaise(True)
        self.volume_icon.clicked.connect(self.toggle_mute)
        self._pre_mute_volume = 70

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(150)
        self.volume_slider.valueChanged.connect(self.set_volume)

        volume_h = QHBoxLayout()
        volume_h.setSpacing(6)
        volume_h.setContentsMargins(20, 0, 0, 5)
        volume_h.addWidget(self.volume_icon)
        volume_h.addWidget(self.volume_slider)
        buttons_layout.addLayout(volume_h)

        transport_col.addLayout(buttons_layout)
        stage_col.addWidget(self.transport_bar)

        root.addWidget(stage, 1)

        # Status bar with progress bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.hide()

        self.status_bar.addPermanentWidget(self.progress_bar)

        # Play Next queue visibility: a one-click badge in the status bar.
        # Hidden while the queue is empty; clicking clears the queue.
        self.queue_indicator = QToolButton()
        self.queue_indicator.setText("Play Next: 0")
        self.queue_indicator.setToolTip(
            "Tracks queued with Queue Next - click to clear")
        self.queue_indicator.setAutoRaise(True)
        self.queue_indicator.setVisible(False)
        self.queue_indicator.clicked.connect(self.clear_play_next_queue)
        self.status_bar.addPermanentWidget(self.queue_indicator)

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
            if isinstance(path, str) and path.startswith(
                    ("http://", "https://")):
                # Stream URL row (e.g. from an imported playlist): play it
                # through the streaming path with its own retry handling.
                self._play_stream(
                    path,
                    os.path.basename(path.split("?", 1)[0].rstrip("/"))
                    or path)
                self.playlist_widget.setCurrentRow(self.current_index)
                item = self.playlist_widget.item(self.current_index)
                if item:
                    self.playlist_widget.scrollToItem(item)
                self.play_btn.setIcon(self._icon_pause())
            else:
                # Local playback: detach stream-retry handlers installed by a
                # previous cloud-stream attempt so their closures cannot hijack
                # this track's media signals (EndOfMedia auto-advance, etc.)
                self._disconnect_stream_handlers()
                src = os.path.abspath(path)
                if self._route_through_engine():
                    self._engine_start('file', src)
                else:
                    # Set up and play the media
                    self.player.setSource(QUrl.fromLocalFile(src))
                    self.player.play()

                # Update UI elements
                self.playlist_widget.setCurrentRow(self.current_index)
                item = self.playlist_widget.item(self.current_index)
                if item:
                    self.playlist_widget.scrollToItem(item)
                self.play_btn.setIcon(self._icon_pause())

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
        if getattr(self, '_using_engine', False):
            if self.eq_engine.is_playing():
                self.eq_engine.pause()
            else:
                self.eq_engine.resume()
            # Update tray UI
            if hasattr(self, 'update_tray_ui'):
                self.update_tray_ui()
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setIcon(self._icon_play())
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia and self.current_index >= 0:
                self.play()
            else:
                self.player.play()
                self.play_btn.setIcon(self._icon_pause())
        # Update tray UI
        if hasattr(self, 'update_tray_ui'):
            self.update_tray_ui()
    
    def stop(self):
        if getattr(self, '_using_engine', False):
            self._using_engine = False
            self._engine_source = ('', '', '')
            self.eq_engine.stop()
            self.seek_slider.setValue(0)
            self.position_label.setText("0:00")
        else:
            self.player.stop()
        self.play_btn.setIcon(self._icon_play())
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
                open_folder(folder)
        except Exception:
            pass

            
    def _on_search_input_changed(self, _text):
        """Restart the live-search debounce (one query per typing pause)."""
        try:
            self._search_debounce.start()
        except Exception:
            pass

    def _search_now(self):
        """Explicit search (Enter): cancel the pending debounce, run now."""
        try:
            self._search_debounce.stop()
        except Exception:
            pass
        self.search_music()

    def _update_visualizer(self):
        """Feed the visualizer: engine spectrum when active, else idle."""
        try:
            if getattr(self, "_using_engine", False):
                data = self.eq_engine.get_spectrum()
            else:
                data = None
        except Exception:
            data = None
        try:
            self.visualizer.set_spectrum(data)
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
        if getattr(self, '_using_engine', False):
            self._engine_was_playing = self.eq_engine.is_playing()
            if self._engine_was_playing:
                self.eq_engine.pause()
            return
        # Store the current state to restore if needed
        self.was_playing = self.player.playbackState() == QMediaPlayer.PlayingState
        if self.was_playing:
            self.player.pause()
    
    def on_slider_released(self):
        if getattr(self, '_using_engine', False):
            if getattr(self, '_engine_was_playing', False):
                self.eq_engine.resume()
            return
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
        if getattr(self, '_using_engine', False):
            self.seek_slider.setValue(position)
            self.eq_engine.seek(int(position))
            return
        max_pos = self.player.duration()
        if position > max_pos and max_pos > 0:
            position = max_pos
            
        # Update the slider position
        self.seek_slider.setValue(position)
        
        # Only update the player position if the change is significant
        # (to avoid excessive updates during drag)
        if abs(self.player.position() - position) > 100:  # 100ms threshold
            self.player.setPosition(position)
    
    def _current_local_source(self):
        """Absolute file path of the current queue item, or None when the
        current track is a cloud stream / nothing is loaded."""
        try:
            item = self.playlist[self.current_index]
        except Exception:
            return None
        if isinstance(item, dict):
            return None
        try:
            src = os.path.abspath(str(item))
            if os.path.exists(src):
                return src
        except Exception:
            pass
        return None

    def _enable_engine_route(self, message):
        """Re-route the current local track through the engine, preserving
        position and pause state (shared by the EQ and visualizer
        toggles). Returns True when a re-route happened."""
        src = self._current_local_source()
        if src is None:
            return False   # nothing local playing: next play() routes
        from PySide6.QtMultimedia import QMediaPlayer
        was_playing = (self.effective_playback_state()
                       == QMediaPlayer.PlaybackState.PlayingState)
        pos = self.player.position()
        self._engine_start("file", src,
                           os.path.basename(src))
        if pos > 0:
            self.eq_engine.seek(int(pos))
        if not was_playing:
            pause = getattr(self.eq_engine, "pause", None)
            if callable(pause):
                pause()   # keep the track paused across the re-route
        self.status_bar.showMessage(message, 4000)
        return True

    def _revert_engine_to_native(self, message):
        """Hand the current engine track back to the native player at the
        same position (shared by the EQ and visualizer toggles)."""
        src = (getattr(self, "_engine_source", None)
               or (None, None, ""))[1]
        if not src:
            src = self._current_local_source()
        if src is None:
            self._using_engine = False
            self._engine_source = ('', '', '')
            return
        was_playing = self.eq_engine.is_playing()
        pos = max(0, int(self.eq_engine.position_ms()))
        self.eq_engine.stop()
        self._using_engine = False
        self._engine_source = ('', '', '')
        self.player.setSource(QUrl.fromLocalFile(str(src)))
        self.player.play()
        if was_playing or pos > 0:
            QTimer.singleShot(
                150, lambda: self.player.setPosition(max(0, int(pos))))
        self.status_bar.showMessage(message, 4000)

    def apply_visualizer_toggle(self, on):
        """Switch visualizer routing live (Settings checkbox apply).

        on:  route the CURRENT track through the engine (flat gains,
             position preserved) so the spectrum starts immediately.
        off: hand the current track back to native at the same position -
             unless the EQ is on, which keeps the engine route.
        Cloud streams always switch at the next track start.
        """
        try:
            if on and not getattr(self, "_using_engine", False):
                self._enable_engine_route(
                    "Visualizer on - audio now routes through the EQ engine")
                return
            if not on and getattr(self, "_using_engine", False):
                if self._eq_active():
                    return   # EQ is on: the engine route stays
                if self._route_through_engine():
                    self._sync_engine_gains()   # visualizer-only: flat
                    return
                self._revert_engine_to_native(
                    "Visualizer off - native playback restored")
        except Exception as e:
            print(f"visualizer toggle failed: {e}")

    def apply_eq_toggle(self, on):
        """Enable/disable the equalizer on the CURRENT track (live,
        VLC-style): on re-routes the native track through the engine with
        the user's gains (position preserved); off returns to native
        unless the visualizer still needs the engine route (flat then).
        Cloud streams switch at the next track."""
        try:
            self.settings.setValue("audio/eq_enabled", bool(on))
            self._flush_settings()
            if on:
                if getattr(self, "_using_engine", False):
                    self._sync_engine_gains()   # engine already runs
                else:
                    # Route even with a flat curve: enabling EQ then
                    # sliding a band must be audible immediately, without
                    # another re-route.
                    self._enable_engine_route(
                        "Equalizer on - audio now routes through the EQ engine")
            else:
                if not getattr(self, "_using_engine", False):
                    return
                if self._route_through_engine():
                    self._sync_engine_gains()   # visualizer keeps it: flat
                    return
                self._revert_engine_to_native(
                    "Equalizer off - native playback restored")
        except Exception as e:
            print(f"equalizer toggle failed: {e}")

    def make_eq_apply_cb(self):
        """apply_cb for the EQ dialog: lives-applied gains, but re-routes
        the current track only on the enable/disable transition (slider
        moves must not restart playback)."""
        last_on = [bool(self.settings.value("audio/eq_enabled",
                                            False, type=bool))]

        def apply_cb(g, on):
            on = bool(on)
            self.settings.setValue("audio/eq_gains",
                                   ",".join(f"{v:g}" for v in g))
            self._flush_settings()
            if on != last_on[0]:
                last_on[0] = on
                self.apply_eq_toggle(on)
            else:
                self.eq_engine.set_gains(
                    self._eq_gains() if on else (0.0,) * 10)

        return apply_cb

    def set_volume(self, volume):
        # Dragging the slider is an explicit level choice: leave mute. (The
        # mute toggle sets the slider to 0 with blockSignals, so this branch
        # cannot fight it.)
        try:
            if volume > 0 and self.audio_output.isMuted():
                self.audio_output.setMuted(False)
                self.volume_icon.setIcon(self._icon("volume", size=18))
        except Exception:
            pass
        self.audio_output.setVolume(volume / 100.0)
        if getattr(self, '_using_engine', False):
            self.eq_engine.set_volume(volume / 100.0)

    def toggle_mute(self):
        """Mute/unmute from the transport bar; remembers the previous level
        and applies to both output routes (native + EQ engine sink)."""
        try:
            if self.audio_output.isMuted():
                level = getattr(self, "_pre_mute_volume", 70) or 70
                self.audio_output.setMuted(False)
                self.volume_icon.setIcon(self._icon("volume", size=18))
                self.volume_slider.blockSignals(True)
                self.volume_slider.setValue(level)
                self.volume_slider.blockSignals(False)
                self.set_volume(level)
                self.status_bar.showMessage("Volume unmuted", 2000)
            else:
                level = self.volume_slider.value()
                if level > 0:
                    self._pre_mute_volume = level
                self.audio_output.setMuted(True)
                self.volume_icon.setIcon(self._icon("volume-x", size=18))
                self.volume_slider.blockSignals(True)
                self.volume_slider.setValue(0)
                self.volume_slider.blockSignals(False)
                try:
                    if getattr(self, '_using_engine', False):
                        self.eq_engine.set_volume(0.0)
                except Exception:
                    pass
                self.status_bar.showMessage("Volume muted", 2000)
        except Exception:
            pass
    
    def toggle_shuffle(self, enabled):
        # Accent highlight handled by stylesheet property (theme.py accentActive)
        self.shuffle_btn.setProperty("accentActive", enabled)
        self.shuffle_btn.style().unpolish(self.shuffle_btn)
        self.shuffle_btn.style().polish(self.shuffle_btn)
        self.shuffle_btn.setChecked(enabled)
        self._apply_toggle_icons()
        # keep the Playback menu checkbox in sync (guard against recursion)
        if hasattr(self, 'shuffle_action') and self.shuffle_action.isChecked() != enabled:
            self.shuffle_action.setChecked(enabled)
        if enabled:
            self.status_bar.showMessage("Shuffle mode enabled: random song will play after each track.")
        else:
            self.status_bar.showMessage("Shuffle mode disabled: normal order.")
        self.highlight_current_track()
    
    def toggle_repeat(self, enabled):
        self.repeat_btn.setProperty("accentActive", enabled)
        self.repeat_btn.style().unpolish(self.repeat_btn)
        self.repeat_btn.style().polish(self.repeat_btn)
        self.repeat_btn.setChecked(enabled)
        self._apply_toggle_icons()
        if hasattr(self, 'repeat_action') and self.repeat_action.isChecked() != enabled:
            self.repeat_action.setChecked(enabled)
    
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
            queued = self._take_from_play_next_queue()
            if queued is not None:
                # User's Play Next outranks repeat/shuffle/sequence
                self.current_index = queued
                self.play()
            elif self.repeat_btn.isChecked():
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
                error_msg = "Could not play media (invalid or unsupported format)"
                self.status_bar.showMessage(error_msg, 5000)
                # NEVER a modal here: this fires during playlist
                # auto-advance and a dialog would stop the queue dead. The
                # playback error is reported and the queue moves on.
                self._tray_toast("HiCloud MP", error_msg)
                self._skip_invalid_track()
            
        # Update play/pause button based on playback state
        if status in [QMediaPlayer.MediaStatus.LoadedMedia, 
                     QMediaPlayer.MediaStatus.BufferedMedia,
                     QMediaPlayer.MediaStatus.BufferingMedia]:
            self.play_btn.setIcon(self._icon_pause()
                if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState 
                else self._icon_play()
            )

    def _skip_invalid_track(self):
        """Advance past a corrupt/undecodable local file instead of
        stopping the queue. Bounded by the playlist: every skip moves the
        index forward, so a fully-corrupt queue ends at the tail with a
        clear message rather than looping."""
        try:
            if not self.playlist or not (0 <= self.current_index
                                         < len(self.playlist)):
                return
            if self.current_index < len(self.playlist) - 1:
                self.current_index += 1
                nxt = self.playlist[self.current_index]
                name = os.path.basename(str(nxt)) if not isinstance(nxt, dict) \
                    else "next track"
                self.status_bar.showMessage(
                    f"Could not play this track - skipping to {name}", 4000)
                self.play()
            else:
                self.status_bar.showMessage(
                    "Could not play media - end of playlist", 5000)
        except Exception:
            pass

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
    
    # === Equalizer routing ===
    def _eq_gains(self):
        raw = self.settings.value("audio/eq_gains", "0,0,0,0,0,0,0,0,0,0")
        try:
            parts = [float(x) for x in str(raw).split(",")]
        except (ValueError, TypeError):
            parts = []
        if len(parts) != 10:
            parts = [0.0] * 10
        return parts

    def _flush_settings(self):
        """Write pending QSettings changes to backing storage NOW.

        QSettings buffers writes and flushes on clean exit only; the
        fastfatal-class deaths of the 0xC0000409 family run no
        destructors, so buffered preferences evaporated - users had to
        re-enable the equalizer/visualizer after every crash. Preferences
        are flushed the moment they change so no crash can eat them."""
        try:
            self.settings.sync()
        except Exception:
            pass


    def open_eq_dialog(self):
        from dialogs import EqualizerDialog

        gains = self._eq_gains()
        try:
            enabled = self.settings.value("audio/eq_enabled", False, type=bool)
        except Exception:
            enabled = False
        preset = str(self.settings.value("audio/eq_preset", "Flat"))

        apply_cb = self.make_eq_apply_cb()
        dlg = EqualizerDialog(self, gains, enabled, preset, apply_cb)
        dlg.exec()
        self.settings.setValue("audio/eq_preset", dlg.preset_combo.currentText())
        self.settings.setValue("audio/eq_enabled",
                               dlg.enabled_check.isChecked())
        self._flush_settings()
        self.apply_eq_toggle(dlg.enabled_check.isChecked())
        self.status_bar.showMessage("Equalizer settings saved", 3000)

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
            
            # Track info used by every branch (provider catalogs carry it)
            base_name = os.path.splitext(file_name)[0]
            info_artist = file_info.get("artist") or "-"
            info_album = file_info.get("album") or "-"

            self.track_title_label.setText(f"Title: {base_name}")
            self.track_artist_label.setText(f"Artist: {info_artist}")
            self.track_album_label.setText(f"Album: {info_album}")
            
            self.player.stop()
            self.player.setSource(QUrl())
            QApplication.processEvents()  # Process events to ensure clean state

            if cloud_type == "webdav":
                # Nextcloud/ownCloud DAV serves files only behind Basic auth,
                # which the streaming backend cannot attach to its GET. Route
                # through the authenticated download-then-play path instead
                # (streaming had failed with endless retries).
                auth_user = cloud["config"].get("webdav_login", "")
                auth_pass = cloud["config"].get("webdav_password", "")
                self._download_and_play(
                    url, cloud_type, cloud["config"], file_name,
                    auth=(auth_user, auth_pass) if auth_user else None,
                )
            else:
                # Ampache/Subsonic embed their session auth in the URL itself
                # (action=stream / stream.view); stream directly.
                if self._route_through_engine():
                    self._engine_start('url', url, file_name)
                else:
                    self._play_stream(url, file_name)

            self.play_btn.setIcon(self._icon_pause())
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
    
    def _retire_qthread(self, thread, worker=None):
        """Keep references to a still-running QThread (and its worker) until
        the thread actually finishes.

        Dropping the last Python reference to a RUNNING QThread makes PySide
        destroy the C++ object; ~QThread() calls qFatal("QThread: Destroyed
        while thread ... is still running") which fastfails the whole process
        with 0xC0000409. A replaced reference therefore must never be the
        last one while isRunning() is true.
        """
        if thread is None:
            return
        try:
            if not thread.isRunning():
                return
        except RuntimeError:
            return  # underlying C++ object already gone
        try:
            retired = self._retired_qthreads
        except AttributeError:
            self._retired_qthreads = retired = []
        pair = (thread, worker)
        if pair not in retired:
            retired.append(pair)
        if pair not in _ORPHAN_QTHREADS:
            _ORPHAN_QTHREADS.append(pair)

        def _done(pair=pair):
            # Delivered queued on finished (verified on PySide6 6.10.3) but
            # mirror metadata._release anyway: the release must be deferred
            # and isRunning-guarded so it stays safe even if a future Qt
            # build emits finished while the thread is still tearing down -
            # dropping references synchronously there would call ~QThread on
            # a running thread and qFatal (0xC0000409).
            def _release(pair=pair):
                try:
                    if pair[0].isRunning():
                        # Final teardown in progress; retry on a later step.
                        QTimer.singleShot(50, lambda p=pair: _release(p))
                        return
                except RuntimeError:
                    pass  # underlying C++ object already gone
                for lst in (retired, _ORPHAN_QTHREADS):
                    try:
                        lst.remove(pair)
                    except ValueError:
                        pass
                try:
                    pair[0].finished.disconnect()
                except Exception:
                    pass
            QTimer.singleShot(0, _release)
        try:
            thread.finished.connect(_done)
        except Exception:
            pass

    def _download_and_play(self, url, cloud_type, config, display_name, auth=None):
        """Download the cloud track to a temporary file then play locally.
        This avoids intermittent TLS resets that can break streaming demux.
        """
        try:
            # Stop any previous download. Its thread may still be running
            # (a network read is in flight); retire it instead of dropping
            # the last reference, which would destroy a live QThread and
            # abort the process (qFatal: "QThread: Destroyed while thread
            # ... is still running").
            prev_thread = getattr(self, 'download_thread', None)
            prev_worker = getattr(self, 'download_worker', None)
            if prev_worker is not None:
                try:
                    prev_worker.abort()
                except Exception:
                    pass
            if prev_thread is not None:
                try:
                    prev_thread.quit()
                except Exception:
                    pass
                self._retire_qthread(prev_thread, prev_worker)
            # Prepare temp file path
            safe_name = os.path.basename(display_name) or 'track'
            fd, temp_path = tempfile.mkstemp(prefix='hicloud_', suffix='_' + safe_name, dir=self.temp_dir)
            os.close(fd)
            # Track for later cleanup on failures
            self.temp_files_to_cleanup.add(temp_path)

            # Setup worker in its own thread. The handlers below capture
            # THEIR OWN thread/worker: a late completion from a replaced
            # download must never touch the newer download's thread.
            self.download_thread = dl_thread = QThread()
            dl_thread.setObjectName("download")  # fatal forensics
            self.download_worker = dl_worker = DownloadWorker(url, temp_path, auth=auth)
            dl_worker.moveToThread(dl_thread)

            # UI: show progress
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            self.status_bar.showMessage(f"Downloading: {display_name}")

            def _stop_thread():
                try:
                    dl_thread.quit()
                    dl_thread.wait(1000)
                except Exception:
                    pass
                self._retire_qthread(dl_thread, dl_worker)

            # Connect signals
            dl_thread.started.connect(dl_worker.run)

            def _on_progress(p):
                # Emitted from the download thread; widget access must run on
                # the UI thread.
                self.run_on_ui.emit(lambda p=p: self.progress_bar.setValue(max(0, min(100, p))))

            dl_worker.progress.connect(_on_progress)

            def on_finished(path):
                try:
                    def _apply_finished():
                        # Runs on the UI thread. QStatusBar.showMessage(msg)
                        # with NO timeout deletes the status bar's running
                        # message QTimer right here; doing that from the
                        # download thread makes Qt skip the timer
                        # deregistration (it only warns), leaving a stale
                        # timer in the main dispatcher that later fires into
                        # freed memory (0xC0000005).
                        self.progress_bar.hide()
                        self.status_bar.showMessage(f"Download complete: {display_name}")
                        # Remove from cleanup set now that it's a valid file
                        if path in self.temp_files_to_cleanup:
                            self.temp_files_to_cleanup.remove(path)
                        self.play_downloaded_file(path)
                    self.run_on_ui.emit(_apply_finished)
                finally:
                    _stop_thread()

            dl_worker.finished.connect(on_finished)

            def on_error(err):
                try:
                    def _apply_error():
                        # Runs on the UI thread (see _apply_finished): the
                        # modal warning and the status message must never be
                        # created inside the download thread.
                        self.progress_bar.hide()
                        self.status_bar.showMessage(f"Download failed: {err}")
                        QMessageBox.warning(self, "Download Error", f"Failed to download: {err}\nAttempting to stream directly…")
                        # Fallback to stream
                        self._play_stream(url, display_name)
                    self.run_on_ui.emit(_apply_error)
                finally:
                    _stop_thread()

            dl_worker.error.connect(on_error)

            dl_thread.start()
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

            # Stop and reset source first to avoid race conditions
            self.player.stop()
            self.player.setSource(QUrl())

            # Disconnect ONLY our stream-specific handlers, then install fresh
            # ones. The app-wide on_media_status_changed subscription (auto
            # advance / shuffle / repeat) must keep working afterwards.
            self._disconnect_stream_handlers()
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
                self._stream_error_handler = handle_error
            except Exception:
                # Fallback: if signature mismatch, still attempt reconnect on media status
                self._stream_error_handler = None

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
            self._stream_status_handler = handle_media_status

            # Start playback
            self.player.play()
            self.status_bar.showMessage(f"Connecting to stream: {display_name}…")

        except Exception as e:
            error_msg = f"Failed to start stream: {str(e)}"
            self.status_bar.showMessage(error_msg)
            # Try again with backoff
            self._schedule_stream_retry(url, display_name)

    def _disconnect_stream_handlers(self):
        """Disconnect only the stream-specific slots installed by _play_stream,
        never the app-wide on_media_status_changed subscription."""
        handlers = [
            ('_stream_error_handler', self.player.errorOccurred),
            ('_stream_status_handler', self.player.mediaStatusChanged),
        ]
        for attr, signal in handlers:
            handler = getattr(self, attr, None)
            if handler is not None:
                try:
                    signal.disconnect(handler)
                except Exception:
                    pass
            setattr(self, attr, None)

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
                if self._route_through_engine():
                    self._engine_start('file', abs_path, file_name)
                    self.play_btn.setIcon(self._icon_pause())
                else:
                    self.player.setSource(url)
                    # Update UI
                    self.play_btn.setIcon(self._icon_pause())
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
        item = self.playlist_widget.itemAt(position)
        if not item:
            return
        menu = QMenu(self)
        self._build_playlist_context_menu(menu, self.playlist_widget.row(item))
        menu.exec(self.playlist_widget.viewport().mapToGlobal(position))

    def _build_playlist_context_menu(self, menu, index):
        """Context-menu builder (shared, testable): transport, Play Next,
        playlist hygiene, and import/export shortcuts."""
        selected_items = self.playlist_widget.selectedItems()
        play_action = menu.addAction("Play")
        play_action.triggered.connect(lambda: self.play_item_at_index(index))
        # Route actions on multi-selection: choosing one row plays exactly
        # that; the whole selection is acancheable as its own action.
        if len(selected_items) > 1:
            play_sel = menu.addAction("Play Selected")
            play_sel.triggered.connect(self._play_first_selected)
        queue_action = menu.addAction("Queue Next")
        queue_action.triggered.connect(self.queue_play_next)
        clear_queue_action = menu.addAction("Clear Play Next Queue")
        clear_queue_action.triggered.connect(self.clear_play_next_queue)
        clear_queue_action.setEnabled(
            bool(getattr(self, "_play_next_queue", None)))
        remove_action = menu.addAction("Remove from Playlist")
        remove_action.triggered.connect(lambda: self.remove_from_playlist(index))
        if len(selected_items) > 1:
            remove_selected_action = menu.addAction("Remove Selected")
            remove_selected_action.triggered.connect(self.remove_selected_from_playlist)
            move_up_action = menu.addAction("Move Selected Up")
            move_up_action.triggered.connect(lambda: self.move_selected_in_playlist(-1))
            move_down_action = menu.addAction("Move Selected Down")
            move_down_action.triggered.connect(lambda: self.move_selected_in_playlist(1))
        menu.addAction("Remove Duplicates", self.remove_duplicates_from_playlist)
        if self.active_playlist:
            save_action = menu.addAction("Save Playlist")
            save_action.triggered.connect(self.save_current_playlist)
        menu.addSeparator()
        menu.addAction("Import Playlist…", self.import_playlist)
        menu.addAction("Export Playlist…", self.export_playlist)
        return menu

    def _play_first_selected(self):
        """Play the TOP of the current selection (Play Selected action)."""
        rows = self.playlist_widget.row(self.playlist_widget.selectedItems()[0])
        self.play_item_at_index(rows)
    
    def remove_selected_from_playlist(self):
        selected_rows = sorted([self.playlist_widget.row(item) for item in self.playlist_widget.selectedItems()], reverse=True)
        for row in selected_rows:
            self.playlist_widget.takeItem(row)
            del self.playlist[row]
        if self.active_playlist:
            self.active_playlist.modified = datetime.now().isoformat()

    # === Play Next queue (P3) ===
    def queue_play_next(self):
        """Queue the selected rows to play right after the current track."""
        rows = sorted({self.playlist_widget.row(it)
                       for it in self.playlist_widget.selectedItems()})
        if self.current_index >= 0:
            rows = [r for r in rows if r != self.current_index]
        if not rows:
            self.status_bar.showMessage(
                "Select a track to queue next", 3000)
            return
        queue = getattr(self, "_play_next_queue", None)
        if queue is None:
            self._play_next_queue = queue = []
        queue.extend(rows)
        self._update_queue_indicator()
        self.status_bar.showMessage(
            f"{len(rows)} track{'s' if len(rows) != 1 else ''} queued"
            f" to play next ({len(queue)} queued)", 3000)

    def _update_queue_indicator(self):
        """Status-bar badge mirrors the Play Next queue depth."""
        try:
            n = len(getattr(self, "_play_next_queue", None) or [])
            self.queue_indicator.setText(f"Play Next: {n}")
            self.queue_indicator.setVisible(n > 0)
        except Exception:
            pass

    def clear_play_next_queue(self):
        """Drop everything waiting in the Play Next queue."""
        n = len(getattr(self, "_play_next_queue", None) or [])
        self._play_next_queue = []
        self._update_queue_indicator()
        if n:
            self.status_bar.showMessage(
                f"Play Next queue cleared"
                f" ({n} track{'s' if n != 1 else ''})", 3000)
        else:
            self.status_bar.showMessage("Play Next queue is empty", 3000)

    def _take_from_play_next_queue(self):
        """Pop the next valid queued row for auto-advance; None when the
        queue is empty. Rows that outlived their track vanish silently."""
        queue = getattr(self, "_play_next_queue", None)
        while queue:
            idx = queue.pop(0)
            if 0 <= idx < len(self.playlist):
                self._update_queue_indicator()
                return idx
        self._update_queue_indicator()
        return None

    def remove_duplicates_from_playlist(self):
        """Drop repeated queue rows (same normalized path, or the same
        cloud track), keeping the first occurrence."""
        seen = set()
        keep = []
        for item in self.playlist:
            if isinstance(item, dict):
                key = ("cloud", item.get("cloud_idx"), item.get("file_idx"))
            else:
                key = os.path.normcase(str(item))
            if key in seen:
                continue
            seen.add(key)
            keep.append(item)
        dupes = len(self.playlist) - len(keep)
        if dupes:
            self.playlist[:] = keep
            self.playlist_widget.clear()
            for it in self.playlist:
                if isinstance(it, dict):
                    try:
                        cloud = self.clouds[it.get("cloud_idx")]
                        file_info = cloud["files"][it.get("file_idx")]
                        name = os.path.basename(file_info["path"])
                    except Exception:
                        name = "Cloud"
                    self.playlist_widget.addItem(f"{name} (Cloud)")
                else:
                    self.playlist_widget.addItem(os.path.basename(str(it)))
            if self.current_index >= len(self.playlist):
                self.current_index = len(self.playlist) - 1
            if self.active_playlist:
                self.active_playlist.modified = datetime.now().isoformat()
        self.status_bar.showMessage(
            (f"Removed {dupes} duplicate{'s' if dupes != 1 else ''}"
             if dupes else "No duplicates in the playlist"), 4000)

    # === Playlist keyboard driving (P3) ===
    def eventFilter(self, obj, event):
        """Playlist widget keys: Del removes the selection, Space starts
        the selected track, Home/End jump selection extremes. The viewport
        filter handles Explorer drag/drop (playlist files import, audio
        rows queue up) while internal reorder drags pass through."""
        if obj is self.playlist_widget and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Delete:
                self.remove_selected_from_playlist()
                return True
            if key == Qt.Key_Space:
                row = self.playlist_widget.currentRow()
                if row >= 0:
                    self.play_item_at_index(row)
                return True
            if key == Qt.Key_Home:
                if self.playlist_widget.count():
                    self.playlist_widget.setCurrentRow(0)
                return True
            if key == Qt.Key_End:
                count = self.playlist_widget.count()
                if count:
                    self.playlist_widget.setCurrentRow(count - 1)
                    self.playlist_widget.item(count - 1).setSelected(True)
                return True
        if obj is self.playlist_widget.viewport():
            et = event.type()
            if et in (QEvent.DragEnter, QEvent.DragMove):
                if self._external_drop_ok(event.mimeData()):
                    event.acceptProposedAction()
                    return True
            elif et == QEvent.Drop:
                if self._external_drop_ok(event.mimeData()):
                    self._handle_file_drop(
                        self._drop_paths_from_mime(event.mimeData()))
                    event.acceptProposedAction()
                    return True
        return super().eventFilter(obj, event)

    def _drop_paths_from_mime(self, mime):
        """Local file paths carried by a drag; [] for anything else (the
        internal reorder mime carries no urls)."""
        try:
            if mime is None or not mime.hasUrls():
                return []
            return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
        except Exception:
            return []

    def _external_drop_ok(self, mime):
        """True when the drop carries at least one row we can use: a
        playlist file to import or a supported audio file to queue."""
        for p in self._drop_paths_from_mime(mime):
            low = p.lower()
            if low.endswith(PLAYLIST_DROP_EXTS) or is_music_file(p):
                return True
        return False

    def _handle_file_drop(self, paths):
        """Explorer drop: playlist files import through the shared path,
        audio files append to the queue. Never fatal."""
        try:
            playlists = [p for p in paths
                         if p.lower().endswith(PLAYLIST_DROP_EXTS)]
            audio = [p for p in paths
                     if not p.lower().endswith(PLAYLIST_DROP_EXTS)
                     and is_music_file(p)]
            for p in playlists:
                self._import_playlist_file(p)
            if audio:
                for p in audio:
                    self.playlist.append(p)
                    self.playlist_widget.addItem(os.path.basename(p))
                if self.current_index < 0 and self.playlist:
                    self.current_index = 0
                n = len(audio)
                self.status_bar.showMessage(
                    f"Added {n} dropped file{'s' if n != 1 else ''} "
                    "to the queue", 4000)
            return bool(playlists) or bool(audio)
        except Exception:
            return False
    
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
    
    def add_folder(self):
        """Add a folder to the media library"""
        folder = QFileDialog.getExistingDirectory(self, "Add Media Folder")
        if folder and folder not in self.media_folders:
            self.media_folders.append(folder)
            self.save_media_folders()
            self.update_library_tree()
            self._start_local_scan()
    
    def add_files(self):
        """Add individual music files to the library or playlist"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Music Files",
            "",
            "Music Files (%s);;All Files (*.*)" %
            " ".join("*" + e for e in SUPPORTED_EXTS)
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
                self._start_local_scan()
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
    
    # === Playlist import / export (File menu, P2b) ===
    def import_playlist(self):
        """Load an m3u/m3u8/pls/xspf file into the current queue.

        Relative paths resolve against the playlist file's folder; local
        audio files and stream URLs are appended (URL rows play through the
        streaming path); undecodable/missing rows are skipped, never fatal.
        """
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "Import playlist", "",
                "Playlists (*.m3u *.m3u8 *.pls *.xspf);;All Files (*.*)")
            if not path:
                return
            self._import_playlist_file(path)
        except Exception as e:
            self.status_bar.showMessage(f"Import failed: {e}", 6000)

    def _import_playlist_file(self, path):
        """Import one playlist file into the queue. Shared by the menu
        action and drag-drop; returns (added, skipped)."""
        from playlist_io import PlaylistIO
        try:
            entries = PlaylistIO.import_playlist(path)["entries"]
            base = os.path.dirname(path)
            added = skipped = 0
            for entry in entries:
                p = entry.get("path") or ""
                if not p:
                    skipped += 1
                    continue
                if p.startswith(("http://", "https://")):
                    self.playlist.append(p)
                    display = os.path.basename(p.split("?", 1)[0].rstrip("/")) \
                        or p
                    self.playlist_widget.addItem(f"{display} (Stream)")
                    added += 1
                    continue
                resolved = p if os.path.isabs(p) else os.path.normpath(
                    os.path.join(base, p))
                if not is_music_file(resolved) or not os.path.isfile(resolved):
                    skipped += 1
                    continue
                self.playlist.append(resolved)
                self.playlist_widget.addItem(os.path.basename(resolved))
                added += 1
            if added and len(self.playlist) == added and self.current_index < 0:
                self.current_index = 0
            msg = f"Imported {added} tracks from playlist"
            if skipped:
                msg += f" ({skipped} skipped)"
            self.status_bar.showMessage(msg, 4000)
            return added, skipped
        except Exception as e:
            self.status_bar.showMessage(f"Import failed: {e}", 6000)
            return 0, 0

    def export_playlist(self):
        """Write the queue (current selection, else everything) to a
        playlist file. Cloud tracks are not exportable (account-bound
        rows); local files become paths/EXTINF rows, relativized by the
        writer when they live under the export folder."""
        from playlist_io import PlaylistIO
        try:
            rows = self.playlist_widget.selectedItems()
            picks = [self.playlist_widget.row(it) for it in rows]
            if not picks:
                picks = list(range(len(self.playlist)))
            entries = []
            skipped = 0
            for i in picks:
                if i < 0 or i >= len(self.playlist):
                    continue   # widget/model row drift guard
                item = self.playlist[i]
                if isinstance(item, dict):
                    skipped += 1
                    continue
                if isinstance(item, str) and item.startswith(
                        ("http://", "https://")):
                    entries.append({
                        "path": item,
                        "title": os.path.splitext(
                            os.path.basename(item.split("?", 1)[0]))[0],
                        "duration": None})
                    continue
                entries.append({
                    "path": os.path.abspath(item),
                    "title": os.path.splitext(os.path.basename(item))[0],
                    "duration": None})
            if not entries:
                self.status_bar.showMessage(
                    "Nothing exportable in the queue", 4000)
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "Export playlist", "",
                "M3U playlist (*.m3u8);;M3U classic (*.m3u);;PLS playlist"
                " (*.pls);;XSPF playlist (*.xspf)")
            if not path:
                return
            n = PlaylistIO.export_playlist(
                path, entries,
                base_dir=os.path.dirname(os.path.abspath(path)))
            msg = f"Exported {n} tracks to playlist"
            if skipped:
                msg += (f" ({skipped} cloud track"
                        f"{'s' if skipped != 1 else ''} excluded)")
            self.status_bar.showMessage(msg, 4000)
        except Exception as e:
            self.status_bar.showMessage(f"Export failed: {e}", 6000)

    def add_cloud(self):
        """Add or manage cloud storage accounts"""
        # Snapshot BEFORE constructing the dialog: AddCloudDialog.__init__ can
        # (and, for prefilled edits, does) mutate the shared list even before exec().
        try:
            import json as _json
            snapshot = _json.dumps(self.clouds, sort_keys=True, default=str)
        except Exception:
            snapshot = sorted((c.get("name", ""), c.get("type", "")) for c in self.clouds)
        dlg = CloudAccountsDialog(self, self.clouds)
        dlg.exec()
        # The dialog edits the shared clouds list in place (add/edit/remove,
        # including config-credential edits); persist on any change.
        try:
            changed = _json.dumps(self.clouds, sort_keys=True, default=str) != snapshot
        except Exception:
            changed = True
        if changed:
            self.save_clouds()
            self.update_library_tree()
            self.status_bar.showMessage(f"Cloud accounts updated ({len(self.clouds)})")
    
    def scan_clouds(self):
        if not self.clouds:
            self.status_bar.showMessage("No cloud accounts configured")
            return
        # Retire still-running threads from a previous scan (the File-menu
        # action bypasses the disabled button). Dropping the last reference
        # to a running QThread would destroy it -> qFatal -> process abort.
        old_threads = list(getattr(self, 'scan_threads', []) or [])
        old_workers = list(getattr(self, 'scan_workers', []) or [])
        for i, old_thread in enumerate(old_threads):
            old_worker = old_workers[i] if i < len(old_workers) else None
            if old_worker is not None and hasattr(old_worker, 'abort'):
                try:
                    old_worker.abort()
                except Exception:
                    pass
            try:
                old_thread.quit()
            except Exception:
                pass
            self._retire_qthread(old_thread, old_worker)
        self.scan_cloud_btn.setEnabled(False)
        self.scan_threads = []
        self.scan_workers = []
        self._scan_errors = []
        self.status_bar.showMessage(f"Starting cloud scan ({len(self.clouds)} accounts)…")
        for idx, cloud in enumerate(self.clouds):
            thread = QThread()
            thread.setObjectName(f"scan-cloud-{idx}")  # fatal forensics
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
            # (no thread.deleteLater-on-own-finished: aborts mid-teardown)
            # handle_scan_complete runs BEFORE thread.quit is processed, so the
            # not-running check needs a second chance on real thread exit.
            thread.finished.connect(self._check_all_scans_complete)
            self.scan_threads.append(thread)
        for thread in self.scan_threads:
            thread.start()

    def update_scan_progress(self, progress, status, cloud_name):
        self.status_bar.showMessage(f"Scanning {cloud_name}: {status}", 0)

    def handle_scan_complete(self, cloud_idx, files):
        try:
            if 0 <= cloud_idx < len(self.clouds):
                self.clouds[cloud_idx]["files"] = files
                self.save_clouds()
                self.update_library_tree()
                name = self.clouds[cloud_idx]["name"]
                self.status_bar.showMessage(f"Scan: {name} — {len(files)} tracks", 0)
        finally:
            self._check_all_scans_complete()

    def handle_scan_error(self, cloud_idx, error_msg):
        name = self.clouds[cloud_idx]["name"] if 0 <= cloud_idx < len(self.clouds) else "?"
        self._scan_errors.append((name, error_msg))
        self.status_bar.showMessage(f"Scan: {name} failed — {str(error_msg)[:120]}", 0)
        self._check_all_scans_complete()

    def cancel_cloud_scan(self):
        for worker in getattr(self, 'scan_workers', []):
            if hasattr(worker, 'abort'):
                worker.abort()
        self.status_bar.showMessage("Cloud scan canceled")

    # ------------------------------------------------ local library scan
    def _start_local_scan(self):
        """(Re)scan local media folders on a daemon thread; results arrive
        on the UI thread via run_on_ui. One scan at a time."""
        import threading as _threading
        from workers import LibraryScanWorker
        self._scan_generation = getattr(self, "_scan_generation", 0) + 1
        gen = self._scan_generation
        if self._local_scan_worker is not None:
            self._local_scan_worker.abort()
        self._local_scan_worker = None
        self._local_scan_thread = None
        self.library_store.reset()
        self.update_library_tree()
        if not self.media_folders:
            return
        worker = LibraryScanWorker(self.media_folders, self.run_on_ui.emit)
        worker.on_folder = lambda f, s: self._on_local_folder_scanned(gen, f, s)
        worker.on_files = lambda f, c: self._on_local_files_scanned(gen, f, c)
        worker.on_indexed = lambda p: self._on_local_indexed(gen, p)
        worker.on_finished = lambda t: self._on_local_scan_finished(gen, t)
        self._local_scan_worker = worker
        thread = _threading.Thread(target=worker.run, daemon=True,
                                   name="library-scan")
        self._local_scan_thread = thread
        thread.start()

    def _superseded(self, gen):
        """True when a newer scan replaced this one (drop stale batches)."""
        return gen != getattr(self, "_scan_generation", 0)

    def _on_local_folder_scanned(self, gen, folder, subdirs):
        if self._superseded(gen):
            return
        self.library_store.add_folder(folder, subdirs)
        self._refresh_local_section()

    def _on_local_files_scanned(self, gen, folder, chunk):
        if self._superseded(gen):
            return
        self.library_store.add_tree_files(folder, chunk)
        self._refresh_local_section()

    def _on_local_indexed(self, gen, paths):
        if self._superseded(gen):
            return
        self.library_store.add_indexed(paths)
        self.status_bar.showMessage(f"Library: {self.library_store.local_count()} tracks", 3000)

    def _on_local_scan_finished(self, gen, total):
        if self._superseded(gen):
            return
        self._local_scan_worker = None
        self._local_scan_thread = None
        self.status_bar.showMessage(f"Library scan complete: {total} tracks", 5000)

    # ------------------------------------------------ audio output device
    def _make_native_output(self, device):
        """Build the QAudioOutput for `device` (None = system default)."""
        from PySide6.QtMultimedia import QAudioOutput
        if device is None:
            return QAudioOutput()
        return QAudioOutput(device)

    def apply_output_device_setting(self):
        """Resolve audio/output_device and apply to native + engine."""
        try:
            import audio_devices
            device = audio_devices.resolve_output(
                str(self.settings.value("audio/output_device", "", type=str)
                    or ""))
        except Exception as e:
            print(f"audio output device: resolve failed: {e}")
            device = None
        # Engine first: it only takes effect at the next sink creation,
        # and must not be skipped by a native-swap hiccup.
        try:
            self.eq_engine.set_output_device(device)
        except Exception as e:
            print(f"audio output device: engine push failed: {e}")
        try:
            output = self._make_native_output(device)
            self.player.setAudioOutput(output)
            self.audio_output = output
            try:
                volume = self.settings.value("volume", 70, int)
                output.setVolume(volume / 100.0)
            except Exception:
                pass
        except Exception as e:
            print(f"audio output device: native apply failed: {e}")

    def cancel_local_scan(self):
        if self._local_scan_worker is not None:
            self._local_scan_worker.abort()
            self.status_bar.showMessage("Library scan canceled")

    def rescan_library(self):
        """File > Rescan Library: re-walk media folders in the background."""
        self._start_local_scan()
        self.status_bar.showMessage("Rescanning library…")

    def _refresh_local_section(self):
        """Re-render only the Local Media subtree from the store."""
        try:
            self.library_mgr.refresh_local_section()
        except Exception:
            pass

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
            atomic_write_text(MEDIA_FOLDERS_FILE, json.dumps(self.media_folders))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save media folders: {e}")
    
    def save_clouds(self):
        """Save cloud accounts to file"""
        try:
            atomic_write_text(CLOUD_FILES_FILE, json.dumps(self.clouds))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save cloud accounts: {e}")
    
    def save_playlists(self):
        """Save all playlists to file"""
        try:
            playlists_data = [p.to_dict() for p in self.playlists]
            atomic_write_text(PLAYLISTS_FILE, json.dumps(playlists_data))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save playlists: {e}")

    def _restore_window_geometry(self):
        """Apply the saved window size/position, when there is one."""
        try:
            geo = self.settings.value("ui/window_geometry")
            if geo is not None:
                self.restoreGeometry(geo)
        except Exception:
            pass

    def _save_window_geometry(self):
        try:
            self.settings.setValue("ui/window_geometry",
                                   self.saveGeometry())
        except Exception:
            pass

    def closeEvent(self, event):
        # Stop the EQ engine before the native player (it owns a QAudioSink
        # and QAudioDecoder that must be torn down cleanly).
        try:
            self.eq_engine.stop()
        except Exception:
            pass
        # Guarded: a dead backend must never interrupt the close mid-way
        # (state saves further below matter more than any single step).
        try:
            self.player.stop()
        except Exception:
            pass
        # Release the decoder BEFORE teardown: the FFmpeg backend crashes at
        # exit when the app closes while media is still attached (exit code 1).
        try:
            self.player.setSource(QUrl())
        except Exception:
            pass
        # Abort any in-flight cloud download and flush its thread
        try:
            if getattr(self, 'download_worker', None) is not None:
                self.download_worker.abort()
        except Exception:
            pass
        try:
            dl_thread = getattr(self, 'download_thread', None)
            if dl_thread is not None:
                dl_thread.quit()
                dl_thread.wait(2000)
                # If it is still running (stalled read), keep it strongly
                # referenced: destroying a running QThread aborts the process.
                self._retire_qthread(
                    dl_thread, getattr(self, 'download_worker', None))
        except Exception:
            pass
        # Flush running cloud-scan threads (retire any that outlive the wait)
        try:
            scan_threads = list(getattr(self, 'scan_threads', []) or [])
            scan_workers = list(getattr(self, 'scan_workers', []) or [])
            for i, scan_thread in enumerate(scan_threads):
                scan_worker = scan_workers[i] if i < len(scan_workers) else None
                try:
                    if scan_worker is not None and hasattr(scan_worker, 'abort'):
                        scan_worker.abort()
                except Exception:
                    pass
                try:
                    scan_thread.quit()
                    if not scan_thread.wait(1000):
                        self._retire_qthread(scan_thread, scan_worker)
                except Exception:
                    pass
        except Exception:
            pass
        # Abort pending cover-art workers
        try:
            if hasattr(self, 'meta'):
                self.meta.stop()
        except Exception:
            pass
        # Stop web server if running (guarded: close must complete)
        try:
            if self.web_server:
                self.web_server.stop()
                self.web_server = None
        except Exception:
            self.web_server = None
        # Clean up temporary files
        for temp_file in list(self.temp_files_to_cleanup):
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    self.temp_files_to_cleanup.remove(temp_file)
            except Exception as e:
                print(f"Error deleting temp file {temp_file}: {e}")

        # Save state - each guarded independently: one broken save must
        # never skip the others (a close that ate the playlists file was
        # the failure mode this guards against).
        for step in (self.save_media_folders, self.save_clouds,
                     self.save_playlists, self._save_window_geometry):
            try:
                step()
            except Exception as e:
                print(f"Warning: state save failed during close: {e}")
        # QSettings writes are buffered; make sure they hit disk even if
        # the process dies immediately after close.
        try:
            self.settings.sync()
        except Exception:
            pass
        
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
                        lambda checked, p=playlist, d=data: self.add_file_to_specific_playlist(p, d)
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
        widget = self.playlist_widget
        widget.setUpdatesEnabled(False)
        try:
            for i in range(widget.count()):
                item = widget.item(i)
                if text in item.text().lower():
                    item.setHidden(False)
                else:
                    item.setHidden(True)
        finally:
            widget.setUpdatesEnabled(True)

    def sort_playlist(self):
        widget = self.playlist_widget
        mode = self.playlist_sort_combo.currentText()
        if mode == "Original":
            # TODO: restore original order if needed
            return
        widget.setUpdatesEnabled(False)
        try:
            # Build a list of (playlist_entry, display_text, meta) for sorting
            items = []
            for i in range(widget.count()):
                entry = self.playlist[i] if i < len(self.playlist) else None
                item = widget.item(i)
                display_text = item.text() if item else ""
                meta = {"title": display_text, "artist": "", "album": ""}
                if isinstance(entry, str) and os.path.exists(entry):
                    meta["title"] = os.path.basename(entry)
                    if mode in ("Artist", "Album"):
                        meta["artist"], meta["album"] = \
                            read_sort_tags(entry)
                items.append((entry, display_text, meta))
            if mode == "Title":
                items.sort(key=lambda x: x[2]["title"].lower())
            elif mode == "Artist":
                items.sort(key=lambda x: (x[2]["artist"].lower(),
                                          x[2]["title"].lower()))
            elif mode == "Album":
                items.sort(key=lambda x: (x[2]["album"].lower(),
                                          x[2]["artist"].lower(),
                                          x[2]["title"].lower()))
            widget.clear()
            new_playlist = []
            for entry, display_text, _ in items:
                widget.addItem(display_text)
                new_playlist.append(entry)
        finally:
            widget.setUpdatesEnabled(True)
        # Update the underlying playlist data
        if self.active_playlist:
            self.active_playlist.items[:] = new_playlist
            self.active_playlist.modified = datetime.now().isoformat()
            self.save_playlists()
            self.playlist = self.active_playlist.items
        else:
            self.playlist = new_playlist

    
    def _check_all_scans_complete(self):
        threads = list(getattr(self, 'scan_threads', []))
        if not threads:
            return
        # Threads may not have finished their quit yet — recheck shortly.
        if any(thread.isRunning() for thread in threads):
            QTimer.singleShot(100, self._check_all_scans_complete)
            return
        self.scan_cloud_btn.setEnabled(True)
        self.scan_threads = []
        self.scan_workers = []
        errors = list(getattr(self, '_scan_errors', []))
        if errors:
            summary = "\n\n".join(f"{name}: {msg}" for name, msg in errors[:6])
            QMessageBox.critical(self, "Cloud Scan Finished With Errors",
                                 f"{len(errors)} account scan(s) failed:\n\n{summary}")
        else:
            self.status_bar.showMessage("Cloud scan complete", 3000)

    def get_all_playlists(self):
        # Returns a list of dicts: {id, name}
        playlists = [{'id': '__queue__', 'name': 'Current Queue'}]
        for p in self.playlists:
            playlists.append({'id': getattr(p, 'id', ''), 'name': getattr(p, 'name', 'Unnamed')})
        return playlists