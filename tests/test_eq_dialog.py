"""The equalizer dialog must actually engage the EQ when the user touches it.

v1.0.4 shipped 'Equalizer on' defaulting to the persisted state (off). With
the box unticked, moving slider predictions stored the curve but forced FLAT
gains into the engine: users set Bass Boost, heard no difference and
concluded the EQ is broken. Standard-player UX (VLC et al.): touching the
curve turns the EQ on; Cancel still restores the state captured at open.
"""
import pytest

from hicloudmp.ui.dialogs import EqualizerDialog


@pytest.fixture()
def applied():
    return []


def _make_dialog(music_player, applied, gains=(0.0,) * 10, enabled=False,
                 preset="Flat"):
    return EqualizerDialog(music_player, gains, enabled, preset,
                           lambda g, on: applied.append((tuple(g), on)))


def test_slider_move_auto_enables(music_player, applied):
    dlg = _make_dialog(music_player, applied)

    dlg._sliders[0].setValue(7)   # user drags the 31 Hz band up

    assert dlg.enabled_check.isChecked(), "moving a slider must turn the EQ on"
    assert applied[-1][1] is True
    assert applied[-1][0][0] == 7.0


def test_preset_pick_auto_enables(music_player, applied):
    dlg = _make_dialog(music_player, applied, preset="Flat")

    dlg.preset_combo.setCurrentText("Bass Boost")

    assert dlg.enabled_check.isChecked(), "picking a preset must turn EQ on"
    assert applied[-1][1] is True


def test_cancel_restores_state_captured_at_open(music_player, applied):
    dlg = _make_dialog(music_player, applied, gains=(0.0,) * 10, enabled=False)

    dlg._sliders[0].setValue(7)          # auto-enables (user touched the curve)
    dlg.reject()                          # Cancel / window X

    assert applied[-1] == ((0.0,) * 10, False), \
        "Cancel must restore the state from before the dialog opened"


def test_explicit_disable_stays_disabled(music_player, applied):
    dlg = _make_dialog(music_player, applied, enabled=True)

    dlg.enabled_check.setChecked(False)   # user deliberately turns EQ off

    assert applied[-1][1] is False
    dlg._sliders[0].setValue(7)
    # ...but a later slider touch re-enables: the whole dialog exists to
    # audition the curve, and sliders while disabled have zero effect.
    assert dlg.enabled_check.isChecked() is True
