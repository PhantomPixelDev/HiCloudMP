"""TEMPORARY diagnostic (delete before merge): which teardown order survives?

Qt 6.10.3 segfaults when a QMediaPlayer/QAudioOutput is destroyed on a
headless runner. Each variant runs in its own subprocess so a crash only
kills that variant and the exit code names the culprit.
"""
import os
import struct
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
WAV = os.path.join(HERE, "_probe_tone.wav")

CHILD = r"""
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QUrl, QEventLoop, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioBufferOutput

variant, wav = sys.argv[1], sys.argv[2]
app = QApplication([])
w = QMainWindow()
p = QMediaPlayer(w)
o = QAudioOutput(w)
p.setAudioOutput(o)
tap = QAudioBufferOutput(w)
p.setAudioBufferOutput(tap)
if variant != "no_source":
    p.setSource(QUrl.fromLocalFile(wav))
    p.play()
    loop = QEventLoop(); QTimer.singleShot(400, loop.quit); loop.exec()
    print("state:", p.playbackState(), "err:", p.error(), flush=True)
if variant in ("detach_source", "detach_both"):
    p.stop()
    p.setSource(QUrl())
if variant == "detach_both":
    p.setAudioOutput(None)
    p.setAudioBufferOutput(None)
if variant != "no_close":
    w.close()
w.deleteLater()
loop = QEventLoop(); QTimer.singleShot(300, loop.quit); loop.exec()
del w, p, o, tap
print("SURVIVED", variant, flush=True)
"""


def make_wav():
    with wave.open(WAV, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", 0) for _ in range(8000)))


def main():
    make_wav()
    variants = ["no_source", "no_close", "source", "detach_source", "detach_both"]
    failures = 0
    for variant in variants:
        proc = subprocess.run([sys.executable, "-c", CHILD, variant, WAV],
                              capture_output=True, text=True)
        tail = (proc.stdout.strip().splitlines() or [""])[-1]
        print(f"VARIANT {variant:14s} rc={proc.returncode} {tail}", flush=True)
        if proc.returncode != 0:
            failures += 1
            err = proc.stderr.strip().splitlines()
            if err:
                print("   stderr:", err[-1][:160], flush=True)
    print(f"SUMMARY failures={failures}/{len(variants)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
