"""Plugins tab: Get plugins (lotrointerface.com), Load plugins (which characters auto-load which plugin, per
server, with named sets), Plugin errors (the game's Script.log) and Skins."""

from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout,
    QWidget,
)

from .. import addons, pluginload, procs
from ..gameprefs import latest_backup
from ..pluginload import Autoload
from .addons_tab import AddonPane, SortItem
from .context import AppContext
from .widgets import open_path, subtle

GREY = QColor("#9a9282")


class CharacterPopup(QFrame):
    """The small menu that opens on a plugin: 'All characters' or a tick per known character."""

    def __init__(self, parent: QWidget, characters: list[str], state: Autoload, on_done):
        super().__init__(parent, Qt.Popup)
        self.setFrameShape(QFrame.StyledPanel)
        self.on_done = on_done
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        self.all = QCheckBox("All characters")
        self.all.setChecked(state.all)
        lay.addWidget(self.all)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        lay.addWidget(line)
        self.boxes: dict[str, QCheckBox] = {}
        for c in characters:
            b = QCheckBox(c)
            b.setChecked(not state.all and c in state.characters)
            b.toggled.connect(self._char_toggled)
            lay.addWidget(b)
            self.boxes[c] = b
        if not characters:
            lay.addWidget(subtle("No characters known on this server yet.\nUse 'Add character…' above."))
        self.all.toggled.connect(self._all_toggled)

    def _all_toggled(self, on: bool) -> None:
        if on:
            for b in self.boxes.values():
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)

    def _char_toggled(self, on: bool) -> None:
        if on and self.all.isChecked():
            self.all.blockSignals(True)
            self.all.setChecked(False)
            self.all.blockSignals(False)

    def result(self) -> Autoload:
        if self.all.isChecked():
            return Autoload(True, [])
        return Autoload(False, [c for c, b in self.boxes.items() if b.isChecked()])

    def hideEvent(self, e):
        super().hideEvent(e)
        cb, self.on_done = self.on_done, None
        if cb:
            cb(self.result())
        self.deleteLater()


class LoadPluginsPane(QWidget):
    COLS = ["Plugin", "Loads on", "Package", "Author", "Version"]

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.game_running = False
        self.path: Path | None = None
        self.key = ""                       # "<account>/<server>"
        self.saved: dict[str, Autoload] = {}
        self.current: dict[str, Autoload] = {}
        self.plugins: list[pluginload.Loadable] = []
        self.sets = pluginload.load_sets()

        self.server = QComboBox()
        self.server.setMinimumWidth(160)
        self.add_char = QPushButton("Add character…")
        self.add_char.setToolTip("Characters appear here by themselves once they've loaded a plugin on this "
                                 "computer. Add others (for example on a server you haven't played here) by name.")
        self.set_combo = QComboBox()
        self.set_combo.setMinimumWidth(160)
        self.set_combo.setPlaceholderText("Saved sets")
        self.load_set = QPushButton("Load set")
        self.save_set = QPushButton("Save as set…")
        self.delete_set = QPushButton("Delete set")
        top = QHBoxLayout()
        top.addWidget(QLabel("Server:"))
        top.addWidget(self.server)
        top.addWidget(self.add_char)
        top.addStretch()
        top.addWidget(QLabel("Set:"))
        top.addWidget(self.set_combo)
        top.addWidget(self.load_set)
        top.addWidget(self.save_set)
        top.addWidget(self.delete_set)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search plugins…")
        self.show_helpers = QCheckBox("Show helper plugins")
        self.show_helpers.setToolTip("Parts of other plugins whose authors say not to auto-load them "
                                     "(for example MoorMap's MMCust). Hidden unless one is set to load.")
        row2 = QHBoxLayout()
        row2.addWidget(self.search, 1)
        row2.addWidget(self.show_helpers)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        h = self.table.horizontalHeader()
        for i in range(len(self.COLS)):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)  # Package

        self.state = QLabel()
        self.state.setWordWrap(True)
        self.save_btn = QPushButton("Save")
        self.discard_btn = QPushButton("Discard changes")
        self.restore_btn = QPushButton("Restore backup")
        self.folder_btn = QPushButton("Open folder")
        bottom = QHBoxLayout()
        bottom.addWidget(self.state, 1)
        for b in (self.save_btn, self.discard_btn, self.restore_btn, self.folder_btn):
            bottom.addWidget(b)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(subtle("Click a plugin to choose who loads it automatically. The game reads this list "
                             "when a character enters the world; /plugins load works for anything else."))
        lay.addLayout(row2)
        lay.addWidget(self.table, 1)
        lay.addLayout(bottom)

        self.server.currentIndexChanged.connect(self._server_changed)
        self.add_char.clicked.connect(self._add_character)
        self.load_set.clicked.connect(self._load_set)
        self.save_set.clicked.connect(self._save_set)
        self.delete_set.clicked.connect(self._delete_set)
        self.set_combo.currentIndexChanged.connect(lambda _i: self._update_buttons())
        self.search.textChanged.connect(self.fill)
        self.show_helpers.toggled.connect(self.fill)
        self.table.cellClicked.connect(self._clicked)
        self.save_btn.clicked.connect(self.save)
        self.discard_btn.clicked.connect(self._discard)
        self.restore_btn.clicked.connect(self.restore)
        self.folder_btn.clicked.connect(lambda: self.path and open_path(self.path.parent))
        ctx.settings_changed.connect(self.reload)
        ctx.games_changed.connect(lambda _n: self._check_game())
        self._timer = QTimer(self)  # the game rewrites the file: check for it only while this page is shown
        self._timer.setInterval(4000)
        self._timer.timeout.connect(self._check_game)
        self._fill_sets()
        self.reload()

    # ---- data ------------------------------------------------------------------------------------
    def _plugindata(self) -> Path | None:
        return self.ctx.settings.subdir("PluginData")

    def reload(self) -> None:
        """Re-read servers and installed plugins (keeps the selected server)."""
        keep = self.server.currentData()
        found = pluginload.servers(self._plugindata())
        extra = [tuple(k.split("/", 1)) for k in self.ctx.settings.known_characters if "/" in k]
        pairs = sorted(set(found) | {p for p in extra if len(p) == 2}, key=lambda p: (p[0].lower(), p[1].lower()))
        many_accounts = len({a for a, _ in pairs}) > 1
        self.server.blockSignals(True)
        self.server.clear()
        for acc, srv in pairs:
            self.server.addItem(f"{srv}  ({acc})" if many_accounts else srv, f"{acc}/{srv}")
        i = self.server.findData(keep) if keep else 0
        self.server.setCurrentIndex(max(i, 0))
        self.server.blockSignals(False)
        plugins_dir = self.ctx.settings.subdir("Plugins")
        packages = {}
        if plugins_dir:
            for a in addons.scan_plugins(plugins_dir):
                for d in a.descriptors:
                    packages[d.lower()] = a.name
        self.plugins = pluginload.loadables(plugins_dir, packages) if plugins_dir else []
        self._server_changed()

    def _server_changed(self, *_, reread: bool = False):
        key = self.server.currentData() or ""
        if key == self.key and self._dirty() and not reread:  # re-read (page shown again): keep the unsaved choices
            self.fill()
            return
        if key != self.key and self._dirty() and not self._confirm_drop():
            i = self.server.findData(self.key)
            self.server.blockSignals(True)
            self.server.setCurrentIndex(max(i, 0))
            self.server.blockSignals(False)
            return
        self.key = key
        pd = self._plugindata()
        self.path = pd / key / pluginload.FILE if pd and key else None
        self.saved = pluginload.read(self.path) if self.path else {}
        self.current = {n: Autoload(a.all, list(a.characters)) for n, a in self.saved.items()}
        self.fill()

    def characters(self) -> list[str]:
        pd = self._plugindata()
        if not pd or not self.key:
            return []
        return pluginload.characters(pd / self.key, self.current, self.ctx.settings.known_characters.get(self.key, []))

    def _dirty(self) -> bool:
        norm = lambda d: {n: (a.all, tuple(sorted(a.characters))) for n, a in d.items() if a.all or a.characters}
        return norm(self.saved) != norm(self.current)

    def _confirm_drop(self) -> bool:
        return QMessageBox.question(self, "Unsaved changes", "Drop the changes you haven't saved for "
                                    f"{self.key.split('/')[-1]}?") == QMessageBox.Yes

    # ---- table -----------------------------------------------------------------------------------
    def fill(self) -> None:
        q = self.search.text().strip().lower()
        unique: dict[str, pluginload.Loadable] = {}  # the game loads by name: one row per name
        for p in self.plugins:
            if p.name not in unique or (p.package and not unique[p.name].package):
                unique[p.name] = p
        installed = set(unique)
        rows = list(unique.items())
        rows += [(n, None) for n in self.current if n not in installed]  # set to load but not installed
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for name, p in rows:
            a = self.current.get(name, Autoload())
            if p and p.helper and not (a.all or a.characters) and not self.show_helpers.isChecked():
                continue
            if q and q not in f"{name} {p.package if p else ''} {p.author if p else ''}".lower():
                continue
            n = self.table.rowCount()
            self.table.insertRow(n)
            loads = SortItem(a.label(), (0 if a.all else 1 if a.characters else 2, a.label().lower()))
            if len(a.characters) > 1:
                loads.setToolTip("\n".join(a.characters))
            vals = [SortItem(name), loads, SortItem(p.package if p else "(not installed)"),
                    SortItem(p.author if p else ""), SortItem(p.version if p else "")]
            vals[0].setData(Qt.UserRole, name)
            if p and p.description:
                vals[0].setToolTip(p.description[:400])
            old = self.saved.get(name, Autoload())
            changed = (old.all, sorted(old.characters)) != (a.all, sorted(a.characters))
            for c, it in enumerate(vals):
                if p is None or (p.helper and c == 0):
                    it.setForeground(GREY)
                if not (a.all or a.characters) and c == 1:
                    it.setForeground(GREY)
                if changed:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.table.setItem(n, c, it)
        self.table.setSortingEnabled(True)
        self._update_buttons()

    def _clicked(self, row: int, _col: int) -> None:
        name = self.table.item(row, 0).data(Qt.UserRole)
        if not self.key:
            return
        rect = self.table.visualRect(self.table.model().index(row, 1))
        pos = self.table.viewport().mapToGlobal(QPoint(rect.left(), rect.bottom()))

        def done(result: Autoload) -> None:
            if result.all or result.characters:
                self.current[name] = result
            else:
                self.current.pop(name, None)
            QTimer.singleShot(0, self.fill)  # after the popup has gone

        popup = CharacterPopup(self, self.characters(), self.current.get(name, Autoload()), done)
        popup.move(pos)
        popup.show()

    # ---- characters and sets ---------------------------------------------------------------------
    def _add_character(self) -> None:
        if not self.key:
            QMessageBox.information(self, "Add character", "No server found yet: start the game once with "
                                    "plugins, or check the documents folder in Settings.")
            return
        name, ok = QInputDialog.getText(self, "Add character",
                                        f"Character name on {self.key.split('/')[-1]}:")
        name = name.strip()
        if ok and name:
            known = self.ctx.settings.known_characters.setdefault(self.key, [])
            if name.lower() not in {c.lower() for c in self.characters()}:
                known.append(name)
                self.ctx.settings.save()
                self.ctx.log(f"Added character {name} on {self.key.split('/')[-1]}")

    def _fill_sets(self, select: str = "") -> None:
        self.set_combo.blockSignals(True)
        self.set_combo.clear()
        self.set_combo.addItems(sorted(self.sets, key=str.lower))
        self.set_combo.setCurrentIndex(self.set_combo.findText(select) if select else -1)
        self.set_combo.blockSignals(False)
        self._update_buttons()

    def _save_set(self) -> None:
        name, ok = QInputDialog.getText(self, "Save as set", "Name for this set of plugins:",
                                        text=self.set_combo.currentText())
        name = name.strip()
        if not ok or not name:
            return
        if name in self.sets and QMessageBox.question(self, "Save as set", f"Replace the set '{name}'?") != QMessageBox.Yes:
            return
        self.sets[name] = {n: Autoload(a.all, list(a.characters)) for n, a in self.current.items()}
        pluginload.save_sets(self.sets)
        self._fill_sets(name)
        self.ctx.log(f"Saved plugin set '{name}' ({len(self.sets[name])} plugins)")

    def _load_set(self) -> None:
        name = self.set_combo.currentText()
        if name not in self.sets:
            return
        self.current = {n: Autoload(a.all, list(a.characters)) for n, a in self.sets[name].items()}
        self.fill()
        self.state.setText(f"Loaded the set '{name}'. Press Save to use it on "
                           f"{self.key.split('/')[-1]}.")

    def _delete_set(self) -> None:
        name = self.set_combo.currentText()
        if name in self.sets and QMessageBox.question(self, "Delete set", f"Delete the set '{name}'?") == QMessageBox.Yes:
            del self.sets[name]
            pluginload.save_sets(self.sets)
            self._fill_sets()

    # ---- state and saving ------------------------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        self._check_game()
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _check_game(self) -> None:
        self.game_running = bool(procs.game_clients())
        self._update_buttons()

    def _update_buttons(self) -> None:
        dirty = self._dirty()
        has_set = self.set_combo.currentIndex() >= 0
        self.load_set.setEnabled(has_set and bool(self.key))
        self.delete_set.setEnabled(has_set)
        self.save_set.setEnabled(bool(self.key))
        if self.game_running:
            self.state.setText("✘ The game is running. It rewrites this list itself, so changes can only be "
                               "saved while it's closed. Use the game's plugin manager for now.")
            self.state.setObjectName("bad")
        elif not self.key:
            self.state.setText("No PluginData folder with a server yet. It appears after you've played once "
                               "with plugins (or set the documents folder in Settings).")
            self.state.setObjectName("")
        elif dirty:
            self.state.setText("Changes not saved yet (shown in bold).")
            self.state.setObjectName("")
        elif not self.state.text().startswith("Loaded the set"):
            self.state.setText("Changes apply the next time a character enters the world.")
            self.state.setObjectName("")
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)
        self.save_btn.setEnabled(dirty and not self.game_running and bool(self.path))
        self.discard_btn.setEnabled(dirty)
        self.restore_btn.setEnabled(bool(self.path) and not self.game_running
                                    and self.path is not None and latest_backup(self.path) is not None)
        self.folder_btn.setEnabled(bool(self.path and self.path.parent.is_dir()))

    def save(self) -> None:
        if self.game_running or not self.path:
            return
        try:
            b = pluginload.save(self.path, self.current)
        except OSError as e:
            QMessageBox.warning(self, "Save", f"Couldn't save {self.path}: {e}")
            return
        self.ctx.log(f"Saved plugin loading for {self.key.split('/')[-1]}" + (f" (previous: {b.name})" if b else ""))
        self.state.setText("")
        self._server_changed(reread=True)

    def _discard(self) -> None:
        self.state.setText("")
        self.current = {n: Autoload(a.all, list(a.characters)) for n, a in self.saved.items()}
        self.fill()

    def restore(self) -> None:
        b = latest_backup(self.path) if self.path else None
        if not b or self.game_running:
            return
        if QMessageBox.question(self, "Restore backup", f"Put back the plugin list from {b.name}?\nThe current "
                                "file is kept as a backup too.") != QMessageBox.Yes:
            return
        text = b.read_bytes()
        pluginload.backup(self.path)
        self.path.write_bytes(text)
        self.ctx.log(f"Restored {self.path.name} from {b.name}")
        self._server_changed(reread=True)


class PluginErrorsPane(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Plugin", "Error"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.detail = QTextBrowser()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setSizes([300, 120])
        self.refresh_btn = QPushButton("Refresh")
        self.open_btn = QPushButton("Open Script.log")
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(self.refresh_btn)
        bottom.addWidget(self.open_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(split, 1)
        lay.addLayout(bottom)
        self.errors: list[pluginload.ScriptError] = []
        self.refresh_btn.clicked.connect(self.refresh)
        self.open_btn.clicked.connect(lambda: self.path() and self.path().exists() and open_path(self.path()))
        self.table.itemSelectionChanged.connect(self._show)
        ctx.settings_changed.connect(self.refresh)

    def path(self) -> Path | None:
        d = self.ctx.settings.docs_path
        return d / "Script.log" if d else None

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    def refresh(self) -> None:
        p = self.path()
        self.errors = pluginload.script_errors(p) if p else []
        when = ""
        if p and p.exists():
            when = dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        plugins_dir = self.ctx.settings.subdir("Plugins")
        owners: dict[str, set[str]] = {}  # folder under Plugins -> installed plugins in it
        if plugins_dir:
            for a in addons.scan_plugins(plugins_dir):
                for d in a.descriptors:
                    owners.setdefault(d.split("/", 1)[0].lower(), set()).add(a.name)
        names = {f: next(iter(n)) for f, n in owners.items() if len(n) == 1}  # else: show the folder
        self.info.setText(
            "These are the plugin errors the game wrote to its log file, <b>Script.log</b>"
            + (f" (last written {when})" if when else " (not written yet)") + ". This is not a live feed: "
            "the game adds errors while it runs, and this page shows the file as it was when you opened it or "
            "pressed Refresh. An error can be from an earlier session if the plugin hasn't been loaded since.")
        self.table.setRowCount(0)
        for e in self.errors:
            n = self.table.rowCount()
            self.table.insertRow(n)
            label = names.get(e.plugin.lower(), e.plugin) if e.plugin else "(unknown)"
            self.table.setItem(n, 0, QTableWidgetItem(label))
            self.table.setItem(n, 1, QTableWidgetItem(e.text.splitlines()[0]))
        if not self.errors:
            self.detail.setHtml("<i>No plugin errors in Script.log.</i>")
        else:
            self.table.selectRow(0)

    def _show(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            e = self.errors[rows[0].row()]
            self.detail.setHtml(f"<pre style='white-space:pre-wrap'>{html.escape(e.text)}</pre>")


class PluginsTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.get = AddonPane(ctx, "plugin")
        self.load_pane = LoadPluginsPane(ctx)
        self.errors = PluginErrorsPane(ctx)
        self.skins = AddonPane(ctx, "skin")
        self.tabs.addTab(self.get, "Get plugins")
        self.tabs.addTab(self.load_pane, "Load plugins")
        self.tabs.addTab(self.errors, "Plugin errors")
        self.tabs.addTab(self.skins, "Skins")
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        self._loaded: set[AddonPane] = set()
        self.tabs.currentChanged.connect(self._page_changed)
        ctx.settings_changed.connect(lambda: [p.rescan() for p in self._loaded])

    def _page_changed(self, *_):
        w = self.tabs.currentWidget()
        if isinstance(w, AddonPane) and w not in self._loaded:
            self._loaded.add(w)
            w.load()
        if w is self.load_pane:
            self.load_pane.reload()

    def showEvent(self, e):  # load lazily the first time the tab is opened
        super().showEvent(e)
        self._page_changed()
