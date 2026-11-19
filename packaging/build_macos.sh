#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
version="$(cat "$root/VERSION")"
arch="$(uname -m)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
app="$stage/PDFHub.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources" "$app/Contents/Helpers/engine"
swiftc -O -parse-as-library "$root/macos/PDFHubMac.swift" -framework SwiftUI -framework AppKit -o "$app/Contents/MacOS/PDFHub"
cp "$root/macos/Info.plist" "$app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $version" "$app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $version" "$app/Contents/Info.plist"
python3 "$root/packaging/macos_icon.py" "$root/ui/icon.svg" "$app/Contents/Resources/PDFHub.icns"
python3 -m pip install --disable-pip-version-check --requirement "$root/requirements.txt" pyinstaller
python3 -m PyInstaller --noconfirm --clean --onedir --console --name engine \
  --add-data "$root/ui/catalog.json:ui" --distpath "$app/Contents/Helpers" --workpath "$stage/work" \
  --specpath "$stage" "$root/worker.py"
# PyInstaller's bundled Python framework contains a plain python3.12 binary
# that Apple's --deep traversal mistakes for a nested application bundle.
# Sign the two executable entry points and the outer app explicitly instead.
codesign --force --sign - "$app/Contents/Helpers/engine/engine"
codesign --force --sign - "$app/Contents/MacOS/PDFHub"
codesign --force --sign - "$app"
mkdir -p "$root/dist"
ditto -c -k --sequesterRsrc --keepParent "$app" "$root/dist/PDFHub-${version}-macOS-${arch}.zip"

