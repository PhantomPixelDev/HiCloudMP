#!/bin/sh
# Generate build/icon.icns from icon.png for the macOS .app bundle.
# Sizes come from Pillow (runtime dependency, pinned in requirements.txt)
# because sips rejected a valid png on the runner (ledger 40179627589);
# the dir -> icns assembly stays with Apple's own iconutil.
set -e
# make-icns.sh lives at packaging/macos/, so the repo root is TWO levels up
# (ledger 40183856769: "/.." landed in packaging/ where icon.png isn't).
cd "$(dirname "$0")/../.."
test -f icon.png || { echo "FATAL: icon.png not present in $(pwd)"; exit 1; }
python tools/make_iconset.py build/icon.iconset icon.png
iconutil -c icns build/icon.iconset -o build/icon.icns
test -s build/icon.icns
echo "build/icon.icns ready"
