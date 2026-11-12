"""Settings tab: game folder, documents folder, runner, game options, music tools."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .. import config, runner
from .context import AppContext
from .widgets import PathPicker, subtle


def check_docs(p: Path) -> tuple[bool, str]:
    if not p.is_dir():
        return False, "Folder does not exist (the game creates it on first start)"
    have = [n for n in ("Plugins", "Music", "PluginData", "UserPreferences.ini") if config.find_case_insensitive(p, n)]
    if not have:
        return True, "Folder exists but looks unused so far"
    return True, "Contains " + ", ".join(have)


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE per line; blank lines and # comments ignored; optional 'export ' and quotes allowed."""
    env = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.removeprefix("export ").split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        if k.replace("_", "").isalnum():
            env[k] = v
    return env


class SettingsTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._loading = True

        # --- locations
        self.game = PathPicker(validator=config.check_game_dir, placeholder="Folder that contains lotroclient.exe")
        self.game_detect = QPushButton("Detect")
        self.docs = PathPicker(validator=check_docs, placeholder="…/Documents/The Lord of the Rings Online")
        self.docs_choose = QPushButton("Choose…")
        self.docs_choose.setToolTip("Pick from the documents folders found on this computer, or make a new one")
        self.use_prefs = QCheckBox("Start the game with this folder (whatever the prefix)")
        self.use_prefs.setToolTip("Passes --prefs <folder>\\UserPreferences.ini to the game, which makes it use this\n"
                                  "folder for its settings, plugins, music, plugin data and screenshots.")
        self.downloads = PathPicker(validator=self._check_downloads, empty_ok=True,
                                    placeholder="Empty = the Downloads folder inside the documents folder")
        self.downloads_reset = QPushButton("Default")
        self.downloads_reset.setToolTip("Use the Downloads folder inside the documents folder")
        loc = QFormLayout()
        loc.addRow("LOTRO game folder", self._with(self.game, self.game_detect))
        loc.addRow("Game documents\nfolder", self._with(self.docs, self.docs_choose))
        loc.addRow("", self.use_prefs)
        loc.addRow("", subtle("Holds your game settings, Plugins, Music, PluginData and ui/skins. With the box ticked "
                              "the game always uses this folder; without it, the game uses "
                              "Documents/The Lord of the Rings Online inside whichever prefix it runs in."))
        loc.addRow("Downloads folder", self._with(self.downloads, self.downloads_reset))
        loc.addRow("", subtle("Where Mithlond puts extra programs it downloads for you: LotRO Companion, Maestro, "
                              "WAN Songbook Filler."))
        loc_box = QGroupBox("Locations")
        loc_box.setLayout(loc)

        # --- runner
        self.runner = QComboBox()
        self.runner.setToolTip("Proton runs the game through umu-run, like Faugus and Steam (umu-run is built into\n"
                               "the AppImage). Wine needs Wine installed on your system.")
        self.prefix = QComboBox()
        self.prefix.setEditable(True)
        self.prefix.lineEdit().setPlaceholderText("Empty = the runner's default prefix")
        self.prefix_browse = QPushButton("Browse…")
        self.runner_info = QLabel()
        self.runner_info.setWordWrap(True)
        self.env = QPlainTextEdit()
        self.env.setPlaceholderText("One per line, e.g.\nDXVK_HUD=fps\nPROTON_ENABLE_WAYLAND=1")
        self.env.setFixedHeight(90)
        self._env_timer = QTimer(self)
        self._env_timer.setSingleShot(True)
        self._env_timer.setInterval(700)
        rr = QHBoxLayout()
        rr.addWidget(self.runner, 1)
        pr = QHBoxLayout()
        pr.addWidget(self.prefix, 1)
        pr.addWidget(self.prefix_browse)
        run = QFormLayout()
        run.addRow("Runner", rr)
        run.addRow("Prefix", pr)
        run.addRow("", self.runner_info)
        run.addRow("Environment\nvariables", self.env)
        self.opts: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        for i, (key, label, tip, needs) in enumerate(runner.GAME_OPTIONS):
            cb = QCheckBox(label)
            cb.setToolTip(tip)
            if needs and not shutil.which(needs):
                cb.setText(f"{label} (not installed)")
                cb.setEnabled(bool(getattr(self.ctx.settings, key)))  # still allow unticking
            self.opts[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        self.gamescope_args = QLineEdit()
        self.gamescope_args.setPlaceholderText("gamescope arguments, e.g. -f -W 2560 -H 1440")
        self.gamescope_args.setToolTip("Arguments passed to gamescope before '--'")
        run.addRow("Game options", grid)
        self.opt_warning = QLabel()
        self.opt_warning.setObjectName("bad")
        self.opt_warning.setWordWrap(True)
        self.opt_warning.setTextInteractionFlags(Qt.TextSelectableByMouse)
        run.addRow("", self.opt_warning)
        run.addRow("gamescope arguments", self.gamescope_args)
        run_box = QGroupBox("Runners and Prefix")
        run_box.setLayout(run)

        # --- game
        self.client = QComboBox()
        self.client.addItem("64-bit (x64/lotroclient64.exe)", "win64")
        self.client.addItem("32-bit (lotroclient.exe)", "win32")
        self.language = QComboBox()
        self.high_res = QCheckBox("High resolution textures")
        self.skip_intro = QCheckBox("Skip the intro videos")
        self.skip_intro.setToolTip("Skips the Turbine logo video that plays at every start (Mithlond sets the file\n"
                                   "aside; unticking puts it back) and marks the intro cinematic as already seen.")
        self.on_start = QComboBox()
        self.on_start.addItem("Keep the launcher open", "stay")
        self.on_start.addItem("Minimize the launcher", "minimize")
        gf = QFormLayout()
        gf.addRow("Client", self.client)
        gf.addRow("Language", self.language)
        gf.addRow("", self.high_res)
        gf.addRow("", self.skip_intro)
        gf.addRow("When the game starts", self.on_start)
        game_box = QGroupBox("Game")
        game_box.setLayout(gf)

        # --- about & updates
        from .. import __version__, selfupdate
        self.update_check_btn = QPushButton("Check for updates")
        self.update_auto = QCheckBox("Check for updates when Mithlond starts")
        self.update_status = QLabel()
        self.update_status.setWordWrap(True)
        ok, why = selfupdate.can_self_update()
        how = ("Updates are downloaded from GitHub and replace this AppImage." if ok else
               f"{why} Updates open the download page instead.")
        ab = QFormLayout()
        vrow = QHBoxLayout()
        vrow.addWidget(QLabel(f"<b>Mithlond {__version__}</b>"))
        vrow.addStretch()
        vrow.addWidget(self.update_check_btn)
        ab.addRow("Version", vrow)
        ab.addRow("", self.update_auto)
        ab.addRow("", self.update_status)
        ab.addRow("", subtle(f"{how} Releases: {selfupdate.RELEASES_PAGE.rsplit('/latest', 1)[0]}"))
        about_box = QGroupBox("About && updates")  # && = a literal & in Qt titles
        about_box.setLayout(ab)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        for b in (loc_box, run_box, game_box, about_box):
            lay.addWidget(b)
        lay.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.load_values()

        self.downloads_reset.clicked.connect(lambda: self.downloads.set_text("", emit=True))
        for picker in (self.game, self.docs, self.downloads):
            picker.changed.connect(self.save)
        for w in (self.high_res, self.skip_intro):
            w.toggled.connect(self.save)
        for cb in self.opts.values():
            cb.toggled.connect(self.save)
        self.gamescope_args.editingFinished.connect(self.save)
        for w in (self.client, self.language, self.on_start):
            w.currentIndexChanged.connect(self.save)
        self.runner.activated.connect(self._runner_picked)
        self.prefix.currentTextChanged.connect(self.save)
        self.prefix_browse.clicked.connect(self._browse_prefix)
        self.env.textChanged.connect(self._env_timer.start)
        self._env_timer.timeout.connect(self.save)
        self.game_detect.clicked.connect(self.detect_game)
        self.docs_choose.clicked.connect(self.choose_docs)
        self.use_prefs.toggled.connect(self.save)
        self.update_auto.toggled.connect(self.save)

    def _check_downloads(self, p: Path) -> tuple[bool, str]:
        if str(p) in ("", "."):
            return True, f"Using {self.ctx.settings.downloads_path()}"
        if p.exists() and not p.is_dir():
            return False, "Not a folder"
        return True, "Exists" if p.is_dir() else "Will be created on the first download"

    @staticmethod
    def _with(w: QWidget, btn: QPushButton) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w, 1)
        h.addWidget(btn)
        return box

    def load_values(self) -> None:
        self._loading = True
        s = self.ctx.settings
        self.game.set_text(s.game_dir)
        self.docs.set_text(s.documents_dir)
        self.downloads.set_text(s.downloads_dir)
        self.use_prefs.setChecked(s.use_prefs)
        self.update_auto.setChecked(s.check_updates_on_start)
        self._fill_runners()
        self._fill_prefixes()
        self.env.setPlainText("\n".join(f"{k}={v}" for k, v in s.extra_env.items()))
        self.client.setCurrentIndex(max(self.client.findData(s.client), 0))
        self._fill_languages()
        self.high_res.setChecked(s.high_res)
        self.skip_intro.setChecked(s.skip_intro)
        self.on_start.setCurrentIndex(max(self.on_start.findData(s.on_game_start), 0))
        for key, cb in self.opts.items():
            cb.setChecked(bool(getattr(s, key)))
        self.gamescope_args.setText(s.gamescope_args)
        self._runner_fields()
        self._loading = False

    def _fill_languages(self) -> None:
        s = self.ctx.settings
        self.language.blockSignals(True)
        self.language.clear()
        langs = config.game_languages(s.game_path) if s.game_path and s.game_path.is_dir() else ["English"]
        self.language.addItems(langs)
        self.language.setCurrentText(s.language if s.language in langs else langs[0])
        self.language.blockSignals(False)

    # ---- runner & prefix ----------------------------------------------------------------
    def _fill_runners(self) -> None:
        """Runner list: system Wine, every Proton found, umu's default Proton, custom entries."""
        s = self.ctx.settings
        self.runner.blockSignals(True)
        self.runner.clear()
        sys_wine = shutil.which("wine")
        self.runner.addItem(f"Wine (system{': ' + sys_wine if sys_wine else ', not installed'})", ("wine", "wine"))
        if not sys_wine and (s.runner, s.wine_binary) != ("wine", "wine"):
            self.runner.model().item(self.runner.count() - 1).setEnabled(False)
        for p in config.proton_versions():
            arch = config.proton_arch(p)
            if arch and arch != config.host_arch():
                self.runner.addItem(f"Proton: {p.name}  ({arch} build, can't run on this computer)", ("umu", str(p)))
                self.runner.model().item(self.runner.count() - 1).setEnabled(False)
            else:
                self.runner.addItem(f"Proton: {p.name}", ("umu", str(p)))
        self.runner.addItem("Proton: umu's default (UMU-Proton, downloaded automatically)", ("umu", ""))
        current = (s.runner, s.wine_binary if s.runner == "wine" else s.proton_path)
        if s.runner == "wine" and s.wine_binary not in ("", "wine"):
            self.runner.addItem(f"Wine: {s.wine_binary}", ("wine", s.wine_binary))
        if s.runner == "umu" and s.proton_path and not any(
                self.runner.itemData(i) == ("umu", s.proton_path) for i in range(self.runner.count())):
            self.runner.addItem(f"Proton: {s.proton_path}", ("umu", s.proton_path))
        self.runner.insertSeparator(self.runner.count())
        self.runner.addItem("Other Wine binary…", ("pick-wine", ""))
        self.runner.addItem("Other Proton folder…", ("pick-proton", ""))
        idx = next((i for i in range(self.runner.count()) if self.runner.itemData(i) == current), 0)
        self.runner.setCurrentIndex(idx)
        self._runner_index = idx
        self.runner.blockSignals(False)

    def _runner_picked(self, idx: int) -> None:
        kind, value = self.runner.itemData(idx) or ("wine", "wine")
        s = self.ctx.settings
        if kind == "pick-wine":
            path, _ = QFileDialog.getOpenFileName(self, "Choose a Wine binary", str(Path.home()))
            if not path:
                self.runner.setCurrentIndex(self._runner_index)
                return
            s.runner, s.wine_binary = "wine", path
        elif kind == "pick-proton":
            path = QFileDialog.getExistingDirectory(self, "Choose a Proton folder (contains 'proton')",
                                                    str(Path.home() / ".local/share/Steam/compatibilitytools.d"))
            if not path:
                self.runner.setCurrentIndex(self._runner_index)
                return
            s.runner, s.proton_path = "umu", path
        elif kind == "wine":
            s.runner, s.wine_binary = "wine", value
        else:
            s.runner, s.proton_path = "umu", value
        self.ctx.save()
        self._fill_runners()
        self._runner_fields()

    def _fill_prefixes(self) -> None:
        s = self.ctx.settings
        self.prefix.blockSignals(True)
        self.prefix.clear()
        for p in config.detect_prefixes():
            self.prefix.addItem(str(p))
        self.prefix.setEditText(s.wine_prefix)
        self.prefix.blockSignals(False)

    def _browse_prefix(self) -> None:
        start = self.prefix.currentText().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Choose a Wine prefix", start)
        if path:
            self.prefix.setEditText(path)

    def _runner_fields(self) -> None:
        s = self.ctx.settings
        umu = s.runner == "umu"
        prefix = s.prefix_path()
        problem = config.prefix_problem(prefix) if umu else config.wine_prefix_problem(prefix)
        if umu and s.proton_path and not problem:
            problem = config.proton_problem(Path(s.proton_path).expanduser())
        if umu and not problem and not config.umu_command():
            problem = "umu-run was not found (running from source: install umu-launcher)"
        if not problem:
            problem = config.selinux_problem()
        if not umu and not problem and not config.wine_installed(s):
            problem = f"Wine ('{s.wine_binary or 'wine'}') isn't installed. Pick a Proton runner instead"
        if problem:
            text, ok = f"✘ {problem}", False
        else:
            state = "existing prefix" if (prefix / "system.reg").exists() else "will be created on first start"
            text, ok = f"✔ Using {prefix} ({state})", True
        self.runner_info.setText(text)
        gm = runner.gamemode_problem() if s.opt_gamemode else None
        self.opt_warning.setText(f"✘ GameMode: {gm}" if gm else "")
        self.opt_warning.setVisible(bool(gm))
        self.runner_info.setObjectName("ok" if ok else "bad")
        self.runner_info.style().unpolish(self.runner_info)
        self.runner_info.style().polish(self.runner_info)

    def save(self, *_):
        if self._loading:
            return
        s = self.ctx.settings
        game_changed = s.game_dir != self.game.text()
        s.game_dir = self.game.text()
        s.documents_dir = self.docs.text()
        s.downloads_dir = self.downloads.text()
        s.use_prefs = self.use_prefs.isChecked()
        s.check_updates_on_start = self.update_auto.isChecked()
        self.downloads.validate()
        s.wine_prefix = self.prefix.currentText().strip()
        s.extra_env = parse_env(self.env.toPlainText())
        s.client = self.client.currentData()
        s.language = self.language.currentText() or "English"
        s.high_res = self.high_res.isChecked()
        s.skip_intro = self.skip_intro.isChecked()
        s.on_game_start = self.on_start.currentData()
        for key, cb in self.opts.items():
            setattr(s, key, cb.isChecked())
        s.gamescope_args = self.gamescope_args.text().strip()
        if game_changed:
            self._fill_languages()
            s.language = self.language.currentText()
        self._runner_fields()
        self.ctx.save()

    def detect_game(self) -> None:
        found = config.detect_game_dirs()
        if not found:
            QMessageBox.information(self, "Detect", "No LOTRO install found automatically. Use Browse… to pick the "
                                    "folder that contains lotroclient.exe.")
            return
        self.game.set_text(str(found[0]), emit=True)

    def choose_docs(self) -> None:
        from .docs_chooser import DocsChooser
        dlg = DocsChooser(self.ctx.settings, self)
        if dlg.exec() and dlg.chosen:
            self.docs.set_text(str(dlg.chosen), emit=True)

    def attach_updater(self, updater) -> None:
        self.update_check_btn.clicked.connect(lambda: updater.check(manual=True))
        updater.status.connect(self.update_status.setText)
