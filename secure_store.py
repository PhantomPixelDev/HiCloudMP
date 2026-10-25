"""DPAPI-backed vault for credential-bearing state files.

cloudfiles.json holds WebDAV/Subsonic/Ampache passwords in the clear
today; save_json() now encrypts with Windows DPAPI (CurrentUser scope)
prefixed with MAGIC, and load_json() transparently reads files written
by older versions (plain JSON). Corruption never degrades to an empty
dict - a silent reset would wipe the user's cloud library over one bad
decrypt; it raises so the caller's existing error dialog fires.

Non-Windows hosts stay plaintext (the packaged app is Windows; the
Linux/dev halves already tolerate plaintext there).
"""
import base64
import ctypes
import json
import os

from utils import atomic_write_text

MAGIC = "HiCloudMP-DPAPI-v1:"

# Portable field types with CRYPT_DATA_BLOB's ABI: DWORD is a 32-bit
# unsigned long on Windows (LLP64 keeps ctypes.c_ulong 4 bytes there) and
# wintypes.DWORD literally aliases ctypes.c_ulong. Referencing
# ctypes.wintypes at module level crashed every import on macOS/Linux, so
# the struct avoids it entirely; the DPAPI calls still only ever run on
# Windows (os.name gates below), other hosts stay plaintext.
class _CRYPTOAPI_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong),
                ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> _CRYPTOAPI_BLOB:
    buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return _CRYPTOAPI_BLOB(len(data), buf)


def protect_text(text: str) -> str:
    """Encrypt text under the current user DPAPI scope; MAGIC-prefixed."""
    if os.name != "nt":
        raise OSError("DPAPI is only available on Windows")
    blob = _blob(text.encode("utf-8"))
    out = _CRYPTOAPI_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob), None, None, None, None, 0,
            ctypes.byref(out)):
        raise OSError("CryptProtectData failed")
    try:
        enc = ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)
    return MAGIC + base64.b64encode(enc).decode("ascii")


def unprotect_text(text: str):
    """Decrypt a MAGIC-prefixed payload; None when not protected. Corruption
    raises (fail loudly: never silently reset a user's cloud list)."""
    if not text.startswith(MAGIC):
        return None
    if os.name != "nt":
        raise OSError("DPAPI vault can only be opened on Windows")
    enc = base64.b64decode(text[len(MAGIC):])
    blob = _blob(enc)
    out = _CRYPTOAPI_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob), None, None, None, None, 0,
            ctypes.byref(out)):
        raise OSError("CryptUnprotectData failed - vault unreadable on "
                      "this user account (file was encrypted elsewhere?)")
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def save_json(path, data) -> None:
    """Atomically persist data; DPAPI-encrypted on Windows, plaintext
    elsewhere. Existing plaintext files upgrade on their next save."""
    text = json.dumps(data, ensure_ascii=False)
    if os.name == "nt":
        text = protect_text(text)
    atomic_write_text(str(path), text)


def load_json(path):
    """Read a file written by save_json of any version (encrypted or
    plaintext). Raises on corruption - callers should surface the error,
    never reset to empty."""
    with open(str(path), "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith(MAGIC):
        text = unprotect_text(text)
    return json.loads(text)
