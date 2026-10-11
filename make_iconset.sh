#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build/Icon.iconset
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" assets/icon.png --out "build/Icon.iconset/icon_${size}x${size}.png" >/dev/null
    doubled=$((size * 2))
    sips -z "$doubled" "$doubled" assets/icon.png --out "build/Icon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns build/Icon.iconset -o assets/icon.icns
