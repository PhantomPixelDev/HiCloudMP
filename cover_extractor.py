import os
import logging
import subprocess
import sys
import tempfile
from base64 import b64decode
from PIL import Image, UnidentifiedImageError
import mutagen

# Windows: child processes (ffmpeg) must never flash a console
# window in the packaged GUI build.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
from mutagen import MutagenError
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from mutagen.flac import Picture, FLAC, FLACNoHeaderError
from mutagen.oggopus import OggOpus, OggOpusHeaderError
from mutagen.oggvorbis import OggVorbis, OggVorbisHeaderError
from mutagen.mp4 import MP4, MP4StreamInfoError
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import requests
from requests.auth import HTTPBasicAuth
from io import BytesIO

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_ffmpeg(exe_dir=None):
    """Resolve the ffmpeg binary for subprocess calls.

    Order: a bundled copy shipped next to the program (standalone/installed
    builds), then one available on PATH. Returns a command string usable as
    argv[0]; falls back to the bare name so PATH lookups still apply."""
    import shutil
    if exe_dir is None:
        try:
            if getattr(sys, "frozen", False):
                exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            else:
                exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        except Exception:
            exe_dir = None
    names = ("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg",)
    if exe_dir:
        for name in names:
            cand = os.path.join(exe_dir, name)
            if os.path.isfile(cand):
                return cand
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg" if os.name == "nt" else "ffmpeg"

class CoverExtractor:
    """
    A class to extract cover art from audio files and streams.
    Supports various audio formats including MP3, FLAC, OGG, OPUS, and M4A.
    """
    
    @staticmethod
    def _extract_with_ffmpeg(file_path):
        """Extract cover art using ffmpeg directly"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_path = temp_file.name
        
            cmd = [
                find_ffmpeg(),
                '-i', file_path,
                '-an',              # Disable audio
                '-vcodec', 'copy',  # Copy the video stream directly
                '-f', 'image2',
                '-vframes', '1',    # Only extract the first frame
                '-y',               # Overwrite output file if it exists
                temp_path
            ]
        
            # Run ffmpeg and capture output
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=8,  # seconds
                    creationflags=_NO_WINDOW,
                )
            except subprocess.TimeoutExpired:
                logger.warning("FFmpeg extraction timed out")
                # Best-effort kill is handled by subprocess
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return None
        
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                try:
                    with Image.open(temp_path) as im:
                        im.load()  # Ensure data is read before deleting file
                        img = im.copy()
                finally:
                    os.unlink(temp_path)  # Clean up temp file
                return img
        
            # If we get here, extraction failed
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
        except Exception as e:
            logger.warning(f"FFmpeg extraction failed: {e}")
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
        return None
    
    @staticmethod
    def _sidecar_artwork_candidates(audio_path):
        """Artwork commonly stored next to local audio files, most specific
        first: an image named exactly like the track, then common album-cover
        names (Cover.jpg, folder.jpg, front.png, albumart.jpg, ...).

        Matching is case-insensitive; files with extra suffixes (e.g.
        <track>_spectrogram.png) never match. Used only when a local file
        carries no embedded art (e.g. archive.org downloads)."""
        try:
            directory = os.path.dirname(os.path.abspath(audio_path))
            entries = os.listdir(directory)
        except OSError:
            return []
        stem = os.path.splitext(os.path.basename(audio_path))[0].lower()
        ranked = []
        for name in entries:
            base, ext = os.path.splitext(name)
            if ext.lower() not in ('.jpg', '.jpeg', '.png', '.webp', '.bmp'):
                continue
            low = base.lower()
            if low == stem:
                ranked.append((0, name))
            elif low in ('cover', 'folder', 'front', 'album', 'albumart',
                         'artwork'):
                ranked.append((1, name))
        ranked.sort()
        return [os.path.join(directory, name) for _, name in ranked]

    @staticmethod
    def _open_sidecar_artwork(audio_path):
        """Open sidecar artwork next to local audio, preferring cover-shaped
        images (roughly square). Wide/tall renders (waveform-like banners,
        e.g. archive.org per-track 800x200 displays) defer to the album
        cover and are used only when nothing cover-shaped exists.
        Returns a PIL Image or None."""
        last_resort = None
        for art_path in CoverExtractor._sidecar_artwork_candidates(audio_path):
            try:
                img = Image.open(art_path)
                width, height = img.size
                ratio = width / float(height)
            except Exception:
                continue
            if 0.45 <= ratio <= 2.2:
                return img
            if last_resort is None:
                last_resort = img
        return last_resort

    @classmethod
    def extract_cover(cls, file_path_or_url, is_url=False, max_size=2*1024*1024):  # 2MB max for remote files
        """
        Extract cover art from an audio file or URL.
        
        Args:
            file_path_or_url (str): Path to the audio file or URL
            is_url (bool): Whether the input is a URL
            max_size (int): Maximum size in bytes to download for URL requests
            
        Returns:
            PIL.Image or None: Extracted cover art as PIL Image, or None if not found
        """
        try:
            if is_url:
                logger.info(f"Extracting cover from URL: {file_path_or_url}")
                try:
                    # Prepare headers and optional Basic Auth
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    auth_url = file_path_or_url
                    try:
                        from urllib.parse import urlparse, urlunparse, quote
                        parsed = urlparse(file_path_or_url)
                        # Build netloc without credentials
                        netloc = parsed.hostname or ''
                        if parsed.port:
                            netloc += f":{parsed.port}"
                        path = quote(parsed.path or '', safe='/')
                        auth_url = urlunparse((parsed.scheme, netloc, path, parsed.params, parsed.query, parsed.fragment))
                        # Add Basic Auth header if credentials provided in URL
                        if parsed.username and parsed.password:
                            import base64
                            auth = f"{parsed.username}:{parsed.password}".encode()
                            headers['Authorization'] = 'Basic ' + base64.b64encode(auth).decode()
                    except Exception:
                        # If parsing fails, continue without header
                        auth_url = file_path_or_url

                    # Use requests so URL is properly encoded and auth handled
                    auth = None
                    try:
                        from urllib.parse import urlparse
                        parsed2 = urlparse(file_path_or_url)
                        if parsed2.username and parsed2.password:
                            auth = HTTPBasicAuth(parsed2.username, parsed2.password)
                    except Exception:
                        pass

                    with requests.get(auth_url, headers=headers, stream=True, timeout=10, auth=auth) as r:
                        r.raise_for_status()
                        content_type = r.headers.get('Content-Type', '').lower()
                        content_length = int(r.headers.get('Content-Length', '0') or 0)

                        # If declared size is huge, handle based on type: images must be small, audio we can read partial
                        if content_length and content_length > max_size and not any(x in content_type for x in ['audio/mpeg', 'audio/flac', 'audio/ogg', 'audio/mp4', 'audio/x-m4a']):
                            logger.warning(f"File too large: {content_length} bytes")
                            return None

                        # If it's an image, return it directly
                        if any(x in content_type for x in ['image/jpeg', 'image/png', 'image/gif']):
                            data = r.content if content_length and content_length <= max_size else b''.join(r.iter_content(1024*64))
                            return Image.open(BytesIO(data))

                        # If it's an audio file, try direct FFmpeg extraction
                        if any(x in content_type for x in ['audio/mpeg', 'audio/flac', 'audio/ogg', 'audio/mp4', 'audio/x-m4a']):
                            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_path_or_url)[1], delete=False) as temp_file:
                                remaining = max_size
                                for chunk in r.iter_content(1024*64):
                                    if not chunk:
                                        break
                                    temp_file.write(chunk)
                                    remaining -= len(chunk)
                                    if remaining <= 0:
                                        break
                            temp_path = temp_file.name

                            try:
                                img = cls._extract_with_ffmpeg(temp_path)
                                if img:
                                    return img
                            finally:
                                if os.path.exists(temp_path):
                                    os.unlink(temp_path)

                        # Otherwise, try to parse as audio for embedded pictures
                        data = b''
                        remaining = max_size
                        for chunk in r.iter_content(1024*64):
                            if not chunk:
                                break
                            data += chunk
                            remaining -= len(chunk)
                            if remaining <= 0:
                                break
                        file_obj = BytesIO(data)
                        
                        # Try to determine file type from content
                        file_obj.seek(0)
                        magic = file_obj.read(8)  # Read more bytes for better detection
                        file_obj.seek(0)
                        
                        if magic.startswith(b'fLaC'):
                            return CoverExtractor._extract_flac_cover(file_obj)
                        elif magic.startswith((b'ID3', b'\x49\x44\x33')):
                            return CoverExtractor._extract_id3_cover(file_obj)
                        elif magic.startswith(b'OggS'):
                            return CoverExtractor._extract_ogg_cover(file_obj)
                        elif magic.startswith(b'\x00\x00\x00 ftypM4A') or b'ftypmp4' in magic:
                            return CoverExtractor._extract_mp4_cover(file_obj)
                        else:
                            logger.warning(f"Unsupported file format for URL: {file_path_or_url}")
                            return None
                            
                except (URLError, HTTPError) as e:
                    logger.error(f"Error fetching URL {file_path_or_url}: {e}")
                    return None
                    
            else:
                # Handle local file path
                logger.info(f"Extracting cover from local file: {file_path_or_url}")
                if not os.path.exists(file_path_or_url):
                    logger.error(f"File not found: {file_path_or_url}")
                    return None
                    
                try:
                    ext = os.path.splitext(file_path_or_url)[1].lower()
                    
                    # First try FFmpeg extraction which is more reliable
                    ffmpeg_cover = cls._extract_with_ffmpeg(file_path_or_url)
                    if ffmpeg_cover:
                        return ffmpeg_cover
                    
                    # Fall back to mutagen-based extraction
                    if ext == '.mp3':
                        cover = cls._extract_id3_cover(file_path_or_url)
                        if cover:
                            return cover
                    elif ext == '.flac':
                        cover = cls._extract_flac_cover(file_path_or_url)
                        if cover:
                            return cover
                    elif ext in ('.ogg', '.oga', '.opus'):
                        cover = cls._extract_ogg_cover(file_path_or_url)
                        if cover:
                            return cover
                    elif ext in ('.m4a', '.mp4'):
                        cover = cls._extract_mp4_cover(file_path_or_url)
                        if cover:
                            return cover
                    elif ext == '.wma':
                        cover = cls._extract_asf_cover(file_path_or_url)
                        if cover:
                            return cover
                    elif ext in ('.aiff', '.aif'):
                        cover = cls._extract_aiff_cover(file_path_or_url)
                        if cover:
                            return cover
                    elif ext == '.wav':
                        cover = cls._extract_wav_cover(file_path_or_url)
                        if cover:
                            return cover
                            
                    # No embedded art: fall back to artwork files stored next
                    # to the audio (per-track images, common cover names).
                    sidecar = cls._open_sidecar_artwork(file_path_or_url)
                    if sidecar:
                        return sidecar

                    # If we get here, try to open as image directly
                    try:
                        return Image.open(file_path_or_url)
                    except UnidentifiedImageError:
                        logger.warning(f"Unsupported image format: {file_path_or_url}")
                        return None
                            
                except Exception as e:
                    logger.error(f"Error processing file {file_path_or_url}: {e}")
                    return None
                        
        except Exception as e:
            logger.error(f"Unexpected error in extract_cover: {e}", exc_info=True)
            return None

    @staticmethod
    def _extract_id3_cover(file_path_or_obj):
        """Extract cover art from ID3 tags (MP3)"""
        try:
            try:
                audio = ID3(file_path_or_obj)
            except ID3NoHeaderError:
                logger.debug("No ID3 header found")
                return None
                
            for tag in audio.values():
                if isinstance(tag, APIC):
                    try:
                        return Image.open(BytesIO(tag.data))
                    except UnidentifiedImageError as e:
                        logger.warning(f"Could not identify image data in ID3 tag: {e}")
                        continue
                        
            logger.debug("No cover art found in ID3 tags")
            return None
            
        except MutagenError as e:
            logger.error(f"Error reading ID3 tags: {e}")
            return None
    
    @staticmethod
    def _extract_flac_cover(file_path_or_obj):
        """Extract cover art from FLAC file"""
        try:
            try:
                audio = FLAC(file_path_or_obj)
            except FLACNoHeaderError:
                logger.debug("No FLAC header found")
                return None
                
            if not audio.pictures:
                logger.debug("No pictures found in FLAC file")
                return None
                
            # Try to find front cover first
            for picture in audio.pictures:
                if picture.type == 3:  # Front cover
                    try:
                        return Image.open(BytesIO(picture.data))
                    except UnidentifiedImageError as e:
                        logger.warning(f"Could not identify image data in FLAC: {e}")
                        continue
            
            # If no front cover found, try any other image
            for picture in audio.pictures:
                try:
                    return Image.open(BytesIO(picture.data))
                except UnidentifiedImageError:
                    continue
                    
            logger.debug("No valid cover art found in FLAC file")
            return None
            
        except MutagenError as e:
            logger.error(f"Error reading FLAC file: {e}")
            return None
    
    @staticmethod
    def _extract_ogg_cover(file_path_or_obj):
        """Extract cover art from Ogg Vorbis or Ogg Opus files"""
        try:
            # Try Ogg Vorbis first
            try:
                audio = OggVorbis(file_path_or_obj)
                if 'METADATA_BLOCK_PICTURE' in audio.tags:
                    for data in audio.tags['METADATA_BLOCK_PICTURE']:
                        try:
                            pic = Picture(b64decode(data))
                            if pic.type == 3:  # Front cover
                                return Image.open(BytesIO(pic.data))
                        except (TypeError, ValueError) as e:
                            logger.warning(f"Error decoding Ogg Vorbis picture: {e}")
                            continue
                            
            except (OggVorbisHeaderError, MutagenError) as e:
                logger.debug(f"Not an Ogg Vorbis file or error reading: {e}")
                pass
                
            # Try Ogg Opus
            try:
                audio = OggOpus(file_path_or_obj)
                if 'METADATA_BLOCK_PICTURE' in audio.tags:
                    for data in audio.tags['METADATA_BLOCK_PICTURE']:
                        try:
                            pic = Picture(b64decode(data))
                            if pic.type == 3:  # Front cover
                                return Image.open(BytesIO(pic.data))
                        except (TypeError, ValueError) as e:
                            logger.warning(f"Error decoding Ogg Opus picture: {e}")
                            continue
                            
            except (OggOpusHeaderError, MutagenError) as e:
                logger.debug(f"Not an Ogg Opus file or error reading: {e}")
                pass
                
            logger.debug("No cover art found in Ogg file")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting Ogg cover: {e}")
            return None
    
    @staticmethod
    def _extract_mp4_cover(file_path_or_obj):
        """Extract cover art from MP4/M4A files"""
        try:
            try:
                audio = MP4(file_path_or_obj)
            except MP4StreamInfoError as e:
                logger.debug(f"Invalid MP4 file: {e}")
                return None
                
            if 'covr' in audio.tags:
                for cover_data in audio.tags['covr']:
                    try:
                        if hasattr(cover_data, 'imageformat'):  # MP4Cover object
                            return Image.open(BytesIO(cover_data))
                        elif isinstance(cover_data, bytes):  # Raw bytes
                            return Image.open(BytesIO(cover_data))
                    except UnidentifiedImageError as e:
                        logger.warning(f"Could not identify MP4 cover image: {e}")
                        continue
                        
            logger.debug("No cover art found in MP4 file")
            return None
            
        except MutagenError as e:
            logger.error(f"Error reading MP4 file: {e}")
            return None
    
    @staticmethod
    def _extract_asf_cover(file_path_or_obj):
        """Extract album art from ASF/WMA tags (WM/Picture attribute).

        mutagen is imported function-locally so a defective install or a
        monkeypatched test double stays possible without module-import cost."""
        try:
            from mutagen.asf import ASF
        except ImportError:
            return None
        try:
            audio = ASF(file_path_or_obj)
            pictures = audio.getall("WM/Picture")
        except Exception:
            return None
        for picture in pictures:
            data = getattr(picture, "data", None) or \
                (getattr(picture, "image", None) if
                 not isinstance(getattr(picture, "image", None), str) else None)
            if not data:
                continue
            try:
                return Image.open(BytesIO(data))
            except UnidentifiedImageError:
                continue
        return None

    @staticmethod
    def _extract_aiff_cover(file_path_or_obj):
        """Extract cover art from an ID3 chunk embedded in AIFF files."""
        try:
            from mutagen.aiff import AIFF
        except ImportError:
            return None
        try:
            audio = AIFF(file_path_or_obj)
            tags = getattr(audio, "tags", None)
            if not tags:
                return None
            frames = tags.getall("APIC")
        except Exception:
            return None
        for frame in frames:
            data = getattr(frame, "data", None)
            if not data:
                continue
            try:
                return Image.open(BytesIO(data))
            except UnidentifiedImageError:
                continue
        return None

    @staticmethod
    def _extract_wav_cover(file_path_or_obj):
        """Extract cover art from an ID3 chunk embedded in WAVE files."""
        try:
            from mutagen.wave import WAVE
        except ImportError:
            return None
        try:
            audio = WAVE(file_path_or_obj)
            tags = getattr(audio, "tags", None)
            if not tags:
                return None
            frames = tags.getall("APIC")
        except Exception:
            return None
        for frame in frames:
            data = getattr(frame, "data", None)
            if not data:
                continue
            try:
                return Image.open(BytesIO(data))
            except UnidentifiedImageError:
                continue
        return None

    @staticmethod
    def _try_generic_extraction(file_path):
        """Try to extract cover art using mutagen's generic file handler"""
        try:
            audio = mutagen.File(file_path)
            if hasattr(audio, 'tags') and 'APIC:' in audio.tags:
                return Image.open(BytesIO(audio.tags['APIC:'].data))
            if hasattr(audio, 'pictures') and audio.pictures:
                return Image.open(BytesIO(audio.pictures[0].data))
        except Exception:
            pass
        return None
    
    # Stream extraction methods (simplified versions for remote files)
    @staticmethod
    def _extract_mp3_from_stream(url):
        """Extract cover art from MP3 stream"""
        try:
            with urlopen(url) as response:
                # Read the first 1MB which should contain the ID3 tags
                data = response.read(1024 * 1024)
                temp_file = BytesIO(data)
                temp_file.name = 'temp.mp3'  # Needed for mutagen
                return CoverExtractor._extract_from_mp3(temp_file)
        except Exception as e:
            print(f"Error extracting MP3 cover from stream: {e}")
            return None
    
    @staticmethod
    def _extract_flac_from_stream(url):
        """Extract cover art from FLAC stream"""
        try:
            with urlopen(url) as response:
                # Read the first 2MB which should contain the metadata
                data = response.read(2 * 1024 * 1024)
                temp_file = BytesIO(data)
                temp_file.name = 'temp.flac'  # Needed for mutagen
                return CoverExtractor._extract_from_flac(temp_file)
        except Exception as e:
            print(f"Error extracting FLAC cover from stream: {e}")
            return None
    
    @staticmethod
    def _extract_ogg_from_stream(url):
        """Extract cover art from OGG/OPUS stream"""
        try:
            with urlopen(url) as response:
                # Read the first 1MB which should contain the metadata
                data = response.read(1024 * 1024)
                temp_file = BytesIO(data)
                temp_file.name = 'temp.ogg'  # Needed for mutagen
                return CoverExtractor._extract_from_ogg(temp_file)
        except Exception as e:
            print(f"Error extracting OGG/OPUS cover from stream: {e}")
            return None
    
    @staticmethod
    def _extract_m4a_from_stream(url):
        """Extract cover art from M4A/MP4 stream"""
        try:
            with urlopen(url) as response:
                # Read the first 2MB which should contain the metadata
                data = response.read(2 * 1024 * 1024)
                temp_file = BytesIO(data)
                temp_file.name = 'temp.m4a'  # Needed for mutagen
                return CoverExtractor._extract_from_m4a(temp_file)
        except Exception as e:
            print(f"Error extracting M4A/MP4 cover from stream: {e}")
            return None
