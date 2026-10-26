from PySide6.QtWidgets import QDialog


class _StubDialog(QDialog):
    """Stands in for CloudAccountsDialog: mutates the shared clouds list in place
    (like the real dialog does), has NO get_data(), and closes with Accepted
    (which the real dialog can never do today — it has no Done button)."""

    def __init__(self, parent, clouds):
        super().__init__(parent)
        self._clouds = clouds

    def exec(self):
        self._clouds.append({"type": "webdav", "name": "T", "config": {},
                             "files": [], "last_sync": "Never"})
        return QDialog.Accepted


def test_add_cloud_saves_once_without_double_append(qtbot, monkeypatch, music_player):
    """Task 5 regression: add_cloud must not call a nonexistent get_data() and must
    not double-append entries the dialog already added to the shared list."""
    from hicloudmp.ui import player as player_mod

    monkeypatch.setattr(player_mod, "CloudAccountsDialog", _StubDialog)
    saved = []
    tree_refreshed = []
    monkeypatch.setattr(music_player, "save_clouds", lambda: saved.append(1))
    monkeypatch.setattr(music_player, "update_library_tree", lambda: tree_refreshed.append(1))

    music_player.clouds.clear()
    music_player.add_cloud()

    assert len(music_player.clouds) == 1, "dialog's in-place mutation is the single source of truth"
    assert len(saved) == 1, "exactly one save_clouds per changed dialog session"
    assert len(tree_refreshed) == 1


def test_cloud_accounts_dialog_has_done_button(qtbot, music_player):
    """Without a Done button, exec() can only ever return Rejected, making the
    whole dialog flow unusable."""
    from hicloudmp.ui import player as player_mod

    from PySide6.QtWidgets import QDialogButtonBox

    dlg = player_mod.CloudAccountsDialog(music_player, [])
    boxes = dlg.findChildren(QDialogButtonBox)
    assert boxes and (boxes[0].standardButtons() & QDialogButtonBox.Ok), "Done/OK button missing"
    dlg.deleteLater()
