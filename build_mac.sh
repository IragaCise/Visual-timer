#!/bin/bash
# macOS 上で Python 同梱 .app を生成する。Apple Silicon / Intel に対応。
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != 'Darwin' ]]; then
    echo 'このスクリプトは macOS で実行する必要があります。'
    exit 1
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -c 'import tkinter; print("Tk:", tkinter.TkVersion)'
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --disable-pip-version-check 'pyinstaller==6.22.3'
bash make_iconset.sh
python -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name 'Visual Bar Timer' \
  --icon 'assets/icon.icns' \
  --osx-bundle-identifier 'io.github.visualbartimer.desktop' \
  visual_bar_timer.py
APP='dist/Visual Bar Timer.app'
test -d "$APP"
# PyInstaller は通常 ad-hoc 署名を行う。検証だけ実施。
codesign --verify --deep "$APP"
mkdir -p output
ARCH=$(uname -m)
ditto -c -k --sequesterRsrc --keepParent "$APP" "output/VisualBarTimer-macOS-${ARCH}.zip"
echo "完成: output/VisualBarTimer-macOS-${ARCH}.zip"
echo '※ Developer ID 署名・公証はしていません。初回起動時にmacOSから確認される場合があります。'
