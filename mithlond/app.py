"""Entry point."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import APP_ID, APP_NAME, Settings, autodetect


def main() -> int:
    ap = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: LOTRO launcher for Linux")
    ap.add_argument("--version", action="version", version=__version__)
    ap.parse_args()

    from . import logfile
    logfile.install_crash_hooks()
    from .hostenv import isolate_bundled_qt
    isolate_bundled_qt()
    import PySide6
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication
    logfile.session_header(__version__, f"PySide6 {PySide6.__version__}, Qt {qVersion()}")

    from .ui import theme
    from .ui.context import AppContext
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    theme.apply(app)

    settings = Settings.load()
    notes = autodetect(settings)
    from . import desktopentry, selfupdate
    try:
        if desktopentry.refresh(selfupdate.running_appimage()):
            notes.append(f"Application menu entry now starts {selfupdate.running_appimage()}")
    except OSError:
        pass
    settings.save()
    ctx = AppContext(settings)
    win = MainWindow(ctx, notes)
    win.show()
    return app.exec()
