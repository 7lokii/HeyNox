#!/usr/bin/env bash
# Empacota o HeyNox para macOS: .app, .dmg (setup) e .tar.gz (portable).
#
# Uso: installer/macos/build.sh <versao> [arch]
#   arch sai de `uname -m` por omissao (arm64 ou x86_64).
#
# Exige que dist/HeyNox ja exista, gerado pelo PyInstaller no mesmo sistema:
#   python -m installer.pyinstaller
#   pyinstaller --noconfirm --clean installer/HeyNox.spec
set -euo pipefail

VERSION="${1:?falta a versao, ex.: 0.0.1}"
ARCH="${2:-$(uname -m)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist"
APP="$DIST/HeyNox.app"
OUT="$ROOT/releases/$VERSION/macos"

if [ ! -x "$DIST/HeyNox/HeyNox" ]; then
  echo "falta dist/HeyNox/HeyNox; corre o PyInstaller antes" >&2
  exit 1
fi

mkdir -p "$OUT"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
# O one-dir do PyInstaller fica inteiro dentro de MacOS/ para que os caminhos
# relativos para _internal continuem a resolver depois de arrastar o .app.
cp -R "$DIST/HeyNox/." "$APP/Contents/MacOS/"

if [ -f "$ROOT/installer/icon.ico" ]; then
  python3 - "$ROOT/installer/icon.ico" "$APP/Contents/Resources" <<'PY'
import sys
from pathlib import Path

from PIL import Image

src, out = Path(sys.argv[1]), Path(sys.argv[2])
iconset = out / "icon.iconset"
iconset.mkdir(parents=True, exist_ok=True)
with Image.open(src) as im:
    base = im.convert("RGBA")
    for size in (16, 32, 64, 128, 256, 512):
        base.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
        base.resize((size * 2, size * 2), Image.LANCZOS).save(
            iconset / f"icon_{size}x{size}@2x.png"
        )
PY
  iconutil -c icns "$APP/Contents/Resources/icon.iconset" -o "$APP/Contents/Resources/icon.icns"
  rm -rf "$APP/Contents/Resources/icon.iconset"
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>HeyNox</string>
  <key>CFBundleDisplayName</key><string>HeyNox</string>
  <key>CFBundleIdentifier</key><string>com.heynox.app</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleExecutable</key><string>HeyNox</string>
  <key>CFBundleIconFile</key><string>icon.icns</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>O Nox precisa do microfone para ouvir "Hey Nox".</string>
</dict>
</plist>
PLIST

# Assinatura ad-hoc: sem ela o arm64 recusa arrancar um binario alterado.
# Nao substitui um Developer ID nem a notarizacao; ve docs/releases.md.
codesign --force --deep --sign - "$APP" >/dev/null

rm -f "$OUT/HeyNox-$VERSION-macos-$ARCH-setup.dmg" "$OUT/HeyNox-$VERSION-macos-$ARCH-portable.tar.gz"
hdiutil create -quiet -volname "HeyNox" -srcfolder "$APP" -ov -format UDZO \
  "$OUT/HeyNox-$VERSION-macos-$ARCH-setup.dmg"
tar -czf "$OUT/HeyNox-$VERSION-macos-$ARCH-portable.tar.gz" -C "$DIST" HeyNox.app

ls -lh "$OUT"
