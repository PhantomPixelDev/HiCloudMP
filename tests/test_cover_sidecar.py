"""Local covers must not depend on embedded art alone.

Archive.org-style downloads (and many tools) ship artwork as separate files
next to the audio: a per-track image named like the track and/or a common
album-cover file (Cover.jpg / folder.jpg / front.png ...). Files without
embedded art used to end with the default cover even when artwork sat right
beside them.
"""
import io

from PIL import Image

from hicloudmp.core.cover_extractor import CoverExtractor

ART = "artwork"


def _png_bytes(size, color):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue(), Image.new("RGB", size, color)


def _audio_without_art(tmp_path, name="track.mp3"):
    """An MP3 with no embedded artwork: ffmpeg finds no video stream and the
    ID3 layer finds no APIC frame."""
    p = tmp_path / name
    p.write_bytes(b"")
    return str(p)


def _track_png(tmp_path, stem, size, color):
    img_path = tmp_path / (stem + ".png")
    img_path.write_bytes(_png_bytes(size, color)[0])
    return str(img_path)


def test_sidecar_track_image_used_when_nothing_embedded(tmp_path):
    audio = _audio_without_art(tmp_path)
    sidecar = _track_png(tmp_path, "track", (8, 6), (200, 10, 10))
    assert sidecar

    img = CoverExtractor.extract_cover(audio, is_url=False)

    assert img is not None, "album has per-track artwork; cover stayed default"
    assert img.size == (8, 6), img.size


def test_album_cover_file_used_when_no_track_image(tmp_path):
    audio = _audio_without_art(tmp_path)
    cover = tmp_path / "Cover.jpg"
    buf = io.BytesIO()
    Image.new("RGB", (9, 9), (1, 2, 3)).save(buf, format="JPEG")
    cover.write_bytes(buf.getvalue())

    img = CoverExtractor.extract_cover(audio, is_url=False)

    assert img is not None, "Cover.jpg sits in the folder; cover stayed default"
    assert img.size == (9, 9), img.size


def test_embedded_art_still_wins_over_sidecar(tmp_path):
    import mutagen.id3

    audio = tmp_path / "track.mp3"
    embedded_png, _ = _png_bytes((10, 4), (250, 250, 0))
    tags = mutagen.id3.ID3()
    tags.add(mutagen.id3.APIC(encoding=3, mime="image/png", type=3,
                              desc="", data=embedded_png))
    tags.save(str(audio), v2_version=3)  # ID3 header only, no audio stream

    _track_png(tmp_path, "track", (8, 6), (200, 10, 10))  # decoy sidecar

    img = CoverExtractor.extract_cover(str(audio), is_url=False)

    assert img is not None
    assert img.size == (10, 4), "embedded art must keep priority: %s" % (img.size,)


def test_spectrogram_render_is_never_used_as_cover(tmp_path):
    audio = _audio_without_art(tmp_path)
    spec = tmp_path / "track_spectrogram.png"
    spec.write_bytes(_png_bytes((8, 8), (0, 0, 250))[0])

    img = CoverExtractor.extract_cover(audio, is_url=False)

    assert img is None, ("analogy: a visualizer spectrogram must not pose as "
                         "the album cover")


def test_corrupt_sidecar_falls_through_to_album_cover(tmp_path):
    audio = _audio_without_art(tmp_path)
    (tmp_path / "track.png").write_bytes(b"\x00\x01\x02 not an image")
    good = tmp_path / "cover.jpg"
    buf = io.BytesIO()
    Image.new("RGB", (7, 7), (9, 9, 9)).save(buf, format="JPEG")
    good.write_bytes(buf.getvalue())

    img = CoverExtractor.extract_cover(audio, is_url=False)

    assert img is not None
    assert img.size == (7, 7), img.size


def test_non_cover_shaped_track_image_defers_to_square_album_cover(tmp_path):
    """Archive.org puts waveform-like wide banners next to each track
    (800x200). They are not covers: the square album art must win."""
    audio = _audio_without_art(tmp_path)
    (tmp_path / "track.png").write_bytes(_png_bytes((800, 200), (0, 0, 0))[0])
    cover = tmp_path / "Cover.jpg"
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), (5, 5, 5)).save(buf, format="JPEG")
    cover.write_bytes(buf.getvalue())

    img = CoverExtractor.extract_cover(audio, is_url=False)

    assert img is not None
    assert img.size == (300, 300), "square Cover.jpg must beat the banner: %s" % (img.size,)
