"""The queue as a real table: Title | Artist | Album.

MusicPlayer's playlist was a single-column QListWidget where every row was
just a filename/label string; users asked for a proper table with artist
(and album) columns. QTreeWidget is the natural multi-column row list, but
~120 call sites and most of the test suite speak the QListWidget dialect
(addItem / count() / item(i) / takeItem(i) / currentRow() / row(item) /
insertItem / itemAt(pos) / selectedItems()). PlaylistQueueWidget subclasses
QTreeWidget and respeaks that dialect so nothing outside this file changes
widget type — the app-side insertion sites feed real metadata cells instead
of one label string.

Cells live on the row item: text(0)=title, text(1)=artist, text(2)=album.
Plain strings behave exactly like QListWidget items (title only).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QTreeWidget, QTreeWidgetItem)

TITLE, ARTIST, ALBUM = 0, 1, 2
COLS = ("Title", "Artist", "Album")

# data() role holding each row's load-order stamp: sort mode "Original"
# re-permutes rows by it. Stored on the item, so sorts and internal
# drag-drops move the row without losing its place in the load order.
ORIGINAL_SEQ_ROLE = Qt.ItemDataRole.UserRole + 1001


class PlaylistQueueItem(QTreeWidgetItem):
    """Queue row: QTreeWidgetItem whose text() defaults to column 0, so
    AudioClip-era expectations (item.text()) keep working."""

    def text(self, col=0):
        return super().text(col)


def _cells(value):
    """Normalize addItem input into the three display cells."""
    if isinstance(value, (tuple, list)):
        cells = ["" if c is None else str(c) for c in value]
        cells += [""] * (3 - len(cells))
        return cells[:3]
    return [str(value), "", ""]


class PlaylistQueueWidget(QTreeWidget):
    """Flat QTreeWidget exposing the QListWidget surface the app uses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playlistWidget")
        self.setColumnCount(3)
        self.setHeaderLabels(COLS)
        self.setRootIsDecorated(False)          # flat rows, no expander rail
        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(True)
        self.setExpandsOnDoubleClick(False)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.header().resizeSection(TITLE, 300)
        self.header().resizeSection(ARTIST, 150)
        self.header().resizeSection(ALBUM, 150)
        self._row_seq = 0

    def _stamp(self, item):
        """Give a NEW row its place in the load order."""
        item.setData(0, ORIGINAL_SEQ_ROLE, self._row_seq)
        self._row_seq += 1

    def clear(self):
        """Rebuilding the queue starts a new 'original' life."""
        self._row_seq = 0
        super().clear()

    # ------------------------------------------------------------ insertion
    def addItem(self, value):
        """Append a row. `value` is a string (title-only, QListWidget
        compatible) or (title, artist[, album]) cells."""
        item = PlaylistQueueItem(_cells(value))
        self._stamp(item)
        self.addTopLevelItem(item)
        return item

    def insertItem(self, row, value):
        """QListWidget-style insert used by the row-move helpers; accepts a
        PlaylistQueueItem/QTreeWidgetItem (reinsertion — keeps its load-order
        stamp) or the same input as addItem() (new row — stamped)."""
        row = max(0, row)
        if isinstance(value, QTreeWidgetItem):
            self.insertTopLevelItem(min(row, self.topLevelItemCount()), value)
            return value
        item = PlaylistQueueItem(_cells(value))
        self._stamp(item)
        self.insertTopLevelItem(min(row, self.topLevelItemCount()), item)
        return item

    def addQueueRow(self, title, artist="", album=""):
        """App-side convenience: append a row from resolved metadata cells."""
        return self.addItem([title, artist, album])

    # ------------------------------------------------------------- Qlist API
    def count(self):
        return self.topLevelItemCount()

    def item(self, row):
        return self.topLevelItem(row)

    def takeItem(self, row):
        return self.takeTopLevelItem(row)

    def currentRow(self):
        return self.indexOfTopLevelItem(self.currentItem())

    def setCurrentRow(self, row):
        if 0 <= row < self.topLevelItemCount():
            self.setCurrentItem(self.topLevelItem(row))
        elif self.topLevelItemCount() == 0:
            self.setCurrentItem(None)

    def row(self, item):
        return self.indexOfTopLevelItem(item)

    def item_text(self, row, col=TITLE):
        """Whole-row convenience text (used by tests/filter)."""
        it = self.item(row)
        return it.text(col) if it is not None else ""

    # ------------------------------------------------------------ filtering
    def matches_filter(self, row, text):
        """True when any cell of the row contains `text` (lowercase given)."""
        it = self.item(row)
        if it is None:
            return not text
        for col in range(3):
            if text in it.text(col).lower():
                return True
        return False
