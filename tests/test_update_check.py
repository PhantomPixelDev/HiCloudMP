"""Check-for-updates: manual, Settings-driven, never a popup spam.

Queries the GitHub releases API off the UI thread; pops a dialog only
when a NEWER release exists (user-initiated check, not per-track noise).
"""

from PySide6.QtWidgets import QMessageBox

import updates_check
from updates_check import compare_versions, latest_release


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_compare_versions_chronology():
    assert compare_versions("1.0.1", "v1.0.2") == -1   # newer available
    assert compare_versions("v1.0.2", "v1.0.2") == 0   # up to date
    assert compare_versions("1.0.2", "v1.0.1") == 1    # local newer
    assert compare_versions("1.0", "v1.0.0") == 0      # pads missing parts


def test_compare_versions_malformed_is_none():
    assert compare_versions("1.0.2", "not-a-version") is None


def test_latest_release_parses_and_sends_ua(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["url"], seen["headers"], seen["timeout"] = url, headers, timeout
        return _FakeResponse({"tag_name": "v1.0.3",
                              "html_url": "https://example.com/rel"})

    monkeypatch.setattr(updates_check.requests, "get", fake_get)
    data = latest_release()
    assert seen["headers"]["User-Agent"] == "HiCloudMP"
    assert seen["timeout"] is not None
    assert data == {"tag": "v1.0.3", "url": "https://example.com/rel"}


def test_dialog_has_update_row(music_player):
    import player as player_mod
    dlg = player_mod.SettingsDialog(music_player)
    assert hasattr(dlg, "update_btn")
    assert hasattr(dlg, "update_result_label")
    assert dlg.update_btn.isEnabled()


def test_check_reports_newer_release(music_player, monkeypatch, qtbot):
    import player as player_mod
    dlg = player_mod.SettingsDialog(music_player)
    opened = []
    monkeypatch.setattr(updates_check, "latest_release",
                        lambda: {"tag": "v1.0.9",
                                 "url": "https://example.com/rel"})
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(
                            lambda *a, **k: opened.append(a[2] if len(a) > 2 else None)))
    dlg.check_for_updates()  # thread -> run_on_ui -> label
    qtbot.waitUntil(lambda: dlg.update_result_label.text() != "Checking…",
                    timeout=5000)
    assert opened, "a newer release must be offered"
    assert "1.0.9" in dlg.update_result_label.text()
    assert dlg.update_btn.isEnabled()


def test_check_up_to_date_is_calm(music_player, monkeypatch, qtbot):
    import player as player_mod
    dlg = player_mod.SettingsDialog(music_player)
    popped = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: popped.append(1)))
    monkeypatch.setattr(updates_check, "latest_release",
                        lambda: {"tag": "v" + updates_check.APP_VERSION,
                                 "url": ""})
    dlg.check_for_updates()
    qtbot.waitUntil(lambda: dlg.update_result_label.text() != "Checking…",
                    timeout=5000)
    assert popped == []  # no popup when current
    assert "up to date" in dlg.update_result_label.text().lower()


def test_check_failure_shows_error_no_popup(music_player, monkeypatch, qtbot):
    import player as player_mod
    dlg = player_mod.SettingsDialog(music_player)
    popped = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: popped.append(1)))

    def boom():
        raise RuntimeError("offline")

    monkeypatch.setattr(updates_check, "latest_release", boom)
    dlg.check_for_updates()
    qtbot.waitUntil(lambda: dlg.update_result_label.text() != "Checking…",
                    timeout=5000)
    assert popped == []
    assert "offline" in dlg.update_result_label.text().lower()
    assert dlg.update_btn.isEnabled()
