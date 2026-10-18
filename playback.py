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

    def _engine_playback_error(self, msg):
        """Decoder/sink failure on the EQ path: replay via the native player."""
        if not getattr(self, '_using_engine', False):
            return
        self._using_engine = False
        kind, src, name = self._engine_source
        self._engine_source = ('', '', '')
        self.status_bar.showMessage(
            "Equalizer unavailable for this track — using standard playback", 4000)
        try:
            if kind == 'url' and src:
                self._play_stream(src, name)
            elif kind == 'file' and src:
                self.player.setSource(QUrl.fromLocalFile(src))
                self.player.play()
            self.play_btn.setIcon(self._icon_pause())
        except Exception:
            pass

