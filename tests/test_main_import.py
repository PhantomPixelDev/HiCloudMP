def test_main_imports_without_linux_backends():
    """Task 3 regression: importing main on a machine without dbus/gi (Windows)
    must not raise ImportError — MPRIS support degrades to a no-op."""
    import main

    assert main.MprisService is None or hasattr(main.MprisService, "start")


def test_main_forensics_captures_qt_messages_to_crashlog():
    """Pin the crash-forensics contract: importing main opens a per-user crash
    log and wires a Qt message handler that labels and records every message.

    Windows fastfails (0xC0000409 / 0xC0000005) kill the process without a
    Python traceback, so this log is the only post-mortem evidence channel;
    it must exist and be wired up before the Qt-heavy modules load (see the
    module-level ordering in main.py - do not move the forensics block below
    the PySide6 imports).
    """
    from pathlib import Path

    from PySide6.QtCore import QtMsgType

    import main

    path = Path(main._crash_log.name)
    assert path.name == "crashlog.txt"
    assert "session start" in path.read_text(encoding="utf-8", errors="replace")

    # pytest-qt swaps in its own capture handler for the duration of each
    # test, so exercise the app's handler directly: it must label and write.
    main._qt_message(QtMsgType.QtWarningMsg, None, "forensics-pin-marker")

    main._crash_log.flush()
    text = path.read_text(encoding="utf-8", errors="replace")
    assert "[WARN] forensics-pin-marker" in text


def test_main_forensics_handler_installed_in_clean_process():
    """Pin the IMPORT-TIME installation of the message handler.

    In a clean interpreter (no pytest-qt handler swaps) a Qt warning emitted
    after importing main must land in the crash log - that is what makes
    deadly Windows fastfails debuggable in the field.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    child = Path(__file__).parent / "_main_forensics_child.py"
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, str(child)],
        capture_output=True, text=True, timeout=180, env=env, cwd=str(root),
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, f"child died: exit={proc.returncode}\n{out}"
    assert "FORENSICS_OK" in out, out
