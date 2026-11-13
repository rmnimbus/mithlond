"""Main window: tabs plus a collapsible log."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDockWidget, QMainWindow, QMessageBox, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..config import APP_NAME, check_game_dir
from .companion_tab import CompanionTab
from .context import AppContext
from .effects_tab import VisualEffectsTab
from .game_settings_tab import GameSettingsTab
from .keybindings_tab import KeybindingsTab
from .layout_tab import LayoutTab
from .play_tab import PlayTab
from .plugins_tab import PluginsTab
from .settings_tab import SettingsTab
from .songs_tab import SongsTab
from .updater import UpdateBanner, UpdateController

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
        self.game_settings = GameSettingsTab(ctx)
        self.effects = VisualEffectsTab(ctx)
        self.layouts = LayoutTab(ctx)
        self.keys = KeybindingsTab(ctx)
        self.plugins = PluginsTab(ctx)
        self.songs = SongsTab(ctx)
        self.companion = CompanionTab(ctx)
        self.settings = SettingsTab(ctx)
        self.tabs.addTab(self.play, "Play")
        self.tabs.addTab(self.game_settings, "In game settings")
        self.tabs.addTab(self.effects, "Visual effects")
        self.tabs.addTab(self.layouts, "Layouts")
        self.tabs.addTab(self.keys, "Key bindings")
        self.tabs.addTab(self.plugins, "Plugins")
        self.tabs.addTab(self.songs, "Music")
        self.tabs.addTab(self.companion, "LotRO Companion")
        self.tabs.addTab(self.settings, "Settings")
        self.update_banner = UpdateBanner()
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)
        cl.addWidget(self.update_banner)
        cl.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.updater = UpdateController(ctx, self, self.update_banner)
        self.settings.attach_updater(self.updater)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        dock = QDockWidget("Log", self)
        dock.setObjectName("log")
        dock.setWidget(self.log)
        dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        # title bar: "Log", Export logs…, close
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton
        from .export_logs import export_logs
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(6, 2, 4, 2)
        bl.addWidget(QLabel("Log"))
        bl.addStretch()
        exp = QPushButton("Export logs…")
        exp.setToolTip("Save the logs and a setup summary as a zip for a bug report (personal data removed)")
        exp.clicked.connect(lambda: export_logs(self, ctx))
        close = QToolButton()
        close.setText("✕")
        close.setAutoRaise(True)
        close.clicked.connect(dock.close)
        bl.addWidget(exp)
        bl.addWidget(close)
        dock.setTitleBarWidget(bar)
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
        self.updater.check_at_startup()

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
