"""Volume slider: clicking the groove must jump to that level.

Qt's stock QSlider pages by pageStep (10) when the groove is clicked, so
clicking at 75% of a 0..100 volume slider only nudged it by 10. Dragging
was required to set a level. ClickJumpSlider makes click-and-drag absolute.
"""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from hicloudmp.ui.slider import ClickJumpSlider


def _slider(qtbot):
    s = ClickJumpSlider(Qt.Horizontal)
    s.setRange(0, 100)
    s.setValue(70)
    s.resize(200, 28)
    qtbot.addWidget(s)
    s.show()
    qtbot.waitExposed(s)
    return s


def test_click_at_quarter_jumps_there_not_page_step(qtbot):
    s = _slider(qtbot)
    QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(50, 14))
    # 25% of the groove ~= 25, not 70 - 10 (stock page step).
    assert 10 <= s.value() <= 40, s.value()


def test_click_at_three_quarters_jumps_there(qtbot):
    s = _slider(qtbot)
    QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(150, 14))
    assert 60 <= s.value() <= 90, s.value()


def test_click_at_center_sets_about_half(qtbot):
    s = _slider(qtbot)
    QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(100, 14))
    assert 40 <= s.value() <= 60, s.value()


def test_drag_after_click_keeps_tracking(qtbot):
    s = _slider(qtbot)
    QTest.mousePress(s, Qt.LeftButton, pos=QPoint(30, 14))
    QTest.mouseMove(s, QPoint(170, 14))
    QTest.mouseRelease(s, Qt.LeftButton, pos=QPoint(170, 14))
    assert s.value() >= 65, s.value()


def test_slider_pressed_and_released_signals_still_fire(qtbot):
    s = _slider(qtbot)
    events = []
    s.sliderPressed.connect(lambda: events.append("pressed"))
    s.sliderReleased.connect(lambda: events.append("released"))
    QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(100, 14))
    assert events == ["pressed", "released"], events


def test_volume_slider_uses_click_jump(qtbot, music_player):
    assert isinstance(music_player.volume_slider, ClickJumpSlider)
    s = music_player.volume_slider
    s.resize(150, 28)
    before = s.value()
    QTest.mouseClick(s, Qt.LeftButton, pos=QPoint(20, 14))
    assert s.value() < before, "clicking near the left end must not page-step"
