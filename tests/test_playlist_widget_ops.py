"""Playlist widget ops keep the user's eyes off repaint churn (P5):
filtering and sorting wrap their item surgery in setUpdatesEnabled so a
500-row playlist does not repaint per row. Behavior (results) must not
change - the pins guard the bracket, not the filter itself.
"""
import os

import pytest


def _seed(mp, names):
    mp.playlist = [str(n) for n in names]
    mp.playlist_widget.clear()
    for n in names:
        mp.playlist_widget.addItem(str(n))


@pytest.fixture
def update_spy(music_player, monkeypatch):
    mp = music_player
    log = []
    monkeypatch.setattr(mp.playlist_widget, "setUpdatesEnabled",
                        lambda on: log.append(bool(on)), raising=False)
    return mp, log


def _seed(mp, names):
    mp.playlist = [str(n) for n in names]
    mp.playlist_widget.clear()
    for n in names:
        mp.playlist_widget.addItem(str(n))
    return mp


def test_filter_playlist_wraps_updates(update_spy):
    mp, log = update_spy
    _seed(mp, ["alpha one.mp3", "beta two.mp3", "alpha three.mp3",
               "gamma four.mp3"])

    mp.playlist_search_input.setText("alpha")   # textChanged drives it

    assert log == [False, True], log
    visible = [not mp.playlist_widget.item(i).isHidden()
               for i in range(mp.playlist_widget.count())]
    assert visible == [True, False, True, False], visible


def test_sort_playlist_wraps_updates_and_rebuild(update_spy, tmp_path):
    mp, log = update_spy
    base = tmp_path / "sortd"
    base.mkdir()
    for name in ("b", "a", "c"):
        (base / f"{name}.mp3").write_bytes(b"")
    mp.playlist = [str(base / "b.mp3"), str(base / "a.mp3"),
                   str(base / "c.mp3")]
    mp.playlist_widget.clear()
    for name in ("b.mp3", "a.mp3", "c.mp3"):   # app shows basenames
        mp.playlist_widget.addItem(name)

    combo_items = [mp.playlist_sort_combo.itemText(i)
                   for i in range(mp.playlist_sort_combo.count())]
    if "Title" in combo_items:
        index = combo_items.index("Title")
        mp.playlist_sort_combo.setCurrentIndex(index)   # signal drives sort

    assert log == [False, True], log
    texts = [mp.playlist_widget.item(i).text()
             for i in range(mp.playlist_widget.count())]
    assert texts == ["a.mp3", "b.mp3", "c.mp3"], texts
    assert [os.path.normcase(p) for p in mp.playlist] == [
        os.path.normcase(str(base / f"{n}.mp3")) for n in ("a", "b", "c")]


def test_sort_keeps_cloud_rows_and_selection(update_spy, tmp_path):
    mp, log = update_spy
    base = tmp_path / "sortc"
    base.mkdir()
    (base / "z.mp3").write_bytes(b"")
    entries = [
        str(base / "z.mp3"),
        {"type": "cloud", "cloud_idx": 0, "file_idx": 0},
    ]
    mp.playlist = list(entries)
    mp.playlist_widget.clear()
    mp.playlist_widget.addItem("z.mp3")
    mp.playlist_widget.addItem("cloudrow (Cloud)")

    combo_items = [mp.playlist_sort_combo.itemText(i)
                   for i in range(mp.playlist_sort_combo.count())]
    if "Title" in combo_items:
        mp.playlist_sort_combo.setCurrentIndex(combo_items.index("Title"))

    assert any("Cloud" in (mp.playlist_widget.item(i).text() or "")
               for i in range(mp.playlist_widget.count()))
    assert len(mp.playlist) == 2
    assert log == [False, True], log
