"""'Original' in the queue sort combo restores the order the rows were
added in. v1.0.4 shipped it as a TODO no-op: mode "Original" did nothing
and the read order stayed whatever the last sort left behind.
"""


def _select(mp, text):
    combo = mp.playlist_sort_combo
    texts = [combo.itemText(i) for i in range(combo.count())]
    combo.setCurrentIndex(texts.index(text))


def _titles(mp):
    return [mp.playlist_widget.item(i).text(0)
            for i in range(mp.playlist_widget.count())]


def _load_rows(mp, entries_with_titles):
    """Clear + add rows in the given (path, title) load order."""
    mp.playlist = [p for p, _t in entries_with_titles]
    mp.playlist_widget.clear()
    for _p, title in entries_with_titles:
        mp.playlist_widget.addItem((title, "", ""))


def test_original_restores_order_after_title_sort(music_player, tmp_path):
    paths = {}
    for name, title, artist in (("a", "Alpha", "One"),
                                ("b", "Beta", "One"),
                                ("c", "Gamma", "One")):
        f = tmp_path / f"{name}.mp3"
        f.write_bytes(b"")
        paths[name] = str(f)
        music_player.library_store.add_tags([(str(f), title, artist, "")])

    # Load order: c, a, b  — Title sort must move the rows to a, b, c.
    _load_rows(music_player, [(paths["c"], "Gamma"),
                              (paths["a"], "Alpha"),
                              (paths["b"], "Beta")])
    _select(music_player, "Title")
    assert _titles(music_player) == ["Alpha", "Beta", "Gamma"]

    _select(music_player, "Original")
    assert _titles(music_player) == ["Gamma", "Alpha", "Beta"]


def test_original_places_rows_appended_after_load(music_player, tmp_path):
    paths = {}
    for name, title, artist in (("a", "Alpha", "One"),
                                ("b", "Beta", "One"),
                                ("c", "Gamma", "One")):
        f = tmp_path / f"{name}.mp3"
        f.write_bytes(b"")
        paths[name] = str(f)
        music_player.library_store.add_tags([(str(f), title, artist, "")])

    _load_rows(music_player, [(paths["b"], "Beta"),
                              (paths["a"], "Alpha")])
    _select(music_player, "Title")
    assert _titles(music_player) == ["Alpha", "Beta"]

    # Append while sorted: lands at the visual end…
    music_player.playlist.append(paths["c"])
    music_player.playlist_widget.addItem(("Gamma", "", ""))
    assert _titles(music_player) == ["Alpha", "Beta", "Gamma"]

    # …but 'Original' is load order, with the late append at the tail.
    _select(music_player, "Original")
    assert _titles(music_player) == ["Beta", "Alpha", "Gamma"]


def test_rebuild_resets_original_order(music_player, tmp_path):
    paths = {}
    for name, title, artist in (("a", "Alpha", "One"),
                                ("b", "Beta", "One")):
        f = tmp_path / f"{name}.mp3"
        f.write_bytes(b"")
        paths[name] = str(f)
        music_player.library_store.add_tags([(str(f), title, artist, "")])

    _load_rows(music_player, [(paths["b"], "Beta"), (paths["a"], "Alpha")])
    _select(music_player, "Title")
    assert _titles(music_player) == ["Alpha", "Beta"]

    # A rebuild (clear + reload) starts a new "original" life.
    _load_rows(music_player, [(paths["a"], "Alpha"), (paths["b"], "Beta")])
    _select(music_player, "Original")
    assert _titles(music_player) == ["Alpha", "Beta"]


def test_sort_ties_keep_original_order(music_player, tmp_path):
    """Sort stability: rows whose full sort key is equal (same artist AND
    title) must keep their relative load order, not scramble."""
    paths = {}
    for name, title, artist in (("a", "Tick", "One"),
                                ("b", "Alpha", "One"),
                                ("c", "Tick", "One")):
        f = tmp_path / f"{name}.mp3"
        f.write_bytes(b"")
        paths[name] = str(f)
        music_player.library_store.add_tags([(str(f), title, artist, "")])

    # Load order: c, a, b — c and a share the full Artist sort key.
    _load_rows(music_player, [(paths["c"], "Tick"),
                              (paths["a"], "Tick"),
                              (paths["b"], "Alpha")])
    _select(music_player, "Artist")
    titles = _titles(music_player)
    assert titles == ["Alpha", "Tick", "Tick"]
    # Tied rows keep their load order: c stays ahead of a.
    assert music_player.playlist == [paths["b"], paths["c"], paths["a"]]
