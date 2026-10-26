"""Slider controls used by the player UI."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class ClickJumpSlider(QSlider):
    """A slider whose groove click jumps to the clicked value.

    QSlider's default behaviour pages by ``pageStep`` when the groove is
    clicked (a 0..100 volume slider moves by 10), which makes clicking feel
    broken: users expect the handle to land under the cursor. This subclass
    also keeps tracking while the button stays down, so one press-and-drag
    sets the level in a single gesture.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dragging = False

    def _value_at(self, x, y):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self)
        if self.orientation() == Qt.Vertical:
            pos = int(y) - groove.y()
            span = groove.height()
        else:
            pos = int(x) - groove.x()
            span = groove.width()
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), pos, max(1, span),
            opt.upsideDown)

    def _jump_to(self, event):
        pos = event.position()
        self.setValue(self._value_at(pos.x(), pos.y()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.setFocus(Qt.MouseFocusReason)
            self.setSliderDown(True)
            self._jump_to(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.LeftButton:
            self._jump_to(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._jump_to(event)
            self._dragging = False
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)
