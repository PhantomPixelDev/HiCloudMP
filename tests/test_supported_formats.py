"""One source of truth for audio formats: utils.SUPPORTED_EXTS.

Before this round the library scan accepted only mp3/flac/wav/ogg while the
add-files dialog advertised aac/m4a/wma — files the ffmpeg backend happily
plays became invisible to scanning. Formats the backend decodes must be
owned by one list.
"""

import pytest

from utils import SUPPORTED_EXTS, is_music_file, scan_music_files


@pytest.mark.parametrize("ext", [
    ".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus",
    ".m4a", ".mp4", ".aac", ".wma", ".aiff", ".aif", ".mka",
])
def test_supported_exts_include_common_codecs(ext):
    assert ext in SUPPORTED_EXTS, ext


def test_supported_exts_exclude_containers_that_are_not_audio():
    for ext in (".m3u", ".m3u8", ".pls", ".xspf", ".txt", ".exe"):
        assert ext not in SUPPORTED_EXTS, ext


def test_is_music_file_case_insensitive():
    assert is_music_file("B/track.FLAC")
    assert is_music_file("item.opus")
    assert not is_music_file("notes.txt")
    assert not is_music_file("list.m3u")


def test_scan_music_files_picks_new_formats(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"")
    (tmp_path / "b.wma").write_bytes(b"")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.opus").write_bytes(b"")
    (sub / "d.m4a").write_bytes(b"")
    (sub / "skip.m3u").write_text("#EXTM3U\n")
    (sub / "note.txt").write_text("nope")

    found = {p.lower() for p in scan_music_files(str(tmp_path))}

    assert any(p.endswith("a.mp3") for p in found)
    assert any(p.endswith("b.wma") for p in found)
    assert any(p.endswith("c.opus") for p in found)
    assert any(p.endswith("d.m4a") for p in found)
    assert not any(p.endswith(".m3u") for p in found)
    assert not any(p.endswith(".txt") for p in found)
