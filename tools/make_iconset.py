"""Resize icon.png into an Apple AppIcon .iconset layout.

Portable by design: PILLOW (already a runtime dependency for cover art)
does every resize, so the macOS CI step does not depend on sips and its
version quirks; the dir -> icns assembly stays with Apple's own iconutil.
"""
import sys
from pathlib import Path

from PIL import Image

# Apple's AppIcon requirement set: (iconset name, pixel size).
SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def make_iconset(out_dir, source):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    src = Image.open(source).convert("RGBA")
    for name, size in SIZES:
        src.resize((size, size), Image.LANCZOS).save(out / name, format="PNG")
    return out


if __name__ == "__main__":
    make_iconset(sys.argv[1], sys.argv[2])
    print(f"{sys.argv[1]}: {len(SIZES)} sizes from {sys.argv[2]}")
