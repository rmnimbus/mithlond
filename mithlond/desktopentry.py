"""Mithlond's entry in the desktop's application menu (freedesktop .desktop file + icon).

The updater saves each release under its own name (Mithlond-X.Y.Z-x86_64.AppImage) and removes the old file, and
people move the AppImage around. So once the entry exists, Mithlond keeps it pointing at the AppImage it is
running from: at every start and right after an update. Only an entry Mithlond wrote itself is touched.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .config import APP_ID

MARK = "X-Mithlond-Managed=true"


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def entry_path() -> Path:
    return data_home() / "applications" / f"{APP_ID}.desktop"


def icon_path() -> Path:
    return data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"


def _quote(path: Path) -> str:
    """An Exec argument per the Desktop Entry spec: double quotes, with \\ " ` $ escaped."""
    return '"' + re.sub(r'([\\"`$])', r"\\\1", str(path)) + '"'


def render(appimage: Path) -> str:
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Mithlond",
        "GenericName=LOTRO Launcher",
        "Comment=Play The Lord of the Rings Online, manage plugins and songs",
        f"Exec={_quote(appimage)}",
        f"TryExec={appimage}",
        f"Icon={APP_ID}",
        "Terminal=false",
        "Categories=Game;",
        "Keywords=lotro;lord of the rings online;launcher;",
        f"StartupWMClass={APP_ID}",
        MARK,
        "",
    ])


def target() -> Path | None:
    """The AppImage the current entry starts, or None if there's no entry (or it isn't Mithlond's own)."""
    try:
        text = entry_path().read_text()
    except OSError:
        return None
    if MARK not in text:
        return None
    m = re.search(r"^TryExec=(.+)$", text, re.M)
    return Path(m.group(1)) if m else None


def install(appimage: Path) -> Path:
    """Write (or rewrite) the menu entry and its icon for this AppImage."""
    from importlib import resources
    icon = icon_path()
    icon.parent.mkdir(parents=True, exist_ok=True)
    icon.write_bytes(resources.files("mithlond").joinpath("resources/mithlond.svg").read_bytes())
    entry = entry_path()
    entry.parent.mkdir(parents=True, exist_ok=True)
    tmp = entry.with_suffix(".tmp")
    tmp.write_text(render(appimage))
    tmp.chmod(0o755)
    tmp.replace(entry)
    return entry


def refresh(appimage: Path | None) -> bool:
    """If Mithlond's own entry exists but starts another file (an update or a move), point it at `appimage`.
    Returns True if the entry was rewritten."""
    if appimage is None:
        return False
    current = target()
    if current is None or current == appimage:
        return False
    install(appimage)
    return True
