import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _musicplayer_method_names():
    tree = ast.parse((ROOT / "player.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MusicPlayer":
            return [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return []


def test_no_duplicate_method_names_in_musicplayer():
    """Task 6 regression: the shadowed add_file_to_specific_playlist copy must stay deleted."""
    names = _musicplayer_method_names()
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate method definitions in MusicPlayer: {sorted(dupes)}"


def test_context_menu_lambda_does_not_pass_two_args_to_one_arg_method():
    """player.show_library_context_menu passed (p, d) to add_file_to_playlist(data)
    -> TypeError on every 'Add to Playlist' click; the correct target is
    add_file_to_specific_playlist(p, d) — mirroring the folder branch above it."""
    src = (ROOT / "player.py").read_text(encoding="utf-8")
    assert "add_file_to_playlist(p, d)" not in src, \
        "two-arg call to one-arg add_file_to_playlist reintroduced at the lambda call site"


def test_add_file_to_specific_playlist_does_not_clobber_queue(music_player, monkeypatch):
    """The kept implementation builds a temp list; the deleted shadow copy reset
    self.playlist=[] and never restored it."""
    from playlist import Playlist

    music_player.playlist = ["existing_track_a", "existing_track_b"]
    pl = Playlist(name="P", items=[])

    seen = {}

    def fake_internal(data, target_list, update_ui=True):
        seen.update(target_list=target_list)
        target_list.append("TrackX")
        return "TrackX"

    monkeypatch.setattr(music_player, "_add_file_to_playlist_internal", fake_internal)

    music_player.add_file_to_specific_playlist(pl, {"type": "local_file", "path": "x"})

    assert music_player.playlist == ["existing_track_a", "existing_track_b"]
    assert "TrackX" in pl.items
    assert seen["target_list"] is not music_player.playlist, "must not build the item in the live queue"
