"""Small reusable widgets."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class PathPicker(QWidget):
    """Line edit + Browse button, with an optional validator whose message is shown underneath."""

    changed = Signal(str)

    def __init__(self, directory: bool = True, validator: Callable[[Path], tuple[bool, str]] | None = None,
                 placeholder: str = "", file_filter: str = "", empty_ok: bool = False, parent=None):
        super().__init__(parent)
        self.empty_ok = empty_ok
        self.directory, self.validator, self.file_filter = directory, validator, file_filter
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.browse = QPushButton("Browse…")
        self.open_btn = QPushButton("Open")
        self.open_btn.setToolTip("Open in the file manager")
        self.status = QLabel()
        self.status.setWordWrap(True)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(self.browse)
        row.addWidget(self.open_btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addLayout(row)
        lay.addWidget(self.status)
        self.status.setVisible(validator is not None)
        self.browse.clicked.connect(self._browse)
        self.open_btn.clicked.connect(self._open)
        self.edit.editingFinished.connect(lambda: self._commit(self.edit.text()))

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, t: str, emit: bool = False) -> None:
        self.edit.setText(t)
        self.validate()
        if emit:
            self.changed.emit(self.text())

    def _commit(self, t: str) -> None:
        self.validate()
        self.changed.emit(t.strip())

    def validate(self) -> bool:
        if not self.validator:
            return True
        t = self.text()
        if not t and not self.empty_ok:
            ok, msg = False, "Not set"
        else:
            ok, msg = self.validator(Path(t).expanduser() if t else Path(""))
        self.status.setText(("✔ " if ok else "✘ ") + msg)
        self.status.setObjectName("ok" if ok else "bad")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        return ok

    def _browse(self) -> None:
        start = self.text() or str(Path.home())
        if self.directory:
            path = QFileDialog.getExistingDirectory(self, "Select folder", start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select file", start, self.file_filter)
        if path:
            self.edit.setText(path)
            self._commit(path)

    def _open(self) -> None:
        t = self.text()
        if t:
            p = Path(t).expanduser()
            open_path(p if p.is_dir() else p.parent)


def open_path(p: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def subtle(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setProperty("subtle", True)
    return lbl
