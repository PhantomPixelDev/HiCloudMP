"""Settings must survive a hard process death.

QSettings buffers writes; Qt flushes periodically and on clean exit.
The app died repeatedly with the 0xC0000409 fastfatal (qFatal on a
retired running QThread at interpreter exit) - fastfail terminates the
process instantly, running no destructors, so any buffered-but-unflushed
setting simply evaporates. Users who enabled the equalizer and the
visualizer saw their choices revert to defaults after every crash:
"EQ and visualizer stopped working". The exit-fatal itself is fixed
(5ed140d); the writes must ALSO be flushed the moment they happen so
any future hard death (power loss, task-kill, unrelated crash) can
never eat a preference again.
"""


def _spy_sync(mp, monkeypatch):
    """Replace instance sync() with a recorder; real behavior unchanged."""
    log = []
    monkeypatch.setattr(mp.settings, "sync",
                        lambda *a, **k: log.append(True), raising=False)
    return log


def test_eq_dialog_accept_flushes_settings(music_player, monkeypatch):
    mp = music_player
    log = _spy_sync(mp, monkeypatch)

    # Non-modal stub standing in for the modal exec(); accept with EQ on.
    calls = {}

    class _FakeDlg:
        def __init__(self, *a, **k):
            self.preset_combo = type("PC", (), {"currentText":
                                                lambda self: "Rock"})()
            self.enabled_check = type("EC", (), {"isChecked":
                                                 lambda self: True})()

        def exec(self):
            calls["exec"] = True
            return 1

    import dialogs
    monkeypatch.setattr(dialogs, "EqualizerDialog", _FakeDlg)

    mp.open_eq_dialog()

    assert calls.get("exec"), "dialog flow must run"
    assert mp.settings.value("audio/eq_enabled", False, type=bool) is True
    assert log, "settings must be flushed right after save, not buffered"


def test_eq_slider_moves_flush_settings(music_player, monkeypatch):
    mp = music_player
    log = _spy_sync(mp, monkeypatch)

    cb = mp.make_eq_apply_cb()
    cb((3, 0, 0, 0, 0, 0, 0, 0, 0, 0), True)    # enable transition
    cb((7, 7, 5, 3, 1, 0, 0, 0, 0, 0), True)    # live slider move

    assert log, "every gain write must be flushed immediately"
    assert mp.settings.value("audio/eq_gains") == "7,7,5,3,1,0,0,0,0,0"


def test_eq_toggle_flushes_enabled_state(music_player, monkeypatch):
    mp = music_player
    log = _spy_sync(mp, monkeypatch)

    mp.apply_eq_toggle(False)   # plain toggle path writes eq_enabled

    assert mp.settings.value("audio/eq_enabled", False, type=bool) is False
    assert log, "the enabled-state write must be flushed"


def test_settings_dialog_save_flushes(music_player):
    mp = music_player
    log = []
    import player as player_mod
    monkeypatch = None
    # direct instance patch (no monkeypatch fixture here: keep it simple)
    real_sync = mp.settings.sync
    try:
        mp.settings.sync = lambda *a, **k: log.append(True)
        dlg = player_mod.SettingsDialog(mp)
        dlg.visualizer_checkbox.setChecked(True)
        dlg.save_settings()
    finally:
        mp.settings.sync = real_sync

    assert mp.settings.value("ui/visualizer_enabled", False,
                             type=bool) is True
    assert log, "settings dialog must flush immediately on save"
