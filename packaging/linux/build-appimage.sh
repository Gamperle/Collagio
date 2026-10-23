#!/usr/bin/env bash
# Build Collagio-<version>-x86_64.AppImage from the PyInstaller folder.
#   packaging/linux/build-appimage.sh <pyinstaller-dist-dir> <version> <output-dir>
# Needs appimagetool on PATH (or APPIMAGETOOL=/path/to/appimagetool).
set -euo pipefail

DIST=$(realpath "$1")
VERSION=$2
OUT=$(realpath "$3")
HERE=$(dirname "$(realpath "$0")")
ROOT=$(realpath "$HERE/../..")
APP_ID=io.github.gamperle.Collagio
APPDIR=$(mktemp -d)/Collagio.AppDir

mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" "$APPDIR/usr/share/metainfo" "$APPDIR/usr/share/mime/packages" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$DIST" "$APPDIR/usr/lib/collagio"
ln -s ../lib/collagio/collagio-gui "$APPDIR/usr/bin/collagio-gui"
ln -s ../lib/collagio/collagio "$APPDIR/usr/bin/collagio"

cp "$HERE/$APP_ID.desktop" "$APPDIR/usr/share/applications/"
cp "$HERE/$APP_ID.metainfo.xml" "$APPDIR/usr/share/metainfo/"
cp "$HERE/$APP_ID.xml" "$APPDIR/usr/share/mime/packages/"
cp "$ROOT/packaging/icons/collagio-256.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp "$ROOT/src/collagio/assets/collagio.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
cp "$HERE/$APP_ID.desktop" "$APPDIR/"
cp "$ROOT/packaging/icons/collagio-256.png" "$APPDIR/$APP_ID.png"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
# "collagio" as the first argument runs the command-line tool, anything else the editor.
HERE=$(dirname "$(readlink -f "$0")")
if [ "$1" = "collagio" ]; then
    shift
    exec "$HERE/usr/lib/collagio/collagio" "$@"
fi
exec "$HERE/usr/lib/collagio/collagio-gui" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

mkdir -p "$OUT"
ARCH=x86_64 "${APPIMAGETOOL:-appimagetool}" --no-appstream "$APPDIR" "$OUT/Collagio-$VERSION-x86_64.AppImage"
echo "$OUT/Collagio-$VERSION-x86_64.AppImage"
