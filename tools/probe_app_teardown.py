"""TEMPORARY diagnostic #2 (delete before merge): real-app teardown probe.

Constructs the actual MusicPlayer repeatedly and destroys it the way
pytest-qt does, under three GC regimes, to find which step segfaults on a
headless runner. Each variant runs in its own subprocess.
"""
import os
import subprocess
import sys

CHILD = r"""
import gc
import os
import sys

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.getcwd())
from player import MusicPlayer  # noqa: E402

variant = sys.argv[1]
iters = int(sys.argv[2])
if variant == "gc_off":
    gc.disable()

app = QApplication([])
for i in range(iters):
    mp = MusicPlayer()
    mp.show()
    mp.close()
    mp.deleteLater()
    loop = QEventLoop()
    QTimer.singleShot(80, loop.quit)
    loop.exec()
    del mp
    if variant == "collect":
        gc.collect()
    print("iter", i, "ok", flush=True)
print("SURVIVED", variant, flush=True)
"""


def main():
    failures = 0
    for variant in ("plain", "collect", "gc_off"):
        proc = subprocess.run(
            [sys.executable, "-c", CHILD, variant, "5"],
            capture_output=True, text=True, env=os.environ.copy())
        tail = (proc.stdout.strip().splitlines() or [""])[-1]
        print(f"VARIANT {variant:8s} rc={proc.returncode} {tail}", flush=True)
        if proc.returncode != 0:
            failures += 1
            err = [ln for ln in proc.stderr.strip().splitlines() if ln.strip()]
            if err:
                print("   stderr:", err[-1][:200], flush=True)
    print(f"SUMMARY failures={failures}/3", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
