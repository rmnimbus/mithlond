"""LotRO Companion tab: where it lives, how it runs, and whether it follows the game."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QRadioButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from .. import companion, procs
from .context import AppContext
from .workers import run_task
from .widgets import PathPicker, subtle


def check_companion(p: Path) -> tuple[bool, str]:
    if not p.is_dir():
        return False, "Folder does not exist"
    has_exe = (p / "LotRO Companion.exe").exists()
    has_app = (p / "app" / "kickstarter").is_dir() or (p / "kickstarter").is_dir()
    if has_exe and has_app:
        return True, "Windows build found (can also run natively with Java)"
    if has_app:
        return True, "Java build found"
    if has_exe:
        return True, "LotRO Companion.exe found"
    return False, "No LotRO Companion here"


class CompanionTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        s = ctx.settings

        self.path = PathPicker(validator=self._check_folder, empty_ok=True,
                               placeholder="Empty = 'LotRO Companion' inside the Downloads folder (see Settings)")
        self.path.set_text(s.companion_dir)

        self.mode_runner = QRadioButton("Through Wine/Proton, in the game's prefix (recommended)")
        self.mode_runner.setToolTip("Needed for Companion to read character data from the running game client")
        self.mode_native = QRadioButton("Natively with system Java")
        java = shutil.which("java")
        self.mode_native.setToolTip(f"Uses {java}" if java else "Java is not installed")
        self.mode_native.setEnabled(bool(java))
        grp = QButtonGroup(self)
        grp.addButton(self.mode_runner)
        grp.addButton(self.mode_native)
        (self.mode_native if s.companion_mode == "native" and java else self.mode_runner).setChecked(True)

        self.with_game = QCheckBox("Start Companion when the game starts")
        self.with_game.setChecked(s.companion_with_game)
        self.delay = QSpinBox()
        self.delay.setRange(0, 300)
        self.delay.setSuffix(" s")
        self.delay.setValue(s.companion_delay)
        self.delay.setMaximumWidth(110)
        self.close_with = QCheckBox("Close Companion when the last game client exits")
        self.close_with.setChecked(s.companion_close_with_game)
        self.skip_updater = QCheckBox("Skip Companion's built-in updater (recommended)")
        self.skip_updater.setToolTip("Companion's own updater can hang forever before its window opens.\n"
                                     "Mithlond starts Companion directly and updates it from the Update button below.")
        self.skip_updater.setChecked(s.companion_skip_updater)

        self.version = QLabel("Version: checking…")
        self.version.setWordWrap(True)
        self.update_btn = QPushButton("Update Companion")
        self.update_btn.setEnabled(False)
        self.check_btn = QPushButton("Check for updates")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.latest: companion.Release | None = None

        form = QFormLayout()
        form.addRow("Folder", self.path)
        form.addRow("Run", self.mode_runner)
        form.addRow("", self.mode_native)
        form.addRow("", self.with_game)
        form.addRow("Delay after game start", self.delay)
        form.addRow("", self.close_with)
        form.addRow("", self.skip_updater)
        vrow = QHBoxLayout()
        vrow.addWidget(self.version, 1)
        vrow.addWidget(self.check_btn)
        vrow.addWidget(self.update_btn)
        form.addRow("Version", vrow)
        form.addRow("", self.progress)
        box = QGroupBox("LotRO Companion")
        box.setLayout(form)

        self.state = QLabel()
        self.toggle = QPushButton()
        row = QHBoxLayout()
        row.addWidget(self.state, 1)
        row.addWidget(self.toggle)

        lay = QVBoxLayout(self)
        lay.addWidget(box)
        lay.addLayout(row)
        lay.addWidget(subtle(
            "Companion is a separate Java/Swing program, so it opens in its own window rather than inside this "
            "launcher. The launcher starts it alongside the game and closes it afterwards. In the Wine/Proton mode it "
            "shares the game's prefix, so its live character sync can see the client. Its data is kept per prefix "
            "(…/drive_c/users/<you>/.lotrocompanion) or in ~/.lotrocompanion when run natively."))
        lay.addStretch()

        self.path.changed.connect(self._save)
        for w in (self.mode_runner, self.mode_native, self.with_game, self.close_with, self.skip_updater):
            w.toggled.connect(self._save)
        self.check_btn.clicked.connect(self.check_updates)
        self.update_btn.clicked.connect(self.do_update)
        self.path.changed.connect(lambda _: self.check_updates())
        self.delay.valueChanged.connect(self._save)
        self.toggle.clicked.connect(self._toggle)
        ctx.companion_changed.connect(self._update_state)
        self._update_state()
        self.check_updates()

    def _save(self, *_):
        s = self.ctx.settings
        s.companion_dir = self.path.text()
        s.companion_mode = "native" if self.mode_native.isChecked() else "runner"
        s.companion_with_game = self.with_game.isChecked()
        s.companion_delay = self.delay.value()
        s.companion_close_with_game = self.close_with.isChecked()
        s.companion_skip_updater = self.skip_updater.isChecked()
        self.ctx.save()

    def _toggle(self):
        if self.ctx.companion_running():
            self.ctx.stop_companion()
        else:
            self.ctx.start_companion()
        self._update_state()

    def _update_state(self, *_):
        running = self.ctx.companion_running()
        self.state.setText("● Running" if running else "○ Not running")
        self.state.setObjectName("ok" if running else "")
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)
        self.toggle.setText("Stop Companion" if running else "Start Companion now")

    # ---- updates ----------------------------------------------------------------------
    def _check_folder(self, p: Path) -> tuple[bool, str]:
        base = p if str(p) not in ("", ".") else self.ctx.settings.companion_path()
        ok, msg = check_companion(base)
        if not base.exists():
            return True, f"{base}: not installed yet. Use 'Download Companion' below."
        return ok, (f"{base}: {msg}" if str(p) in ("", ".") else msg)

    def _base(self) -> Path:
        t = self.path.text()
        return Path(t).expanduser() if t else self.ctx.settings.companion_path()

    def check_updates(self) -> None:
        base = self._base()
        installed = companion.installed_version(base) if base.is_dir() else ""
        if not base.exists():
            self.version.setText("Not installed · checking the latest version…")
        self.version.setText(f"Installed {installed or 'unknown'} · checking for updates…")
        self.check_btn.setEnabled(False)

        def done(rel):
            self.check_btn.setEnabled(True)
            self.latest = rel
            newer = companion.is_newer(rel.version, installed)
            if not base.exists():
                self.version.setText(f"Not installed · latest {rel.version}")
                self.update_btn.setText("Download Companion")
                self.update_btn.setEnabled(True)
                return
            self.version.setText(f"Installed {installed or 'unknown'} · latest {rel.version}"
                                 + ("  ⬆ update available" if newer else "  ✔ up to date"))
            self.update_btn.setText("Update Companion" if newer else "Reinstall")
            self.update_btn.setEnabled(True)

        def failed(e):
            self.check_btn.setEnabled(True)
            self.version.setText(f"Installed {installed or 'unknown'} · {e}")

        run_task(companion.latest_release, on_done=done, on_error=failed)

    def do_update(self) -> None:
        base, rel = self._base(), self.latest
        if not base or not rel:
            return
        running = [p for p in procs.related(self.ctx.settings)
                   if p.exe_name == "lotro companion.exe" or "delta.games.lotro.Main" in " ".join(p.argv)
                   or "delta.kickstarter.Kickstarter" in " ".join(p.argv)]
        if self.ctx.companion_running() or running:
            QMessageBox.information(self, "Update Companion", "Close LotRO Companion first (or use STOP).")
            return
        if not base.exists():
            question = f"Download LotRO Companion {rel.version} (about 270 MB) into\n{base}?"
        else:
            question = (f"Download LotRO Companion {rel.version} (about 270 MB) and replace\n{base}?\n\n"
                        f"The current version is kept as '{base.name}.old-…' next to it. Your Companion data "
                        "(characters, settings) is stored elsewhere and isn't touched.")
        if QMessageBox.question(self, "LotRO Companion", question) != QMessageBox.Yes:
            return
        self.update_btn.setEnabled(False)
        self.check_btn.setEnabled(False)
        self.progress.setVisible(True)

        def prog(p):
            stage, d, t = p
            self.progress.setRange(0, t or 0)
            self.progress.setFormat(f"{stage}… %p%" if t else f"{stage}…")
            if t:
                self.progress.setValue(d)

        def done(backup):
            self.progress.setVisible(False)
            self.ctx.log(f"LotRO Companion {rel.version} installed in {base}"
                         + (f"; previous version kept in {backup}" if backup else ""))
            self.path.validate()
            self.check_updates()

        def failed(e):
            self.progress.setVisible(False)
            self.check_btn.setEnabled(True)
            self.update_btn.setEnabled(True)
            QMessageBox.warning(self, "Update Companion", str(e))

        run_task(lambda progress: companion.update(base, rel, lambda *a: progress(a)),
                 on_done=done, on_error=failed, on_progress=prog)
