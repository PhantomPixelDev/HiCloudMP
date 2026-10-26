"""Cloud playback flows must complete without pumping the event loop.

These slots called QApplication.processEvents() mid-flight: the status-bar
"paint now" variant is redundant (Qt paints on the next loop turn), and the
stop/setSource "settle" hack runs bare in closeEvent - which is the very
teardown those comments point at - proving it doesn't need a pump. A pump
here re-enters the event loop while the flow is half-way through state
changes: queued clicks and progress-dialog callbacks run against
inconsistent state, which is exactly what processEvents is infamous for.
"""


def _stub_flow_tails(mp, monkeypatch):
    """Stub everything past the call sites under test."""
    monkeypatch.setattr(mp, "_play_stream", lambda *a, **k: None,
                        raising=False)
    monkeypatch.setattr(mp, "_download_and_play", lambda *a, **k: None,
                        raising=False)
    monkeypatch.setattr(mp, "_route_through_engine", lambda: False,
                        raising=False)


def test_cloud_flows_never_pump_events(music_player, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    mp = music_player
    _stub_flow_tails(mp, monkeypatch)

    pumped = []
    monkeypatch.setattr(QApplication, "processEvents",
                        staticmethod(lambda *a, **k: pumped.append(1)))

    mp.clouds = [{
        "name": "S", "type": "subsonic", "config": {},
        "files": [{"path": "Artist/Album/Song.mp3",
                   "url": "https://x/stream?f=song.mp3"}],
    }]

    mp.play_cloud_file(0, 0)

    downloaded = tmp_path / "downloaded.mp3"
    downloaded.write_bytes(b"")
    mp.play_downloaded_file(str(downloaded))

    assert pumped == [], \
        f"flows pumped the event loop {len(pumped)}x mid-state-change"


def test_no_production_process_events():
    """Tripwire: player.py must stay free of processEvents. Any future
    occurrence needs a written justification peer to the four removed
    here (re-entrant event delivery mid-flow is the failure mode)."""
    from sourcepaths import read
    src = read("ui/player.py")
    assert "processEvents" not in src
