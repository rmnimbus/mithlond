"""The environment to hand to external programs (wine, umu-run, java, secret-tool, bsdtar, xdg-open).

Inside the AppImage, Mithlond runs on its own bundled Python and Qt. Variables that would make the bundled Qt
load the host's Qt plugins are removed from our own process at startup. External programs, on the other hand,
must see the user's original environment, without the AppImage runtime's own variables.
"""

from __future__ import annotations

import os

APPIMAGE_VARS = ("APPDIR", "APPIMAGE", "ARGV0", "OWD", "MITHLOND_APPIMAGE")
# Host Qt settings that can crash or confuse a different Qt build.
QT_HOST_VARS = ("QT_PLUGIN_PATH", "QT_QPA_PLATFORMTHEME", "QML2_IMPORT_PATH", "QML_IMPORT_PATH", "QT_STYLE_OVERRIDE")

_removed: dict[str, str] = {}


def in_appimage() -> bool:
    return bool(os.environ.get("MITHLOND_APPIMAGE"))


def isolate_bundled_qt() -> None:
    """Call before importing PySide6."""
    if in_appimage():
        for k in QT_HOST_VARS:
            if k in os.environ:
                _removed[k] = os.environ.pop(k)


def host_env() -> dict[str, str]:
    env = {**os.environ, **_removed}
    for k in APPIMAGE_VARS:
        env.pop(k, None)
    return env
