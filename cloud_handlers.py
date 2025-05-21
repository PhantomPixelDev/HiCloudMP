import os
import concurrent.futures
import threading
from utils import is_music_file, SUPPORTED_EXTS

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
        self.current_file = ""  # Track current file being processed
        self.discovery_progress = 0  # Progress during discovery phase
        
    def scan(self):
        try:
            # Import here to avoid global dependency
            from webdav3.client import Client as WebDAVClient
            
            # Setup the client with more verbose error reporting
            client = WebDAVClient(self.config)
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
            
            # Process directories in parallel - increase worker count for better performance
            dir_count = len(all_dirs)
            dir_processed = 0
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_dir = {executor.submit(self._scan_directory, client, dir_path): dir_path for dir_path in all_dirs}
                
                # Also scan the root if not already included
                if "" not in all_dirs and "/" not in all_dirs:
                    future_to_dir[executor.submit(self._scan_directory, client, "")] = "/"
                    dir_count += 1
                
                all_files = []
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
        """Check if path is a directory with caching for performance"""
        if path in self._dir_cache:
            return self._dir_cache[path]
            
        try:
            result = client.is_dir(path)
            self._dir_cache[path] = result
            return result
        except Exception:
            self._dir_cache[path] = False
            return False
    
    def _discover_directories_with_progress(self, client, path, max_depth=10, depth=0):
        """Discover directories with progress updates"""
        if depth > max_depth:  # Prevent infinite recursion
            return []
            
        try:
            dirs = []
            norm_path = self._normalize_path(path)
            
            try:
                # Update status for better user feedback
                self.status_message = f"Discovering directories... Current path: {norm_path or '/'}"
                self.discovery_progress = min(50, self.discovery_progress + 1)  # Max 50% for discovery phase
                
                items = client.list(norm_path)
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
                        # Generate proper URL for the file
                        base_url = self.config["webdav_hostname"].rstrip("/")
                        file_url = f"{base_url}/{full_path}"
                        files.append({
                            "path": full_path,
                            "url": file_url
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

class DropboxHandler(CloudHandlerBase):
    """Handler for Dropbox cloud storage"""
    def __init__(self, config):
        super().__init__(config)
        self.debug = False  # Set to True only for debugging
        self._dir_cache = {}  # Cache for folder checks
        self.current_file = ""
        
    def scan(self):
        try:
            # Import here to avoid global dependency
            import dropbox
            
            dbx = dropbox.Dropbox(self.config["token"])
            self.files = []
            
            # Get all directories to scan first
            all_paths = self._discover_paths(dbx, "")
            self.total_items = len(all_paths) + 1  # +1 for root
            self.processed_items = 0
            self.status_message = "Scanning Dropbox directories..."
            
            # Process directories in parallel - increase worker count
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_path = {executor.submit(self._scan_path, dbx, path): path for path in all_paths}
                future_to_path[executor.submit(self._scan_path, dbx, "")] = "/"
                
                all_files = []
                for future in concurrent.futures.as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        path_files = future.result()
                        all_files.extend(path_files)
                        self.processed_items += 1
                        self.status_message = f"Scanned {self.processed_items}/{self.total_items} Dropbox directories..."
                    except Exception as e:
                        if self.debug: print(f"Error scanning Dropbox path {path}: {e}")
            
            self.files = all_files
            self.status_message = f"Dropbox scan complete. Found {len(self.files)} music files."
            
        except Exception as e:
            error_msg = f"Dropbox scan error: {str(e)}"
            self.status_message = error_msg
            print(error_msg)
            raise Exception(error_msg)
    
    def _discover_paths(self, dbx, path):
        """Discover all paths in Dropbox account"""
        try:
            paths = []
            try:
                results = dbx.files_list_folder(path)
            except Exception as e:
                if self.debug: print(f"Error listing Dropbox path {path}: {e}")
                return []
            
            for entry in results.entries:
                if isinstance(entry, dropbox.files.FolderMetadata):
                    folder_path = entry.path_display
                    paths.append(folder_path)
                    # Store in cache
                    self._dir_cache[folder_path] = True
                    
                    # Get subfolders
                    subpaths = self._discover_paths(dbx, folder_path)
                    paths.extend(subpaths)
            
            return paths
        except Exception as e:
            if self.debug: print(f"Error discovering Dropbox paths for {path}: {e}")
            return []
    
    def _scan_path(self, dbx, path):
        """Scan a single Dropbox path for music files"""
        try:
            files = []
            try:
                results = dbx.files_list_folder(path)
            except Exception as e:
                if self.debug: print(f"Error listing Dropbox path {path}: {e}")
                return []
            
            for entry in results.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    # Fast check for music file extensions
                    if any(entry.name.lower().endswith(ext) for ext in SUPPORTED_EXTS):
                        files.append({
                            "path": entry.path_display,
                            "url": f"https://content.dropboxapi.com/2/files/download?authorization=Bearer {self.config['token']}&arg={{'path':'{entry.path_display}'}}"
                        })
            
            return files
        except Exception as e:
            if self.debug: print(f"Error scanning Dropbox path {path}: {e}")
            return []

# Stubs for Google Drive, OneDrive
class GoogleDriveHandler(CloudHandlerBase):
    def scan(self):
        self.files = []  # TODO: Implement

class OneDriveHandler(CloudHandlerBase):
    def scan(self):
        self.files = []  # TODO: Implement

# Dictionary mapping cloud types to their handler classes
CLOUD_TYPES = {
    "webdav": WebDAVHandler,
    "dropbox": DropboxHandler,
    "gdrive": GoogleDriveHandler,
    "onedrive": OneDriveHandler
} 