#!/bin/sh
# Install Mithlond for the current user (no root needed).
#   ./install.sh            install / update
#   ./install.sh --uninstall
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/mithlond/app"
BIN="$HOME/.local/bin/mithlond"
DESKTOP="$DATA/applications/mithlond.desktop"
ICON="$DATA/icons/hicolor/scalable/apps/mithlond.svg"

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$APP" "$BIN" "$DESKTOP" "$ICON"
    echo "Removed Mithlond. Settings (~/.config/mithlond) and the install log (~/.local/share/mithlond) were kept."
    exit 0
fi

PY_BIN="$(command -v python3)"
"$PY_BIN" - <<'PY'
import sys
missing = []
for mod, pkg in (("PySide6", "pyside6"), ("requests", "python-requests")):
    try:
        __import__(mod)
    except ImportError:
        missing.append(pkg)
if sys.version_info < (3, 11):
    sys.exit("Python 3.11 or newer is required")
if missing:
    sys.exit("Missing Python packages: " + " ".join(missing) + "  (e.g. pacman -S " + " ".join(missing) + ")")
PY
for tool in secret-tool bsdtar java; do
    command -v "$tool" >/dev/null 2>&1 || echo "note: optional '$tool' not found (see README)"
done

mkdir -p "$APP" "$(dirname "$BIN")" "$(dirname "$DESKTOP")" "$(dirname "$ICON")"
rm -rf "$APP/mithlond"
cp -r "$SRC/mithlond" "$APP/mithlond"
find "$APP" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$SRC/mithlond/resources/mithlond.svg" "$ICON"

cat > "$BIN" <<SH
#!/bin/sh
export PYTHONPATH="$APP\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PY_BIN" -m mithlond "\$@"
SH
chmod +x "$BIN"

cat > "$DESKTOP" <<DE
[Desktop Entry]
Type=Application
Name=Mithlond
GenericName=LOTRO Launcher
Comment=Play The Lord of the Rings Online, manage plugins and songs
Exec=$BIN
Icon=mithlond
Terminal=false
Categories=Game;
StartupWMClass=mithlond
DE
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$(dirname "$DESKTOP")" >/dev/null 2>&1 || true
echo "Installed. Start it from your menu (Mithlond) or run: $BIN"
