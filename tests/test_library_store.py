"""Library as data: an in-memory store built by a background worker.
The UI tree renders from the store - os.walk must never run on the UI
thread, and search must never touch the filesystem."""

from hicloudmp.core.library_store import LibraryStore


def test_store_merges_folder_scan(tmp_path):
    store = LibraryStore()
    f = str(tmp_path / "a.mp3")
    store.add_folder(str(tmp_path), ["sub"])
    store.add_tree_files(str(tmp_path), [f])
    store.add_indexed([f, str(tmp_path / "sub" / "deep.flac")])
    tree = store.local_tree_data()
    assert tree[str(tmp_path)] == {"subdirs": ["sub"], "files": [f]}
    assert store.local_count() == 2  # includes the deep file


def test_store_chunked_files_accumulate(tmp_path):
    store = LibraryStore()
    files = [str(tmp_path / f"{i}.mp3") for i in range(5)]
    store.add_folder(str(tmp_path), [])
    store.add_tree_files(str(tmp_path), files[:2])
    store.add_tree_files(str(tmp_path), files[2:])
    assert store.local_tree_data()[str(tmp_path)]["files"] == files


def test_store_add_folder_replaces_previous(tmp_path):
    store = LibraryStore()
    store.add_folder(str(tmp_path), ["old"])
    store.add_tree_files(str(tmp_path), [str(tmp_path / "gone.mp3")])
    # rescan of the same folder resets its entry
    store.add_folder(str(tmp_path), ["new"])
    tree = store.local_tree_data()
    assert tree[str(tmp_path)] == {"subdirs": ["new"], "files": []}


def test_store_reset_clears_everything(tmp_path):
    store = LibraryStore()
    store.add_folder(str(tmp_path), ["s"])
    store.add_tree_files(str(tmp_path), [str(tmp_path / "a.mp3")])
    store.add_indexed([str(tmp_path / "a.mp3")])
    store.reset()
    assert store.local_tree_data() == {}
    assert store.local_count() == 0


def test_search_local_matches_basename_case_insensitive(tmp_path):
    store = LibraryStore()
    hit = str(tmp_path / "Midnight Drive.mp3")
    miss = str(tmp_path / "other.ogg")
    store.add_folder(str(tmp_path), [])
    store.add_indexed([hit, miss])
    assert store.search_local("midnight") == [hit]
    assert store.search_local("DRIVE") == [hit]
    assert store.search_local("zzz") == []


def test_worker_walks_and_emits(tmp_path):
    from hicloudmp.core.workers import LibraryScanWorker

    root = tmp_path / "lib"
    (root / "sub").mkdir(parents=True)
    (root / "01 song.mp3").write_bytes(b"x")
    (root / "noise.txt").write_bytes(b"x")
    (root / "sub" / "02 song.flac").write_bytes(b"x")

    folders, tree_files, indexed, totals = [], [], [], []
    executed = []
    w = LibraryScanWorker([str(root)], dispatch=executed.append)
    w.on_folder = lambda f, s: folders.append((f, s))
    w.on_files = lambda f, c: tree_files.append((f, list(c)))
    w.on_indexed = lambda c: indexed.extend(c)
    w.on_finished = lambda t: totals.append(t)
    w.run()

    assert totals == [], "callbacks must be dispatched, not run inline"
    assert executed, "walk must hand its callbacks to dispatch"
    assert folders == []          # nothing ran until the UI thread does
    for fn in executed:           # simulate the UI thread pumping
        fn()
    assert totals == [2]  # both music files, recursive
    assert folders == [(str(root), ["sub"])]
    flat_tree = [p for _, chunk in tree_files for p in chunk]
    assert str(root / "01 song.mp3") in flat_tree
    assert str(root / "noise.txt") not in flat_tree
    assert sorted(indexed) == sorted([
        str(root / "01 song.mp3"), str(root / "sub" / "02 song.flac")])


def test_worker_respects_abort(tmp_path):
    from hicloudmp.core.workers import LibraryScanWorker

    root = tmp_path / "lib"
    root.mkdir()
    (root / "a.mp3").write_bytes(b"x")
    executed = []
    totals = []
    w = LibraryScanWorker([str(root)], dispatch=executed.append)
    w.on_finished = lambda t: totals.append(t)
    w.abort()
    w.run()
    for fn in executed:
        fn()
    assert totals == [0]  # aborted: nothing walked, clean finish


def test_player_scans_library_in_background(music_player, tmp_path, monkeypatch):
    """Boot wiring: MusicPlayer owns a store and a _start_local_scan()
    that runs the walk in a QThread, never on the UI thread."""
    mp = music_player
    mp.media_folders = [str(tmp_path)]
    (tmp_path / "b.mp3").write_bytes(b"x")
    (tmp_path / "sub").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sub" / "c.flac").write_bytes(b"x")

    assert hasattr(mp, "library_store")
    mp._start_local_scan()

    # pump events until the worker thread finishes feeding the store
    import time
    deadline = time.time() + 5
    while time.time() < deadline and mp.library_store.local_count() < 2:
        mp.app_process_events() if hasattr(mp, "app_process_events") else None
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        time.sleep(0.05)
    assert mp.library_store.local_count() == 2
    assert mp.library_store.search_local("c.flac") == [
        str(tmp_path / "sub" / "c.flac")]


def test_file_menu_has_rescan_library(music_player):
    """File > Rescan Library re-walks folders in the background."""
    mp = music_player
    mp.media_folders = []  # keep the scan trivial
    names, targets = [], {}
    for act in mp.menuBar().actions():      # top-level menus
        m = act.menu()
        if m is None:
            continue
        for a in m.actions():
            if a.text().strip():
                names.append(a.text())
                targets[a.text()] = a
    assert "Rescan Library" in names, f"menu items: {names}"
    started = []
    mp._start_local_scan = lambda: started.append(1)
    targets["Rescan Library"].trigger()
    assert started, "triggering Rescan Library must start a scan"


def test_view_tree_and_search_use_store_not_walk(music_player, tmp_path, monkeypatch):
    """update_library_tree + search_music render from the store; os.walk
    in the library module is forbidden (UI-thread freeze regression)."""
    from hicloudmp.ui import library_view

    mp = music_player
    mp.media_folders = [str(tmp_path)]
    hit = str(tmp_path / "Glass Harbor.mp3")
    (tmp_path / "Glass Harbor.mp3").write_bytes(b"x")
    mp.library_store.add_folder(str(tmp_path), [])
    mp.library_store.add_tree_files(str(tmp_path), [hit])
    mp.library_store.add_indexed([hit])

    def forbidden_walk(*a, **k):
        raise AssertionError("os.walk ran on the UI thread")
    monkeypatch.setattr(library_view.os, "walk", forbidden_walk)

    mp.update_library_tree()
    assert mp.library_tree.topLevelItemCount() >= 2
    texts = []
    for i in range(mp.library_tree.topLevelItemCount()):
        texts.append(mp.library_tree.topLevelItem(i).text(0))
    assert "Local Media" in texts

    # search must come from the index too
    from PySide6.QtWidgets import QLineEdit
    if not hasattr(mp, "search_input"):
        mp.search_input = QLineEdit()
    mp.search_input.setText("glass")
    mp.search_music()
    found = mp.library_tree.findItems(
        "Glass Harbor.mp3",
        __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MatchRecursive, 0)
    assert found, "search should find the indexed file without walking"
