"""Mithlond self-update UI: startup check, the 'update available' banner, and the update/restart flow."""

from __future__ import annotations

import html
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressDialog, QPushButton, QTextBrowser,
    QVBoxLayout, QDialog, QDialogButtonBox,
)

from .. import __version__, selfupdate
from ..hostenv import host_env
from .context import AppContext
from .theme import GOLD
from .widgets import open_url
from .workers import run_task


class UpdateBanner(QFrame):
    """Thin bar above the tabs: 'Mithlond X is available — Update now / What's new / Skip / ×'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("updateBanner")
        self.setStyleSheet(f"QFrame#updateBanner {{ background: #3a3020; border: 1px solid {GOLD}; border-radius: 6px; }}")
        self.text = QLabel()
        self.update_btn = QPushButton("Update now")
        self.notes_btn = QPushButton("What's new")
        self.skip_btn = QPushButton("Skip this version")
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedWidth(34)
        self.close_btn.setToolTip("Hide until next start")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        lay.addWidget(self.text, 1)
        for b in (self.update_btn, self.notes_btn, self.skip_btn, self.close_btn):
            lay.addWidget(b)
        self.hide()


class UpdateController(QObject):
    status = Signal(str)  # human-readable state for the Settings tab

    def __init__(self, ctx: AppContext, window, banner: UpdateBanner):
        super().__init__(window)
        self.ctx, self.window, self.banner = ctx, window, banner
        self.release: selfupdate.Release | None = None
        self._busy = False
        banner.update_btn.clicked.connect(self.start_update)
        banner.notes_btn.clicked.connect(self.show_notes)
        banner.skip_btn.clicked.connect(self._skip)
        banner.close_btn.clicked.connect(banner.hide)

    # ---- checking ---------------------------------------------------------------------------
    def check_at_startup(self) -> None:
        if self.ctx.settings.check_updates_on_start:
            QTimer.singleShot(2000, lambda: self.check(manual=False))

    def check(self, manual: bool = True) -> None:
        if self._busy:
            return
        self._busy = True
        self.status.emit("Checking GitHub for a newer Mithlond…")

        def done(rel: selfupdate.Release):
            self._busy = False
            self.release = rel
            if not selfupdate.is_newer(rel.version):
                self.status.emit(f"You have the latest version ({__version__}).")
                self.ctx.log(f"Mithlond is up to date ({__version__})")
                if manual:
                    QMessageBox.information(self.window, "Mithlond", f"You have the latest version ({__version__}).")
                return
            self.status.emit(f"Mithlond {rel.version} is available (you have {__version__}).")
            self.ctx.log(f"Mithlond {rel.version} is available (you have {__version__})")
            if manual:
                self.start_update()
            elif rel.version != self.ctx.settings.skipped_version:
                self.banner.text.setText(f"<b>Mithlond {html.escape(rel.version)}</b> is available "
                                         f"(you have {__version__}).")
                self.banner.show()

        def failed(e):
            self._busy = False
            self.status.emit(str(e))
            self.ctx.log(str(e))
            if manual:
                QMessageBox.warning(self.window, "Mithlond", str(e))

        run_task(selfupdate.latest_release, on_done=done, on_error=failed)

    def _skip(self) -> None:
        if self.release:
            self.ctx.settings.skipped_version = self.release.version
            self.ctx.save()
            self.ctx.log(f"Won't remind about Mithlond {self.release.version} again")
        self.banner.hide()

    def show_notes(self) -> None:
        if not self.release:
            return
        dlg = QDialog(self.window)
        dlg.setWindowTitle(f"What's new in Mithlond {self.release.version}")
        dlg.resize(640, 460)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setMarkdown(self.release.notes or "_No release notes._")
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        page = buttons.addButton("Open on GitHub", QDialogButtonBox.ActionRole)
        page.clicked.connect(lambda: open_url(self.release.page))
        buttons.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addWidget(view)
        lay.addWidget(buttons)
        dlg.exec()

    # ---- updating ---------------------------------------------------------------------------
    def start_update(self) -> None:
        rel = self.release
        if rel is None or not selfupdate.is_newer(rel.version):
            return
        ok, why = selfupdate.can_self_update()
        if not ok:
            if QMessageBox.question(self.window, "Update Mithlond",
                                    f"Mithlond {rel.version} is available.\n\n{why}\n\nOpen the download page?") \
                    == QMessageBox.Yes:
                open_url(rel.page)
            return
        current = selfupdate.running_appimage()
        if QMessageBox.question(self.window, "Update Mithlond",
                                f"Update Mithlond {__version__} → {rel.version}?\n\n"
                                f"The new AppImage ({rel.asset_size / 1048576:.0f} MB) is downloaded from GitHub, "
                                f"checked, and replaces\n{current}.") != QMessageBox.Yes:
            return
        dlg = QProgressDialog(f"Downloading Mithlond {rel.version}…", "", 0, 0, self.window)
        dlg.setWindowTitle("Update Mithlond")
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()

        def prog(p):
            d, t = p
            if t:
                dlg.setMaximum(t)
                dlg.setValue(min(d, t))

        def done(new_path: Path):
            dlg.close()
            self.banner.hide()
            self.ctx.log(f"Mithlond updated to {rel.version}: {new_path}")
            self.status.emit(f"Updated to {rel.version}. Restart Mithlond to use it.")
            if QMessageBox.question(self.window, "Update Mithlond",
                                    f"Mithlond {rel.version} is installed:\n{new_path}\n\nRestart now?") \
                    == QMessageBox.Yes:
                self.restart(new_path)

        def failed(e):
            dlg.close()
            self.ctx.log(f"Mithlond update failed: {e}")
            self.status.emit(f"Update failed: {e}")
            QMessageBox.warning(self.window, "Update Mithlond", str(e))

        run_task(lambda progress: selfupdate.update(rel, lambda d, t: progress((d, t))),
                 on_done=done, on_error=failed, on_progress=prog)

    def restart(self, new_path: Path) -> None:
        if not self.window.close():  # asks first if a game is still running
            return
        subprocess.Popen([str(new_path)], env=host_env(), start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        QApplication.quit()
