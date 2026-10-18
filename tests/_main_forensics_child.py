"""Child process for test_main_forensics_handler_installed_in_clean_process.

Imports main in a clean interpreter (no pytest-qt handler overrides), emits a
Qt warning and verifies it reached the crash log opened at import time.
Prints FORENSICS_OK on success and exits non-zero otherwise.

Invoked by tests/test_main_import.py in a subprocess; not a test itself.
"""
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import platformdirs  # noqa: E402

TMPDIR = tempfile.mkdtemp(prefix="hicloudmp-forensics-child-")
platformdirs.user_data_dir = lambda *a, **k: TMPDIR  # type: ignore

import main  # noqa: E402

from PySide6.QtCore import qWarning  # noqa: E402

qWarning("child-forensics-marker")
main._crash_log.flush()

with open(os.path.join(TMPDIR, "crashlog.txt"), encoding="utf-8", errors="replace") as fh:
    text = fh.read()

ok = "session start" in text and "[WARN] child-forensics-marker" in text
print("FORENSICS_OK" if ok else "FORENSICS_MISSING", flush=True)
print(text[-400:], flush=True)
sys.exit(0 if ok else 1)
