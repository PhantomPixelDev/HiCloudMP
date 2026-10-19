"""Visualizer repaint discipline (P5): the 20 Hz timer drives set_spectrum
forever; an idle (all-None) screen and byte-identical frames must not
force a repaint each tick. The timer test in test_visualizer.py keeps
pinning the 20 Hz cadence - this only clips needless repaints.
"""
import pytest

from visualizer import SFVisualizer


@pytest.fixture
def viz(qapp, monkeypatch):
    v = SFVisualizer(n_bands=12)
    calls = []
    monkeypatch.setattr(v, "update", lambda *a, **k: calls.append(1),
                        raising=False)
    return v, calls


def test_repeated_none_does_not_repaint(viz):
    v, calls = viz
    v.set_spectrum(None)
    n_after_first = len(calls)
    for _ in range(5):
        v.set_spectrum(None)
    assert len(calls) == n_after_first, "idle-to-idle must not repaint"


def test_identical_values_do_not_repaint(viz):
    v, calls = viz
    v.set_spectrum([0.1, 0.2, 0.3])
    n_after_first = len(calls)
    v.set_spectrum([0.1, 0.2, 0.3])       # fresh list object, same content
    assert len(calls) == n_after_first


def test_value_change_repaints_once(viz):
    v, calls = viz
    v.set_spectrum([0.0] * 12)            # explicit calm baseline: 1 paint
    assert len(calls) == 1
    v.set_spectrum([0.1, 0.2])            # idle -> live: repaints
    assert len(calls) == 2
    v.set_spectrum([0.1, 0.21])           # change repaints
    assert len(calls) == 3
    v.set_spectrum(None)                  # live -> idle: repaints
    assert len(calls) == 4


def test_palette_change_repaint_not_broken(viz):
    v, calls = viz
    v.set_spectrum([0.5])
    before = len(calls)
    v.set_palette("#123456")              # accent change repaints when live
    assert len(calls) >= before, "palette change keeps repainting live view"
