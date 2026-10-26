import hashlib
import os
import secrets
import concurrent.futures
import threading
from hicloudmp.utils import is_music_file, SUPPORTED_EXTS

# --- Cloud Handlers ---
class CloudHandlerBase:
    """Base class for cloud storage handlers"""
    def __init__(self, config):
        self.config = config
        self.files = []
        # For progress reporting
        self.total_items = 0
        self.processed_items = 0
        self.status_message = ""
    
    def scan(self):
        raise NotImplementedError
        
    def get_links(self):
        return self.files
        
    def get_progress(self):
        # During directory discovery, use discovery_progress
        if hasattr(self, 'discovery_progress') and self.discovery_progress > 0:
            return self.discovery_progress
            
        # Normal calculation during scanning phase
        if self.total_items > 0:
            progress = (self.processed_items / self.total_items) * 100
            return progress
        return 0
        
    def get_status(self):
        # Include current file in status if available
        if hasattr(self, 'current_file') and self.current_file:
            return f"{self.status_message} | File: {self.current_file}"
        return self.status_message

class WebDAVHandler(CloudHandlerBase):
    """Handler for WebDAV cloud storage"""
    def __init__(self, config):
        super().__init__(config)
        self.debug = False  # Set to True only for debugging
        self._dir_cache = {}  # Cache for is_dir checks
        self._list_cache = {}  # Cache for directory listings
        self.current_file = ""  # Track current file being processed
        self.discovery_progress = 0  # Progress during discovery phase
        self._client = None  # Cached client instance
        self._session = None  # For connection reuse
        self._lock = threading.Lock()  # Thread safety for shared resources

    def _get_client(self):
        """Get or create a WebDAV client with optimized settings"""
        if self._client is None:
            from webdav3.client import Client as WebDAVClient
            
            # Configure client with optimized settings
            client_options = {
                'webdav_hostname': self.config.get('webdav_hostname'),
                'webdav_login': self.config.get('webdav_login', ''),
                'webdav_password': self.config.get('webdav_password', ''),
                'webdav_root': self.config.get('webdav_root', '/'),
                'webdav_timeout': 30,  # 30 seconds timeout
                'webdav_verbose': self.debug,
                'webdav_override_methods': {
                    'check': 'GET',  # Use GET for checking existence (lighter than PROPFIND)
                },
                'webdav_headers': {
                    'Connection': 'keep-alive',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            }
            self._client = WebDAVClient(client_options)
            
            # Enable session reuse
            if self._session is None:
                import requests
                self._session = requests.Session()
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=10,
                    pool_maxsize=10,
                    max_retries=3
                )
                self._session.mount('http://', adapter)
                self._session.mount('https://', adapter)
                self._client.session = self._session
                
        return self._client

    def scan(self):
        try:
            client = self._get_client()
            self.files = []
            
            # Test the connection first
            try:
                self.status_message = f"Testing connection to {self.config['webdav_hostname']}..."
                if self.debug: print(f"Testing WebDAV connection to: {self.config['webdav_hostname']}")
                client.check("")
                if self.debug: print("WebDAV connection successful!")
            except Exception as conn_err:
                error_msg = f"WebDAV connection error: {str(conn_err)}"
                print(error_msg)
                self.status_message = error_msg
                raise Exception(error_msg)
            
            # Split the scan into two phases:
            # Phase 1: Discovering directories (50% of progress)
            self.total_items = 2  # Two phases: discovery and scanning
            self.processed_items = 0
            self.status_message = "Phase 1/2: Discovering directories..."
            
            # Discover all directories with progress updates
            all_dirs = self._discover_directories_with_progress(client, "")
            
            # Update progress - we're 50% done after directory discovery
            self.processed_items = 1
            
            if not all_dirs:
                # If no directories found, we're only scanning root
                all_dirs = [""]
            
            # Phase 2: Scanning for files (remaining 50% of progress)
            self.status_message = f"Phase 2/2: Scanning {len(all_dirs)} directories for music files..."
            
            # Process directories in parallel with optimized worker count
            max_workers = min(32, (os.cpu_count() or 4) * 4)
            dir_count = len(all_dirs)
            dir_processed = 0
            
            # Process directories in batches to avoid too many concurrent connections
            batch_size = max(10, max_workers * 2)
            all_files = []
            
            for i in range(0, len(all_dirs), batch_size):
                batch = all_dirs[i:i + batch_size]
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_dir = {executor.submit(self._scan_directory, client, dir_path): dir_path for dir_path in batch}
                    
                    # Also scan the root if not already included
                    if "" not in all_dirs and "/" not in all_dirs:
                        future_to_dir[executor.submit(self._scan_directory, client, "")] = "/"
                        dir_count += 1
                    
                    for future in concurrent.futures.as_completed(future_to_dir):
                        dir_path = future_to_dir[future]
                        try:
                            dir_files = future.result()
                            all_files.extend(dir_files)
                            dir_processed += 1
                            
                            # Calculate the exact progress
                            # Phase 1 was 50%, phase 2 is the other 50%
                            # Within phase 2, each directory is equal weight
                            phase2_progress = (dir_processed / dir_count) * 50
                            overall_progress = 50 + phase2_progress
                            
                            self.status_message = f"Scanning directory {dir_processed}/{dir_count}: {dir_path}"
                            
                            # Force progress update
                            self.discovery_progress = overall_progress
                        except Exception as e:
                            if self.debug: print(f"Error scanning directory {dir_path}: {e}")
            
            self.files = all_files
            # Explicitly set to 100% when done
            self.discovery_progress = 100.0
            self.processed_items = 2  # Both phases complete
            self.status_message = f"WebDAV scan complete. Found {len(self.files)} music files."
            if self.debug: print(self.status_message)
            
        except Exception as e:
            detailed_error = f"WebDAV scan failed: {str(e)}\n"
            detailed_error += f"Server: {self.config.get('webdav_hostname', 'N/A')}\n"
            detailed_error += f"Username: {self.config.get('webdav_login', 'N/A')}"
            print(detailed_error)
            self.status_message = detailed_error
            raise Exception(detailed_error)
    
    def _normalize_path(self, path):
        """Normalize WebDAV path to prevent duplicates"""
        # Fast normalization for common cases
        if not path or path == "/":
            return ""
            
        # Remove leading/trailing slashes and fix double slashes
        path = path.strip('/')
        return path.replace('//', '/')
    
    def _join_path(self, base, child):
        """Safely join WebDAV paths"""
        if not base:
            return child
        if not child:
            return base
        
        return f"{base}/{child}"
    
    def _is_dir(self, client, path):
        """Check if path is a directory with caching and optimized checking"""
        with self._lock:
            if path in self._dir_cache:
                return self._dir_cache[path]
                
            try:
                # First check if we have this path in our list cache
                parent = os.path.dirname(path)
                if parent in self._list_cache:
                    for item in self._list_cache[parent]:
                        item_path = self._join_path(parent, item)
                        if item_path == path:
                            is_dir = client.is_dir(path)
                            self._dir_cache[path] = is_dir
                            return is_dir
                
                # If not in cache, do a direct check with timeout
                result = client.is_dir(path)
                self._dir_cache[path] = result
                return result
            except Exception as e:
                if self.debug:
                    print(f"Error checking if {path} is directory: {e}")
                self._dir_cache[path] = False
                return False

    def _discover_directories_with_progress(self, client, path, max_depth=10, depth=0):
        """Discover directories with progress updates and optimized listing"""
        if depth > max_depth:  # Prevent infinite recursion
            return []
            
        try:
            dirs = []
            norm_path = self._normalize_path(path)
            
            # Check cache first
            with self._lock:
                if norm_path in self._list_cache:
                    items = self._list_cache[norm_path]
                else:
                    # Update status for better user feedback
                    self.status_message = f"Discovering directories... Current path: {norm_path or "/"}"
                    self.discovery_progress = min(50, self.discovery_progress + 1)
                    
                    try:
                        items = client.list(norm_path)
                        self._list_cache[norm_path] = items  # Cache the result
                    except Exception as e:
                        if self.debug: print(f"Error listing directory '{path}': {e}")
                        return []
            
            # Count potential subdirectories first
            subdirs_to_process = []
            for item in items:
                if item in (".", ".."):
                    continue
                
                full_path = self._join_path(norm_path, item)
                
                try:
                    if self._is_dir(client, full_path):
                        dirs.append(full_path)
                        subdirs_to_process.append(full_path)
                except Exception as e:
                    if self.debug: print(f"Error checking directory '{full_path}': {e}")
            
            # Process each subdirectory and update progress
            for i, subdir in enumerate(subdirs_to_process):
                # Update progress for this level
                progress_increment = 25.0 / (len(subdirs_to_process) + 1) / (depth + 1)
                self.discovery_progress = min(50, self.discovery_progress + progress_increment)
                self.status_message = f"Discovering directories... Level {depth+1}: {i+1}/{len(subdirs_to_process)}"
                
                # Recursively get subdirectories
                subdirs = self._discover_directories_with_progress(client, subdir, max_depth, depth + 1)
                dirs.extend(subdirs)
            
            return dirs
        except Exception as e:
            if self.debug: print(f"Error in directory discovery for '{path}': {e}")
            return []
    
    def _scan_directory(self, client, path):
        """Scan a single directory for music files"""
        try:
            files = []
            norm_path = self._normalize_path(path)
            
            try:
                items = client.list(norm_path)
            except Exception as e:
                if self.debug: print(f"Error listing directory '{path}': {e}")
                return []
            
            for item in items:
                if item in (".", ".."):
                    continue
                
                # Only process potential music files based on extension
                if not any(item.lower().endswith(ext) for ext in SUPPORTED_EXTS):
                    continue
                
                full_path = self._join_path(norm_path, item)
                
                # Update current file for status updates
                self.current_file = item
                
                try:
                    # Check if it's a directory first - skip directories
                    if self._is_dir(client, full_path):
                        continue
                    
                    # Only process music files
                    if is_music_file(item):
                        # Generate proper URL for the file. webdav_root is the
                        # path scope the DAV client operates in (e.g.
                        # /remote.php/dav/files/Admin); the static file URL must
                        # carry it or the player's GET 404s.
                        base_url = self.config["webdav_hostname"].rstrip("/")
                        root = (self.config.get("webdav_root") or "/").strip("/")
                        if root and not base_url.endswith(root):
                            base_url = f"{base_url}/{root}"
                        file_url = f"{base_url}/{full_path}"
                        
                        # Extract basic metadata from filename
                        name = os.path.splitext(os.path.basename(full_path))[0]
                        
                        # Try to extract artist and album from path if possible
                        path_parts = full_path.split('/')
                        artist = 'Unknown Artist'
                        album = 'Unknown Album'
                        
                        # Common pattern: /Artist/Album/Track - Title.ext
                        if len(path_parts) >= 3:
                            artist = path_parts[-3]  # Second to last part is often artist
                            album = path_parts[-2]   # Third to last part is often album
                        elif len(path_parts) == 2:
                            artist = path_parts[-2]  # If only one level deep, use that as artist
                        
                        files.append({
                            "path": full_path,
                            "url": file_url,
                            "name": name,
                            "artist": artist,
                            "album": album
                        })
                except Exception as e:
                    if self.debug: print(f"Error processing file '{full_path}': {e}")
            
            # Clear current file when done with directory
            self.current_file = ""
            return files
        except Exception as e:
            if self.debug: print(f"Error scanning directory '{path}': {e}")
            self.current_file = ""
            return []


# Dictionary mapping cloud types to their handler classes
CLOUD_TYPES = {
    "webdav": WebDAVHandler,
    "ampache": None,   # replaced below; import-time registration keeps all in one module
    "subsonic": None,
}

import time
import urllib.parse
import xml.etree.ElementTree as ET
import requests

_AMPACHE_API_TIMEOUT = (10, 30)


class _HTTPCloudHandler(CloudHandlerBase):
    """Shared plumbing for HTTP catalog APIs (Ampache / Subsonic)."""

    def __init__(self, config):
        super().__init__(config)
        self.total_items = 0
        self.processed_items = 0

    def _http_get(self, url, params=None, timeout=_AMPACHE_API_TIMEOUT):
        return requests.get(url, params=params, timeout=timeout)

    def _add_song(self, path_extra=None, path=None, url=None, name="",
                  artist="", album="", cover_url=None):
        entry = {"path": path or "", "url": url or "", "name": name,
                 "artist": artist or "Unknown Artist",
                 "album": album or "Unknown Album"}
        if cover_url:
            entry["cover_url"] = cover_url
        if path_extra:
            entry.update(path_extra)
        self.files.append(entry)


class AmpacheHandler(_HTTPCloudHandler):
    """Ampache-compatible API (Nextcloud Music app and Ampache itself).

    Auth: auth = SHA256(timestamp + SHA256(password)) with user + timestamp
    params — the passphrase construction used by Nextcloud Music (verified
    empirically against the user's instance; also valid for Ampache >= v5).
    """

    def __init__(self, config):
        super().__init__(config)
        self.token = None
        self.endpoint = config.get("ampache_url", "").rstrip("/")
        if self.endpoint and not self.endpoint.endswith("server/xml.server.php"):
            self.endpoint += "/server/xml.server.php"

    def scan(self):
        self.files = []
        self.status_message = "Connecting to Ampache..."
        if not self.endpoint:
            raise Exception("Ampache URL is not configured")

        # --- handshake: sha256(sha256(password) + timestamp) ---
        ts = str(int(time.time()))
        key = hashlib.sha256(self.config.get("ampache_password", "").encode()).hexdigest()
        passphrase = hashlib.sha256((ts + key).encode()).hexdigest()
        resp = self._http_get(self.endpoint, params={
            "action": "handshake", "auth": passphrase, "user": self.config.get("ampache_user", ""),
            "timestamp": ts, "version": "6", "client": "HiCloudMP",
        })
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        token_el = root.find("./auth")
        if token_el is None:
            err = root.find("./error/errorMessage")
            msg = err.text if err is not None else "handshake failed"
            raise Exception(f"Ampache handshake failed: {msg}")
        self.token = token_el.text
        self._api_params = {"auth": self.token, "user": self.config.get("ampache_user", "")}

        # --- paginate the catalog ---
        limit = 1000
        offset = 0
        while True:
            r = self._http_get(self.endpoint, params={
                "action": "songs", "limit": limit, "offset": offset, **self._api_params,
            })
            r.raise_for_status()
            sroot = ET.fromstring(r.text)
            songs = sroot.findall("./song")
            if not songs:
                break
            for s in songs:
                # <url> carries a ready-to-use stream URL (action=stream)
                url = s.findtext("./url") or ""
                if url and not url.strip():
                    url = ""
                title = s.findtext("./title") or "Untitled"
                artist = (s.findtext("./artist/name") or
                          s.findtext("./artist") or "Unknown Artist")
                album = (s.findtext("./album/name") or
                         s.findtext("./album") or "Unknown Album")
                album_el = s.find("./album")
                album_id = album_el.get("id") if album_el is not None else None
                # Dedicated artwork: <art> URL when the server provides one, else
                # Ampache get_art on the album with the session token.
                art_url = s.findtext("./art") or ""
                if not art_url and album_id:
                    art_url = (self.endpoint + "?" + urllib.parse.urlencode({
                        "action": "get_art", "auth": self.token, "type": "album",
                        "id": album_id, "size": 480, "client": "HiCloudMP",
                    }))
                path = f"{artist}/{album}/{title}"
                self._add_song(path=path, url=url, name=title, artist=artist, album=album,
                               cover_url=art_url or None)
                self.processed_items += 1
                self.current_file = title
                self.status_message = f"Ampache: fetched {self.processed_items} songs"
            if len(songs) < limit:
                break
            offset += limit

        self.status_message = f"Ampache scan complete. Found {len(self.files)} songs."

    def get_links(self):
        return [f for f in self.files if f.get("url")]


class SubsonicHandler(_HTTPCloudHandler):
    """Subsonic-compatible API (Nextcloud Music app "Subsonic" address).

    Auth: token auth (t=md5(password+salt), s=salt, fresh salt per
    request) is the wire default. Servers without token support answer
    Subsonic error 41 "Token authentication not supported" - Nextcloud
    Music does, verified on the user's instance - and the session
    silently falls back to legacy u/p auth after the first such ping.
    """

    _API_VERSION = "1.16.1"
    _CLIENT = "HiCloudMP"

    def __init__(self, config):
        super().__init__(config)
        base = config.get("subsonic_url", "").rstrip("/")
        self.rest_base = base if base.endswith("/rest") else base + "/rest"
        self._token_auth = True

    def _auth_params(self):
        user = self.config.get("subsonic_user", "")
        if self._token_auth:
            salt = secrets.token_hex(6)
            token = hashlib.md5(
                (self.config.get("subsonic_password", "") + salt)
                .encode("utf-8")).hexdigest()
            return {"u": user, "t": token, "s": salt}
        return {"u": user, "p": self.config.get("subsonic_password", "")}

    def _common_params(self):
        return {**self._auth_params(),
                "v": self._API_VERSION, "c": self._CLIENT, "f": "json"}

    def _get_json(self, endpoint, **extra):
        params = {**self._common_params(), **extra}
        r = self._http_get(f"{self.rest_base}/{endpoint}", params=params)
        r.raise_for_status()
        return r.json().get("subsonic-response", {})

    def scan(self):
        self.files = []
        self.status_message = "Connecting to Subsonic..."
        ping = self._get_json("ping.view")
        if ping.get("status") != "ok":
            err = ping.get("error") or {}
            if self._token_auth and err.get("code") == 41:
                # Token auth unsupported (Nextcloud Music & friends):
                # stay on legacy u/p auth for the whole session.
                self._token_auth = False
                ping = self._get_json("ping.view")
                if ping.get("status") != "ok":
                    raise Exception(f"Subsonic ping failed: {ping}")
            else:
                raise Exception(f"Subsonic ping failed: {ping}")

        # albums, paged
        albums = []
        offset = 0
        size = 500
        while True:
            data = self._get_json("getAlbumList2.view", type="alphabeticalByName",
                                  size=size, offset=offset)
            page = data.get("albumList2", {}).get("album", [])
            if not page:
                break
            albums.extend(page)
            if len(page) < size:
                break
            offset += size

        self.total_items = len(albums) or 1

        # Fetch album song lists concurrently — sequential one-request-per-album
        # made scans take minutes on big libraries; a bounded pool cuts this to
        # roughly one "page" of round trips. Results stay in catalog order.
        fetch_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)

        def _fetch_album(payload):
            i, alb = payload
            try:
                album_data = self._get_json("getAlbum.view", id=alb.get("id"))
            except Exception:
                return i, []
            return i, album_data.get("album", {}).get("song", [])

        try:
            for i, songs in fetch_pool.map(_fetch_album, enumerate(albums)):
                alb = albums[i]
                artist = alb.get("artist") or "Unknown Artist"
                album_name = alb.get("name") or "Unknown Album"
                for s in songs:
                    title = s.get("title") or "Untitled"
                    stream_id = s.get("id")
                    url = (f"{self.rest_base}/stream.view?"
                           + urllib.parse.urlencode({**self._common_params(), "id": stream_id}))
                    # Nextcloud Music / Subsonic servers expose artwork at
                    # getCoverArt.view; a direct image URL avoids re-downloading
                    # (and re-decoding) the whole track for its embedded art.
                    cover_id = s.get("coverArt") or alb.get("coverArt") or ""
                    cover_url = ""
                    if cover_id:
                        cover_url = (f"{self.rest_base}/getCoverArt.view?"
                                     + urllib.parse.urlencode({**self._common_params(),
                                                               "id": cover_id}))
                    self._add_song(
                        path=f"{artist}/{album_name}/{title}", url=url,
                        name=title, artist=artist, album=album_name,
                        cover_url=cover_url or None)
                self.processed_items = i + 1
                self.current_file = album_name
                self.status_message = (f"Subsonic: {len(self.files)} tracks "
                                       f"({i + 1}/{len(albums)} albums)")
        finally:
            fetch_pool.shutdown(wait=False)

        self.status_message = f"Subsonic scan complete. Found {len(self.files)} songs."

    def get_links(self):
        return [f for f in self.files if f.get("url")]


CLOUD_TYPES["ampache"] = AmpacheHandler
CLOUD_TYPES["subsonic"] = SubsonicHandler