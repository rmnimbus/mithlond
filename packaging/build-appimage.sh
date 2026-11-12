#!/bin/sh
# Build Mithlond-<version>-x86_64.AppImage: bundled Python 3.13 (python-appimage, manylinux_2_28)
# + PySide6-Essentials + requests, pruned to the Qt libraries the app actually loads.
#   packaging/build-appimage.sh [output-dir]      (needs: curl, readelf, ar, python3; no root, no FUSE)
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
curl -fsSL --retry 3 -o python.AppImage "$PY_URL"
curl -fsSL --retry 3 -o appimagetool.AppImage "$TOOL_URL"
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

# --- xcb-util libraries for Qt's X11 plugin. Qt >= 6.5 needs libxcb-cursor, which Ubuntu/Mint and other
# distros don't install by default ("xcb-cursor0 or libxcb-cursor0 is needed to load the Qt xcb platform
# plugin"). Bundled next to libQt6XcbQpa (RUNPATH $ORIGIN). Pinned Debian builds that need glibc <= 2.14;
# deb.debian.org first, snapshot.debian.org (by SHA-1) once the version leaves the mirror.
mkdir -p "$WORK/xcb"
while read -r src deb sha256 sha1; do
    f="$WORK/xcb/$deb"
    curl -fsSL --retry 3 -o "$f" "https://deb.debian.org/debian/pool/main/x/$src/$deb" \
        || curl -fsSL --retry 3 -o "$f" "https://snapshot.debian.org/file/$sha1"
    echo "$sha256  $f" | sha256sum -c --quiet
    ( cd "$WORK/xcb" && ar x "$f" data.tar.xz && tar -xJf data.tar.xz --wildcards './usr/lib/x86_64-linux-gnu/*.so.*' \
      && rm data.tar.xz )
done <<'DEBS'
xcb-util-cursor libxcb-cursor0_0.1.4-1_amd64.deb a4b3c32dc008275ffcacccc1c77c030f01aad38e232e05d5ad116b76656c607c 65e6e05bd9d8485ea4203a4723d19e9ee551f277
xcb-util-wm libxcb-icccm4_0.4.2-1_amd64.deb 28f04c7fa76939bbc03fbaa1191dc58200c0c894d48ac6105a7039ba4d223b4a 76c1124e016c60ef93db0ef8fc6208b0fd6f18f0
xcb-util-image libxcb-image0_0.4.0-2+b2_amd64.deb 81e2654e1b1da5cff9ea2bf46970a46eb5c81f1e35b1356691705e8cd6ab3ed6 088d52669e858425a5af10b2b74e82acbed41953
xcb-util-keysyms libxcb-keysyms1_0.4.1-1_amd64.deb 6989138382e5b9966aa731db68f851858c1d40cf8c98d7e5d7952c9e5a09d710 2a740f96c46a97efe924740919e69143749f84e9
xcb-util-renderutil libxcb-render-util0_0.3.10-1_amd64.deb 9bdd6247e45cea5047e4da883dabf168366474fb1b00a37bb194359ca1f975ab f7d80f7bba76d14c24324e3d228cc1f32cc263e7
xcb-util libxcb-util1_0.4.1-1_amd64.deb c242371fdfc806aa5599290150c6008a723c9b0fdb34ac6688f1a4083682172a 4cbc14f510c6ebf03bc1cec99e93f966c4be33c2
DEBS
for l in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 libxcb-keysyms.so.1 libxcb-render-util.so.0 libxcb-util.so.1; do
    cp -L "$WORK/xcb/usr/lib/x86_64-linux-gnu/$l" "$P6/Qt/lib/$l"
done

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
