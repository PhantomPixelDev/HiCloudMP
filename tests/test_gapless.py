"""Gapless EQ-engine path: a preloaded decoder is swapped onto the SAME
sink, so sequential local tracks hand off sample-continuously instead of
tearing down the decoder/sink between songs. The visible track change is
reported at the audible boundary (the sink may hold about a second of the
old track when the swap happens). Shuffle, Play Next, cloud rows and the
last row deliberately stay on the normal path.
"""
import numpy as np

from hicloudmp.audio import eq_engine as eq_mod


class _SignalStub:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def disconnect(self, fn):
        if fn in self.slots:
            self.slots.remove(fn)


class _FakeDecoder:
    def __init__(self, duration=0):
        self._duration = duration
        self.bufferReady = _SignalStub()
        self.finished = _SignalStub()
        self.durationChanged = _SignalStub()
        self.stopped = False
        self.deleted = False
        self.source_value = None
        self.started = False

    def setAudioFormat(self, fmt):
        self.format = fmt

    def start(self):
        self.started = True

    def duration(self):
        return self._duration

    def stop(self):
        self.stopped = True

    def setSource(self, url):
        self.source_value = url

    def deleteLater(self):
        self.deleted = True


class _FakeSink:
    def __init__(self, us=0):
        self.us = us
        self.stopped = False
        self.deleted = False

    def processedUSecs(self):
        return self.us

    def stop(self):
        self.stopped = True

    def deleteLater(self):
        self.deleted = True


def _engine_with_next(old_ms=10000, new_ms=8000):
    eng = eq_mod.EQEngine()
    eng._playing = True
    eng._decoder = _FakeDecoder(old_ms)
    eng._sink = _FakeSink(0)
    eng._proc = object()
    eng._duration_ms = old_ms
    eng._base_ms = 0
    eng._prof_us_base = 0
    eng._decoding_done = True
    eng._finish_emitted = False
    eng._error_reported = False
    eng._pending = np.zeros((0, 2), dtype=np.int16)
    next_decoder = _FakeDecoder(new_ms)
    eng._next_decoder = next_decoder
    eng._next_source = "C:/music/next.mp3"
    advanced = []
    finished = []
    eng.track_advanced.connect(advanced.append)
    eng.track_finished.connect(lambda: finished.append(1))
    return eng, next_decoder, advanced, finished


def test_promotes_next_on_the_same_sink(qapp):
    eng, next_decoder, advanced, finished = _engine_with_next()
    sink = eng._sink
    old_decoder = eng._decoder

    eng._maybe_promote_next()

    assert eng._decoder is next_decoder
    assert eng._sink is sink, "the sink must never be recreated"
    assert old_decoder.stopped and old_decoder.deleted
    assert eng._advance_target_us == 10_000_000
    assert eng._prof_us_base == 10_000_000 and eng._base_ms == 0
    assert advanced == [] and finished == [], "UI change waits for the audio"


def test_old_position_holds_until_the_audible_handoff(qapp):
    eng, _, advanced, finished = _engine_with_next()
    positions = []
    eng.position_changed.connect(positions.append)
    eng._maybe_promote_next()

    eng._sink.us = 9_000_000
    eng._emit_position()
    assert positions[-1] == 9000, "still the old track's tail"
    assert advanced == []

    eng._sink.us = 10_400_000
    eng._emit_position()
    assert advanced == ["C:/music/next.mp3"]
    assert positions[-1] == 400, "new track starts at 0 at the boundary"
    assert finished == []


def test_no_queued_next_still_finishes_normally(qapp):
    eng = eq_mod.EQEngine()
    eng._playing = True
    eng._decoder = _FakeDecoder(5000)
    eng._sink = _FakeSink(5_200_000)
    eng._duration_ms = 5000
    eng._base_ms = 0
    eng._prof_us_base = 0
    eng._decoding_done = True
    eng._finish_emitted = False
    eng._error_reported = False
    eng._pending = np.zeros((0, 2), dtype=np.int16)
    finished = []
    eng.track_finished.connect(lambda: finished.append(1))

    eng._check_finished()

    assert finished == [1]
    assert eng._decoder is None and eng._sink is None


def test_finish_is_suppressed_during_handoff(qapp):
    eng, _, advanced, finished = _engine_with_next()
    eng._maybe_promote_next()
    eng._sink.us = 30_000_000

    eng._check_finished()

    assert finished == [], "the sink keeps running; no end-of-track event"


def test_promoted_decoder_losing_duration_does_not_stall(qapp):
    """Real FFmpeg decoders re-report duration -1 right after promotion;
    that must not erase the known duration or playback never finishes."""
    eng, next_decoder, advanced, finished = _engine_with_next()
    eng._maybe_promote_next()
    eng._sink.us = 10_400_000
    eng._emit_position()
    assert advanced == ["C:/music/next.mp3"]
    assert eng._duration_ms == 8000

    for slot in list(next_decoder.durationChanged.slots):
        slot(-1)

    assert eng._duration_ms == 8000, "a late -1 must not clobber the duration"
    eng._decoding_done = True
    eng._sink.us = 18_500_000
    eng._check_finished()
    assert finished == [1]


def test_queue_next_preloads_and_clears(qapp, monkeypatch):
    made = []

    class _Dec(_FakeDecoder):
        def __init__(self, parent=None):
            super().__init__(duration=7000)
            made.append(self)

    monkeypatch.setattr(eq_mod, "QAudioDecoder", _Dec)
    eng = eq_mod.EQEngine()
    eng._decoder = _FakeDecoder(10000)

    assert eng.queue_next("C:/music/next.mp3") is True
    assert len(made) == 1 and made[0].started
    assert eng._next_decoder is made[0]
    assert eng._next_source == "C:/music/next.mp3"

    eng.clear_queued_next()
    assert eng._next_decoder is None and eng._next_source is None
    assert made[0].stopped and made[0].deleted


def test_queue_next_refuses_when_idle(qapp, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("must not create a decoder while idle")

    monkeypatch.setattr(eq_mod, "QAudioDecoder", _boom)
    eng = eq_mod.EQEngine()

    assert eng.queue_next("C:/music/next.mp3") is False
    assert eng._next_decoder is None


def test_player_queues_only_plain_sequential_local_rows(
        music_player, monkeypatch, tmp_path):
    mp = music_player
    first = tmp_path / "first.mp3"
    second = tmp_path / "second.mp3"
    first.write_bytes(b"")
    second.write_bytes(b"")
    mp.playlist = [str(first), str(second)]
    mp.current_index = 0
    mp._using_engine = True
    armed = []
    monkeypatch.setattr(mp.eq_engine, "queue_next",
                        lambda src: armed.append(src), raising=False)

    mp._queue_gapless_next()
    assert armed == [str(second)]

    armed.clear()
    mp.current_index = 1          # last row: no candidate
    mp._queue_gapless_next()
    assert armed == []

    mp.current_index = 0
    mp.shuffle_btn.setChecked(True)
    mp._queue_gapless_next()
    assert armed == [], "shuffle order is unknown up front"
    mp.shuffle_btn.setChecked(False)

    mp._play_next_queue = [1]
    mp._queue_gapless_next()
    assert armed == [], "Play Next outranks the sequential row"
    mp._play_next_queue = []

    mp.playlist = [str(first),
                   {"type": "cloud", "cloud_idx": 0, "file_idx": 0,
                    "name": "cloud.mp3"}]
    mp.current_index = 0
    mp._queue_gapless_next()
    assert armed == [], "cloud rows re-resolve their stream URL"


def test_engine_advance_updates_ui_without_replaying(
        music_player, monkeypatch, tmp_path):
    mp = music_player
    files = [tmp_path / name for name in ("a.mp3", "b.mp3", "c.mp3")]
    for f in files:
        f.write_bytes(b"")
    mp.playlist = [str(f) for f in files]
    mp.playlist_widget.clear()
    for f in files:
        mp.playlist_widget.addItem(f.name)
    mp.current_index = 0
    mp._using_engine = True
    played = []
    armed = []
    monkeypatch.setattr(mp, "play", lambda: played.append(1), raising=False)
    monkeypatch.setattr(mp.eq_engine, "queue_next",
                        lambda src: armed.append(src), raising=False)

    mp._on_engine_track_advanced(str(files[1]))

    assert played == [], "restarting playback would reintroduce the gap"
    assert mp.current_index == 1
    assert mp.playlist_widget.currentRow() == 1
    assert armed == [str(files[2])], "the following row is pre-armed"
    assert str(files[1]) in mp._history["recent"]


def test_engine_start_arms_the_next_row(music_player, monkeypatch):
    mp = music_player
    monkeypatch.setattr(mp.eq_engine, "play", lambda src: None, raising=False)
    armed = []
    monkeypatch.setattr(mp, "_queue_gapless_next",
                        lambda: armed.append(1), raising=False)

    mp._engine_start("file", "C:/music/a.mp3", "a.mp3")

    assert armed == [1]

    armed.clear()
    mp._engine_start("url", "https://cloud/x.mp3", "x.mp3")
    assert armed == [], "cloud streams stay on the normal path"


def test_play_next_invalidates_preload_and_clear_rearms(
        music_player, monkeypatch, tmp_path):
    mp = music_player
    first = tmp_path / "first.mp3"
    second = tmp_path / "second.mp3"
    first.write_bytes(b"")
    second.write_bytes(b"")
    mp.playlist = [str(first), str(second)]
    mp.playlist_widget.clear()
    mp.playlist_widget.addItem("first.mp3")
    mp.playlist_widget.addItem("second.mp3")
    mp.current_index = 0
    mp._using_engine = True
    invalidated = []
    armed = []
    monkeypatch.setattr(mp.eq_engine, "clear_queued_next",
                        lambda: invalidated.append(1), raising=False)
    monkeypatch.setattr(mp.eq_engine, "queue_next",
                        lambda src: armed.append(src), raising=False)

    mp.playlist_widget.setCurrentRow(1)
    mp.queue_play_next()
    assert invalidated == [1], "a user-queued row must win"

    mp.clear_play_next_queue()
    assert armed == [str(second)], "clearing the queue re-arms the sequence"
