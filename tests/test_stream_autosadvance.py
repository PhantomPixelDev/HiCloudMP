import wave

from PySide6.QtMultimedia import QMediaPlayer


def _make_wav(path, seconds=0.2, rate=8000):
    """Real, tiny, playable WAV (monaural sine-ish clicks) via the stdlib."""
    silence = b"\x80\x00" * int(rate * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        # a single frame of maximum swing so the file is not "empty"
        w.writeframes(b"\x00\x40")
        w.writeframes(silence)
    return path


def test_end_of_media_advances_after_stream_attempt(music_player, monkeypatch, qtbot, tmp_path):
    """Task 11 regression: after one cloud-stream attempt, EndOfMedia on a later
    local track must still auto-advance. The old blanket disconnect() permanently
    killed the app's own mediaStatusChanged subscription."""
    import player as player_mod

    # Make stream retries deterministic (no background timers during the test)
    monkeypatch.setattr(music_player, "_schedule_stream_retry", lambda *a, **k: None)

    wav1 = _make_wav(tmp_path / "t1.wav")
    wav2 = _make_wav(tmp_path / "t2.wav")

    music_player.playlist = [str(wav1), str(wav2)]
    music_player.playlist_widget.clear()
    music_player.playlist_widget.addItem(wav1.name)
    music_player.playlist_widget.addItem(wav2.name)

    # 1) A cloud-stream attempt happens first (the buggy code path)
    music_player._play_stream("http://0.0.0.0:9/unreachable.wav", "unreachable")

    # 2) Then the user plays a local track
    music_player.current_index = 0
    music_player.play()

    # 3) Wait for the real EndOfMedia on the short wav
    with qtbot.waitSignal(music_player.player.mediaStatusChanged, timeout=15000,
                          check_params_cb=lambda s: s == QMediaPlayer.MediaStatus.EndOfMedia):
        pass

    # 4) Auto-advance must have fired via on_media_status_changed → next_track
    assert music_player.current_index == 1, \
        "EndOfMedia after a stream attempt must advance to the next track"
