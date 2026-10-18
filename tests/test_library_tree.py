"""Regression for the manual-testing crash reported on 2026-10-18:
Add Folder -> update_library_tree -> AttributeError on the unscoped enum
(QTreeWidget instance no longer resolves ExtendedSelection in PySide 6.10)."""

from PySide6.QtWidgets import QAbstractItemView


def test_update_library_tree_sets_extended_selection(music_player):
    # Must not raise AttributeError (PySide 6.10 removed unscoped instance enums)
    music_player.update_library_tree()

    assert music_player.library_tree.selectionMode() == \
        QAbstractItemView.SelectionMode.ExtendedSelection
    # The two structural roots that test output pinned down
    assert music_player.library_tree.topLevelItemCount() >= 2
