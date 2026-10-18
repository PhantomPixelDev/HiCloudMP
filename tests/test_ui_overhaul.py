"""Pin the 2026-10-18 UI overhaul: modern two-zone layout (sidebar + stage),
transport bar, large cover card, no legacy menubar. All legacy attribute names
must survive (tests + web_control bridge depend on them)."""

LEGACY_WIDGETS = [
    "search_input", "library_tree", "add_folder_btn", "add_files_btn",
    "add_cloud_btn", "scan_cloud_btn", "playlist_selector",
    "playlist_search_input", "playlist_sort_combo", "playlist_widget",
    "cover_art_label", "track_title_label", "track_artist_label",
    "track_album_label", "position_label", "duration_label", "seek_slider",
    "prev_btn", "play_btn", "stop_btn", "next_btn", "shuffle_btn",
    "repeat_btn", "volume_slider", "status_bar", "progress_bar",
]


def _attr_names(obj):
    out = set()
    for k in vars(obj).keys():
        out.add(k)
    return out


def test_player_has_modern_structural_widgets(music_player):
    assert music_player.sidebar.objectName() == "sidebar"
    assert music_player.sidebar.parent() is music_player.centralWidget() or \
        music_player.sidebar.parent() is not None
    assert music_player.nav_brand.objectName() == "brandTitle"
    assert music_player.transport_bar.objectName() == "transportBar"
    # The play button is a big accent circle
    assert music_player.play_btn.objectName() == "playBtn"
    assert music_player.play_btn.minimumSize().width() >= 52
    # Big cover
    assert music_player.cover_art_label.minimumSize().width() >= 256


def test_no_legacy_menubar(music_player):
    from PySide6.QtWidgets import QMenuBar
    assert music_player.findChild(QMenuBar) is None, "legacy menu bar must be gone"


def test_stream_handler_slots_reset(music_player):
    """Sanity pin for stream handler slots (Task 11 contract keeps holding)."""
    assert getattr(music_player, "_stream_status_handler", None) is None
    assert getattr(music_player, "_stream_error_handler", None) is None


def test_theme_contains_structural_rules():
    import theme as theme_mod
    qss = theme_mod.build_qss(theme="Dark", accent="#10b981", density="comfortable")
    for anchor in ("QWidget#sidebar", "QToolButton#playBtn", "QFrame#transportBar",
                   "QLabel#trackTitle", "QLabel#brandTitle"):
        assert anchor in qss, f"missing structural rule: {anchor}"


def test_legacy_contract_widgets_present(music_player):
    names = _attr_names(music_player)
    for attr in LEGACY_WIDGETS:
        assert attr in names, f"legacy widget lost during overhaul: {attr}"
