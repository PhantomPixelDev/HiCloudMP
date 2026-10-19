"""Spectrum visualizer widget.

Small bar canvas for the transport bar. Data comes from the EQ engine's
spectrum tap; None means "no data" and renders a calm idle baseline —
deliberately NOT a fake animation (the EQ is not placebo, and neither is
the visualizer).
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class SFVisualizer(QWidget):
    """Paints n_bands vertical bars from a spectrum (list of 0..1)."""

    DEFAULT_ACCENT = "#e11d48"

    def __init__(self, n_bands=24, parent=None):
        super().__init__(parent)
        self._n_bands = n_bands
        self._values = None          # None = idle baseline
        self._accent = self.DEFAULT_ACCENT
        self.setMouseTracking(False)

    def set_palette(self, accent_hex):
        """Theme hook: the accent color the bars are painted with."""
        try:
            if accent_hex:
                QColor(accent_hex)   # validate
                self._accent = accent_hex
                if self._values is not None or self.isVisible():
                    self.update()
        except Exception:
            pass

    def set_spectrum(self, values):
        """Feed band energies (sequence of floats) or None to go idle.

        Identical frames (and idle-to-idle) skip the repaint: the 20 Hz
        timer must not force widget updates through an unchanged canvas.
        """
        fresh = None if values is None else \
            [max(0.0, min(1.0, float(v))) for v in values]
        if fresh == self._values:
            return
        self._values = fresh
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        n = self._n_bands
        accent = QColor(self._accent)
        if not accent.isValid():
            accent = QColor(self.DEFAULT_ACCENT)
        accent.setAlpha(150)
        baseline = QColor(accent)
        baseline.setAlpha(70)

        slot = w / n
        bar_w = max(2.0, slot * 0.62)
        min_h = 2.0
        if self._values is None:
            for i in range(n):
                x = i * slot + (slot - bar_w) / 2.0
                p.fillRect(QRectF(x, h - min_h - 3.0, bar_w, min_h), baseline)
            p.end()
            return
        count = min(n, len(self._values))
        p.setPen(Qt.NoPen) if hasattr(Qt, "NoPen") else None
        for i in range(count):
            v = self._values[i]
            bar_h = min_h + v * (h - min_h - 4.0)
            x = i * slot + (slot - bar_w) / 2.0
            p.fillRect(QRectF(x, h - 3.0 - bar_h, bar_w, bar_h), accent)
        if count < n:  # engine gives fewer bands than planned: baseline the rest
            for i in range(count, n):
                x = i * slot + (slot - bar_w) / 2.0
                p.fillRect(QRectF(x, h - min_h - 3.0, bar_w, min_h), baseline)
        p.end()
