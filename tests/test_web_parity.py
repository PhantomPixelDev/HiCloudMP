"""Web remote parity/push: the panel gained the desktop's newer controls
(mute, playback speed, Play Next queue visibility + clear) and desktop
changes are pushed to connected browsers instead of waiting for a poll.
"""


def test_status_reports_parity_fields(web_server, music_player):
    mp = music_player
    mp.audio_output.setMuted(True)
    mp.settings.setValue("audio/playback_rate", 1.25)
    mp._play_next_queue = [1, 2]
    mp._update_queue_indicator()

    status = web_server._get_status()

    assert status["muted"] is True
    assert abs(status["rate"] - 1.25) < 1e-6
    assert status["queue_count"] == 2


def test_panel_can_toggle_mute(web_server, music_player, sio_client_drained):
    mp = music_player
    client = sio_client_drained

    client.emit("toggle_mute")
    assert mp.audio_output.isMuted() is True

    client.emit("toggle_mute")
    assert mp.audio_output.isMuted() is False


def test_panel_can_set_rate(web_server, music_player, sio_client_drained):
    mp = music_player
    client = sio_client_drained

    client.emit("set_rate", {"rate": 1.5})
    assert mp._playback_rate() == 1.5
    assert abs(mp.player.playbackRate() - 1.5) < 1e-3

    client.emit("set_rate", {"rate": 9})      # out of range: ignored
    client.emit("set_rate", None)             # junk: ignored
    assert mp._playback_rate() == 1.5


def test_panel_can_clear_queue(web_server, music_player, sio_client_drained):
    mp = music_player
    mp._play_next_queue = [0, 1]
    mp._update_queue_indicator()

    sio_client_drained.emit("clear_queue")

    assert mp._play_next_queue == []
    assert mp.queue_indicator.isHidden()


def test_broadcast_state_pushes_status_and_progress(web_server, music_player,
                                                    sio_client_drained):
    client = sio_client_drained
    client.get_received()

    web_server.broadcast_state()

    names = [m["name"] for m in client.get_received()]
    assert "status" in names
    assert "progress" in names


def test_desktop_volume_change_is_pushed(web_server, music_player,
                                         sio_client_drained):
    mp = music_player
    mp.web_server = web_server          # as after start_web_interface()
    client = sio_client_drained
    client.get_received()

    mp.volume_slider.setValue(33)   # the real desktop drag path

    received = client.get_received()
    statuses = [m["args"][0] for m in received if m["name"] == "status"]
    assert statuses and statuses[-1]["volume"] == 33


def test_panel_html_exposes_new_controls():
    from sourcepaths import resource
    html = resource("web_panel.html").read_text(encoding="utf-8")
    for marker in ('id="mute"', 'id="rate"', 'id="queue-badge"',
                   "toggle_mute", "set_rate", "clear_queue"):
        assert marker in html, marker
