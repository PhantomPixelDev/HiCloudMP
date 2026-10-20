"""Embedded-art branches for the newly supported containers.

ffmpeg's attached-pic layer (primary) covers a lot, but bundled/PATH-less
builds still must read art from the containers' tag systems: ASF
WM/Picture for WMA, ID3 chunks inside AIFF/WAVE. Branches are tested at
the extractor-contract level with real mutagen objects where a
pytest-constructable container exists (WAV via stdlib wave) and with
class-level fakes where writing a real container from Python alone is
not feasible (ASF/AIFF keep 16-byte GUID/extended-float binaries).
"""
import wave
from io import BytesIO

from PIL import Image

from cover_extractor import CoverExtractor


def _png_bytes(size, color):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _tiny_png():
    return _png_bytes((12, 8), (11, 22, 33))


def _real_wav_with_id3_art(tmp_path):
    u = tmp_path / "song.wav"
    with wave.open(str(u), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 4000)
    from mutagen.wave import WAVE
    from mutagen.id3 import APIC
    f = WAVE(str(u))
    f.add_tags()
    f.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="",
                    data=_tiny_png()))
    f.save()
    return str(u)


# --- WAVE (real container end-to-end) ---------------------------------------
def test_wav_id3_art_extracts_after_ffmpeg_layer_misses(tmp_path):
    u = _real_wav_with_id3_art(tmp_path)
    img = CoverExtractor.extract_cover(u, is_url=False)
    assert img is not None, "wav with embedded ID3 art came back empty"
    assert img.size == (12, 8), img.size


# --- ASF / WMA branch --------------------------------------------------------
def test_wma_branch_reads_wm_picture(tmp_path, monkeypatch):
    (tmp_path / "x.wma").write_bytes(b"")  # ffmpeg layer fails fast on this
    png = _tiny_png()

    class _Pic:
        data = png

    class _FakeASF:
        def __init__(self, path):
            pass

        def getall(self, key):
            return [_Pic()] if key == "WM/Picture" else []

    import mutagen.asf as asf_mod
    monkeypatch.setattr(asf_mod, "ASF", _FakeASF)
    monkeypatch.setattr(CoverExtractor, "_extract_with_ffmpeg",
                        staticmethod(lambda p: None))

    img = CoverExtractor.extract_cover(str(tmp_path / "x.wma"), is_url=False)

    assert img is not None
    assert img.size == (12, 8), img.size


def test_wma_branch_survives_unpackaged_picture_shape(tmp_path, monkeypatch):
    class _Pic:
        data = b"\x00\x01not an image"

    class _FakeASF:
        def __init__(self, path):
            pass

        def getall(self, key):
            return [_Pic()]

    import mutagen.asf as asf_mod
    monkeypatch.setattr(asf_mod, "ASF", _FakeASF)
    monkeypatch.setattr(CoverExtractor, "_extract_with_ffmpeg",
                        staticmethod(lambda p: None))

    assert CoverExtractor.extract_cover(
        str(tmp_path / "x.wma"), is_url=False) is None


# --- AIFF branch -------------------------------------------------------------
def test_aiff_branch_reads_id3_apic(tmp_path, monkeypatch):
    (tmp_path / "y.aiff").write_bytes(b"")  # ffmpeg layer fails fast on this
    png = _tiny_png()

    class _Tags:
        def getall(self, key):
            png_frame = type("F", (), {"data": png})()
            return [png_frame] if key == "APIC" else []

    class _FakeAIFF:
        def __init__(self, path):
            self.tags = _Tags()

    import mutagen.aiff as aiff_mod
    monkeypatch.setattr(aiff_mod, "AIFF", _FakeAIFF)
    monkeypatch.setattr(CoverExtractor, "_extract_with_ffmpeg",
                        staticmethod(lambda p: None))

    img = CoverExtractor.extract_cover(str(tmp_path / "y.aiff"), is_url=False)

    assert img is not None
    assert img.size == (12, 8), img.size


# --- container routing -------------------------------------------------------
def test_oga_ext_routes_through_ogg_parser(tmp_path, monkeypatch,):
    (tmp_path / "z.oga").write_bytes(b"")
    seen = []
    monkeypatch.setattr(CoverExtractor, "_extract_with_ffmpeg",
                        staticmethod(lambda p: None))
    monkeypatch.setattr(CoverExtractor, "_extract_ogg_cover",
                        staticmethod(lambda p: seen.append(p) or None))

    CoverExtractor.extract_cover(str(tmp_path / "z.oga"), is_url=False)

    assert seen == [str(tmp_path / "z.oga")], "oga must hit the ogg branch"
