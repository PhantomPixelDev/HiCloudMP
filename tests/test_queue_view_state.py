"""Queue view state survives a restart: the sort combo and the filter text
the user last used come back on the next launch, and a queue rebuild
(loading a playlist, cloud folder, local folder) re-applies the standing
sort mode and filter to the fresh rows instead of leaving the view reset.

v1.0.4 reset both on every launch and every load.
"""
from PySide6.QtCore import QSettings


def _texts_index(combo, text):
    texts = [combo.itemText(i) for i in range(combo.count())]
    return texts.index(text)


def test_sort_and_filter_survive_restart(qtbot, monkeypatch, tmp_path):
    from hicloudmp.ui import player as player_mod

    ini = str(tmp_path / "state.ini")

    def _factory(*args, **kwargs):
        return QSettings(ini, QSettings.IniFormat)

    monkeypatch.setattr(player_mod, "QSettings", _factory)

    mp1 = player_mod.MusicPlayer()
    qtbot.addWidget(mp1)
    mp1.playlist_sort_combo.setCurrentIndex(
        _texts_index(mp1.playlist_sort_combo, "Artist"))
    mp1.playlist_search_input.setText("al")
    mp1._save_queue_view_state()
    mp1.settings.sync()

    # A "restart": a fresh instance reading the same QSettings store.
    mp2 = player_mod.MusicPlayer()
    qtbot.addWidget(mp2)
    assert mp2.playlist_sort_combo.currentText() == "Artist"
    assert mp2.playlist_search_input.text() == "al"


def test_rebuild_reapplies_filter(music_player, tmp_path):
    paths = {}
    for name, title in (("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")):
        f = tmp_path / f"{name}.mp3"
        f.write_bytes(b"")
        paths[name] = str(f)
        music_player.library_store.add_tags([(str(f), title, "One", "")])

    music_player.playlist = [paths["a"], paths["b"], paths["c"]]
    music_player.playlist_widget.clear()
    for title in ("Alpha", "Beta", "Gamma"):
        music_player.playlist_widget.addItem((title, "", ""))
    music_player.playlist_search_input.setText("beta")

    music_player._apply_queue_view_state()

    rows = music_player.playlist_widget
    assert not rows.item(1).isHidden()
    assert rows.item(0).isHidden()
    assert rows.item(2).isHidden()


def test_rebuild_reapplies_standing_sort(music_player, tmp_path):
    paths = {}
    for name, title in (("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")):
        f = tmp_path / f"{name}.mp3"
        f.write_bytes(b"")
        paths[name] = str(f)
        music_player.library_store.add_tags([(str(f), title, "One", "")])

    # The standing mode is Title (loaded before rows exist).
    music_player.playlist_sort_combo.setCurrentIndex(
        _texts_index(music_player.playlist_sort_combo, "Title"))

    # Fresh rows arrive in load order Gamma, Alpha, Beta.
    # But I want the load order distinct: c, a, b.
    music_player.playlist = [paths["c"], paths["a"], paths["b"]]
    music_player.playlist_widget.clear()
    for title in ("Gamma", "Alpha", "Beta"):
        music_player.playlist_widget.addItem((title, "", ""))

    music_player._apply_queue_view_state()

    titles = [music_player.playlist_widget.item(i).text(0)
              for i in range(music_player.playlist_widget.count())]
    assert titles == ["Alpha", "Beta", "Gamma"]


def test_original_mode_does_not_resort_rebuild(music_player, tmp_path):
    paths = {}
    for name, title in (("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")):
        f = tmp_path / f"{name}.mp3"
        f.write_bytes(b"")
        paths[name] = str(f)
        music_player.library_store.add_tags([(str(f), title, "One", "")])

    music_player.playlist = [paths["c"], paths["a"], paths["b"]]
    music_player.playlist_widget.clear()
    for title in ("Gamma", "Alpha", "Beta"):
        music_player.playlist_widget.addItem((title, "", ""))

    music_player._apply_queue_view_state()

    titles = [music_player.playlist_widget.item(i).text(0)
              for i in range(music_player.playlist_widget.count())]
    assert titles == ["Gamma", "Alpha", "Beta"]
