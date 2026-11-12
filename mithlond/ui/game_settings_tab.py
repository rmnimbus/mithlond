"""Game settings tab: the game's own options (UserPreferences.ini), categorized, edited while the game is closed."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .. import gameprefs, procs
from ..config import DOCS_FOLDER_NAME, Settings
from .context import AppContext


def prefs_file(s: Settings) -> Path | None:
    """The UserPreferences.ini the game will use: the documents folder Mithlond starts it with, or (without
    --prefs) the newest one inside the prefix."""
    if s.use_prefs and s.docs_path:
        return s.docs_path / "UserPreferences.ini"
    users = s.prefix_path() / "drive_c" / "users"
    found = sorted(users.glob(f"*/Documents/{DOCS_FOLDER_NAME}/UserPreferences.ini"),
                   key=lambda p: p.stat().st_mtime, reverse=True) if users.is_dir() else []
    return found[0] if found else None


class Field:
    """One setting's row: builds the widget, reads it back as the file's text form."""

    def __init__(self, pref: gameprefs.Pref, value: str, on_change):
        self.pref, self.original = pref, value
        p = pref
        if p.kind == "bool":
            w = QCheckBox()
            w.setChecked(value.lower() == "true")
            w.toggled.connect(on_change)
        elif p.kind == "choice":
            w = QComboBox()
            w.setEditable(p.editable)
            items = list(p.choices) + ([value] if value and value not in p.choices else [])
            for item in items:  # shown readable, stored as the game writes it
                w.addItem(item if p.editable else gameprefs.pretty(item), item)
            w.setCurrentIndex(items.index(value) if value in items else 0)
            w.currentTextChanged.connect(on_change)
        elif p.kind in ("float", "int"):
            num = _num(value)
            w = QSpinBox() if p.kind == "int" else QDoubleSpinBox()
            if p.kind == "float":
                w.setDecimals(2)
            lo, hi = min(p.lo, num), max(p.hi, num)  # never clip what's already set
            w.setRange(int(lo) if p.kind == "int" else lo, int(hi) if p.kind == "int" else hi)
            w.setSingleStep(int(p.step) if p.kind == "int" else p.step)
            w.setValue(int(num) if p.kind == "int" else num)
            w.valueChanged.connect(on_change)
        elif p.kind == "volume":
            w = QWidget()
            row = QHBoxLayout(w)
            row.setContentsMargins(0, 0, 0, 0)
            self.slider = QSlider(Qt.Horizontal)
            self.slider.setRange(0, 100)
            self.slider.setValue(round(_num(value) * 100))
            pct = QLabel()
            pct.setMinimumWidth(40)
            self.slider.valueChanged.connect(lambda v: pct.setText(f"{v}%"))
            self.slider.valueChanged.connect(on_change)
            pct.setText(f"{self.slider.value()}%")
            row.addWidget(self.slider, 1)
            row.addWidget(pct)
        else:
            w = QLineEdit(value)
            w.textChanged.connect(on_change)
        w.setToolTip((p.tip + "\n\n" if p.tip else "") + f"[{p.section}] {p.key}")
        self.widget = w
        self.label = QLabel(p.label)
        self.label.setToolTip(w.toolTip())

    def current(self) -> str:
        p, w = self.pref, self.widget
        if p.kind == "bool":
            return gameprefs.format_value(p, w.isChecked())
        if p.kind == "choice":
            if p.editable:
                return w.currentText().strip()
            return w.currentData() or ""
        if p.kind in ("float", "int"):
            return gameprefs.format_value(p, w.value())
        if p.kind == "volume":
            return gameprefs.format_value(p, self.slider.value() / 100)
        return w.text().strip()

    def changed(self) -> bool:
        cur, orig = self.current(), self.original
        if self.pref.kind in ("float", "volume", "int"):
            return abs(_num(cur) - _num(orig)) > 1e-6
        return cur != orig


def _num(v: str) -> float:
    try:
        return float(v)
    except ValueError:
        return 0.0


class GameSettingsTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.path: Path | None = None
        self.fields: list[Field] = []
        self.game_running = False

        self.where = QLabel()
        self.where.setWordWrap(True)
        self.where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.state = QLabel()
        self.state.setWordWrap(True)
        self.save_btn = QPushButton("Save changes")
        self.discard_btn = QPushButton("Discard changes")
        self.restore_btn = QPushButton("Restore previous")
        self.restore_btn.setToolTip("Put back the settings as they were before the last save from Mithlond")
        self.reload_btn = QPushButton("Reload")
        self.reload_btn.setToolTip("Read the file again (e.g. after playing)")
        self.open_btn = QPushButton("Open folder")
        buttons = QHBoxLayout()
        for b in (self.save_btn, self.discard_btn, self.restore_btn):
            buttons.addWidget(b)
        buttons.addStretch()
        buttons.addWidget(self.reload_btn)
        buttons.addWidget(self.open_btn)

        # live search over every category; categories on the left jump to their box on the right
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search settings, e.g. shadow, volume, scale, fps…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.no_match = QLabel("No setting matches your search.")
        self.no_match.setVisible(False)
        self.nav = QListWidget()
        self.nav.setMaximumWidth(220)
        self.nav.itemClicked.connect(self._jump)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.groups: dict[str, tuple[QGroupBox, QFormLayout, list[Field]]] = {}
        right = QVBoxLayout()
        right.addWidget(self.search)
        right.addWidget(self.no_match)
        right.addWidget(self.scroll, 1)
        body = QHBoxLayout()
        body.addWidget(self.nav)
        body.addLayout(right, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.where)
        lay.addWidget(self.state)
        lay.addLayout(body, 1)
        lay.addLayout(buttons)

        self.save_btn.clicked.connect(self.save)
        self.discard_btn.clicked.connect(self.load)
        self.reload_btn.clicked.connect(self.load)
        self.restore_btn.clicked.connect(self.restore)
        self.open_btn.clicked.connect(lambda: self.path and QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path.parent))))
        ctx.settings_changed.connect(self.load)
        ctx.games_changed.connect(lambda _n: self._check_game())
        self._timer = QTimer(self)
        self._timer.setInterval(4000)
        self._timer.timeout.connect(self._check_game)
        self.load()

    # ---- loading -------------------------------------------------------------------------
    def load(self) -> None:
        self.path = prefs_file(self.ctx.settings)
        self.nav.clear()
        self.groups = {}
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.fields = []
        if not self.path or not self.path.is_file():
            self.where.setText("No game settings file yet. The game creates <b>UserPreferences.ini</b> in the "
                               "documents folder the first time it starts (Mithlond seeds one when you press PLAY).")
            self._update_buttons()
            return
        values = gameprefs.read(self.path)
        self.where.setText(f"The game's own settings from <b>{self.path}</b>. Hover over a setting to see its "
                           "name in the file.")
        by_cat: dict[str, list[gameprefs.Pref]] = {}
        for p in gameprefs.visible(values):
            by_cat.setdefault(p.category, []).append(p)
        page = QWidget()
        col = QVBoxLayout(page)
        for cat in gameprefs.CATEGORIES:
            prefs = by_cat.get(cat)
            if not prefs:
                continue
            box = QGroupBox(cat.replace("&", "&&"))
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
            fields = []
            for p in prefs:
                f = Field(p, values[p.id], self._changed)
                fields.append(f)
                form.addRow(f.label, f.widget)
            self.fields += fields
            self.groups[cat] = (box, form, fields)
            col.addWidget(box)
            self.nav.addItem(cat)
        col.addStretch()
        self.scroll.setWidget(page)
        self._filter()
        self._check_game()
        self._timer.start()

    # ---- search and navigation ----------------------------------------------------------
    @staticmethod
    def _haystack(f: Field) -> str:
        p = f.pref
        return " ".join((p.label, p.key, p.section, p.category, p.tip, gameprefs.pretty(p.key))).lower()

    def _filter(self, *_):
        """Show only settings whose name, file key, category or description contain every typed word."""
        words = self.search.text().lower().split()
        total = 0
        for i in range(self.nav.count()):
            item = self.nav.item(i)
            cat = item.data(Qt.UserRole) or item.text()
            item.setData(Qt.UserRole, cat)
            box, form, fields = self.groups[cat]
            shown = 0
            for row, f in enumerate(fields):
                hit = all(w in self._haystack(f) for w in words)
                form.setRowVisible(row, hit)
                shown += hit
            box.setVisible(shown > 0)
            item.setHidden(shown == 0)
            item.setText(f"{cat} ({shown})")
            total += shown
        self.no_match.setVisible(bool(words) and total == 0)
        self.scroll.verticalScrollBar().setValue(0)

    def _jump(self, item) -> None:
        box = self.groups[item.data(Qt.UserRole)][0]
        self.scroll.verticalScrollBar().setValue(box.y())

    def showEvent(self, e):
        super().showEvent(e)
        if self.path != prefs_file(self.ctx.settings):
            self.load()

    # ---- state ---------------------------------------------------------------------------
    def _changes(self) -> dict[str, str]:
        return {f.pref.id: f.current() for f in self.fields if f.changed()}

    def _changed(self, *_):
        for f in self.fields:
            font = f.label.font()
            font.setBold(f.changed())
            f.label.setFont(font)
        self._update_buttons()

    def _check_game(self) -> None:
        self.game_running = bool(procs.game_clients())
        self._update_buttons()

    def _update_buttons(self) -> None:
        n = len(self._changes())
        have = bool(self.path and self.path.is_file())
        if self.game_running:
            self.state.setText("✘ The game is running. It rewrites this file when it closes, so changes can only "
                               "be saved while it's closed. Change settings in the game itself for now.")
            self.state.setObjectName("bad")
        elif n:
            self.state.setText(f"{n} change{'s' if n != 1 else ''} not saved yet (shown in bold).")
            self.state.setObjectName("")
        else:
            self.state.setText("Changes apply the next time the game starts.")
            self.state.setObjectName("")
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)
        self.save_btn.setEnabled(have and n > 0 and not self.game_running)
        self.discard_btn.setEnabled(n > 0)
        self.restore_btn.setEnabled(have and not self.game_running and gameprefs.latest_backup(self.path) is not None)
        self.open_btn.setEnabled(have)

    # ---- actions -------------------------------------------------------------------------
    def save(self) -> None:
        if self.game_running or not self.path:
            return
        changes = self._changes()
        try:
            backup = gameprefs.save(self.path, changes)
        except OSError as e:
            QMessageBox.warning(self, "Game settings", f"Couldn't save: {e}")
            return
        self.ctx.log(f"Game settings: saved {len(changes)} change(s) to {self.path.name}"
                     + (f" (previous version: {backup.name})" if backup else ""))
        self.load()

    def restore(self) -> None:
        b = gameprefs.latest_backup(self.path) if self.path else None
        if not b or self.game_running:
            return
        if QMessageBox.question(self, "Restore previous settings",
                                f"Put back the game settings from {b.name}?\nThe current file is kept as a backup "
                                "too.") != QMessageBox.Yes:
            return
        try:
            data = b.read_bytes()
            gameprefs.backup(self.path)
            self.path.write_bytes(data)
            b.unlink()
        except OSError as e:
            QMessageBox.warning(self, "Game settings", f"Couldn't restore: {e}")
            return
        self.ctx.log(f"Game settings: restored {b.name}")
        self.load()
