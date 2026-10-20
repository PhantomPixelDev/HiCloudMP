"""Web remote seek must be engine-aware.

Root cause shared with the desktop seek bug: the handler had been
calling the NATIVE QMediaPlayer only; with EQ/visualizer routing the
engine plays and native setPosition is a no-op on an idle player.
"""


def test_web_seek_routes_through_player_seek(
        sio_client_drained, web_server, music_player, monkeypatch):
    mp = music_player
    captured = []
    monkeypatch.setattr(mp, "seek_position",
                        lambda pos: captured.append(pos), raising=False)
    client = sio_client_drained
    client.get_received()          # drain the connect burst
    client.emit("seek", {"position": 8000})
    assert captured == [8000], \
        "seek must go through seek_position (engine-aware), not native-only setPosition"


def test_web_seek_validates_payload(
        sio_client_drained, web_server, music_player, monkeypatch):
    mp = music_player
    captured = []
    monkeypatch.setattr(mp, "seek_position",
                        lambda pos: captured.append(pos), raising=False)
    client = sio_client_drained
    client.get_received()
    client.emit("seek", None)
    client.emit("seek", {"position": None})
    client.emit("seek", {"position": -50})
    assert captured == [], "bad payloads must not reach the player"
