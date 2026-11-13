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


class SectionedPage(QWidget):
    """Category list on the left; the selected category's box on the right; a live search box. Typing hides every
    form row that doesn't contain all the typed words and categories left without a match; the selected category
    shows only its matching rows. Each row's search text is collected once, when its category is added."""

    def __init__(self, placeholder: str = "Search…", counts: bool = False, parent=None):
        from PySide6.QtWidgets import QListWidget, QScrollArea
        super().__init__(parent)
        self.counts = counts  # show "Title (n)" in the category list
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter)
        self.search_row = QHBoxLayout()  # callers may add widgets next to the search box
        self.search_row.addWidget(self.search, 1)
        self.no_match = QLabel("Nothing matches your search.")
        self.no_match.setVisible(False)
        self.nav = QListWidget()
        self.nav.setMaximumWidth(220)
        self.nav.currentRowChanged.connect(lambda _r: self._show_current())
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.sections: list[tuple[str, QWidget]] = []
        self._rows: list[list[str]] = []  # per section: lower-case search text of each form row
        self._counts: list[int] = []
        self._new_page()
        right = QVBoxLayout()
        right.addLayout(self.search_row)
        right.addWidget(self.no_match)
        right.addWidget(self.scroll, 1)
        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.nav)
        body.addLayout(right, 1)

    def _new_page(self) -> None:
        self.page = QWidget()
        self.col = QVBoxLayout(self.page)
        self.col.addStretch()
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.scroll.setWidget(self.page)

    def clear(self) -> None:
        """Remove every category (e.g. to rebuild them after reloading data)."""
        self.nav.blockSignals(True)
        self.nav.clear()
        self.nav.blockSignals(False)
        self.sections, self._rows, self._counts = [], [], []
        self._new_page()

    def add(self, title: str, box: QWidget, texts: list[str] | None = None, refilter: bool = True) -> None:
        """Add a category. `texts`: search text per form row (default: the row's visible words)."""
        from PySide6.QtWidgets import QFormLayout
        self.col.insertWidget(self.col.count() - 1, box)  # before the stretch
        self.sections.append((title, box))
        item_title = title
        self.nav.addItem(item_title)
        self.nav.item(self.nav.count() - 1).setData(0x0100, title)  # Qt.UserRole: the plain title
        form = box.layout()
        if texts is None:
            texts = []
            if isinstance(form, QFormLayout):
                for row in range(form.rowCount()):
                    items = [form.itemAt(row, role) for role in (QFormLayout.LabelRole, QFormLayout.FieldRole,
                                                                 QFormLayout.SpanningRole)]
                    texts.append(" ".join(t for it in items if it for t in self._texts(it.widget() or it.layout())))
            else:
                texts = [" ".join(self._texts(box))]
        self._rows.append([(title + " " + t).lower() for t in texts])
        if refilter:
            self.filter()

    @staticmethod
    def _own_texts(w) -> list[str]:
        from PySide6.QtWidgets import QComboBox
        out = [w.toolTip()]
        if isinstance(w, QComboBox):
            out += [w.itemText(i) for i in range(w.count())]
        else:
            for attr in ("text", "placeholderText", "title"):
                f = getattr(w, attr, None)
                if callable(f):
                    try:
                        v = f()
                    except TypeError:
                        continue
                    if isinstance(v, str):
                        out.append(v)
        return out

    @classmethod
    def _texts(cls, obj) -> list[str]:
        """Words shown by a widget or layout and everything inside it (texts, placeholders, tooltips, list items)."""
        from PySide6.QtWidgets import QLayout
        if obj is None:
            return []
        if isinstance(obj, QLayout):
            out = []
            for i in range(obj.count()):
                item = obj.itemAt(i)
                out += cls._texts(item.widget() or item.layout())
            return out
        out = cls._own_texts(obj)
        for child in obj.findChildren(QWidget):
            out += cls._own_texts(child)
        return out

    def filter(self, *_):
        from PySide6.QtWidgets import QFormLayout
        words = self.search.text().lower().split()
        counts: list[int] = []
        for i, (title, box) in enumerate(self.sections):
            form = box.layout()
            hits = [all(w in t for w in words) for t in self._rows[i]]
            if isinstance(form, QFormLayout) and len(hits) == form.rowCount():
                for row, hit in enumerate(hits):
                    form.setRowVisible(row, hit)
            shown = sum(hits)
            counts.append(shown)
            item = self.nav.item(i)
            item.setHidden(shown == 0)
            if self.counts:
                item.setText(f"{title} ({shown})")
        self._counts = counts
        self.no_match.setVisible(bool(words) and not any(counts))
        select_first_visible(self.nav)
        self._show_current()

    def select(self, title: str) -> None:
        """Show the category with this title."""
        for i, (t, _box) in enumerate(self.sections):
            if t == title and not self.nav.item(i).isHidden():
                self.nav.setCurrentRow(i)

    def current_title(self) -> str | None:
        row = self.nav.currentRow()
        return self.sections[row][0] if 0 <= row < len(self.sections) else None

    def _show_current(self) -> None:
        cur = self.nav.currentRow()
        for i, (_title, box) in enumerate(self.sections):
            box.setVisible(i == cur and i < len(self._counts) and self._counts[i] > 0)
        self.scroll.verticalScrollBar().setValue(0)


def select_first_visible(nav) -> None:
    """Keep the selected category if it's still listed; otherwise select the first one that is."""
    cur = nav.currentRow()
    if 0 <= cur < nav.count() and not nav.item(cur).isHidden():
        return
    for i in range(nav.count()):
        if not nav.item(i).isHidden():
            nav.setCurrentRow(i)
            return


class Collapsible(QWidget):
    """A titled section that opens and closes with a click on its header (closed by default)."""

    def __init__(self, title: str, content: QWidget, expanded: bool = False, parent=None):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QToolButton
        super().__init__(parent)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self.content = content
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle)
        lay.addWidget(content)
        self.toggle.toggled.connect(self._set)
        self._set(expanded)

    def _set(self, open_: bool) -> None:
        from PySide6.QtCore import Qt
        self.toggle.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)
        self.content.setVisible(open_)
