"""Library rows and queue cells for LOCAL files must show real tags, not
bare filenames (user: "list and playlist show only song title").

Tags are read once by the background scan worker into LibraryStore; the
library tree, the queue table, and the playlist sort then resolve from that
cache and never touch the filesystem on the UI thread.
"""
import os
import wave


from hicloudmp.core.library_store import LibraryStore
from hicloudmp.core.workers import LibraryScanWorker


# ---------------------------------------------------------------- store
def test_store_caches_tags_and_reset_clears():
    store = LibraryStore()
    store.add_tags([("/m/a.mp3", "Song", "Artist", "Album")])
    assert store.tags("/m/a.mp3") == ("Song", "Artist", "Album")
    # Unknown paths are neutral: exact list membership, never guesses.
    assert store.tags("/m/other.mp3") == ("", "", "")
    store.reset()
    assert store.tags("/m/a.mp3") == ("", "", "")


def test_worker_emits_tags_for_scanned_files(tmp_path):
    """The scan worker reads the tags of every file it indexes and hands
    (path, title, artist, album) pairs to the UI thread."""
    f = tmp_path / "song.wav"
    with wave.open(str(f), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 400)
    from mutagen.id3 import TALB, TIT2, TPE1
    from mutagen.wave import WAVE

    audio = WAVE(str(f))
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text="Song"))
    audio.tags.add(TPE1(encoding=3, text="Artist"))
    audio.tags.add(TALB(encoding=3, text="Album"))
    audio.save()

    pairs = []
    worker = LibraryScanWorker([str(tmp_path)], lambda fn: fn())
    worker.on_tags = lambda p: pairs.extend(p)
    worker.run()
    assert (str(f), "Song", "Artist", "Album") in pairs


# ---------------------------------------------------------- queue cells
def test_queue_cells_prefers_cached_local_tags(music_player):
    f1 = "X:\\music\\tagged.mp3"   # fixed strings are cache keys on every OS
    music_player.library_store.add_tags([(f1, "Song", "Artist", "Album")])
    assert music_player.meta.queue_cells(f1) == ("Song", "Artist", "Album")
    # Untagged files keep the old basename title and empty cells; the path
    # uses the host separator so the basename fallback means the same thing
    # on POSIX (where a backslash path is one component) and Windows.
    assert music_player.meta.queue_cells(
        f"X:{os.sep}music{os.sep}none") == ("none", "", "")


# --------------------------------------------------------- library tree
def test_library_tree_local_rows_show_tag_columns(music_player, tmp_path):
    f_tagged = tmp_path / "t.mp3"
    f_plain = tmp_path / "p.mp3"
    f_tagged.write_bytes(b"")
    f_plain.write_bytes(b"")
    store = music_player.library_store
    store.add_folder(str(tmp_path), [])
    store.add_tree_files(str(tmp_path), [str(f_tagged), str(f_plain)])
    store.add_tags([(str(f_tagged), "Song", "Artist", "Album")])
    music_player.media_folders = [str(tmp_path)]
    music_player.update_library_tree()

    tree = music_player.library_tree
    assert tree.columnCount() == 3
    assert [tree.headerItem().text(i) for i in range(3)] == \
        ["Name", "Artist", "Album"]

    local_root = tree.topLevelItem(0)
    assert local_root.text(0) == "Local Media"
    folder_item = local_root.child(0)
    tagged_row = folder_item.child(0)
    assert tagged_row.text(0) == "Song"
    assert tagged_row.text(1) == "Artist"
    assert tagged_row.text(2) == "Album"
    plain_row = folder_item.child(1)
    # Untagged: basename without extension in the Name column only.
    assert plain_row.text(0) == "p"
    assert plain_row.text(1) == ""
    assert plain_row.text(2) == ""


def test_library_tree_cloud_rows_show_metadata(music_player):
    music_player.clouds = [{
        "name": "Sub",
        "files": [{"path": "Music/Song.mp3", "name": "Song title",
                   "artist": "Art", "album": "Al"}],
    }]
    music_player.update_library_tree()
    tree = music_player.library_tree
    cloud_root = tree.topLevelItem(2)
    assert cloud_root.text(0) == "Cloud Media"
    account = cloud_root.child(0)
    folder_item = account.child(0)
    row = folder_item.child(0)
    # Catalog title (name), not the remote filename.
    assert row.text(0) == "Song title"
    assert row.text(1) == "Art"
    assert row.text(2) == "Al"


# ------------------------------------------------------------- playlist
def test_sort_prefers_scanned_tags_over_disk_reads(music_player,
                                                   monkeypatch, tmp_path):
    from hicloudmp.ui import player as player_mod

    f1 = tmp_path / "b.mp3"
    f2 = tmp_path / "a.mp3"
    f1.write_bytes(b"")
    f2.write_bytes(b"")
    music_player.library_store.add_tags([
        (str(f1), "Song B", "Bee", ""),
        (str(f2), "Song A", "Aye", ""),
    ])
    music_player.playlist = [str(f1), str(f2)]
    music_player.playlist_widget.clear()
    music_player.playlist_widget.addItem((os.path.basename(str(f1)), "", ""))
    music_player.playlist_widget.addItem((os.path.basename(str(f2)), "", ""))

    disk_reads = []
    monkeypatch.setattr(player_mod, "read_sort_tags",
                        lambda p: disk_reads.append(p) or ("", ""))

    combo = music_player.playlist_sort_combo
    texts = [combo.itemText(i) for i in range(combo.count())]
    combo.setCurrentIndex(texts.index("Artist"))

    titles = [music_player.playlist_widget.item(i).text(0)
              for i in range(music_player.playlist_widget.count())]
    assert titles == [os.path.basename(str(f2)), os.path.basename(str(f1))]
    # Scanned tags answered the sort: nothing was read from disk.
    assert disk_reads == []
