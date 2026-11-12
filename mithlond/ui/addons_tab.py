"""Downloads tab: browse, install, update and remove plugins, skins and music packs from lotrointerface.com."""

from __future__ import annotations

import datetime as dt
import html
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QSplitter, QStyle, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

from .. import addons
from .context import AppContext
from .widgets import open_path, open_url
from .workers import run_task

KIND_LABEL = {"plugin": "Plugins", "skin": "Skins", "music": "Music packs"}
TARGET = {"plugin": "Plugins", "skin": "ui/skins", "music": "Music"}


@dataclass
class Row:
    remote: addons.RemoteAddon | None
    installed: addons.InstalledAddon | None

    @property
    def name(self) -> str:
        return (self.remote or self.installed).name  # type: ignore[union-attr]

    @property
    def update(self) -> bool:
        return bool(self.remote and self.installed and addons.is_newer(self.remote.version, self.installed.version))


class SortItem(QTableWidgetItem):
    def __init__(self, text: str, key=None):
        super().__init__(text)
        self.key = key if key is not None else text.lower()

    def __lt__(self, other):
        try:
            return self.key < other.key
        except TypeError:
            return str(self.key) < str(other.key)


class AddonPane(QWidget):
    COLS = ["Name", "Author", "Category", "Installed", "Latest", "Updated", "Downloads"]

    def __init__(self, ctx: AppContext, kind: str, parent=None):
        super().__init__(parent)
        self.ctx, self.kind = ctx, kind
        self.remote: list[addons.RemoteAddon] = []
        self.rows: list[Row] = []
        self._busy = False

        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search {KIND_LABEL[kind].lower()}…")
        self.show_filter = QComboBox()
        self.show_filter.addItems(["All", "Installed", "Updates available", "Not installed"])
        self.category = QComboBox()
        self.category.addItem("All categories")
        self.refresh = QPushButton("Refresh")
        self.refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.from_file = QPushButton("Install from file…")
        self.from_link = QPushButton("Install from link…")
        self.from_link.setToolTip("Install any addon from its lotrointerface.com page, even one that isn't in this list")
        top = QHBoxLayout()
        top.addWidget(self.search, 2)
        top.addWidget(self.show_filter)
        top.addWidget(self.category, 1)
        top.addWidget(self.refresh)
        top.addWidget(self.from_link)
        top.addWidget(self.from_file)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(self.COLS)):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.details)
        split.setSizes([420, 160])

        self.install_btn = QPushButton("Install")
        self.remove_btn = QPushButton("Uninstall")
        self.update_all = QPushButton("Update all")
        self.web_btn = QPushButton("lotrointerface page")
        self.folder_btn = QPushButton("Open folder")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.status = QLabel()
        bottom = QHBoxLayout()
        for b in (self.install_btn, self.remove_btn, self.update_all, self.web_btn, self.folder_btn):
            bottom.addWidget(b)
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.status, 1)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(bottom)

        self.search.textChanged.connect(self.fill)
        self.show_filter.currentIndexChanged.connect(self.fill)
        self.category.currentIndexChanged.connect(self.fill)
        self.refresh.clicked.connect(lambda: self.load(force=True))
        self.from_file.clicked.connect(self.install_from_file)
        self.from_link.clicked.connect(self.install_from_link)
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.doubleClicked.connect(lambda _: self.install_selected())
        self.install_btn.clicked.connect(self.install_selected)
        self.remove_btn.clicked.connect(self.uninstall_selected)
        self.update_all.clicked.connect(self.update_everything)
        self.web_btn.clicked.connect(self._open_web)
        self.folder_btn.clicked.connect(lambda: self.target() and open_path(self.target()))
        self._selection()

    # ---- data -------------------------------------------------------------------------
    def target(self) -> Path | None:
        return self.ctx.settings.subdir(TARGET[self.kind])

    def scan_installed(self) -> list[addons.InstalledAddon]:
        t = self.target()
        if t is None:
            return []
        return {"plugin": addons.scan_plugins, "skin": addons.scan_skins, "music": addons.scan_music}[self.kind](t)

    def load(self, force: bool = False) -> None:
        self.status.setText("Loading list from lotrointerface.com…")
        self.refresh.setEnabled(False)
        run_task(lambda: addons.fetch_feed(self.kind, force), on_done=self._loaded, on_error=self._load_failed)

    def _loaded(self, remote: list[addons.RemoteAddon]) -> None:
        self.remote = remote
        self.refresh.setEnabled(True)
        cats = sorted({r.category for r in remote if r.category})
        cur = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("All categories")
        self.category.addItems(cats)
        i = self.category.findText(cur)
        self.category.setCurrentIndex(max(i, 0))
        self.category.blockSignals(False)
        self.rescan()

    def _load_failed(self, e: Exception) -> None:
        self.refresh.setEnabled(True)
        self.status.setText(str(e))
        self.ctx.log(str(e))
        self.rescan()

    def rescan(self) -> None:
        if self.kind == "plugin" and self.target():
            adopted = addons.adopt_plugins(self.target())
            if adopted:
                self.ctx.log(f"Now managing {len(adopted)} existing plugin(s): {', '.join(adopted)}")
        installed = self.scan_installed()
        rows: list[Row] = []
        used: set[int] = set()
        by_id = {r.id: r for r in self.remote}
        for inst in installed:
            r = by_id.get(inst.id) if inst.id else addons.match_remote(inst, self.remote)
            if r is not None and id(r) in used:
                r = None
            if r is not None:
                used.add(id(r))
            rows.append(Row(r, inst))
        rows += [Row(r, None) for r in self.remote if id(r) not in used]
        self.rows = rows
        n_upd = sum(1 for r in rows if r.update)
        self.update_all.setText(f"Update all ({n_upd})" if n_upd else "Update all")
        self.update_all.setEnabled(n_upd > 0)
        self.fill()
        n_inst = sum(1 for r in rows if r.installed)
        self.status.setText(f"{n_inst} installed, {len(self.remote)} available")

    def fill(self) -> None:
        q = self.search.text().strip().lower()
        show = self.show_filter.currentIndex()
        cat = self.category.currentText() if self.category.currentIndex() > 0 else None
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        gold, green = QColor("#e0bd72"), QColor("#8fc77f")
        for idx, row in enumerate(self.rows):
            r, i = row.remote, row.installed
            if show == 1 and not i or show == 2 and not row.update or show == 3 and i:
                continue
            if cat and (not r or r.category != cat):
                continue
            if q and q not in f"{row.name} {(r or i).author} {r.category if r else ''}".lower():  # type: ignore[union-attr]
                continue
            n = self.table.rowCount()
            self.table.insertRow(n)
            updated = dt.datetime.fromtimestamp(r.updated).strftime("%Y-%m-%d") if r and r.updated else ""
            vals = [
                SortItem(row.name), SortItem((r or i).author),  # type: ignore[union-attr]
                SortItem(r.category if r else "(not on lotrointerface)"),
                SortItem(i.version or "✔" if i else ""), SortItem(r.version if r else ""),
                SortItem(updated, r.updated if r else 0), SortItem(f"{r.downloads:,}" if r else "", r.downloads if r else 0),
            ]
            vals[0].setData(Qt.UserRole, idx)
            for c, it in enumerate(vals):
                if row.update:
                    it.setForeground(gold)
                elif i:
                    it.setForeground(green)
                self.table.setItem(n, c, it)
        self.table.setSortingEnabled(True)
        self._selection()

    def selected_rows(self) -> list[Row]:
        idxs = {self.table.item(i.row(), 0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows()}
        return [self.rows[i] for i in sorted(idxs)]

    def _selection(self) -> None:
        rows = self.selected_rows()
        can_install = any(r.remote and (not r.installed or r.update) for r in rows)
        reinstall = any(r.remote and r.installed and not r.update for r in rows)
        self.install_btn.setText("Update" if any(r.update for r in rows) else ("Reinstall" if reinstall and not can_install else "Install"))
        self.install_btn.setEnabled(not self._busy and any(r.remote for r in rows))
        self.remove_btn.setEnabled(not self._busy and any(r.installed for r in rows))
        self.web_btn.setEnabled(len(rows) == 1 and rows[0].remote is not None)
        if len(rows) == 1:
            self._show_details(rows[0])
        else:
            self.details.setHtml(f"<i>{len(rows)} selected</i>" if rows else "")

    def _show_details(self, row: Row) -> None:
        r, i = row.remote, row.installed
        parts = [f"<h3>{html.escape(row.name)}</h3>"]
        meta = []
        if (r or i).author:  # type: ignore[union-attr]
            meta.append(f"by {html.escape((r or i).author)}")  # type: ignore[union-attr]
        if i:
            meta.append(f"installed {html.escape(i.version or '(unknown version)')}")
            if i.path:
                meta.append(f"<span style='color:#9a9282'>{html.escape(i.path)}</span>")
        if r:
            meta.append(f"latest {html.escape(r.version)}")
            meta.append(f"<a href='{r.info_url}'>lotrointerface.com</a>")
        parts.append(" · ".join(meta))
        if i and i.dependencies:
            parts.append(f"<p>Requires: {html.escape(', '.join(i.dependencies))}</p>")
        if r and r.description:
            parts.append("<p style='white-space:pre-wrap'>" + html.escape(r.description.strip()) + "</p>")
        self.details.setHtml("".join(parts))

    def _open_web(self) -> None:
        rows = self.selected_rows()
        if rows and rows[0].remote:
            open_url(rows[0].remote.info_url)

    # ---- actions ------------------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.setVisible(busy)
        for w in (self.refresh, self.from_file, self.from_link, self.update_all):
            w.setEnabled(not busy)
        self._selection()

    def _check_target(self) -> Path | None:
        t = self.target()
        if t is None or not self.ctx.settings.docs_path or not self.ctx.settings.docs_path.is_dir():
            QMessageBox.warning(self, "Documents folder", "Set your LOTRO documents folder on the Settings tab first.")
            return None
        return t

    def _install(self, items: list[addons.RemoteAddon], local_files: dict[str, Path] | None = None) -> None:
        target = self._check_target()
        if target is None or not items:
            return
        self._set_busy(True)
        installed_ids = {r.installed.id for r in self.rows if r.installed and r.installed.id}
        by_id = {r.id: r for r in self.remote}

        def work(progress):
            done, notes, queue, seen = [], [], list(items), set()
            while queue:
                a = queue.pop(0)
                if a.id in seen:
                    continue
                seen.add(a.id)
                progress(("label", f"Downloading {a.name}…"))
                if local_files and a.id in local_files:
                    archive = local_files[a.id]
                else:
                    archive = addons.download(a, lambda d, t: progress(("bytes", d, t)))
                progress(("label", f"Installing {a.name}…"))
                files = addons.install_archive(self.kind, archive, a, target)
                done.append(a.name)
                if self.kind == "plugin":
                    for dep in addons.dependencies_of(files, target):
                        if dep in installed_ids or dep in seen:
                            continue
                        if dep in by_id:
                            notes.append(f"{by_id[dep].name} (needed by {a.name})")
                            queue.append(by_id[dep])
                        else:
                            notes.append(f"dependency #{dep} of {a.name} is not on lotrointerface; install it by hand")
            return done, notes

        def prog(p):
            if p[0] == "label":
                self.status.setText(p[1])
                self.progress.setRange(0, 0)
            else:
                _, d, t = p
                if t:
                    self.progress.setRange(0, t)
                    self.progress.setValue(min(d, t))

        def done(res):
            names, notes = res
            self._set_busy(False)
            self.ctx.log(f"Installed: {', '.join(names)}" + (f"; also: {'; '.join(notes)}" if notes else ""))
            self.rescan()
            self.status.setText(f"Installed {', '.join(names)}" + (f" (+ {len(notes)} dependencies)" if notes else ""))
            if self.kind == "music":
                self.ctx.music_changed.emit()

        def fail(e):
            self._set_busy(False)
            self.rescan()
            self.status.setText(f"Failed: {e}")
            self.ctx.log(f"Install failed: {e}")
            QMessageBox.warning(self, "Install failed", str(e))

        run_task(work, on_done=done, on_error=fail, on_progress=prog)

    def install_selected(self) -> None:
        self._install([r.remote for r in self.selected_rows() if r.remote])

    def update_everything(self) -> None:
        self._install([r.remote for r in self.rows if r.update and r.remote])

    def install_from_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Install from archive", str(Path.home() / "Downloads"),
                                                "Archives (*.zip *.rar *.7z);;All files (*)")
        if not paths:
            return
        items, files = [], {}
        for p in map(Path, paths):
            a = addons.local_addon(p, self.kind)
            items.append(a)
            files[a.id] = p
        self._install(items, files)

    def install_from_link(self) -> None:
        text, ok = QInputDialog.getText(self, "Install from link",
                                        "lotrointerface.com link or addon number, e.g.\n"
                                        "https://www.lotrointerface.com/downloads/info1218-.html")
        if not ok or not text.strip():
            return
        self.status.setText("Looking it up on lotrointerface.com…")

        def found(a):
            known = next((r for r in self.remote if r.id == a.id), None)
            self._install([known or a])

        def failed(e):
            self.status.setText(str(e))
            QMessageBox.warning(self, "Install from link", str(e))

        run_task(lambda: addons.addon_from_link(text, self.kind), on_done=found, on_error=failed)

    def uninstall_selected(self) -> None:
        target = self._check_target()
        rows = [r for r in self.selected_rows() if r.installed]
        if target is None or not rows:
            return
        names = "\n".join(f"  • {r.name}" for r in rows)
        if QMessageBox.question(self, "Uninstall", f"Remove these from {target}?\n\n{names}\n\n"
                                "Their saved settings in PluginData are kept.") != QMessageBox.Yes:
            return
        errors = []
        for r in rows:
            try:
                addons.uninstall(r.installed, target)
                self.ctx.log(f"Uninstalled {r.name}")
            except (addons.AddonError, OSError) as e:
                errors.append(f"{r.name}: {e}")
        self.rescan()
        if errors:
            QMessageBox.warning(self, "Uninstall", "\n".join(errors))
        if self.kind == "music":
            self.ctx.music_changed.emit()


class AddonsTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.panes = {k: AddonPane(ctx, k) for k in ("plugin", "skin", "music")}
        for k, p in self.panes.items():
            self.tabs.addTab(p, KIND_LABEL[k])
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        self._loaded: set[str] = set()
        self.tabs.currentChanged.connect(self._ensure_loaded)
        ctx.settings_changed.connect(lambda: [p.rescan() for k, p in self.panes.items() if k in self._loaded])

    def _ensure_loaded(self) -> None:
        k = list(self.panes)[self.tabs.currentIndex()]
        if k not in self._loaded:
            self._loaded.add(k)
            self.panes[k].load()

    def showEvent(self, e):  # load lazily the first time the tab is opened
        super().showEvent(e)
        self._ensure_loaded()
