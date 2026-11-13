"""The 'Export logs…' action (Settings → About & updates, and the log panel)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from .. import diagnostics
from .context import AppContext
from .workers import run_task


def export_logs(parent: QWidget, ctx: AppContext) -> None:
    start = diagnostics.default_path()
    path, _ = QFileDialog.getSaveFileName(parent, "Export logs", str(start), "Zip archive (*.zip)")
    if not path:
        return
    dest = Path(path if path.endswith(".zip") else path + ".zip")
    ctx.log("Collecting logs…")

    def done(p: Path) -> None:
        ctx.log(f"Logs exported to {p}")
        box = QMessageBox(parent)
        box.setWindowTitle("Logs exported")
        box.setText(f"Saved <b>{p.name}</b> in {p.parent}.<br><br>Send this file to whoever helps you. Your user "
                    "name, account names, login tickets and e-mail addresses are removed; README.txt inside lists "
                    "what it contains.")
        open_btn = box.addButton("Open folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    def failed(e: Exception) -> None:
        ctx.log(f"Exporting logs failed: {e}")
        QMessageBox.warning(parent, "Export logs", f"Couldn't export the logs: {e}")

    run_task(lambda: diagnostics.export(ctx.settings, dest), done, failed)
