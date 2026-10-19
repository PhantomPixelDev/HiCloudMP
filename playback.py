"""EQ-engine playback glue (mixin).

PlaybackEngineMixin carries the decoder-route decision (_eq_active),
engine start/replay/error handling, and engine-driven transport state.
It is mixed into MusicPlayer; every method touches the app through
self exactly as before the split.
"""

from PySide6.QtCore import QUrl


class PlaybackEngineMixin:
    """See module docstring. Requires on the mixing class: settings,
    _eq_gains(), eq_engine, play_btn/_icon_*, repeat/shuffle buttons,
    playlist/current_index, play()/next_track(), _play_stream(),
    player (QMediaPlayer) and status_bar."""

    def effective_playback_state(self):
        """Single truth for playback state across native + EQ engine.

        The web panel and tray must ask THIS, not the native player:
        while the engine plays, the native player sits idle."""
        from PySide6.QtMultimedia import QMediaPlayer
        if getattr(self, "_using_engine", False):
            engine = getattr(self, "eq_engine", None)
            if engine is not None:
                if engine.is_playing():
                    return QMediaPlayer.PlaybackState.PlayingState
                if engine.is_paused():
                    return QMediaPlayer.PlaybackState.PausedState
            return QMediaPlayer.PlaybackState.StoppedState
        return self.player.playbackState()

    def _route_through_engine(self):
        """The engine takes the track when the EQ is active, or when the
        user just wants the visualizer (flat gains = bit-transparent)."""
        try:
            if self._eq_active():
                return True
            return bool(self.settings.value("ui/visualizer_enabled",
                                            False, type=bool))
        except Exception:
            return False

    def _sync_engine_gains(self):
        """Push routing-appropriate gains to the engine: the user's curve
        when the EQ is on, flat otherwise (visualizer-only run must not
        color the audio)."""
        if self._eq_active():
            self.eq_engine.set_gains(self._eq_gains())
        else:
            self.eq_engine.set_gains((0.0,) * 10)

    def _eq_active(self):
        """EQ drives playback only when enabled and gains are non-neutral."""
        try:
            enabled = self.settings.value("audio/eq_enabled", False, type=bool)
        except Exception:
            enabled = False
        if not enabled:
            return False
        return any(abs(g) > 0.05 for g in self._eq_gains())

    def _engine_start(self, kind, src, name=''):
        """Route the current track through the EQ engine (decoder→EQ→sink)."""
        self._disconnect_stream_handlers()
        self._using_engine = True
        self._engine_source = (kind, src, name)
        self._sync_engine_gains()
        self.eq_engine.play(src)

    def _on_engine_state(self, state):
        try:
            self.play_btn.setIcon(self._icon_pause()
                                  if state == 'playing' else self._icon_play())
        except Exception:
            pass

    def _on_engine_track_finished(self):
        # Mirror the native EndOfMedia auto-advance rules.
        self._using_engine = False
        self._engine_source = ('', '', '')
        queued = self._take_from_play_next_queue()
        if queued is not None:
            # User's Play Next outranks repeat/shuffle/sequence
            self.current_index = queued
            self.play()
            return
        if self.repeat_btn.isChecked():
            self.play()
        elif self.shuffle_btn.isChecked() and len(self.playlist) > 1:
            import random
            next_index = self.current_index
            while next_index == self.current_index and len(self.playlist) > 1:
                next_index = random.randint(0, len(self.playlist) - 1)
            self.current_index = next_index
            self.play()
        elif self.current_index < len(self.playlist) - 1:
            self.next_track()

    def _tray_toast(self, title, body, ms=6000):
        """Raise a tray notification when a tray icon exists; silently a
        no-op on tray-less installs (tests, remote sessions)."""
        try:
            from PySide6.QtWidgets import QSystemTrayIcon
            icon = getattr(getattr(self, "tray", None), "tray_icon", None)
            if icon is not None:
                icon.showMessage(title, body,
                                 QSystemTrayIcon.Information, ms)
        except Exception:
            pass

    def _engine_playback_error(self, msg):
        """Decoder/sink failure on the EQ path: replay via the native player."""
        if not getattr(self, '_using_engine', False):
            return
        self._using_engine = False
        kind, src, name = self._engine_source
        self._engine_source = ('', '', '')
        self.status_bar.showMessage(
            "Playback engine unavailable — using standard playback", 4000)
        # Beyond the 4 s status line: raise a tray notification. EQ and
        # visualizer both disappear when this route fails; the wording
        # must not pretend it is only the equalizer.
        detail = str(msg)[:160]
        self._tray_toast(
            "HiCloud MP",
            "Audio engine unavailable — using standard playback"
            + (f" ({detail})" if detail else ""))
        try:
            if kind == 'url' and src:
                self._play_stream(src, name)
            elif kind == 'file' and src:
                self.player.setSource(QUrl.fromLocalFile(src))
                self.player.play()
            self.play_btn.setIcon(self._icon_pause())
        except Exception:
            pass

