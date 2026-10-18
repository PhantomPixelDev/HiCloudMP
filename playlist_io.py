"""Playlist import/export engine: M3U/M3U8, PLS and XSPF.

Pure text work — no Qt, no network, no player coupling: the app wires this
into menus/drop events separately. Entries are plain dicts:

    {"path": str, "title": str|None, "duration": int|None}

"durations" are seconds (exact -1/None means unknown), mirroring M3U/PLS.
Local paths may be relative to the playlist file; import leaves them as
written (resolution is the caller's job), file: URIs are decoded, and
export relativizes an entry only when it lives under ``base_dir``.
"""
import os
from urllib.parse import quote, unquote, urlparse
from urllib.request import url2pathname
import xml.etree.ElementTree as ET

_M3U_EXTS = (".m3u", ".m3u8")


class PlaylistIO:
    """Import/export playlists in the three exchange formats."""

    @staticmethod
    def import_playlist(path):
        """Parse ``path``. Returns {"format": "m3u"|"pls"|"xspf",
        "path": path, "entries": [entry, ...]} in playlist order.
        Raises FileNotFoundError for a missing file and ValueError for an
        unsupported extension."""
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        ext = os.path.splitext(path)[1].lower()
        if ext in _M3U_EXTS:
            fmt, entries = "m3u", PlaylistIO._read_m3u(path)
        elif ext == ".pls":
            fmt, entries = "pls", PlaylistIO._read_pls(path)
        elif ext == ".xspf":
            fmt, entries = "xspf", PlaylistIO._read_xspf(path)
        else:
            raise ValueError("Unsupported playlist format: %s" % ext)
        return {"format": fmt, "path": path, "entries": entries}

    @staticmethod
    def export_playlist(path, entries, base_dir=None):
        """Write ``entries`` to ``path`` in the format its extension names.
        Returns the entry count written. Entries whose absolute path lies
        under ``base_dir`` are stored relative to it (album folders stay
        movable). Raises ValueError for an unknown extension."""
        ext = os.path.splitext(path)[1].lower()
        if ext not in _M3U_EXTS and ext not in (".pls", ".xspf"):
            raise ValueError("Unsupported playlist format: %s" % ext)
        rows = [PlaylistIO._entry_for_write(e) for e in entries]
        if ext == ".pls":
            text = PlaylistIO._pls_text(rows)
        elif ext == ".xspf":
            PlaylistIO._write_xspf(path, rows)
            return len(rows)
        else:
            text = PlaylistIO._m3u_text(rows, base_dir)
        enc = "utf-8"
        try:
            data = text.encode(enc)
        except UnicodeEncodeError:  # legacy .m3u consumers / ANSI systems
            data = text.encode("cp1252", errors="replace")
        with open(path, "wb") as fh:
            fh.write(data)
        return len(rows)

    # --- m3u ----------------------------------------------------------------
    @staticmethod
    def _read_m3u(path):
        # m3u8 promises utf-8; legacy .m3u falls back to cp1252 equipment
        with open(path, "rb") as fh:
            raw = fh.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        entries = []
        pending = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                if line.lower().startswith("#extinf:"):
                    pending = PlaylistIO._parse_extinf(line[8:])
                continue
            entries.append({"path": line,
                            "title": (pending or {}).get("title"),
                            "duration": (pending or {}).get("duration")})
            pending = None
        return entries

    @staticmethod
    def _parse_extinf(payload):
        # "#EXTINF:213,Artist - Title" (and friends): first comma splits
        dur_s, _, title = payload.partition(",")
        try:
            dur = int(dur_s.strip())
        except ValueError:
            dur = None
        return {"duration": dur if (dur is not None and dur >= 0) else None,
                "title": title.strip() or None}

    @staticmethod
    def _m3u_text(rows, base_dir):
        lines = ["#EXTM3U"]
        for row in rows:
            dur = row["duration"]
            lines.append("#EXTINF:%d,%s" % (dur if dur is not None else -1,
                                            row["title"] or ""))
            lines.append(PlaylistIO._stored_location(row["path"], base_dir))
        return "\n".join(lines) + "\n"

    @staticmethod
    def _stored_location(path, base_dir):
        """Relative-and-portable: a local file inside ``base_dir`` becomes
        forward-slash relative; URLs and outside paths stay verbatim."""
        if isinstance(path, str) and "://" not in path and base_dir:
            try:
                if os.path.isabs(path):
                    rel = os.path.relpath(path, base_dir)
                    if os.path.join(base_dir, rel) == os.path.normpath(path):
                        return rel.replace("\\", "/")
            except ValueError:
                pass
        return path

    # --- pls ----------------------------------------------------------------
    @staticmethod
    def _read_pls(path):
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8-sig", errors="replace")
        cols = {}
        for raw_line in text.splitlines():
            k, _, v = raw_line.partition("=")
            k = k.strip()
            if k.lower().startswith("file"):
                idx = k[4:].rstrip()
                cols.setdefault(idx, {}).update(
                    {"path": v.strip() if v else None})
            elif k.lower().startswith("title"):
                cols.setdefault(k[5:].rstrip(), {})["title"] = v.strip() or None
            elif k.lower().startswith("length"):
                idx = k[6:].rstrip()
                try:
                    dur = int(v.strip())
                except ValueError:
                    dur = None
                cols.setdefault(idx, {}).update(
                    {"duration": dur if (dur is not None and dur >= 0) else None})
        if "playlist" not in text[:64].lower():
            raise ValueError("Not a PLS playlist: %s" % path)
        rows = sorted(cols.items(), key=lambda kv: int(kv[0] or 0) if kv[0].isdigit() else 0)
        return [col for _, col in rows if col.get("path")]

    @staticmethod
    def _pls_text(rows):
        lines = ["[playlist]"]
        for i, row in enumerate(rows, 1):
            lines.append("File%d=%s" % (i, row["path"]))
            lines.append("Title%d=%s" % (i, row["title"] or ""))
            dur = row["duration"]
            lines.append("Length%d=%d" % (i, dur if dur is not None else -1))
        lines.append("NumberOfEntries=%d" % len(rows))
        lines.append("Version=2")
        return "\n".join(lines) + "\n"

    # --- xspf ---------------------------------------------------------------
    @staticmethod
    def _read_xspf(path):
        tree = ET.parse(path)  # raises ET.ParseError on malformed XML
        tracks = [el for el in tree.getroot().iter()
                  if el.tag.rsplit("}", 1)[-1] == "track"]
        entries = []
        for track in tracks:
            location = (track.findtext("{*}location") or "").strip()
            if not location:
                continue
            title = (track.findtext("{*}title") or "").strip() or None
            dur_ms = (track.findtext("{*}duration") or "").strip()
            try:
                dur = int(int(dur_ms) / 1000)
            except ValueError:
                dur = None
            entries.append({"path": PlaylistIO._location_to_path(location),
                            "title": title,
                            "duration": dur if (dur is not None and dur >= 0) else None})
        return entries

    @staticmethod
    def _location_to_path(location):
        if "://" in location:
            parsed = urlparse(location)
            if parsed.scheme in ("file", ""):
                local = unquote(url2pathname(parsed.path))
                return local.replace("\\", "/") if os.name == "nt" else local
        return unquote(location)

    @staticmethod
    def _write_xspf(path, rows):
        root = ET.Element("playlist",
                          {"xmlns": "http://xspf.org/ns/0/", "version": "1"})
        track_list = ET.SubElement(root, "trackList")
        for row in rows:
            track = ET.SubElement(track_list, "track")
            loc = ET.SubElement(track, "location")
            loc.text = PlaylistIO._location_for_write(row["path"])
            if row["title"]:
                ET.SubElement(track, "title").text = row["title"]
            if row["duration"] is not None:
                ET.SubElement(track, "duration").text = str(row["duration"] * 1000)
        with open(path, "wb") as fh:
            ET.ElementTree(root).write(fh, encoding="UTF-8", xml_declaration=True)

    @staticmethod
    def _location_for_write(path):
        if "://" in path:
            return path
        norm = path.replace("\\", "/") if os.name == "nt" else path
        return "file://" + quote("/" + norm.lstrip("/"), safe="/:~-._") if os.path.isabs(norm) else norm

    # --- shared -------------------------------------------------------------
    @staticmethod
    def _entry_for_write(entry):
        path = entry.get("path") or ""
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Playlist entry needs a usable path/URL: %r" % (entry,))
        return {"path": path,
                "title": entry.get("title") or None,
                "duration": entry.get("duration")
                if isinstance(entry.get("duration"), int) else None}
