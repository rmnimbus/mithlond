"""Layouts tab: edit the game's saved interface layouts (ui/layouts/*.layout): window positions and sizes on a
screen-shaped canvas, interface options, and chat colors. The game applies a layout with /ui layout load <name>."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout, QGraphicsItem, QGraphicsRectItem,
    QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from .. import gameprefs, uilayout
from ..config import Settings
from .context import AppContext
from .widgets import SectionedPage, subtle

GRIP = 14  # resize handle size in screen pixels
SNAP = 10  # snap to an edge within this many pixels
GRIDS = (1, 5, 10)


def snap_axis(start: float, size: float, limit: float, targets: list[float], grid: int,
              dist: float = SNAP) -> float:
    """Where a window's start edge goes on one axis while it's dragged.

    Snaps either edge (start or start+size) to the nearest target edge within `dist` (the screen edges are
    always targets); otherwise rounds to the grid. Always stays on the screen."""
    best, best_d = None, dist + 0.001
    for t in [0.0, float(limit)] + list(targets):
        for cand in (t, t - size):  # our start on the edge, or our end on it
            d = abs(start - cand)
            if d < best_d:
                best, best_d = cand, d
    pos = best if best is not None else round(start / grid) * grid
    return float(round(min(max(pos, 0), limit - size)))


def snap_size(start: float, size: float, limit: float, targets: list[float], grid: int, minimum: float,
              dist: float = SNAP) -> float:
    """A window's size while its corner is dragged: its end edge snaps to a target edge within `dist`,
    otherwise the end edge is rounded to the grid."""
    end = start + size
    best, best_d = None, dist + 0.001
    for t in [float(limit)] + list(targets):
        d = abs(end - t)
        if d < best_d and t - start >= minimum:
            best, best_d = t, d
    end = best if best is not None else round(end / grid) * grid
    return float(round(min(max(end - start, minimum), limit - start)))


def game_resolution(s: Settings, fallback: tuple[int, int]) -> tuple[int, int]:
    """The game's full-screen resolution from its settings, for the canvas size."""
    p = gameprefs.prefs_file(s)
    try:
        res = gameprefs.read(p).get("Display.Resolution", "") if p and p.is_file() else ""
        w, h = (int(v) for v in res.lower().split("x"))
        return (w, h) if w > 0 and h > 0 else fallback
    except (ValueError, OSError):
        return fallback


def changes(a: uilayout.Layout, b: uilayout.Layout) -> int:
    wa = {w.id: (w.x, w.y, w.w, w.h) for w in a.windows}
    ca = {c.type: (c.color, c.size) for c in a.chat}
    return (sum(wa.get(w.id) != (w.x, w.y, w.w, w.h) for w in b.windows)
            + sum(a.options.get(k) != v for k, v in b.options.items())
            + sum(ca.get(c.type) != (c.color, c.size) for c in b.chat))


# ---- window canvas ----------------------------------------------------------------------------------------
class WindowItem(QGraphicsRectItem):
    """A window on the canvas: drag to move, drag the bottom-right corner to resize."""

    def __init__(self, win: uilayout.Window, screen: tuple[int, int], moved, options=None):
        self.win, self.sw, self.sh, self.moved = win, screen[0], screen[1], moved
        self.options = options  # the editor: .grid (1/5/10) and .snap_windows
        super().__init__(0, 0, max(win.w * self.sw, GRIP), max(win.h * self.sh, GRIP))
        self.setPos(win.x * self.sw, win.y * self.sh)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setBrush(QBrush(QColor(200, 160, 70, 60)))
        self.setPen(QPen(QColor(220, 180, 90), 2))
        self.label = QGraphicsSimpleTextItem(win.name, self)
        self.label.setBrush(QBrush(QColor(235, 225, 200)))
        f = QFont()
        f.setPixelSize(max(10, int(self.sh / 70)))
        self.label.setFont(f)
        self.label.setPos(4, 2)
        self._resizing = self._dragging = False
        self._targets: tuple[list[float], list[float]] = ([], [])
        self._fit_label()

    def _fit_label(self) -> None:
        r = self.rect()
        self.label.setVisible(r.width() > 40 and r.height() > 16)

    def _grip(self, p) -> bool:
        r = self.rect()
        return p.x() > r.width() - GRIP and p.y() > r.height() - GRIP

    def hoverMoveEvent(self, e):
        self.setCursor(Qt.SizeFDiagCursor if self._grip(e.pos()) else Qt.SizeAllCursor)

    def _grid(self) -> int:
        return getattr(self.options, "grid", 1) or 1

    def _edges(self) -> tuple[list[float], list[float]]:
        """Left/right and top/bottom edges of the other windows shown, if snapping to windows is on."""
        xs: list[float] = []
        ys: list[float] = []
        if self.scene() is None or not getattr(self.options, "snap_windows", False):
            return xs, ys
        for it in self.scene().items():
            if isinstance(it, WindowItem) and it is not self and it.isVisible():
                xs += [it.pos().x(), it.pos().x() + it.rect().width()]
                ys += [it.pos().y(), it.pos().y() + it.rect().height()]
        return xs, ys

    def mousePressEvent(self, e):
        self._resizing = self._grip(e.pos())
        self._dragging = not self._resizing  # snapping applies to mouse drags, not to typed pixel values
        self._targets = self._edges()  # other windows don't move during this drag
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resizing:
            xs, ys = getattr(self, "_targets", ([], []))
            g = self._grid()
            w = snap_size(self.pos().x(), e.pos().x(), self.sw, xs, g, GRIP * 2)
            h = snap_size(self.pos().y(), e.pos().y(), self.sh, ys, g, GRIP * 2)
            self.setRect(0, 0, w, h)
            self._fit_label()
            self._store()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._resizing = self._dragging = False
        super().mouseReleaseEvent(e)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            r = self.rect()
            if getattr(self, "_dragging", False):
                xs, ys = self._targets
                g = self._grid()
                value.setX(snap_axis(value.x(), r.width(), self.sw, xs, g))
                value.setY(snap_axis(value.y(), r.height(), self.sh, ys, g))
            else:  # typed values: exactly as typed, kept on the screen
                value.setX(round(min(max(value.x(), 0), self.sw - r.width())))
                value.setY(round(min(max(value.y(), 0), self.sh - r.height())))
            return value
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._store()
        return super().itemChange(change, value)

    def _store(self) -> None:
        r = self.rect()
        self.win.x, self.win.y = round(self.pos().x() / self.sw, 6), round(self.pos().y() / self.sh, 6)
        self.win.w, self.win.h = round(r.width() / self.sw, 6), round(r.height() / self.sh, 6)
        self.moved(self)

    def set_pixels(self, x: int, y: int, w: int, h: int) -> None:
        self.setRect(0, 0, w, h)
        self.setPos(x, y)
        self._fit_label()
        self._store()


class Canvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(20, 20, 24)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)


class WindowsEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: dict[str, WindowItem] = {}
        self.layout_data: uilayout.Layout | None = None
        self.screen_size = (1920, 1080)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a window…")
        self.search.setClearButtonEnabled(True)
        self.hud_only = QCheckBox("Only always-on-screen parts (HUD)")
        self.hud_only.setChecked(True)
        self.list = QListWidget()
        self.canvas = Canvas()
        self.sel_name = QLabel("Click a window on the screen or in the list.")
        self.grid = 1
        self.snap_windows = False
        self.grid_box = QComboBox()
        for g in GRIDS:
            self.grid_box.addItem("1 px (free)" if g == 1 else f"{g} px", g)
        self.grid_box.setToolTip("Moving and resizing with the mouse goes in steps of this many pixels")
        self.snap_box = QCheckBox("Snap to other windows")
        self.snap_box.setToolTip("While dragging, edges snap to the edges of the other windows shown\n"
                                 "(they always snap to the screen edges)")
        self.grid_box.currentIndexChanged.connect(lambda _i: setattr(self, "grid", self.grid_box.currentData()))
        self.snap_box.toggled.connect(lambda on: setattr(self, "snap_windows", on))
        self.px = {k: QSpinBox() for k in ("X", "Y", "Width", "Height")}
        for sb in self.px.values():
            sb.setRange(0, 16000)
            sb.setSuffix(" px")
            sb.setEnabled(False)
            sb.editingFinished.connect(self._typed)
        geo = QHBoxLayout()
        geo.addWidget(self.sel_name, 1)
        for k, sb in self.px.items():
            geo.addWidget(QLabel(k))
            geo.addWidget(sb)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.search)
        lv.addWidget(self.hud_only)
        lv.addWidget(self.list, 1)
        self.all_btn = QPushButton("Show all")
        self.none_btn = QPushButton("Show none")
        self.all_btn.setToolTip("Show every window in the list (as filtered) on the screen")
        self.all_btn.clicked.connect(lambda: self._tick_listed(True))
        self.none_btn.clicked.connect(lambda: self._tick_listed(False))
        btns = QHBoxLayout()
        btns.addWidget(self.all_btn)
        btns.addWidget(self.none_btn)
        lv.addLayout(btns)
        lv.addWidget(subtle("Ticked windows are shown on the screen. Drag to move, drag the bottom-right corner to "
                            "resize; windows snap to the screen edges (and to each other, if ticked above the screen)."))
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        snap_row = QHBoxLayout()
        snap_row.addWidget(QLabel("Move in steps of"))
        snap_row.addWidget(self.grid_box)
        snap_row.addWidget(self.snap_box)
        snap_row.addStretch()
        rv.addLayout(snap_row)
        rv.addWidget(self.canvas, 1)
        rv.addLayout(geo)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 800])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)
        self.search.textChanged.connect(self._filter)
        self.hud_only.toggled.connect(self._filter)
        self.list.itemChanged.connect(self._ticked)
        self.list.currentItemChanged.connect(self._list_selected)
        self.canvas.scene().selectionChanged.connect(self._canvas_selected)

    def load(self, data: uilayout.Layout, screen: tuple[int, int]) -> None:
        self.layout_data, self.screen_size = data, screen
        scene = self.canvas.scene()
        scene.blockSignals(True)
        scene.clear()
        scene.blockSignals(False)
        self.items = {}
        w, h = screen
        scene.setSceneRect(QRectF(0, 0, w, h))
        frame = scene.addRect(0, 0, w, h, QPen(QColor(120, 120, 130), 2), QBrush(QColor(38, 40, 46)))
        frame.setZValue(-10)
        self.list.blockSignals(True)
        self.list.clear()
        for win in sorted(data.windows, key=lambda x: x.name.lower()):
            it = QListWidgetItem(win.name)
            it.setData(Qt.UserRole, win.id)
            it.setToolTip(win.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if win.core else Qt.Unchecked)
            self.list.addItem(it)
            item = WindowItem(win, screen, self._moved, self)
            item.setVisible(win.core)
            scene.addItem(item)
            self.items[win.id] = item
        self.list.blockSignals(False)
        self._filter()
        self.canvas.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)
        self._show_selected(None)

    def _filter(self, *_):
        words = self.search.text().lower().split()
        for i in range(self.list.count()):
            it = self.list.item(i)
            win = self.items[it.data(Qt.UserRole)].win
            hay = f"{win.name} {win.id}".lower()
            it.setHidden(not all(w in hay for w in words) or (self.hud_only.isChecked() and not win.hud and not words))

    def _tick_listed(self, on: bool) -> None:
        for i in range(self.list.count()):
            it = self.list.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _ticked(self, it: QListWidgetItem) -> None:
        self.items[it.data(Qt.UserRole)].setVisible(it.checkState() == Qt.Checked)

    def _list_selected(self, it, _prev=None) -> None:
        if not it:
            return
        item = self.items[it.data(Qt.UserRole)]
        if not item.isVisible():
            it.setCheckState(Qt.Checked)
        scene = self.canvas.scene()
        scene.blockSignals(True)
        scene.clearSelection()
        item.setSelected(True)
        scene.blockSignals(False)
        item.setZValue(1)
        self._show_selected(item)

    def _canvas_selected(self) -> None:
        sel = [i for i in self.canvas.scene().selectedItems() if isinstance(i, WindowItem)]
        item = sel[0] if sel else None
        if item:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole) == item.win.id:
                    self.list.blockSignals(True)
                    self.list.setCurrentRow(i)
                    self.list.blockSignals(False)
        self._show_selected(item)

    def _show_selected(self, item: WindowItem | None) -> None:
        self._current = item
        for sb in self.px.values():
            sb.setEnabled(item is not None)
        if item is None:
            self.sel_name.setText("Click a window on the screen or in the list.")
            return
        self.sel_name.setText(f"<b>{item.win.name}</b>")
        self._fill_px(item)

    def _fill_px(self, item: WindowItem) -> None:
        w, h = self.screen_size
        vals = {"X": item.win.x * w, "Y": item.win.y * h, "Width": item.win.w * w, "Height": item.win.h * h}
        for k, sb in self.px.items():
            sb.blockSignals(True)
            sb.setValue(round(vals[k]))
            sb.blockSignals(False)

    def _typed(self) -> None:
        item = getattr(self, "_current", None)
        if item:
            item.set_pixels(*(self.px[k].value() for k in ("X", "Y", "Width", "Height")))

    def _moved(self, item: WindowItem) -> None:
        if item is getattr(self, "_current", None):
            self._fill_px(item)
        self.changed.emit()


# ---- small widgets ----------------------------------------------------------------------------------------
class ColorButton(QPushButton):
    changed = Signal(tuple)

    def __init__(self, color: tuple[float, float, float, float], parent=None):
        super().__init__(parent)
        self.setFixedWidth(64)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, c) -> None:
        self.color = tuple(c)
        q = QColor.fromRgbF(*self.color)
        self.setStyleSheet(f"background-color: {q.name()}; border: 1px solid #888;")
        self.setToolTip(f"{q.name()} — click to change")

    def _pick(self) -> None:
        q = QColorDialog.getColor(QColor.fromRgbF(*self.color), self, "Choose a color",
                                  QColorDialog.ShowAlphaChannel)
        if q.isValid():
            self.set_color((round(q.redF(), 3), round(q.greenF(), 3), round(q.blueF(), 3), round(q.alphaF(), 3)))
            self.changed.emit(self.color)


def _is_color(v: str) -> bool:
    parts = v.split()
    try:
        return len(parts) == 4 and all(0 <= float(p) <= 1 for p in parts)
    except ValueError:
        return False


def _is_number(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


# ---- the tab ------------------------------------------------------------------------------------------------
class LayoutTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.original: uilayout.Layout | None = None
        self.edited: uilayout.Layout | None = None
        self.files = QComboBox()
        self.files.setMinimumWidth(220)
        self.new_btn = QPushButton("Copy as…")
        self.new_btn.setToolTip("Save a copy of this layout under a new name")
        self.rename_btn = QPushButton("Rename…")
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setToolTip("Moves the file into the backup folder (ui/layouts/.mithlond-backups)")
        self.reload_btn = QPushButton("Reload")
        self.open_btn = QPushButton("Open folder")
        top = QHBoxLayout()
        top.addWidget(QLabel("Layout"))
        top.addWidget(self.files)
        for b in (self.new_btn, self.rename_btn, self.delete_btn):
            top.addWidget(b)
        top.addStretch()
        top.addWidget(self.reload_btn)
        top.addWidget(self.open_btn)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.state = QLabel()
        self.state.setWordWrap(True)

        self.windows = WindowsEditor()
        self.windows.changed.connect(self._changed)
        s = ctx.settings  # remembered: steps and snapping
        self.windows.grid_box.setCurrentIndex(max(self.windows.grid_box.findData(s.layout_grid), 0))
        self.windows.snap_box.setChecked(s.layout_snap_windows)
        self.windows.grid_box.currentIndexChanged.connect(lambda _i: self._save_snap())
        self.windows.snap_box.toggled.connect(lambda _on: self._save_snap())
        self.options_page = SectionedPage("Search interface options, e.g. scale, duel, toolbar…", counts=True)
        self.chat_page = SectionedPage("Search chat types, e.g. tell, kinship, loot…", counts=True)
        self.sub = QTabWidget()
        self.sub.addTab(self.windows, "Windows")
        self.sub.addTab(self.options_page, "Interface options")
        self.sub.addTab(self.chat_page, "Chat colors")

        self.save_btn = QPushButton("Save changes")
        self.discard_btn = QPushButton("Discard changes")
        self.restore_btn = QPushButton("Restore previous")
        self.restore_btn.setToolTip("Put back the layout as it was before the last save from Mithlond")
        bottom = QHBoxLayout()
        for b in (self.save_btn, self.discard_btn, self.restore_btn):
            bottom.addWidget(b)
        bottom.addStretch()

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.hint)
        lay.addWidget(self.state)
        lay.addWidget(self.sub, 1)
        lay.addLayout(bottom)

        self.files.activated.connect(lambda _i: self._open(self.files.currentData()))
        self.new_btn.clicked.connect(self._copy)
        self.rename_btn.clicked.connect(self._rename)
        self.delete_btn.clicked.connect(self._delete)
        self.reload_btn.clicked.connect(lambda: self.refresh(keep=True))
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._dir()))))
        self.save_btn.clicked.connect(self.save)
        self.discard_btn.clicked.connect(lambda: self._open(self.original.path if self.original else None))
        self.restore_btn.clicked.connect(self.restore)
        ctx.settings_changed.connect(lambda: self.refresh(keep=True))
        self.refresh()

    # ---- files ------------------------------------------------------------------------------------
    def _save_snap(self) -> None:
        self.ctx.settings.layout_grid = self.windows.grid
        self.ctx.settings.layout_snap_windows = self.windows.snap_windows
        self.ctx.settings.save()

    def _dir(self) -> Path:
        docs = self.ctx.settings.docs_path
        return uilayout.layouts_dir(docs) if docs else Path.home()

    def refresh(self, keep: bool = False) -> None:
        current = self.original.path if (keep and self.original) else None
        docs = self.ctx.settings.docs_path
        files = uilayout.list_layouts(docs) if docs else []
        self.files.clear()
        for p in files:
            self.files.addItem(p.stem, p)
        if not files:
            self.original = self.edited = None
            self.hint.setText("No saved layouts yet. In the game, type <b>/ui layout save main</b> (any name works), "
                              f"then press Reload. Layouts are saved in {self._dir()}.")
            self.windows.load(uilayout.Layout(Path("none")), (1920, 1080))
            self.options_page.clear()
            self.chat_page.clear()
            self._update()
            return
        target = current if current in files else files[0]
        self._open(target)

    def _open(self, path: Path | None) -> None:
        if path is None:
            return
        try:
            self.original = uilayout.read(path)
        except (OSError, ValueError) as e:  # ET.ParseError is a ValueError
            QMessageBox.warning(self, "Layouts", f"Can't read {path.name}: {e}")
            return
        self.edited = copy.deepcopy(self.original)
        self.files.setCurrentIndex(max(self.files.findText(path.stem), 0))
        self.hint.setText(f"Apply it in the game with <b>/ui layout load {path.stem}</b>. To capture the layout you "
                          f"have in game right now: <b>/ui layout save {path.stem}</b>, then Reload.")
        scr = self.screen().size() * self.screen().devicePixelRatio() if self.screen() else None
        fallback = (scr.width(), scr.height()) if scr else (1920, 1080)
        self.windows.load(self.edited, game_resolution(self.ctx.settings, fallback))
        self._build_options()
        self._build_chat()
        self._update()

    def _ask_name(self, title: str, start: str) -> str | None:
        name, ok = QInputDialog.getText(self, title, "Name (letters, digits, - and _; used in /ui layout load):",
                                        text=start)
        name = name.strip()
        if not ok or not name:
            return None
        if not uilayout.valid_name(name):
            QMessageBox.warning(self, title, "Use letters, digits, - and _ only (no spaces).")
            return None
        return name

    def _copy(self) -> None:
        if not self.original:
            return
        name = self._ask_name("Copy layout", self.original.path.stem + "-copy")
        if name:
            try:
                p = uilayout.copy_layout(self.original.path, name)
            except OSError as e:
                QMessageBox.warning(self, "Copy layout", str(e))
                return
            self.ctx.log(f"Layouts: copied {self.original.path.name} to {p.name}")
            self.original = uilayout.Layout(p)
            self.refresh(keep=True)

    def _rename(self) -> None:
        if not self.original:
            return
        name = self._ask_name("Rename layout", self.original.path.stem)
        if name and name != self.original.path.stem:
            try:
                p = uilayout.rename_layout(self.original.path, name)
            except OSError as e:
                QMessageBox.warning(self, "Rename layout", str(e))
                return
            self.ctx.log(f"Layouts: renamed to {p.name}")
            self.original = uilayout.Layout(p)
            self.refresh(keep=True)

    def _delete(self) -> None:
        if not self.original:
            return
        p = self.original.path
        if QMessageBox.question(self, "Delete layout", f"Delete {p.name}?\nIt is moved into the backup folder, so it "
                                "can be recovered.") != QMessageBox.Yes:
            return
        b = uilayout.delete_layout(p)
        self.ctx.log(f"Layouts: deleted {p.name} (kept as {b.name})")
        self.original = None
        self.refresh()

    # ---- options and chat -------------------------------------------------------------------------
    def _option_widget(self, name: str, value: str) -> QWidget:
        def set_opt(v: str) -> None:
            self.edited.options[name] = v
            self._changed()
        if value in ("True", "False"):
            w = QCheckBox()
            w.setChecked(value == "True")
            w.toggled.connect(lambda on: set_opt("True" if on else "False"))
        elif _is_color(value):
            w = ColorButton(uilayout._color(value))
            w.changed.connect(lambda c: set_opt(uilayout.color_text(c)))
        elif _is_number(value):
            decimals = uilayout._decimals(value, 0)
            w = QDoubleSpinBox()
            w.setDecimals(min(decimals, 3))
            w.setRange(-100000, 100000)
            w.setSingleStep(0.05 if decimals else 1)
            w.setValue(float(value))
            w.valueChanged.connect(lambda v: set_opt(f"{v:.{decimals}f}"))
        else:
            w = QLineEdit(value)
            w.editingFinished.connect(lambda: set_opt(w.text().strip()))
        w.setToolTip(name)
        return w

    def _build_options(self) -> None:
        page = self.options_page
        keep = page.current_title()
        page.clear()
        groups: dict[str, list[str]] = {}
        for name in self.edited.options:
            groups.setdefault(uilayout.option_group(name), []).append(name)
        for group in [g for g, _ in uilayout.OPTION_GROUPS] + ["Other"]:
            names = sorted(groups.get(group, []), key=str.lower)
            if not names:
                continue
            box = QGroupBox(group)
            form = QFormLayout(box)
            for n in names:
                form.addRow(uilayout.pretty_option(n), self._option_widget(n, self.edited.options[n]))
            page.add(group, box, [f"{uilayout.pretty_option(n)} {n}" for n in names], refilter=False)
        if keep:
            page.select(keep)
        page.filter()

    def _build_chat(self) -> None:
        page = self.chat_page
        keep = page.current_title()
        page.clear()
        groups: dict[str, list[uilayout.ChatFont]] = {}
        for c in self.edited.chat:
            groups.setdefault(uilayout.chat_group(c.type), []).append(c)
        for group in ("Social", "Game messages", "Combat"):
            fonts = sorted(groups.get(group, []), key=lambda c: uilayout.pretty_chat(c.type).lower())
            if not fonts:
                continue
            box = QGroupBox(group)
            form = QFormLayout(box)
            for c in fonts:
                form.addRow(uilayout.pretty_chat(c.type), self._chat_row(c))
            page.add(group, box, [f"{uilayout.pretty_chat(c.type)} {c.type}" for c in fonts], refilter=False)
        if keep:
            page.select(keep)
        page.filter()

    def _chat_row(self, c: uilayout.ChatFont) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        color = ColorButton(c.color)
        size = QComboBox()
        size.addItems(uilayout.CHAT_SIZES + ([c.size] if c.size not in uilayout.CHAT_SIZES else []))
        size.setCurrentText(c.size)
        preview = QLabel(f"[{uilayout.pretty_chat(c.type)}] The quick brown fox jumps over the lazy dog")

        def paint():
            q = QColor.fromRgbF(*c.color)
            px = {"Small": 11, "Medium": 13, "Large": 15, "XLarge": 18}.get(c.size, 13)
            preview.setStyleSheet(f"color: {q.name()}; font-size: {px}px; background: #15161a; padding: 2px 6px;")

        def set_color(col):
            c.color = col
            paint()
            self._changed()

        def set_size(t):
            c.size = t
            paint()
            self._changed()
        color.changed.connect(set_color)
        size.currentTextChanged.connect(set_size)
        paint()
        h.addWidget(color)
        h.addWidget(size)
        h.addWidget(preview, 1)
        return row

    # ---- state, save, restore -----------------------------------------------------------------------
    def _changed(self, *_):
        self._update()

    def _update(self) -> None:
        have = self.original is not None
        n = changes(self.original, self.edited) if have else 0
        self.state.setText(f"{n} change{'s' if n != 1 else ''} not saved yet." if n else
                           "Changes are written to the layout file; the game uses them after /ui layout load.")
        self.save_btn.setEnabled(n > 0)
        self.discard_btn.setEnabled(n > 0)
        self.restore_btn.setEnabled(have and uilayout.latest_backup(self.original.path) is not None)
        for b in (self.new_btn, self.rename_btn, self.delete_btn):
            b.setEnabled(have)

    def save(self) -> None:
        if not self.original:
            return
        try:
            b = uilayout.save(self.original, self.edited)
        except OSError as e:
            QMessageBox.warning(self, "Layouts", f"Couldn't save: {e}")
            return
        name = self.original.path.stem
        self.ctx.log(f"Layouts: saved {name}.layout" + (f" (previous version: {b.name})" if b else "") +
                     f" — in game: /ui layout load {name}")
        self._open(self.original.path)

    def restore(self) -> None:
        b = uilayout.latest_backup(self.original.path) if self.original else None
        if not b:
            return
        if QMessageBox.question(self, "Restore layout", f"Put back {self.original.path.name} from {b.name}?\n"
                                "The current file is kept as a backup too.") != QMessageBox.Yes:
            return
        data = b.read_bytes()
        uilayout.backup(self.original.path)
        self.original.path.write_bytes(data)
        b.unlink()
        self.ctx.log(f"Layouts: restored {self.original.path.name} from {b.name}")
        self._open(self.original.path)
