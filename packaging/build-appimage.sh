#!/bin/sh
# Build Mithlond-<version>-x86_64.AppImage: bundled Python 3.13 (python-appimage, manylinux_2_28)
# + PySide6-Essentials + requests, pruned to the Qt libraries the app actually loads.
#   packaging/build-appimage.sh [output-dir]      (needs: curl, readelf, python3; no root, no FUSE)
set -eu
SRC="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$SRC/dist}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PY_URL="https://github.com/niess/python-appimage/releases/download/python3.13/python3.13.17-cp313-cp313-manylinux_2_28_x86_64.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
PYSIDE="PySide6-Essentials==6.12.0"
VER="$(sed -n 's/__version__ = "\(.*\)"/\1/p' "$SRC/mithlond/__init__.py")"

cd "$WORK"
curl -fsSL -o python.AppImage "$PY_URL"
curl -fsSL -o appimagetool.AppImage "$TOOL_URL"
chmod +x python.AppImage appimagetool.AppImage
./python.AppImage --appimage-extract >/dev/null
mv squashfs-root AppDir
cd AppDir
PY=opt/python3.13/bin/python3.13
SP=opt/python3.13/lib/python3.13/site-packages
PYTHONNOUSERSITE=1 $PY -s -m pip install -q --no-cache-dir --disable-pip-version-check "$PYSIDE" requests

# --- prune Qt: keep QtCore/QtGui/QtWidgets bindings and only the libraries they and the kept plugins need
P6=$SP/PySide6
for f in "$P6"/*.abi3.so; do
    case "$(basename "$f")" in QtCore.*|QtGui.*|QtWidgets.*) ;; *) rm -f "$f" "${f%.abi3.so}.pyi" ;; esac
done
rm -rf "$P6"/libpyside6qml.* "$P6"/svgtoqml "$P6"/Qt/qml "$P6"/Qt/translations "$P6"/Qt/metatypes "$P6"/Qt/libexec \
       "$P6"/Qt/plugins/designer "$P6"/Qt/plugins/qmltooling "$P6"/Qt/plugins/sqldrivers "$P6"/Qt/plugins/printsupport \
       "$P6"/Qt/plugins/networkinformation "$P6"/Qt/plugins/tls "$P6"/Qt/plugins/vectorimageformats \
       "$P6"/Qt/plugins/wayland-graphics-integration-server \
       "$P6"/assistant "$P6"/designer "$P6"/linguist "$P6"/lrelease "$P6"/lupdate "$P6"/qmlformat "$P6"/qmlls \
       "$P6"/qmllint "$P6"/qmlimportscanner "$P6"/doc "$P6"/glue "$P6"/include "$P6"/scripts "$P6"/typesystems \
       "$P6"/examples "$P6"/pyside6-*
find "$P6"/Qt/plugins \( -name libqeglfs-kms-integration.so -o -name libqpdf.so -o -name libqtvirtualkeyboardplugin.so \) -delete
python3 - "$P6" <<'PY'
import glob, os, re, subprocess, sys
root = sys.argv[1]; lib = os.path.join(root, "Qt/lib")
avail = {os.path.basename(p) for p in glob.glob(lib + "/*.so*")}
needed = lambda p: re.findall(r"\(NEEDED\).*\[(.+?)\]", subprocess.run(["readelf", "-d", p], capture_output=True, text=True).stdout)
todo = glob.glob(root + "/*.so*") + glob.glob(root + "/../shiboken6/*.so*") + glob.glob(root + "/Qt/plugins/**/*.so", recursive=True)
keep, broken = set(), []
while todo:
    p = todo.pop()
    for n in needed(p):
        if n in avail and n not in keep:
            keep.add(n); todo.append(os.path.join(lib, n))
        elif n.startswith("libQt6") and n not in avail:
            broken.append(f"{p} -> {n}")
for d in avail - keep:
    os.remove(os.path.join(lib, d))
if broken:
    sys.exit("missing Qt libraries:\n" + "\n".join(broken))
print("Qt libraries kept:", len(keep))
PY

# --- drop build-only and unused stdlib bits
rm -rf AppRun python.png ./*.desktop .DirIcon usr/share/applications usr/share/icons usr/share/metainfo usr/share/tcltk \
       usr/bin/pip* $SP/pip $SP/pip-* $SP/build $SP/build-* $SP/pyproject_hooks* $SP/packaging $SP/packaging-* \
       opt/python3.13/lib/python3.13/tkinter opt/python3.13/lib/python3.13/idlelib \
       opt/python3.13/lib/python3.13/turtledemo opt/python3.13/lib/python3.13/test opt/python3.13/lib/python3.13/ensurepip

# --- the app
cp -r "$SRC/mithlond" "$SP/mithlond"
find . -name __pycache__ -prune -exec rm -rf {} +
cat > AppRun <<'SH'
#!/bin/sh
# Mithlond AppImage entry point: run the bundled Python in isolated mode (ignores PYTHONPATH,
# PYTHONHOME and ~/.local site-packages), so the host's Python setup can't interfere.
HERE="$(dirname "$(readlink -f "$0")")"
export MITHLOND_APPIMAGE=1
exec "$HERE/opt/python3.13/bin/python3.13" -I -m mithlond "$@"
SH
chmod +x AppRun
cat > mithlond.desktop <<DE
[Desktop Entry]
Type=Application
Name=Mithlond
GenericName=LOTRO Launcher
Comment=Play The Lord of the Rings Online, manage plugins and songs
Exec=mithlond
Icon=mithlond
Terminal=false
Categories=Game;
StartupWMClass=mithlond
X-AppImage-Version=$VER
DE
cp "$SRC/mithlond/resources/mithlond.svg" mithlond.svg
ln -s mithlond.svg .DirIcon
./AppRun --version >/dev/null
chmod -R a+rX .
cd "$WORK"

mkdir -p "$OUT"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 ./appimagetool.AppImage --comp zstd -n AppDir "$OUT/Mithlond-$VER-x86_64.AppImage" >/dev/null 2>&1
echo "Built $OUT/Mithlond-$VER-x86_64.AppImage ($(du -h "$OUT/Mithlond-$VER-x86_64.AppImage" | cut -f1))"
