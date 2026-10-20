import pytest



def test_write_and_no_leftovers(tmp_path):
    import utils

    target = tmp_path / "clouds.json"
    utils.atomic_write_text(str(target), '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'
    assert [p.name for p in tmp_path.iterdir()] == ["clouds.json"], "temp file must never survive"


def test_failed_replace_keeps_previous_file(tmp_path, monkeypatch):
    import utils

    target = tmp_path / "playlists.json"
    target.write_text("OLD", encoding="utf-8")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(utils.os, "replace", boom)
    with pytest.raises(OSError):
        utils.atomic_write_text(str(target), "NEW")
    assert target.read_text(encoding="utf-8") == "OLD", "previous config must survive a failed save"
    assert list(tmp_path.glob("*.tmp")) == [], "failed saves must clean their temp file"


def test_download_worker_requests_have_timeout():
    """workers.py DownloadWorker.run must not issue open-ended requests."""
    src_txt = (__import__("pathlib").Path(__file__).resolve().parents[1] / "workers.py").read_text(encoding="utf-8")
    assert "timeout=" in src_txt, "requests.get without timeout found in workers.py"


def test_save_methods_use_atomic_writes():
    """Regression pin: the three save_* methods route through atomic_write_text."""
    src_txt = (__import__("pathlib").Path(__file__).resolve().parents[1] / "player.py").read_text(encoding="utf-8")
    assert "atomic_write_text" in src_txt
    assert 'with open(CLOUD_FILES_FILE, "w")' not in src_txt
    assert 'with open(PLAYLISTS_FILE, "w")' not in src_txt


def test_save_media_folders_survives_and_writes_correct_json(music_player, monkeypatch):
    """Behavioral: save_media_folders writes valid JSON into the isolated config dir."""
    music_player.media_folders = [r"C:\music"]
    saved = []
    real_atomic = __import__("utils").atomic_write_text

    def recording_atomic(path, text):
        saved.append((path, text))
        real_atomic(path, text)

    monkeypatch.setattr(__import__("player"), "atomic_write_text", recording_atomic)
    music_player.save_media_folders()
    assert saved, "save_media_folders did not write anything"
    import json
    assert json.loads(saved[0][1]) == [r"C:\music"]
