#!/bin/sh
# Generate build/icon.icns from icon.png for the macOS .app bundle.
# GitHub macos runners have sips/iconutil preinstalled.
set -e
cd "$(dirname "$0")/.."
mkdir -p build/icon.iconset

convert() {
  sips -s format png -z "$2" "$2" icon.png --out "build/icon.iconset/$1" >/dev/null
}

convert icon_16x16.png 16
convert icon_16x16@2x.png 32
convert icon_32x32.png 32
convert icon_32x32@2x.png 64
convert icon_128x128.png 128
convert icon_128x128@2x.png 256
convert icon_256x256.png 256
convert icon_256x256@2x.png 512
convert icon_512x512.png 512
convert icon_512x512@2x.png 1024

iconutil -c icns build/icon.iconset -o build/icon.icns
test -s build/icon.icns
echo "build/icon.icns ready"
