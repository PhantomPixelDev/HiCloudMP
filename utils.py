import os
import sys
import subprocess

# Supported file extensions — the ONE list for scanning, dialogs and
# cloud ingestion; the ffmpeg-backed Qt player decodes all of these.
SUPPORTED_EXTS = [".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus",
                  ".m4a", ".mp4", ".aac", ".wma", ".aiff", ".aif", ".mka"]

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


def atomic_write_text(path, text):
    """Write text to path atomically: write a .tmp sibling, then os.replace
    over the target. A crash mid-write can never corrupt the previous file,
    and the temp file is cleaned up on any failure."""
    tmp = str(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, str(path))
    except Exception:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass
        raise


def open_folder(path):
    """Open a folder in the OS file manager. Never raises.
    Windows explorer.exe (os.startfile), macOS Finder (open), else xdg-open."""
    try:
        if sys.platform == "win32" and hasattr(os, "startfile"):
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print(f"Warning: could not open folder {path}: {e}") 