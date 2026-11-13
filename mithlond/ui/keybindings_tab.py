"""Key bindings tab: view, search and change the game's key bindings (lotro.keymap), find keys that do two
things, and save or load whole key binding files."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget,
)

from .. import keymap, procs
from ..config import CONFIG_DIR
from ..keymap import Keymap
from .addons_tab import SortItem
from .context import AppContext
from .widgets import open_path, subtle

KEYMAPS_DIR = CONFIG_DIR / "keymaps"
RED, GREY = QColor("#e07a6b"), QColor("#9a9282")

# Qt key -> DirectInput key name (keyboard). Shifted symbols map to the key they're on (US layout).
_QT_DIK: dict[int, str] = {}


def _qt_dik() -> dict[int, str]:
    if _QT_DIK:
        return _QT_DIK
    K = Qt.Key
    m = {getattr(K, f"Key_{c}"): f"DIK_{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"}
    m.update({getattr(K, f"Key_F{i}"): f"DIK_F{i}" for i in range(1, 16)})
    m.update({
        K.Key_Space: "DIK_SPACE", K.Key_Return: "DIK_RETURN", K.Key_Enter: "DIK_NUMPADENTER",
        K.Key_Tab: "DIK_TAB", K.Key_Backtab: "DIK_TAB", K.Key_Backspace: "DIK_BACK", K.Key_Escape: "DIK_ESCAPE",
        K.Key_Insert: "DIK_INSERT", K.Key_Delete: "DIK_DELETE", K.Key_Home: "DIK_HOME", K.Key_End: "DIK_END",
        K.Key_PageUp: "DIK_PGUP", K.Key_PageDown: "DIK_PGDN", K.Key_Up: "DIK_UPARROW", K.Key_Down: "DIK_DOWNARROW",
        K.Key_Left: "DIK_LEFTARROW", K.Key_Right: "DIK_RIGHTARROW", K.Key_Minus: "DIK_MINUS",
        K.Key_Equal: "DIK_EQUALS", K.Key_BracketLeft: "DIK_LBRACKET", K.Key_BracketRight: "DIK_RBRACKET",
        K.Key_Backslash: "DIK_BACKSLASH", K.Key_Semicolon: "DIK_SEMICOLON", K.Key_Apostrophe: "DIK_APOSTROPHE",
        K.Key_QuoteLeft: "DIK_GRAVE", K.Key_Comma: "DIK_COMMA", K.Key_Period: "DIK_PERIOD", K.Key_Slash: "DIK_SLASH",
        K.Key_Print: "DIK_SYSRQ", K.Key_Pause: "DIK_PAUSE", K.Key_ScrollLock: "DIK_SCROLL",
        K.Key_NumLock: "DIK_NUMLOCK", K.Key_CapsLock: "DIK_CAPITAL",
        # shifted symbols
        K.Key_Exclam: "DIK_1", K.Key_At: "DIK_2", K.Key_NumberSign: "DIK_3", K.Key_Dollar: "DIK_4",
        K.Key_Percent: "DIK_5", K.Key_AsciiCircum: "DIK_6", K.Key_Ampersand: "DIK_7", K.Key_Asterisk: "DIK_8",
        K.Key_ParenLeft: "DIK_9", K.Key_ParenRight: "DIK_0", K.Key_Underscore: "DIK_MINUS", K.Key_Plus: "DIK_EQUALS",
        K.Key_BraceLeft: "DIK_LBRACKET", K.Key_BraceRight: "DIK_RBRACKET", K.Key_Bar: "DIK_BACKSLASH",
        K.Key_Colon: "DIK_SEMICOLON", K.Key_QuoteDbl: "DIK_APOSTROPHE", K.Key_AsciiTilde: "DIK_GRAVE",
        K.Key_Less: "DIK_COMMA", K.Key_Greater: "DIK_PERIOD", K.Key_Question: "DIK_SLASH",
    })
    _QT_DIK.update({int(k): v for k, v in m.items()})
    return _QT_DIK


_KEYPAD = {"DIK_MINUS": "DIK_NUMPADMINUS", "DIK_EQUALS": "DIK_NUMPADPLUS", "DIK_8": "DIK_NUMPADSTAR",
           "DIK_SLASH": "DIK_NUMPADSLASH", "DIK_PERIOD": "DIK_DECIMAL"}


def dik_for(key: int, keypad: bool, plus: bool = False) -> str | None:
    """DirectInput name for a Qt key press (None for keys the game can't bind, like a lone modifier)."""
    name = _qt_dik().get(int(key))
    if name is None:
        return None
    if keypad:
        if name[4:].isdigit():
            return "DIK_NUMPAD" + name[4:]
        if plus:
            return "DIK_NUMPADPLUS"
        return _KEYPAD.get(name, name)
    return name


class KeyCapture(QDialog):
    """Waits for one key (with modifiers) or the middle / side mouse buttons."""

    def __init__(self, parent, km: Keymap, action: str):
        super().__init__(parent)
        self.km = km
        self.result_key: tuple[int, str, int] | None = None
        self.setWindowTitle("Choose a key")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{action}</b><br>Press the key or key combination to use (Shift, Ctrl and Alt "
                             "work as modifiers).<br>The middle mouse button and the side buttons work too."))
        self.shown = QLabel("…")
        self.shown.setAlignment(Qt.AlignCenter)
        self.shown.setStyleSheet("font-size: 18px; padding: 12px;")
        lay.addWidget(self.shown)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = buttons.button(QDialogButtonBox.Ok)
        self.ok.setEnabled(False)
        for b in buttons.buttons():
            b.setFocusPolicy(Qt.NoFocus)  # every key goes to the capture, including Enter and Esc
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _mods(self, mods) -> int:
        names = set()
        if mods & Qt.ShiftModifier:
            names.add("Shift")
        if mods & Qt.ControlModifier:
            names.add("Ctrl")
        if mods & Qt.AltModifier:
            names.add("Alt")
        if mods & Qt.MetaModifier:
            names.add("Win")
        return self.km.mask_for(names)

    def _set(self, device: int, key: str, mask: int) -> None:
        self.result_key = (device, key, mask)
        b = keymap.Binding("", "", "User", device, key, mask)
        self.shown.setText(self.km.chord_name(b))
        self.ok.setEnabled(True)

    def keyPressEvent(self, e):
        name = dik_for(e.key(), bool(e.modifiers() & Qt.KeypadModifier), e.key() == Qt.Key_Plus)
        if name:
            self._set(keymap.KEYBOARD, name, self._mods(e.modifiers()))

    def mousePressEvent(self, e):
        b = {Qt.MiddleButton: "DIMOFS_BUTTON2", Qt.BackButton: "DIMOFS_BUTTON3",
             Qt.ForwardButton: "DIMOFS_BUTTON4"}.get(e.button())
        if b:
            self._set(keymap.MOUSE, b, self._mods(e.modifiers()))
        else:
            super().mousePressEvent(e)


class KeybindingsTab(QWidget):
    COLS = ["Action", "Key", "Where", "Changed by you"]

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.path: Path | None = None
        self.km: Keymap | None = None
        self.disk_text = ""
        self.disk: set = set()
        self.loaded_from = ""
        self.game_running = False

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search actions or keys, e.g. map, quickslot 5, ctrl+q…")
        self.where = QComboBox()
        self.conflicts_only = QCheckBox("Keys that do two things")
        self.show_blocked = QCheckBox("Show blocked keys")
        self.show_blocked.setToolTip("Keys set to do nothing (the game writes these when you clear a default key)")
        top = QHBoxLayout()
        top.addWidget(self.search, 2)
        top.addWidget(self.where, 1)
        top.addWidget(self.conflicts_only)
        top.addWidget(self.show_blocked)

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
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(self.COLS)):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.change_btn = QPushButton("Change key…")
        self.add_btn = QPushButton("Add another key…")
        self.remove_btn = QPushButton("Remove key")
        edit = QHBoxLayout()
        for b in (self.change_btn, self.add_btn, self.remove_btn):
            edit.addWidget(b)
        edit.addStretch()

        self.state = QLabel()
        self.state.setWordWrap(True)
        self.save_btn = QPushButton("Save")
        self.discard_btn = QPushButton("Discard changes")
        self.restore_btn = QPushButton("Restore backup")
        self.export_btn = QPushButton("Save to file…")
        self.export_btn.setToolTip("Save these key bindings as a file, to keep or to use on another computer")
        self.import_btn = QPushButton("Load from file…")
        self.import_btn.setToolTip("Load key bindings from a file saved earlier (you still press Save to use them)")
        self.folder_btn = QPushButton("Open folder")
        bottom = QHBoxLayout()
        bottom.addWidget(self.state, 1)
        for b in (self.save_btn, self.discard_btn, self.restore_btn, self.export_btn, self.import_btn,
                  self.folder_btn):
            bottom.addWidget(b)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(subtle("Double-click a row to change its key. Keys shown in red do more than one thing in "
                             "the same place. Changes apply the next time the game starts."))
        lay.addWidget(self.table, 1)
        lay.addLayout(edit)
        lay.addLayout(bottom)

        self.search.textChanged.connect(self.fill)
        self.where.currentIndexChanged.connect(self.fill)
        self.conflicts_only.toggled.connect(self.fill)
        self.show_blocked.toggled.connect(self.fill)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.doubleClicked.connect(lambda _i: self.change_key())
        self.change_btn.clicked.connect(self.change_key)
        self.add_btn.clicked.connect(self.add_key)
        self.remove_btn.clicked.connect(self.remove_key)
        self.save_btn.clicked.connect(self.save)
        self.discard_btn.clicked.connect(self.load)
        self.restore_btn.clicked.connect(self.restore)
        self.export_btn.clicked.connect(self.export)
        self.import_btn.clicked.connect(self.import_)
        self.folder_btn.clicked.connect(lambda: self.path and open_path(self.path.parent))
        ctx.settings_changed.connect(self.load)
        ctx.games_changed.connect(lambda _n: self._check_game())
        self._timer = QTimer(self)  # the game rewrites the file on exit: check for it only while shown
        self._timer.setInterval(4000)
        self._timer.timeout.connect(self._check_game)
        self.load()

    # ---- loading ---------------------------------------------------------------------------------
    def load(self) -> None:
        self.path = keymap.keymap_file(self.ctx.settings)
        self.loaded_from = ""
        self.km = None
        self.disk_text, self.disk = "", set()
        if self.path and self.path.is_file():
            self.km = Keymap.load(self.path)
            self.disk_text = self.km.render()
            self.disk = {(b.chord(), b.action) for b in self.km.bindings}
        self._fill_where()
        self.fill()

    def _fill_where(self) -> None:
        keep = self.where.currentData()
        self.where.blockSignals(True)
        self.where.clear()
        self.where.addItem("Everywhere", "")
        if self.km:
            for c in dict.fromkeys(b.context for b in self.km.bindings):
                self.where.addItem(keymap.context_name(c), c)
        self.where.setCurrentIndex(max(self.where.findData(keep), 0) if keep else 0)
        self.where.blockSignals(False)

    def fill(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        if not self.km:
            self.table.setSortingEnabled(True)
            self._update_buttons()
            return
        q = self.search.text().strip().lower().replace(" + ", "+")
        where = self.where.currentData()
        conflicts = self.km.conflicts()
        clash: dict[tuple, list[str]] = {}
        for i in conflicts:
            b = self.km.bindings[i]
            clash.setdefault(b.chord(), []).append(keymap.action_name(b.action))
        for i, b in enumerate(self.km.bindings):
            if b.action == keymap.NOTHING and not self.show_blocked.isChecked():
                continue
            if where and b.context != where:
                continue
            if self.conflicts_only.isChecked() and i not in conflicts:
                continue
            action, key, ctxname = keymap.action_name(b.action), self.km.chord_name(b), keymap.context_name(b.context)
            if q and q not in f"{action} {key} {ctxname} {b.action}".lower():
                continue
            n = self.table.rowCount()
            self.table.insertRow(n)
            changed = (b.chord(), b.action) not in self.disk
            vals = [SortItem(action), SortItem(key), SortItem(ctxname),
                    SortItem("not saved" if changed else ("yes" if b.kind == "User" else ""))]
            vals[0].setData(Qt.UserRole, i)
            vals[0].setToolTip(b.action)
            for c, it in enumerate(vals):
                if i in conflicts:
                    it.setForeground(RED)
                    others = [a for a in clash.get(b.chord(), []) if a != action]
                    it.setToolTip("Also: " + ", ".join(dict.fromkeys(others)))
                elif b.action == keymap.NOTHING:
                    it.setForeground(GREY)
                if changed:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.table.setItem(n, c, it)
        self.table.setSortingEnabled(True)
        self._update_buttons()

    def _selected(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole) if rows else None

    # ---- editing ---------------------------------------------------------------------------------
    def _capture(self, index: int) -> tuple[int, str, int] | None:
        b = self.km.bindings[index]
        dlg = KeyCapture(self, self.km, keymap.action_name(b.action))
        return dlg.result_key if dlg.exec() == QDialog.Accepted else None

    def change_key(self) -> None:
        i = self._selected()
        if i is None or not self.km:
            return
        got = self._capture(i)
        if got:
            self.km.set_binding(i, *got)
            self._after_edit(i)

    def add_key(self) -> None:
        i = self._selected()
        if i is None or not self.km:
            return
        b = self.km.bindings[i]
        if b.context not in self.km.context_end:
            return
        got = self._capture(i)
        if got:
            j = self.km.add_binding(b.context, b.action, *got)
            self._after_edit(j)

    def remove_key(self) -> None:
        i = self._selected()
        if i is None or not self.km:
            return
        b = self.km.bindings[i]
        if b.kind == "Old" and QMessageBox.question(
                self, "Remove key", f"{self.km.chord_name(b)} is one of the game's default keys for "
                f"'{keymap.action_name(b.action)}'. Remove it?") != QMessageBox.Yes:
            return
        self.km.remove_binding(i)
        self.fill()

    def _after_edit(self, index: int) -> None:
        self.fill()
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole) == index:
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, 0))
                break
        b = self.km.bindings[index]
        if index in self.km.conflicts():
            others = {keymap.action_name(x.action) for x in self.km.bindings
                      if x.chord() == b.chord() and x.action not in (b.action, keymap.NOTHING)}
            QMessageBox.information(self, "Key already used", f"{self.km.chord_name(b)} also does: "
                                    f"{', '.join(sorted(others))}.\nIt's shown in red until one of them changes.")

    # ---- state and files -------------------------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        if self.path != keymap.keymap_file(self.ctx.settings):
            self.load()
        self._check_game()
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _check_game(self) -> None:
        self.game_running = bool(procs.game_clients())
        self._update_buttons()

    def _dirty(self) -> bool:
        return bool(self.km) and self.km.render() != self.disk_text

    def _update_buttons(self) -> None:
        dirty = self._dirty()
        sel = self._selected()
        have = bool(self.path and self.path.is_file())
        if self.game_running:
            self.state.setText("✘ The game is running. It rewrites its key bindings when it closes, so changes "
                               "can only be saved while it's closed.")
            self.state.setObjectName("bad")
        elif not self.km:
            self.state.setText("No lotro.keymap in the documents folder yet. The game writes it the first time "
                               "it runs (or check the documents folder in Settings).")
            self.state.setObjectName("")
        elif self.loaded_from and dirty:
            self.state.setText(f"Loaded from {self.loaded_from}: press Save to use these key bindings.")
            self.state.setObjectName("")
        elif dirty:
            self.state.setText("Changes not saved yet (shown in bold).")
            self.state.setObjectName("")
        else:
            self.state.setText(f"{len(self.km.bindings)} key bindings.")
            self.state.setObjectName("")
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)
        self.change_btn.setEnabled(sel is not None)
        self.add_btn.setEnabled(sel is not None and self.km is not None
                                and self.km.bindings[sel].context in self.km.context_end)
        self.remove_btn.setEnabled(sel is not None)
        self.save_btn.setEnabled(dirty and not self.game_running and bool(self.path))
        self.discard_btn.setEnabled(dirty)
        self.restore_btn.setEnabled(have and not self.game_running and keymap.latest_backup(self.path) is not None)
        self.export_btn.setEnabled(self.km is not None)
        self.import_btn.setEnabled(bool(self.path))
        self.folder_btn.setEnabled(have)

    def save(self) -> None:
        if self.game_running or not self.path or not self.km:
            return
        try:
            b = keymap.save(self.path, self.km)
        except OSError as e:
            QMessageBox.warning(self, "Save", f"Couldn't save {self.path}: {e}")
            return
        self.ctx.log("Saved key bindings" + (f" (previous version: {b.name})" if b else ""))
        self.load()

    def restore(self) -> None:
        b = keymap.latest_backup(self.path) if self.path else None
        if not b or self.game_running:
            return
        if QMessageBox.question(self, "Restore backup", f"Put back the key bindings from {b.name}?\nThe current "
                                "file is kept as a backup too.") != QMessageBox.Yes:
            return
        data = b.read_bytes()
        keymap.backup(self.path)
        self.path.write_bytes(data)
        self.ctx.log(f"Restored key bindings from {b.name}")
        self.load()

    def export(self) -> None:
        if not self.km:
            return
        KEYMAPS_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Save key bindings to a file", str(KEYMAPS_DIR / "my-keys.keymap"),
                                              "Key bindings (*.keymap);;All files (*)")
        if not path:
            return
        p = Path(path if path.endswith(".keymap") else path + ".keymap")
        p.write_bytes(self.km.render().encode("utf-8"))
        self.ctx.log(f"Key bindings saved to {p}")

    def import_(self) -> None:
        KEYMAPS_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Load key bindings from a file", str(KEYMAPS_DIR),
                                              "Key bindings (*.keymap);;All files (*)")
        if not path:
            return
        try:
            text = Path(path).read_bytes().decode("utf-8", errors="replace")
        except OSError as e:
            QMessageBox.warning(self, "Load from file", str(e))
            return
        if not keymap.is_keymap(text):
            QMessageBox.warning(self, "Load from file", f"{Path(path).name} isn't a LOTRO key bindings file.")
            return
        self.km = Keymap.parse(text)
        self.loaded_from = Path(path).name
        self._fill_where()
        self.fill()
