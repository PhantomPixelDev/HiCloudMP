"""Double-clicking a track in the left library appends to the current queue
and plays it - it must never wipe the queue (user-reported on v1.0.4:
"adding and playing a track from left list clears current queue").
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem


def _library_item(payload, text="row"):
    item = QTreeWidgetItem([text])
    item.setData(0, Qt.UserRole, payload)
    return item


def test_local_library_click_appends_and_keeps_queue(music_player,
                                                     tmp_path, monkeypatch):
    mp = music_player
    keep1 = tmp_path / "keep1.mp3"
    keep2 = tmp_path / "keep2.mp3"
    keep1.write_bytes(b"")
    keep2.write_bytes(b"")
    mp.playlist = [str(keep1), str(keep2)]
    mp.current_index = 0
    for p in (str(keep1), str(keep2)):
        mp.playlist_widget.addItem(p)
    added = tmp_path / "new-song.mp3"
    added.write_bytes(b"")

    played = []
    monkeypatch.setattr(mp, "play",
                        lambda: played.append(mp.current_index),
                        raising=False)

    item = _library_item({"type": "local_file", "path": str(added)},
                         "new-song.mp3")
    mp.library_mgr.on_library_item_clicked(item, 0)

    assert mp.playlist == [str(keep1), str(keep2), str(added)]
    assert len(mp.playlist) == mp.playlist_widget.count()
    assert mp.current_index == 2
    assert played == [2]


def test_cloud_library_click_appends_and_keeps_queue(music_player,
                                                     monkeypatch):
    mp = music_player
    mp.clouds = [{"name": "Cloud", "files": [dict(x) for x in [
        {"path": "a/x.mp3", "artist": "A", "name": "X"},
        {"path": "a/y.mp3", "artist": "A", "name": "Y"},
        {"path": "b/spend.mp3", "artist": "Skillibeng", "name": "Spend It"},
    ]]}]
    mp.playlist = [{"type": "cloud", "cloud_idx": 0, "file_idx": 0}]
    mp.current_index = 0
    mp.playlist_widget.addItem("A – X")

    played = []
    monkeypatch.setattr(mp, "play",
                        lambda: played.append(mp.current_index),
                        raising=False)

    item = _library_item({"type": "cloud_file", "cloud_index": 0,
                          "file_index": 2}, "spend.mp3")
    mp.library_mgr.on_library_item_clicked(item, 0)

    assert mp.playlist == [
        {"type": "cloud", "cloud_idx": 0, "file_idx": 0},
        {"type": "cloud", "cloud_idx": 0, "file_idx": 2},
    ]
    assert mp.current_index == 1
    assert mp.playlist_widget.count() == 2
    assert mp.playlist_widget.item(1).text() == "Skillibeng – Spend It"
    assert played == [1]
