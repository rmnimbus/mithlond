"""Main window: tabs plus a collapsible log."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDockWidget, QMainWindow, QMessageBox, QPlainTextEdit, QTabWidget

from .. import __version__
from ..config import APP_NAME, check_game_dir
from .addons_tab import AddonsTab
from .companion_tab import CompanionTab
from .context import AppContext
from .play_tab import PlayTab
from .settings_tab import SettingsTab
from .songs_tab import SongsTab

ICON = Path(__file__).resolve().parent.parent / "resources" / "mithlond.svg"


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, notes: list[str]):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} — LOTRO launcher")
        self.setWindowIcon(QIcon(str(ICON)))
        self.resize(1040, 720)

        self.tabs = QTabWidget()
        self.play = PlayTab(ctx)
        self.addons = AddonsTab(ctx)
        self.songs = SongsTab(ctx)
        self.companion = CompanionTab(ctx)
        self.settings = SettingsTab(ctx)
        self.tabs.addTab(self.play, "Play")
        self.tabs.addTab(self.addons, "Downloads")
        self.tabs.addTab(self.songs, "Music")
        self.tabs.addTab(self.companion, "Companion")
        self.tabs.addTab(self.settings, "Settings")
        self.setCentralWidget(self.tabs)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        dock = QDockWidget("Log", self)
        dock.setObjectName("log")
        dock.setWidget(self.log)
        dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [110], Qt.Vertical)
        self.log_dock = dock
        ctx.log_line.connect(self.log.appendPlainText)

        ctx.log(f"{APP_NAME} {__version__}")
        for n in notes:
            ctx.log(f"Detected {n}")

        game = ctx.settings.game_path
        if not game or not check_game_dir(game)[0]:
            self.tabs.setCurrentWidget(self.settings)
            ctx.log("Choose your LOTRO game folder on the Settings tab")
        else:
            self.play.load_worlds()

    def closeEvent(self, e):
        if self.ctx.games:
            r = QMessageBox.question(self, "Quit", "The game is still running. Quit the launcher anyway?\n"
                                     "(The game keeps running; LotRO Companion is closed.)")
            if r != QMessageBox.Yes:
                e.ignore()
                return
        self.ctx.stop_companion()
        self.ctx.shutdown()
        super().closeEvent(e)
