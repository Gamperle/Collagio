#!/usr/bin/env bash
# Build Collagio-<version>-x86_64.AppImage from the PyInstaller folder.
#   packaging/linux/build-appimage.sh [<pyinstaller-dist-dir> [<version> [<output-dir>]]]
# Defaults: build/dist/Collagio, the version in src/collagio/__init__.py, build/release.
# Needs appimagetool on PATH (or APPIMAGETOOL=/path/to/appimagetool).
set -euo pipefail

HERE=$(dirname "$(realpath "$0")")
ROOT=$(realpath "$HERE/../..")
DIST=${1:-$ROOT/build/dist/Collagio}
VERSION=${2:-$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/src/collagio/__init__.py")}
OUT=${3:-$ROOT/build/release}

if [ ! -x "$DIST/collagio-gui" ]; then
    echo "error: no PyInstaller build in $DIST; build it first:" >&2
    echo "  uv sync --group build" >&2
    echo "  uv run pyinstaller packaging/pyinstaller/collagio.spec --noconfirm --distpath build/dist" >&2
    exit 1
fi
if ! command -v "${APPIMAGETOOL:-appimagetool}" > /dev/null; then
    echo "error: appimagetool not found; put it on PATH or set APPIMAGETOOL=/path/to/appimagetool" >&2
    echo "  (https://github.com/AppImage/appimagetool/releases)" >&2
    exit 1
fi
DIST=$(realpath "$DIST")
mkdir -p "$OUT"
OUT=$(realpath "$OUT")
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

# appimagetool is an AppImage itself; extracting it avoids needing FUSE (libfuse2).
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "${APPIMAGETOOL:-appimagetool}" --no-appstream "$APPDIR" "$OUT/Collagio-$VERSION-x86_64.AppImage"
echo "$OUT/Collagio-$VERSION-x86_64.AppImage"
