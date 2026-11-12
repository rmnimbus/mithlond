"""Dialog for picking the game documents folder: every LOTRO documents folder found on this computer,
with what's in it, plus 'New folder…' and 'Browse…'."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .. import config
from ..config import DOCS_FOLDER_NAME, HOME, Settings
from .widgets import subtle


@dataclass
class Candidate:
    path: Path
    source: str
    last_played: float  # UserPreferences.ini mtime, 0 if none
    plugins: int
    songs: int
    link_target: Path | None


def _source(p: Path) -> str:
    parts = p.parts
    if "drive_c" in parts:
        return "Prefix " + str(Path(*parts[: parts.index("drive_c")])).replace(str(HOME), "~", 1)
    return "Home folder"


def candidates(s: Settings) -> list[Candidate]:
    paths = [HOME / "Documents" / DOCS_FOLDER_NAME]
    prefixes = {s.prefix_path(), *config.detect_prefixes()}
    for pfx in prefixes:
        users = pfx / "drive_c" / "users"
        if users.is_dir():
            paths += [u / "Documents" / DOCS_FOLDER_NAME for u in users.iterdir() if u.name.lower() != "public"]
    if s.docs_path:
        paths.append(s.docs_path)
    out, seen = [], set()
    for p in paths:
        if not p.is_dir() or p in seen:
            continue
        seen.add(p)
        prefs = p / "UserPreferences.ini"
        plugins_dir = config.find_case_insensitive(p, "Plugins")
        music_dir = config.find_case_insensitive(p, "Music")
        plugins = len({d.parent for d in plugins_dir.glob("*/*.plugin")}) if plugins_dir else 0
        songs = sum(1 for f in music_dir.rglob("*.abc")) if music_dir else 0
        target = p.resolve() if p.is_symlink() or p.parent.is_symlink() else None
        out.append(Candidate(p, _source(p), prefs.stat().st_mtime if prefs.exists() else 0, plugins, songs,
                             target if target and target != p else None))
    out.sort(key=lambda c: c.last_played, reverse=True)
    return out


class DocsChooser(QDialog):
    COLS = ["Folder", "Belongs to", "Last played", "Plugin folders", "Songs", "Links to"]

    def __init__(self, s: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose the game documents folder")
        self.resize(1000, 420)
        self.s = s
        self.chosen: Path | None = None
        self.items = candidates(s)

        self.table = QTableWidget(len(self.items), len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.setWordWrap(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(self.COLS)):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        current = s.docs_path
        for r, c in enumerate(self.items):
            when = dt.datetime.fromtimestamp(c.last_played).strftime("%Y-%m-%d %H:%M") if c.last_played else "never"
            vals = [str(c.path).replace(str(HOME), "~", 1) + ("   (current)" if c.path == current else ""),
                    c.source, when, str(c.plugins), f"{c.songs:,}",
                    str(c.link_target).replace(str(HOME), "~", 1) if c.link_target else ""]
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setToolTip(str(c.path) if col == 0 else v)
                if col in (3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, col, it)
            if c.path == current:
                self.table.selectRow(r)
        if not self.table.selectedItems() and self.items:
            self.table.selectRow(0)

        new_btn = QPushButton("New folder…")
        new_btn.setToolTip(f"Create an empty '{DOCS_FOLDER_NAME}' folder wherever you like")
        browse_btn = QPushButton("Browse…")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Use this folder")
        row = QHBoxLayout()
        row.addWidget(new_btn)
        row.addWidget(browse_btn)
        row.addStretch()
        row.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("LOTRO documents folders found on this computer (most recently played first):"))
        lay.addWidget(self.table, 1)
        lay.addWidget(subtle("Each Wine/Proton prefix has its own documents folder. The game starts with the one "
                             "you choose here, so your settings, plugins and songs stay together whatever the "
                             "prefix. 'Links to' means that folder is a link to another one."))
        lay.addLayout(row)

        self.table.doubleClicked.connect(lambda _: self._accept_selected())
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        new_btn.clicked.connect(self._new)
        browse_btn.clicked.connect(self._browse)

    def _accept_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        self.chosen = self.items[rows[0].row()].path
        self.accept()

    def _browse(self) -> None:
        start = str(self.s.docs_path or HOME / "Documents")
        d = QFileDialog.getExistingDirectory(self, "Choose the game documents folder", start)
        if d:
            self.chosen = Path(d)
            self.accept()

    def _new(self) -> None:
        parent = QFileDialog.getExistingDirectory(self, f"Where should the new '{DOCS_FOLDER_NAME}' folder go?",
                                                  str(HOME / "Documents"))
        if not parent:
            return
        p = Path(parent)
        target = p if p.name == DOCS_FOLDER_NAME else p / DOCS_FOLDER_NAME
        if target.exists() and any(target.iterdir()):
            if QMessageBox.question(self, "Folder exists", f"{target} already exists and isn't empty. Use it?") \
                    != QMessageBox.Yes:
                return
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "New folder", str(e))
            return
        self.chosen = target
        self.accept()
