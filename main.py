"""Launcher for HiCloud MP.

Kept at the repo root so ``python main.py``, the Nuitka entry point and the
packaging contract keep working. The application lives in ``hicloudmp/``;
importing this module also opens the crash log, exactly as before.
"""
import sys

from hicloudmp.app import main

if __name__ == "__main__":
    sys.exit(main())
