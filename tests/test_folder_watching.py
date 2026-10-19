"""Library folders were only rescanned on demand: files added in Explorer
did not show up until File > Rescan. A QFileSystemWatcher now watches the
library roots and their subdirectories; a burst of changes debounces into
one background rescan (the watch list is rebuilt after it, so new
subfolders are picked up and removed folders are dropped). The watch set
is bounded.
"""
import os

import folder_watch


def test_watcher_watches_existing_directories(music_player, tmp_path):
    mp = music_player
    root = tmp_path / "library"
    sub = root / "album"
    sub.mkdir(parents=True)
    missing = str(tmp_path / "gone")
    mp.media_folders = [str(root), missing]

    mp._refresh_folder_watcher()

    watched = {os.path.normcase(p) for p in mp._folder_watcher.directories()}
    assert os.path.normcase(str(root)) in watched
    assert os.path.normcase(str(sub)) in watched
    assert os.path.normcase(missing) not in watched


def test_change_debounces_into_one_rescan(music_player, tmp_path, qtbot,
                                          monkeypatch):
    mp = music_player
    root = tmp_path / "lib"
    root.mkdir()
    mp.media_folders = [str(root)]
    mp._refresh_folder_watcher()
    rescans = []
    monkeypatch.setattr(mp, "_start_local_scan",
                        lambda: rescans.append(1), raising=False)
    mp._folder_watch_timer.setInterval(40)

    mp._on_watched_folder_changed(str(root))
    mp._on_watched_folder_changed(str(root))
    mp._on_watched_folder_changed(str(root))
    assert rescans == [], "must wait for the burst to settle"

    qtbot.wait(180)
    assert rescans == [1], "one debounced rescan for the burst"


def test_new_subfolder_is_watched_after_refresh(music_player, tmp_path):
    mp = music_player
    root = tmp_path / "lib"
    root.mkdir()
    mp.media_folders = [str(root)]
    mp._refresh_folder_watcher()

    new_dir = root / "new_album"
    new_dir.mkdir()
    mp._refresh_folder_watcher()

    watched = {os.path.normcase(p) for p in mp._folder_watcher.directories()}
    assert os.path.normcase(str(new_dir)) in watched


def test_removed_folder_is_unwatched(music_player, tmp_path):
    mp = music_player
    root = tmp_path / "lib"
    root.mkdir()
    mp.media_folders = [str(root)]
    mp._refresh_folder_watcher()
    assert mp._folder_watcher.directories()

    mp.media_folders = []
    mp._refresh_folder_watcher()

    assert mp._folder_watcher.directories() == []


def test_watch_list_is_bounded(music_player, tmp_path, monkeypatch):
    mp = music_player
    root = tmp_path / "big"
    for i in range(6):
        (root / f"d{i}").mkdir(parents=True)
    mp.media_folders = [str(root)]
    monkeypatch.setattr(folder_watch, "FOLDER_WATCH_MAX_DIRS", 4)

    mp._refresh_folder_watcher()

    assert len(mp._folder_watcher.directories()) <= 4


def test_watch_walk_prefers_shallow_dirs_over_deep_chain(
        music_player, tmp_path, monkeypatch):
    """Breadth-first: an album folder next to a deep chain must be watched
    before descending into the chain (old os.walk order missed siblings)."""
    mp = music_player
    root = tmp_path / "lib"
    deep = root / "deep" / "a" / "b"
    deep.mkdir(parents=True)
    album = root / "album"
    album.mkdir()
    mp.media_folders = [str(root)]
    monkeypatch.setattr(folder_watch, "FOLDER_WATCH_MAX_DIRS", 4)

    mp._refresh_folder_watcher()

    watched = {os.path.normcase(p) for p in mp._folder_watcher.directories()}
    assert os.path.normcase(str(album)) in watched
    assert os.path.normcase(str(deep)) not in watched, \
        "deepest chain must not crowd out shallow album folders"


def test_large_watch_list_is_added_in_chunks(qtbot, music_player, tmp_path,
                                             monkeypatch):
    """Adding hundreds of paths takes ~1 ms each on Windows: do it across
    event-loop ticks instead of freezing startup for half a second."""
    mp = music_player
    root = tmp_path / "big"
    for i in range(12):
        (root / f"d{i}").mkdir(parents=True)
    mp.media_folders = [str(root)]
    monkeypatch.setattr(folder_watch, "FOLDER_WATCH_MAX_DIRS", 20)
    monkeypatch.setattr(folder_watch, "FOLDER_WATCH_ADD_BATCH", 3)
    monkeypatch.setattr(folder_watch, "FOLDER_WATCH_ADD_INTERVAL_MS", 5)

    mp._refresh_folder_watcher()

    assert len(mp._folder_watcher.directories()) <= 3, \
        "first tick must not add the whole watch set"
    assert mp._pending_watch_paths, "remaining paths must be queued"
    qtbot.wait(300)
    watched = {os.path.normcase(p) for p in mp._folder_watcher.directories()}
    assert os.path.normcase(str(root)) in watched
    assert os.path.normcase(str(root / "d11")) in watched


def test_refresh_after_scan_does_not_raise_with_no_folders(music_player):
    mp = music_player
    mp.media_folders = []
    mp._refresh_folder_watcher()   # must be a no-op, not a crash
    assert mp._folder_watcher.directories() == []
