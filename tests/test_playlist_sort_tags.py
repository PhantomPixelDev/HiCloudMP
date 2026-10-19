"""Artist/Album sort used hardcoded empty strings - a placebo that fell
back to insertion order. Now real tags are read (mutagen; easy
interface first, raw ID3 frames as fallback - WAV+ID3 containers have no
easy mapping). Rows without tags sort first; ties fall back to the
display title so the result is deterministic. Unreadable files stay
safe (("", "")).
"""
import os
import wave


def _tagged_wav(dir_path, name, artist=None, album=None, title=None):
    p = dir_path / name
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 400)
    from mutagen.wave import WAVE
    from mutagen.id3 import TIT2, TPE1, TALB
    f = WAVE(str(p))
    f.add_tags()
    if title:
        f.tags.add(TIT2(encoding=3, text=[title]))
    if artist:
        f.tags.add(TPE1(encoding=3, text=[artist]))
    if album:
        f.tags.add(TALB(encoding=3, text=[album]))
    f.save()
    return str(p)


def _load(mp, paths):
    mp.playlist = list(paths)
    mp.playlist_widget.clear()
    for p in paths:
        mp.playlist_widget.addItem(os.path.basename(p))
    mp.current_index = 0


def _set_mode(mp, mode):
    combo = mp.playlist_sort_combo
    idx = combo.findText(mode)
    assert idx >= 0, mode
    if combo.currentIndex() != idx:
        combo.setCurrentIndex(idx)   # signal drives sort_playlist
    else:
        mp.sort_playlist()


def _names(mp):
    return [os.path.basename(p) for p in mp.playlist]


def test_sort_by_artist_uses_tags(music_player, tmp_path):
    mp = music_player
    zed = _tagged_wav(tmp_path, "a.wav", artist="Zed", title="Z")
    amy = _tagged_wav(tmp_path, "b.wav", artist="Amy", title="A")
    moe = _tagged_wav(tmp_path, "c.wav", artist="Moe", title="M")
    _load(mp, [zed, amy, moe])

    _set_mode(mp, "Artist")

    assert _names(mp) == ["b.wav", "c.wav", "a.wav"], _names(mp)


def test_sort_by_album_uses_tags(music_player, tmp_path):
    mp = music_player
    beta = _tagged_wav(tmp_path, "one.wav", album="Beta", title="B")
    alpha = _tagged_wav(tmp_path, "two.wav", album="Alpha", title="A")
    untagged = _tagged_wav(tmp_path, "three.wav")   # no album tag
    _load(mp, [beta, alpha, untagged])

    _set_mode(mp, "Album")

    assert _names(mp) == ["three.wav", "two.wav", "one.wav"], _names(mp)


def test_sort_by_artist_ties_fall_back_to_title(music_player, tmp_path):
    mp = music_player
    z = _tagged_wav(tmp_path, "z.wav", artist="Same", title="Zeta")
    a = _tagged_wav(tmp_path, "a.wav", artist="Same", title="Alpha")
    _load(mp, [z, a])

    _set_mode(mp, "Artist")

    assert _names(mp) == ["a.wav", "z.wav"], _names(mp)


def test_unreadable_file_sorts_first_without_error(music_player, tmp_path):
    mp = music_player
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"\xff\xfb not really an mp3")
    good = _tagged_wav(tmp_path, "good.wav", artist="Amy")
    _load(mp, [good, str(junk)])

    _set_mode(mp, "Artist")

    assert _names(mp) == ["junk.mp3", "good.wav"], _names(mp)


def test_title_sort_still_uses_filenames(music_player, tmp_path):
    mp = music_player
    # tag titles deliberately conflict with filenames; Title sort must
    # keep using the display name (existing behavior).
    z = _tagged_wav(tmp_path, "a.wav", title="Zulu")
    a = _tagged_wav(tmp_path, "z.wav", title="Alpha")
    _load(mp, [z, a])

    _set_mode(mp, "Title")

    assert _names(mp) == ["a.wav", "z.wav"], _names(mp)
