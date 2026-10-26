"""Audio output device picker.

Settings > Playback picks which speaker/headphones sound comes out of.
Native QMediaPlayer and the EQ engine both honor it (engine at the next
track start). Empty selection = system default.
"""
import pytest

from hicloudmp.audio import audio_devices


def test_default_entry_always_present():
    devices = audio_devices.list_output_devices()
    assert devices[0][0] == ""          # empty id = system default
    assert devices[0][1] == "System default"


def test_descriptions_unique_with_ids():
    devices = audio_devices.list_output_devices()
    ids = [d[0] for d in devices]
    assert len(ids) == len(set(ids)), "device ids must be unique"
    for did, desc in devices:
        assert desc.strip(), f"device {did!r} has an empty description"


def test_resolve_default_and_garbage():
    if len(audio_devices.list_output_devices()) < 2:
        pytest.skip("no real audio outputs on this host")
    d = audio_devices.resolve_output("")
    assert d is not None  # system default resolves to a real device where HW exists
    assert audio_devices.resolve_output("definitely-not-a-device-id") is None


def test_resolve_roundtrips_real_device_id():
    devices = audio_devices.list_output_devices()
    if len(devices) < 2:
        pytest.skip("no real audio outputs on this host")
    did, desc = devices[1]
    resolved = audio_devices.resolve_output(did)
    assert resolved is not None


def test_engine_uses_stored_device(qapp):
    if len(audio_devices.list_output_devices()) < 2:
        pytest.skip("no real audio outputs on this host")
    from hicloudmp.audio.eq_engine import EQEngine
    eng = EQEngine()
    assert eng._choose_output_device() is not None   # default fallback

    class _Dev:
        def isNull(self):
            return False

    d = _Dev()
    eng.set_output_device(d)
    assert eng._choose_output_device() is d
    eng.set_output_device(None)
    assert eng._choose_output_device() is not None   # None back -> default
    eng.set_output_device(object())                   # garbage -> default
    assert eng._choose_output_device() is not None


def test_settings_dialog_lists_devices(music_player, monkeypatch):
    from hicloudmp.ui import player as player_mod
    monkeypatch.setattr(audio_devices, "list_output_devices",
                        lambda: [("", "System default"),
                                 ("DEV1", "Speakers"),
                                 ("DEV2", "Headphones")])
    dlg = player_mod.SettingsDialog(music_player)
    data = [dlg.output_combo.itemData(i) for i in range(dlg.output_combo.count())]
    assert data == ["", "DEV1", "DEV2"]
    assert dlg.output_combo.currentData() in ("", None)


def test_settings_roundtrip_device(music_player, monkeypatch):
    from hicloudmp.ui import player as player_mod
    monkeypatch.setattr(audio_devices, "list_output_devices",
                        lambda: [("", "System default"),
                                 ("DEV1", "Speakers")])
    mp = music_player
    mp.settings.setValue("audio/output_device", "DEV1")
    dlg = player_mod.SettingsDialog(mp)
    assert dlg.output_combo.currentData() == "DEV1"
    dlg.output_combo.setCurrentIndex(0)   # back to system default
    dlg.save_settings()
    assert mp.settings.value("audio/output_device", "x", str) == ""


def test_player_applies_device_to_native_and_engine(music_player, monkeypatch):
    """apply_output_device_setting(): resolve, swap native output, push to engine."""
    mp = music_player
    pushed = []
    applied = []

    class _FakeOut:
        def setVolume(self, v):
            applied.append(("vol", v))

    monkeypatch.setattr(audio_devices, "resolve_output",
                        lambda did: "RESOLVED-DEVICE" if did == "DEV1" else None)
    monkeypatch.setattr(mp.eq_engine, "set_output_device",
                        lambda d: pushed.append(d), raising=False)
    monkeypatch.setattr(music_player, "_make_native_output",
                        lambda dev: _FakeOut())
    mp.settings.setValue("audio/output_device", "DEV1")
    mp.apply_output_device_setting()
    assert pushed == ["RESOLVED-DEVICE"]
    mp.settings.setValue("audio/output_device", "")
    mp.apply_output_device_setting()
    assert pushed[-1] is None
