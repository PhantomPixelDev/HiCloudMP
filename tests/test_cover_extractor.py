

def test_ffprobe_metadata_path_is_gone():
    """The packaged build never shipped ffprobe.exe, so extract_metadata()
    (ffprobe-based, zero callers) was a silent no-op at best. The
    metadata path lives in the scan worker's mutagen tags now; the
    extractor must not drift back to spawning a missing binary."""
    from hicloudmp.core.cover_extractor import CoverExtractor
    assert not hasattr(CoverExtractor, "extract_metadata")
