"""Playback engine for the 10-band equalizer.

QAudioDecoder (forced to s16 stereo 44100 — verified honored by the FFmpeg
backend in PySide6 6.10.3 for both local files AND network URLs) feeds a numpy
overlap-add EQ (dsp.EQProcessor), whose output is pumped into a QAudioSink.

MusicPlayer routes a track through this engine when the equalizer is enabled;
on any engine error the player falls back to native QMediaPlayer playback.
"""
import numpy as np

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import (QAudioDecoder, QAudioFormat, QAudioSink,
                                  QMediaDevices)

import dsp


class EQEngine(QObject):
    """Decoder → 10-band EQ → QAudioSink playback engine."""

    position_changed = Signal(int)      # ms within track
    duration_changed = Signal(int)      # ms
    track_finished = Signal()
    error_occurred = Signal(str)
    state_changed = Signal(str)         # 'playing' | 'paused' | 'stopped'

    SAMPLE_RATE = 44100
    CHANNELS = 2
    _BYTES_PER_SAMPLE = 2               # int16
    _SINK_BUFFER_BYTES = 192 * 1024     # ~1.1 s cushion against UI hiccups
    _MAX_PENDING_SECONDS = 6.0          # deep EQ'd cushion: network jitter +
                                        # decoder single-slot refills must not
                                        # starve the sink (playback 'hops')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._decoder = None
        self._sink = None
        self._io = None
        self._proc = None
        self._gains = (0.0,) * 10
        self._playing = False
        self._decoding_done = False
        self._finish_emitted = False
        self._error_reported = False
        self._got_first_buffer = False
        self._fallback_timer = QTimer(self)          # watchdog + finish poll
        self._fallback_timer.setInterval(250)
        self._fallback_timer.timeout.connect(self._tick)
        self._pending = np.zeros((0, self.CHANNELS), dtype=np.int16)
        self._base_ms = 0
        self._prof_us_base = 0
        self._duration_ms = 0
        self._skip_until_ms = 0
        self._skip_done = True
        self._volume = 1.0
        # Spectrum tap (visualizer): rolling mono tail + latest band data.
        self._spectrum = None
        self._spec_buf = np.zeros((0,), dtype=np.float32)
        # Output device: None = system default (re-choosable in Settings;
        # applied when the next sink is created).
        self._out_device = None
        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(40)
        self._pump_timer.timeout.connect(self._pump)
        # bufferReady wake: the decoder holds ONE buffer slot; waiting for
        # the next 40ms tick after every buffer throttles decoding to
        # just-in-time. The slot must never be read here (single-consumer
        # rule) — this timer only wakes the pump immediately.
        self._wake_scheduled = False
        self._wake_timer = QTimer(self)
        self._wake_timer.setInterval(0)
        self._wake_timer.setSingleShot(True)
        self._wake_timer.timeout.connect(self._wake_pump)

    # ------------------------------------------------------------------ API
    def set_gains(self, gains_db):
        self._gains = tuple(float(g) for g in gains_db)
        if self._proc is not None:
            self._proc.set_gains(self._gains)

    def set_volume(self, volume):
        self._volume = max(0.0, min(1.0, float(volume)))
        if self._sink is not None:
            self._sink.setVolume(self._volume)

    def set_output_device(self, device):
        """Pick the sink endpoint for the NEXT track (None/garbage = default)."""
        self._out_device = device

    def _choose_output_device(self):
        try:
            dev = self._out_device
            if dev is not None and not dev.isNull():
                return dev
        except Exception:
            pass
        try:
            d = QMediaDevices().defaultAudioOutput()
            if d is not None and not d.isNull():
                return d
        except Exception:
            pass
        return None

    def is_playing(self):
        return self._playing

    def is_paused(self):
        """Engine holds a loaded sink but audio is currently paused."""
        return (not self._playing) and self._sink is not None

    def is_active(self):
        return self._decoder is not None

    def play(self, source, start_ms=0):
        """Play a local file path or an http(s) URL through the EQ chain."""
        self._teardown()
        self._base_ms = int(start_ms)
        self._prof_us_base = 0
        self._pending = np.zeros((0, self.CHANNELS), dtype=np.int16)
        self._decoding_done = False
        self._finish_emitted = False
        self._error_reported = False
        self._got_first_buffer = False
        self._duration_ms = 0
        self._skip_until_ms = 0
        self._skip_done = True

        fmt = QAudioFormat()
        fmt.setSampleRate(self.SAMPLE_RATE)
        fmt.setChannelCount(self.CHANNELS)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        self._decoder = QAudioDecoder(self)
        self._decoder.setAudioFormat(fmt)
        self._decoder.bufferReady.connect(self._on_buffer_ready)
        self._decoder.finished.connect(self._on_decoder_finished)
        self._decoder.durationChanged.connect(self._on_duration_changed)

        src = str(source)
        if src.startswith("http://") or src.startswith("https://"):
            url = QUrl(src)
        else:
            url = QUrl.fromLocalFile(src)
        self._decoder.setSource(url)

        self._proc = dsp.EQProcessor(self.SAMPLE_RATE, self.CHANNELS, self._gains)

        device = self._choose_output_device()
        if device is not None:
            self._sink = QAudioSink(device, fmt, self)
        else:
            self._sink = QAudioSink(fmt, self)
        self._sink.setBufferSize(self._SINK_BUFFER_BYTES)
        self._sink.setVolume(self._volume)
        # PySide6 6.10: push mode returns the QIODevice to write into; the
        # sink object itself no longer exposes .write(). Older builds expose
        # sink.write — _write_bytes handles both.
        self._io = self._sink.start()
        if self._io is None and not hasattr(self._sink, 'write'):
            msg = "audio sink exposes no push-write API"
            self._teardown()
            self._playing = False
            self.error_occurred.emit(msg)
            return

        self._decoder.start()
        self._playing = True
        self._pump_timer.start()
        self._fallback_timer.start()
        self.state_changed.emit("playing")

    def pause(self):
        if self._playing and self._sink is not None:
            try:
                self._sink.suspend()
            except Exception:
                pass
            self._playing = False
            self.state_changed.emit("paused")

    def resume(self):
        if (not self._playing and self._sink is not None
                and self._decoder is not None):
            try:
                self._sink.resume()
            except Exception:
                pass
            self._playing = True
            self.state_changed.emit("playing")

    def seek(self, ms):
        """PySide6 6.10 QAudioDecoder has no setPosition: restart from the top
        and discard decoded frames until decoder.position() reaches the target."""
        if self._decoder is None or self._proc is None:
            return
        ms = max(0, int(ms))
        self._pending = np.zeros((0, self.CHANNELS), dtype=np.int16)
        self._proc.reset()
        self._skip_until_ms = ms
        self._skip_done = False
        self._base_ms = ms
        if self._sink is not None:
            # Qt6 semantics: reset()/stop() leave the sink StoppedState and
            # close the push-mode QIODevice - later writes hit bytesFree()==0
            # and silently no-op (playback dies, position freezes at the
            # target). Flush by RESTARTING the push stream immediately.
            was_suspended = False
            try:
                from PySide6.QtMultimedia import QtAudio
                st = self._sink.state()
                was_suspended = st == QtAudio.State.SuspendedState
            except Exception:
                pass
            try:
                self._sink.stop()
                self._io = self._sink.start()
                self._prof_us_base = 0     # processedUSecs() runs from 0 again
                if was_suspended:
                    self._sink.suspend()   # scrub space: stay silenced
            except Exception as e:
                self._report_error(f"seek: sink restart failed: {e}")
                return
        try:
            url = self._decoder.source()
            self._decoder.stop()
            self._decoder.setSource(QUrl())
            self._decoder.setSource(url)
            self._decoder.start()
        except Exception as e:
            raise RuntimeError(f"seek restart failed: {e}")

    def stop(self):
        was_active = self._decoder is not None
        self._teardown()
        if was_active or self._playing:
            self._playing = False
            self.state_changed.emit("stopped")

    # ------------------------------------------------------------- internals
    def _teardown(self):
        self._pump_timer.stop()
        self._fallback_timer.stop()
        self._wake_timer.stop()
        self._wake_scheduled = False
        if self._decoder is not None:
            try:
                self._decoder.stop()
                self._decoder.bufferReady.disconnect(self._on_buffer_ready)
                self._decoder.finished.disconnect(self._on_decoder_finished)
                self._decoder.durationChanged.disconnect(self._on_duration_changed)
                self._decoder.stop()
                self._decoder.setSource(QUrl())
                self._decoder.deleteLater()
            except Exception:
                pass
            self._decoder = None
        if self._sink is not None:
            try:
                self._sink.stop()
                self._sink.deleteLater()
            except Exception:
                pass
            self._sink = None
        self._io = None
        self._proc = None
        self._pending = np.zeros((0, self.CHANNELS), dtype=np.int16)
        self._spectrum = None
        self._spec_buf = np.zeros((0,), dtype=np.float32)

    def _on_duration_changed(self, ms):
        self._duration_ms = int(ms)
        self.duration_changed.emit(self._duration_ms)

    def _on_buffer_ready(self):
        # The 40ms pump is the ONLY reader (single-consumer keeps every
        # buffer on the EQ path); this slot just marks decoder progress
        # and wakes the pump so the pending cushion fills immediately.
        self._got_first_buffer = True
        if not self._wake_scheduled:
            self._wake_scheduled = True
            self._wake_timer.start()

    def _wake_pump(self):
        self._wake_scheduled = False
        self._pump()

    def _on_decoder_finished(self):
        self._decoding_done = True
        err = self._decoder_error()
        if err and not self._got_first_buffer and not self._pending.size:
            self._report_error(err)
            return
        # Drain the EQ tail (analysis-window latency) into the sink.
        try:
            tail = self._proc.flush()
            if tail.size:
                self._pending = np.concatenate([self._pending, tail], axis=0)
        except Exception:
            pass
        self._pump()

    def _decoder_error(self):
        if self._decoder is None:
            return None
        try:
            err = self._decoder.error()
            if err == QAudioDecoder.Error.NoError:
                return None
            return str(self._decoder.errorString() or "decoder error")
        except Exception:
            return None

    def _report_error(self, msg):
        if self._error_reported:
            return
        self._error_reported = True
        self._teardown()
        self._playing = False
        self.error_occurred.emit(msg)

    def _pump(self):
        if self._sink is None or self._proc is None or not self._playing:
            return
        try:
            self._refill()
            self._flush_to_sink()
        except Exception as e:
            # A broken sink must surface (player falls back to native
            # playback) instead of looping silently tick after tick.
            self._report_error(f"Audio sink error: {e}")

    def _process_or_discard(self, arr, buffer_end_position_ms):
        """During a seek-skip, drop buffers that end before the target."""
        if self._skip_done:
            return arr
        if buffer_end_position_ms is not None and \
                buffer_end_position_ms < self._skip_until_ms:
            return np.zeros((0, self.CHANNELS), dtype=np.int16)
        self._skip_done = True
        return arr

    def _refill(self):
        """Pull decoded buffers through the EQ while behind the pending cap."""
        max_pending = int(self._MAX_PENDING_SECONDS * self.SAMPLE_RATE)
        skip_pos = None
        try:
            while (self._decoder is not None
                   and self._decoder.bufferAvailable()
                   and self._pending.shape[0] < max_pending):
                buf = self._decoder.read()
                if buf is None or buf.byteCount() <= 0:
                    break
                if not self._skip_done:
                    try:
                        skip_pos = self._decoder.position()
                    except Exception:
                        skip_pos = None
                data = bytes(buf.constData())
                arr = np.frombuffer(data, dtype=np.int16)
                frames = arr.size // self.CHANNELS
                if frames == 0:
                    break
                self._got_first_buffer = True
                if self._proc is None:
                    return
                arr = arr[:frames * self.CHANNELS].reshape(
                    frames, self.CHANNELS)
                arr = self._process_or_discard(arr, skip_pos)
                skip_pos = None
                if arr.shape[0] == 0:
                    continue
                out = self._proc.process(arr)
                if out.shape[0]:
                    self._pending = np.concatenate(
                        [self._pending, out], axis=0)
        except Exception as e:
            raise RuntimeError(f"decode error: {e}")

    def _flush_to_sink(self):
        try:
            free = self._sink.bytesFree()
        except Exception:
            free = 0
        if free > 0 and self._pending.shape[0]:
            take_samples = min(self._pending.shape[0], free //
                               (self.CHANNELS * self._BYTES_PER_SAMPLE))
            if take_samples > 0:
                chunk = self._pending[:take_samples]
                written = self._write_bytes(chunk.tobytes())
                if written > 0:
                    consumed = written // (self.CHANNELS * self._BYTES_PER_SAMPLE)
                    self._tap_spectrum(self._pending[:consumed])
                    self._pending = self._pending[consumed:]
        self._emit_position()
        self._check_finished()

    def _tap_spectrum(self, chunk):
        """Roll the written (post-EQ = audible) audio through the analyzer."""
        try:
            import spectrum
            mono = chunk.astype(np.float32).mean(axis=1)
            self._spec_buf = np.concatenate(
                [self._spec_buf, mono])[-spectrum.N_FFT:]
            if self._spec_buf.size >= spectrum.N_FFT:
                self._spectrum = spectrum.compute_spectrum(self._spec_buf)
        except Exception:
            pass

    def get_spectrum(self):
        """Latest band energies (np array) or None when nothing is playing."""
        return self._spectrum

    def _write_bytes(self, data):
        """Push s16 bytes to the sink. PySide6 6.10 exposes push mode via the
        QIODevice returned by start(); older builds expose sink.write()."""
        if self._io is not None:
            try:
                return self._io.write(data)
            except Exception as e:
                raise RuntimeError(f"push device write failed: {e}")
        sink = self._sink
        if sink is not None and hasattr(sink, 'write'):
            return sink.write(data)
        raise RuntimeError("audio sink exposes no push-write API")

    def _emit_position(self):
        if self._sink is None:
            return
        try:
            us = self._sink.processedUSecs()
        except Exception:
            return
        if us < self._prof_us_base:
            us = self._prof_us_base
        ms = self._base_ms + int((us - self._prof_us_base) / 1000)
        if self._duration_ms > 0:
            ms = min(ms, self._duration_ms)
        self.position_changed.emit(max(0, ms))

    def position_ms(self):
        """Current playback position in ms (sink-derived; safe when idle)."""
        if self._sink is None:
            return self._base_ms
        try:
            us = self._sink.processedUSecs()
        except Exception:
            return self._base_ms
        if us < self._prof_us_base:
            us = self._prof_us_base
        return self._base_ms + int((us - self._prof_us_base) / 1000)

    def duration_ms(self):
        """Track duration in ms as known by the engine (0 when unknown)."""
        return self._duration_ms

    def _check_finished(self):
        if (not self._playing or self._finish_emitted or not self._decoding_done
                or self._error_reported):
            return
        if self._sink is None:
            return
        try:
            us = self._sink.processedUSecs()
            played_ms = (us - self._prof_us_base) / 1000
            dur = self._duration_ms
            if dur <= 0:
                return
            total = self._base_ms + played_ms
            if total >= dur - 120 or us >= (dur * 1000) - 100000:
                self._emit_finished()
        except Exception:
            pass

    def _tick(self):
        # Watchdog: a source that never yields a first buffer is an error
        # the finished() signal may stay silent about.
        if (self._playing and not self._got_first_buffer
                and self._decoder is not None):
            if not self._decoder.isDecoding():
                err = self._decoder_error()
                if err:
                    self._report_error(err)
        self._emit_position()
        self._check_finished()

    def _emit_finished(self):
        if self._finish_emitted:
            return
        self._finish_emitted = True
        self._teardown()
        self._playing = False
        self.state_changed.emit("stopped")
        self.track_finished.emit()
