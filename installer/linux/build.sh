#!/usr/bin/env bash
# Empacota o HeyNox para Linux: AppImage e .deb (setup) e .tar.gz (portable).
#
# Uso: installer/linux/build.sh <versao> [arch]
#
# Exige que dist/HeyNox ja exista, gerado pelo PyInstaller no mesmo sistema.
# O AppImage precisa do appimagetool; se nao estiver no PATH, e descarregado.
set -euo pipefail

VERSION="${1:?falta a versao, ex.: 0.0.1}"
ARCH="${2:-$(uname -m)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist"
OUT="$ROOT/releases/$VERSION/linux"
WORK="$ROOT/build/package"
APP_ID="heynox"

if [ ! -x "$DIST/HeyNox/HeyNox" ]; then
  echo "falta dist/HeyNox/HeyNox; corre o PyInstaller antes" >&2
  exit 1
fi

mkdir -p "$OUT"
rm -rf "$WORK"
mkdir -p "$WORK"

# Icone PNG a partir do .ico, para o .desktop e o .deb.
ICON_PNG="$WORK/$APP_ID.png"
python3 - "$ROOT/installer/icon.ico" "$ICON_PNG" <<'PY'
import sys
from pathlib import Path

from PIL import Image

src, out = Path(sys.argv[1]), Path(sys.argv[2])
with Image.open(src) as im:
    im.convert("RGBA").resize((256, 256), Image.LANCZOS).save(out)
PY

# ---------------------------------------------------------------- AppImage
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/bin"
cp -R "$DIST/HeyNox" "$APPDIR/usr/bin/HeyNox"
cp "$ICON_PNG" "$APPDIR/$APP_ID.png"
cp "$ICON_PNG" "$APPDIR/.DirIcon"

cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/HeyNox/HeyNox" "$@"
RUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=HeyNox
Comment=Assistente pessoal local-first
Exec=HeyNox
Icon=heynox
Terminal=false
Categories=Utility;
DESKTOP

TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
  TOOL="$WORK/appimagetool"
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$TOOL"
fi

ARCH_APPIMAGE="x86_64"
[ "$ARCH" = "aarch64" ] && ARCH_APPIMAGE="aarch64"
ARCH="$ARCH_APPIMAGE" "$TOOL" --no-appstream "$APPDIR" \
  "$OUT/HeyNox-$VERSION-linux-$ARCH-setup.AppImage"

# --------------------------------------------------------------------- deb
DEBROOT="$WORK/deb"
mkdir -p "$DEBROOT/DEBIAN" "$DEBROOT/opt" "$DEBROOT/usr/bin" \
  "$DEBROOT/usr/share/applications" "$DEBROOT/usr/share/icons/hicolor/256x256/apps"

cp -R "$DIST/HeyNox" "$DEBROOT/opt/heynox"
cp "$ICON_PNG" "$DEBROOT/usr/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp "$APPDIR/$APP_ID.desktop" "$DEBROOT/usr/share/applications/$APP_ID.desktop"

cat > "$DEBROOT/usr/bin/heynox" <<'LAUNCH'
#!/bin/sh
exec /opt/heynox/HeyNox/HeyNox "$@"
LAUNCH
chmod +x "$DEBROOT/usr/bin/heynox"

SIZE_KB="$(du -sk "$DEBROOT" | cut -f1)"
DEB_ARCH="amd64"
[ "$ARCH" = "aarch64" ] && DEB_ARCH="arm64"

cat > "$DEBROOT/DEBIAN/control" <<CONTROL
Package: heynox
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEB_ARCH
Installed-Size: $SIZE_KB
Depends: libportaudio2, libsndfile1, xdotool
Maintainer: 7lokii <https://github.com/7lokii>
Description: HeyNox, assistente pessoal de IA local-first
 O Nox ouve por "Hey Nox", transcreve a fala, executa ferramentas seguras,
 guarda memoria e fala de volta. Nucleo em Python, interface local.
CONTROL

dpkg-deb --build --root-owner-group "$DEBROOT" \
  "$OUT/HeyNox-$VERSION-linux-$ARCH-setup.deb"

# ---------------------------------------------------------------- portable
tar -czf "$OUT/HeyNox-$VERSION-linux-$ARCH-portable.tar.gz" -C "$DIST" HeyNox

ls -lh "$OUT"
