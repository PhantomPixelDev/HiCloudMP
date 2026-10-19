"""The playlist is a real table: Title | Artist | Album.

v1.0.4 showed the queue and library as single-column filename lists. The
queue becomes a multi-column table fed by the scanned cloud catalog; the
widget keeps the QListWidget surface (count()/item()/takeItem()/...)
because the whole app speaks it.
"""
import os

from PySide6.QtCore import QPointF, QPoint
from PySide6.QtWidgets import QTreeWidgetItem


def test_table_columns_and_headers(music_player):
    mp = music_player
    assert mp.playlist_widget.columnCount() == 3
    assert mp.playlist_widget.headerItem().text(0) == "Title"
    assert mp.playlist_widget.headerItem().text(1) == "Artist"
    assert mp.playlist_widget.headerItem().text(2) == "Album"
    assert mp.playlist_widget.rootIsDecorated() is False


def test_cloud_rows_get_full_cells_from_catalog(music_player):
    mp = music_player
    mp.clouds = [{"name": "Cloud", "files": [dict(x) for x in [
        {"path": "a/x.mp3", "artist": "Aa", "name": "X", "album": "LX"},
        {"path": "a/y.mp3", "artist": "Aa", "name": "Y", "album": "LX"},
        {"path": "b/spend.mp3", "artist": "Skillibeng",
         "name": "Spend It", "album": "Mr. Villain"},
    ]]}]

    cells = mp.meta.queue_cells({"type": "cloud", "cloud_idx": 0,
                                 "file_idx": 2})
    assert cells == ("Spend It", "Skillibeng", "Mr. Villain")

    row = mp.playlist_widget.addQueueRow(*cells)
    assert mp.playlist_widget.item(0) is row
    assert row.text(0) == "Spend It"
    assert row.text(1) == "Skillibeng"
    assert row.text(2) == "Mr. Villain"


def test_local_rows_title_only_and_string_compat(music_player, tmp_path):
    mp = music_player
    song = tmp_path / "grand_project.mp3"
    song.write_bytes(b"")
    cells = mp.meta.queue_cells(str(song))
    assert cells[0] == "grand_project"
    assert cells[1] == "" and cells[2] == ""

    # plain-string addItem keeps the QListWidget behavior (title only)
    mp.playlist_widget.addItem("first.mp3")
    item = mp.playlist_widget.item(0)
    assert isinstance(item, QTreeWidgetItem)
    assert item.text(0) == "first.mp3"
    assert item.text(1) == ""


def test_qlistwidget_surface_shim(music_player):
    mp = music_player
    w = mp.playlist_widget
    w.addItem("first.mp3")
    w.addItem(["second", "Artist", "Album"])
    w.addItem("third.mp3")

    assert w.count() == 3
    assert w.currentRow() == -1
    w.setCurrentRow(1)
    assert w.currentRow() == 1
    assert w.row(w.item(1)) == 1

    moved = w.takeItem(1)
    assert moved.text(0) == "second"
    assert w.count() == 2
    w.insertItem(0, moved)
    assert w.item(0).text(0) == "second"
    assert w.row(moved) == 0

    w.itemAt(QPoint(5, 5))            # context-menu lookup works
    w.selectedItems()
    first = w.item(0)
    first.setSelected(True)
    assert first.isSelected()


def test_filter_and_sort_read_all_cells(music_player):
    mp = music_player
    w = mp.playlist_widget
    a = w.addQueueRow("Spend It", "Skillibeng", "Mr. Villain")
    b = w.addItem("plain.mp3")

    assert w.matches_filter(0, "skill") is True
    assert w.matches_filter(0, "zulu") is False
    assert w.matches_filter(1, "plain") is True

    # widget rows can report their sort keys out of the cells
    assert a.text(1) == "Skillibeng" and a.text(2) == "Mr. Villain"
    assert b.text(1) == "" and b.text(2) == ""
