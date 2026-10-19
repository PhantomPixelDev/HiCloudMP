"""Cloud metadata display must never block the UI on a network probe.

Subsonic scan rows carry the track title as `name` (the API title field is
stored there), with artist/album already populated. The display code treated
the empty `title` field as missing metadata and ran ffprobe against the
stream on the UI thread: ~0.8 s of freeze on every cloud track change.
"""
import time


def _cloud_item(**overrides):
    item = {
        "type": "cloud",
        "name": "Glock 40 (Radio Edit)",
        "artist": "Various Artists",
        "album": "Unknown album",
    }
    item.update(overrides)
    return item


def test_cloud_track_uses_scan_name_without_a_blocking_probe(
        music_player, monkeypatch):
    import metadata as metadata_mod

    calls = []

    def fake_extract(*args, **kwargs):
        calls.append((args, kwargs))
        time.sleep(1.0)          # a real remote ffprobe is slower than this
        return {"title": "From the network"}

    monkeypatch.setattr(metadata_mod.CoverExtractor, "extract_metadata",
                        staticmethod(fake_extract))
    mp = music_player
    mp.playlist = [_cloud_item()]
    mp.current_index = 0

    started = time.perf_counter()
    mp.meta.update_metadata_display()
    elapsed = time.perf_counter() - started

    assert calls == [], "cloud metadata must not be probed on the UI thread"
    assert elapsed < 0.5, f"display blocked for {elapsed:.2f}s"
    assert "Glock 40 (Radio Edit)" in mp.track_title_label.text()
    assert "Various Artists" in mp.track_artist_label.text()
    assert "Unknown album" in mp.track_album_label.text()


def test_cloud_track_falls_back_to_path_basename(music_player, monkeypatch):
    import metadata as metadata_mod

    calls = []
    monkeypatch.setattr(
        metadata_mod.CoverExtractor, "extract_metadata",
        staticmethod(lambda *a, **k: calls.append(1) or {}))

    mp = music_player
    mp.playlist = [{
        "type": "cloud",
        "path": "Music/Some Artist/Some Album/Track Name.flac",
        "artist": "",
        "album": "",
    }]
    mp.current_index = 0
    mp.meta.update_metadata_display()

    assert calls == []
    assert "Track Name" in mp.track_title_label.text()
    assert "Unknown Artist" in mp.track_artist_label.text()
    assert "Unknown Album" in mp.track_album_label.text()


def test_explicit_title_still_wins(music_player):
    mp = music_player
    mp.playlist = [_cloud_item(title="Real Title")]
    mp.current_index = 0
    mp.meta.update_metadata_display()
    assert "Real Title" in mp.track_title_label.text()


def test_index_only_cloud_item_resolves_metadata_from_scan_row(
        music_player, monkeypatch):
    """Queue rows built by the library only carry account/file indices.

    The scanned cloud row is the metadata cache: displaying the now-playing
    labels must resolve it instead of falling back to Unknown, without any
    network probe or rescan.
    """
    mp = music_player
    monkeypatch.setattr(mp.meta, "_start_cover_art_fetch",
                        lambda *a, **k: None)
    mp.clouds = [{"name": "Test Cloud", "config": {}, "files": [{
        "path": "Real Artist/Real Album/internal-id.flac",
        "url": "https://s/stream?x=1",
        "name": "Real Song",
        "artist": "Real Artist",
        "album": "Real Album",
    }]}]
    mp.playlist = [{"type": "cloud", "cloud_idx": 0, "file_idx": 0}]
    mp.current_index = 0

    mp.meta.update_metadata_display()

    assert "Real Song" in mp.track_title_label.text()
    assert "Real Artist" in mp.track_artist_label.text()
    assert "Real Album" in mp.track_album_label.text()


def test_resolved_cloud_metadata_is_cached_on_the_playlist_item(
        music_player, monkeypatch):
    """A resolved queue row keeps its metadata for later displays.

    Playlist rows are displayed repeatedly (track changes, tray refreshes,
    web-state pushes). Caching the resolved values on the row avoids repeat
    catalog lookups and keeps labels intact if the catalog is unavailable.
    """
    mp = music_player
    monkeypatch.setattr(mp.meta, "_start_cover_art_fetch",
                        lambda *a, **k: None)
    mp.clouds = [{"name": "Test Cloud", "config": {}, "files": [{
        "path": "Real Artist/Real Album/internal-id.flac",
        "url": "https://s/stream?x=1",
        "name": "Real Song",
        "artist": "Real Artist",
        "album": "Real Album",
    }]}]
    item = {"type": "cloud", "cloud_idx": 0, "file_idx": 0}
    mp.playlist = [item]
    mp.current_index = 0

    mp.meta.update_metadata_display()
    mp.clouds = []  # catalog unavailable: the queue row is the cache
    mp.meta.update_metadata_display()

    assert item.get("title") == "Real Song"
    assert item.get("artist") == "Real Artist"
    assert item.get("album") == "Real Album"
    assert "Real Song" in mp.track_title_label.text()
    assert "Real Artist" in mp.track_artist_label.text()
    assert "Real Album" in mp.track_album_label.text()
