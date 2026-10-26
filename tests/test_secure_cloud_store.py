"""cloudfiles.json holds WebDAV/Subsonic/Ampache credentials. It earned
a vault: DPAPI (CurrentUser scope) on write, transparent plaintext
reading on load so existing installs upgrade on their next save.

Rulings: 
- Corrupt vault fails loudly, never silently resets to [] (a silent
  reset would wipe the user's cloud library over one bad decrypt).
- Non-Windows stays plaintext (the packaged app is Windows; the
  mpris/dbus halves already tolerate a Linux dev host).
"""
import json
import os

from hicloudmp.core import secure_store


def test_roundtrip_encrypts_at_rest(tmp_path):
    p = tmp_path / "cloudfiles.json"
    data = {"a": {"type": "webdav", "config": {"webdav_password": "s3cret"}}}

    secure_store.save_json(p, data)

    raw = p.read_text(encoding="utf-8")
    if os.name == "nt":
        assert raw.startswith(secure_store.MAGIC)
        assert "s3cret" not in raw
    assert secure_store.load_json(p) == data


def test_plaintext_file_still_loads(tmp_path):
    p = tmp_path / "cloudfiles.json"
    data = {"a": {"type": "subsonic", "config": {"subsonic_password": "pw"}}}
    p.write_text(json.dumps(data), encoding="utf-8")

    assert secure_store.load_json(p) == data


def test_secure_store_importable_off_windows(monkeypatch):
    """macOS/Linux reality: os.name != 'nt' and ctypes.wintypes absent
    (not bound by 'import ctypes', not in sys.modules). Module import
    must not touch any DPAPI types during definition."""
    import ctypes
    import importlib
    import sys

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.delattr(ctypes, "wintypes", raising=False)
    monkeypatch.delitem(sys.modules, "ctypes.wintypes", raising=False)
    importlib.reload(secure_store)
    assert secure_store.MAGIC == "HiCloudMP-DPAPI-v1:"


def test_corrupt_vault_fails_loudly(tmp_path):
    p = tmp_path / "cloudfiles.json"
    secure_store.save_json(p, {"ok": 1})
    raw = p.read_text(encoding="utf-8")
    if not raw.startswith(secure_store.MAGIC):
        return  # non-DPAPI host: nothing to corrupt
    magic_len = len(secure_store.MAGIC)
    body = raw[magic_len:]
    flipped = "A" if body[0] != "A" else "B"
    p.write_text(raw[:magic_len] + flipped + body[1:], encoding="utf-8")

    try:
        secure_store.load_json(p)
        raised = False
    except Exception:
        raised = True
    assert raised, "corrupt vault must not degrade to an empty dict"


def test_unicode_secret_survives(tmp_path):
    p = tmp_path / "cloudfiles.json"
    pw = "pain\u00e9-\u4e2d\u6587-\U0001f600-\"quote\\slash"
    secure_store.save_json(p, {"pw": pw})
    assert secure_store.load_json(p) == {"pw": pw}


def test_player_save_clouds_encrypts_and_reloads(music_player, monkeypatch,
                                                 tmp_path):
    from hicloudmp.ui import player as player_mod

    p = tmp_path / "cloudfiles.json"
    monkeypatch.setattr(player_mod, "CLOUD_FILES_FILE", str(p))

    mp = music_player
    mp.clouds = [{
        "name": "Vault", "type": "subsonic",
        "config": {"subsonic_password": "up-the-keyhole"},
        "files": [],
    }]
    mp.save_clouds()

    raw = p.read_text(encoding="utf-8")
    if os.name == "nt":
        assert "up-the-keyhole" not in raw, "plaintext password on disk"

    fresh_player = mp   # same process, real reload path:
    fresh_player.clouds = []
    fresh_player.load_clouds()
    assert fresh_player.clouds[0]["config"]["subsonic_password"] == \
        "up-the-keyhole"