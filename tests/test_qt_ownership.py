"""Qt ownership: the multimedia objects must belong to the window, not the GC.

An unparented QMediaPlayer/QAudioOutput survives until a generational
collection happens to run at some arbitrary allocation point; the C++
destructor then executes with the media backend in an unknown state. On
audio-less Linux CI runners that surfaced as a segfault *inside GC* while
the next test's MusicPlayer was being constructed (faulthandler dump:
"Garbage-collecting" at player.py _build_menubar -> _create_menubar ->
__init__ -> conftest music_player, ledger run 40229404221).

QMediaPlayer.setAudioOutput() explicitly does NOT take ownership of the
output, so the window itself must be the parent of both objects. Then
pytest-qt's per-test teardown (close -> deleteLater -> processEvents)
destroys them, and joins any decoder thread, before the next test starts.
"""


def test_media_player_and_output_are_owned_by_the_window(music_player):
    assert music_player.player.parent() is music_player, \
        "QMediaPlayer must be parented to the window (GC-time destruction crashes)"
    assert music_player.audio_output.parent() is music_player, \
        "QAudioOutput must be parented to the window (setAudioOutput keeps no owner)"


def test_rebuilt_audio_output_is_also_owned(music_player, monkeypatch):
    """Switching output device replaces self.audio_output; the replacement
    must be owned too, or the old crash path comes straight back."""
    import audio_devices

    monkeypatch.setattr(audio_devices, "resolve_output",
                        lambda *_a, **_k: None)
    music_player.apply_output_device_setting()
    assert music_player.audio_output.parent() is music_player, \
        "_make_native_output must parent the rebuilt QAudioOutput to the window"
