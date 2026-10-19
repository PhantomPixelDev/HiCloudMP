"""Recently / Most Played play history (mixin).

The data lives in play_history.json next to the other user data. Recording
dedups (a re-play moves to the front), counts feed Most Played, the recent
list is capped, and a corrupt file is simply an empty history.
"""
import json
import os

from PySide6.QtCore import QSettings  # noqa: F401  (kept for patch parity)

from utils import atomic_write_text

# Last N entries kept; menus show the top 15.
HISTORY_LIMIT = 50


class PlayHistoryMixin:
    """Requires on the mixing class: data_dir, playlist/current_index,
    playlist_widget, status_bar, play(), recent_menu, most_menu."""

    def _history_path(self):
        return os.path.join(self.data_dir, "play_history.json")

    def _load_play_history(self):
        """Corrupt or missing history is simply an empty history."""
        try:
            with open(self._history_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            recent = [p for p in data.get("recent", [])
                      if isinstance(p, str)]
            counts = {}
            for key, value in (data.get("counts") or {}).items():
                try:
                    counts[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
            names = {}
            for key, value in (data.get("names") or {}).items():
                if isinstance(value, str):
                    names[str(key)] = value
            return {"recent": recent[:HISTORY_LIMIT],
                    "counts": counts, "names": names}
        except Exception:
            return {"recent": [], "counts": {}, "names": {}}

    def _save_play_history(self):
        try:
            atomic_write_text(self._history_path(),
                              json.dumps(self._history, ensure_ascii=False,
                                         indent=1))
        except Exception:
            pass

    def _history_key(self, item):
        if isinstance(item, dict) and item.get("type") == "cloud":
            return f"cloud:{item.get('cloud_idx')}:{item.get('file_idx')}"
        if isinstance(item, str):
            return item
        return None

    def _cloud_row_for_key(self, key):
        """Resolve a 'cloud:<idx>:<file>' key against the in-memory catalog.

        Queue rows and history entries only persist account/file indices;
        the scanned cloud row (loaded with the app, never a network call)
        is the metadata cache. Returns None when the row no longer exists.
        """
        try:
            parts = key.split(":")
            if len(parts) < 3 or parts[0] != "cloud":
                return None
            cloud_idx = int(parts[1])
            file_idx = int(parts[2])
            clouds = getattr(self, "clouds", None) or []
            if not (0 <= cloud_idx < len(clouds)):
                return None
            cloud = clouds[cloud_idx]
            if not isinstance(cloud, dict):
                return None
            files = cloud.get("files") or []
            if not (0 <= file_idx < len(files)):
                return None
            row = files[file_idx]
            return row if isinstance(row, dict) else None
        except Exception:
            return None

    def _cloud_display(self, row):
        """Human label for a catalog row: 'Artist – Title' (or title only)."""
        try:
            if not isinstance(row, dict):
                return None
            title = row.get("title") or row.get("name")
            if not title:
                path = row.get("path")
                if path:
                    title = os.path.splitext(os.path.basename(str(path)))[0]
            artist = row.get("artist") or ""
            title = str(title) if title else None
            if title and row.get("artist"):
                return f"{artist} – {title}"
            return title
        except Exception:
            return None

    def record_play(self, item=None):
        """Track a started play for Recently/Most Played: re-plays move to
        the front, counts accumulate, the list is capped. Cloud entries are
        named from the catalog row so menus show real song names."""
        try:
            if item is None:
                if not (0 <= self.current_index < len(self.playlist)):
                    return
                item = self.playlist[self.current_index]
            key = self._history_key(item)
            if not key:
                return
            row = self._cloud_row_for_key(key) \
                if isinstance(item, dict) else None
            if isinstance(item, dict):
                name = (self._cloud_display(row)
                        or self._dict_item_display(item)
                        or key)
            else:
                name = os.path.basename(str(item).split("?", 1)[0].rstrip("/"))
                name = name or str(item)
            recent = [k for k in self._history.get("recent", []) if k != key]
            recent.insert(0, key)
            self._history["recent"] = recent[:HISTORY_LIMIT]
            counts = self._history.setdefault("counts", {})
            counts[key] = int(counts.get(key, 0)) + 1
            self._history.setdefault("names", {})[key] = str(name)
            self._save_play_history()
        except Exception:
            pass

    @staticmethod
    def _dict_item_display(item):
        """Label from fields cached on the queue row itself (catalog first,
        then whatever the row already carries)."""
        try:
            if not isinstance(item, dict):
                return None
            title = item.get("title") or item.get("name")
            if not title:
                return None
            artist = item.get("artist")
            if artist:
                return f"{artist} – {title}"
            return str(title)
        except Exception:
            return None

    def _history_display(self, key):
        try:
            names = self._history.get("names") or {}
            name = names.get(key)
            if name and name != key:
                return name
            if key.startswith("cloud:"):
                # Legacy entries stored the raw key as the "name": repair on
                # display from the catalog row (names stay untouched on disk
                # and heal on the next play of the same track).
                resolved = self._cloud_display(self._cloud_row_for_key(key))
                if resolved:
                    return resolved
                return key
            return os.path.basename(str(key).split("?", 1)[0].rstrip("/")) \
                or str(key)
        except Exception:
            return str(key)

    def _fill_history_menu(self, menu, keys, with_counts=False):
        menu.clear()
        if not keys:
            empty = menu.addAction("Nothing played yet")
            empty.setEnabled(False)
            return
        for key in keys[:15]:
            label = self._history_display(key)
            if with_counts:
                label = f"{label}  ({self._history['counts'].get(key, 0)})"
            act = menu.addAction(label)
            act.triggered.connect(
                lambda _checked=False, k=key: self._play_history_entry(k))

    def _rebuild_recent_menu(self):
        self._fill_history_menu(
            self.recent_menu, self._history.get("recent", []))

    def _rebuild_most_menu(self):
        counts = self._history.get("counts") or {}
        ranked = sorted(
            counts.items(),
            key=lambda kv: (-kv[1], self._history_display(kv[0]).lower()))
        self._fill_history_menu(self.most_menu, [k for k, _ in ranked],
                                with_counts=True)

    def _play_history_entry(self, key):
        """Replay a history row: reuse its queue slot when present, append
        otherwise. Missing local files report instead of failing silently."""
        try:
            if key.startswith("cloud:"):
                for i, item in enumerate(self.playlist):
                    if self._history_key(item) == key:
                        self.current_index = i
                        self.play()
                        return
                self.status_bar.showMessage(
                    "Track is not in the current queue", 3000)
                return
            is_url = key.startswith(("http://", "https://"))
            if not is_url and not os.path.exists(key):
                self.status_bar.showMessage(
                    "File no longer exists: " + os.path.basename(key), 4000)
                return
            try:
                idx = self.playlist.index(key)
            except ValueError:
                self.playlist.append(key)
                if is_url:
                    label = (os.path.basename(key.split("?", 1)[0].rstrip("/"))
                             or key) + " (Stream)"
                else:
                    label = os.path.basename(key)
                self.playlist_widget.addItem(label)
                idx = len(self.playlist) - 1
            self.current_index = idx
            self.play()
        except Exception:
            pass
