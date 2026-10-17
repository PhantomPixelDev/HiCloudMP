import os
import sys

# Supported file extensions
SUPPORTED_EXTS = [".mp3", ".flac", ".wav", ".ogg"]

from platformdirs import user_data_dir

# Get application data directory
app_name = "HiCloudMP"
app_author = "HiCloudMP"
data_dir = user_data_dir(app_name, app_author, ensure_exists=True)

# File paths for configuration
MEDIA_FOLDERS_FILE = os.path.join(data_dir, "mediafolders.json")
CLOUD_FILES_FILE = os.path.join(data_dir, "cloudfiles.json")
PLAYLISTS_FILE = os.path.join(data_dir, "playlists.json")

# Windows platform flag (pywin32 removed along with the dead media-key
# handler it fed — nothing imports pywin32 anymore)
HAS_WIN32 = (sys.platform == 'win32')

def is_music_file(path):
    """Check if a file is a supported music file based on extension"""
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTS

def scan_music_files(folder):
    """Recursively scan a folder for music files"""
    files = []
    for root, _, filenames in os.walk(folder):
        for f in filenames:
            if is_music_file(f):
                files.append(os.path.join(root, f))
    return files

def format_time(ms):
    """Convert milliseconds to mm:ss format"""
    total_seconds = round(ms / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}" 