"""Music tab: import ABC files into the Music folder and keep the Songbook plugin's list current."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMessageBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import runner, songs, tools
from ..config import Settings
from .context import AppContext
from .widgets import Collapsible, PathPicker, open_path, open_url, subtle
from .workers import run_task


def songbook_accounts(s: Settings) -> list[str]:
    """Account folders in PluginData, plus configured accounts that have none yet."""
    pd = s.subdir("PluginData")
    accs = songs.plugindata_accounts(pd) if pd else []
    lower = {a.lower() for a in accs}
    accs += [a.username for a in s.accounts if a.username.lower() not in lower]
    return accs


def songbook_installed(s: Settings) -> bool:
    plugins = s.subdir("Plugins")
    return bool(plugins and plugins.is_dir() and any(plugins.glob("*/Songbook*.plugin")))


class SongsTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setAcceptDrops(True)

        self.import_files = QPushButton("Import songs…")
        self.import_files.setToolTip("Copy .abc files (or .zip archives of them) into your Music folder")
        self.import_dir = QPushButton("Import folder…")
        self.dest = QComboBox()
        self.dest.setToolTip("Folder inside Music to import into")
        self.new_folder = QPushButton("New folder")
        top = QHBoxLayout()
        top.addWidget(self.import_files)
        top.addWidget(self.import_dir)
        top.addWidget(QLabel("into"))
        top.addWidget(self.dest, 1)
        top.addWidget(self.new_folder)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Song", "Parts", "File"])
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.setAlternatingRowColors(True)

        self.delete_btn = QPushButton("Delete")
        self.folder_btn = QPushButton("Open Music folder")
        self.songbook_btn = QPushButton("Update Songbook list")
        self.songbook_btn.setToolTip("Write SongbookData.plugindata so the Songbook plugin sees your songs\n"
                                     "(replaces SongbookFiller.exe / songbook.hta)")
        bottom = QHBoxLayout()
        for b in (self.delete_btn, self.folder_btn, self.songbook_btn):
            bottom.addWidget(b)
        bottom.addStretch()

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.hint = subtle("")

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(subtle("Drop .abc files, folders or .zip archives here to import them. "
                             "In game: /play <file> (without .abc), or use the Songbook plugin."))
        lay.addWidget(self.tree, 1)
        lay.addLayout(bottom)
        lay.addWidget(self.status)
        lay.addWidget(self.hint)

        self.songbook_auto = QCheckBox("Update the Songbook list automatically when songs change")
        self.songbook_auto.setToolTip("After imports, deletions, music pack installs and closing Maestro/BruTE/"
                                      "WAN Songbook Filler started from here")
        self.songbook_auto.setChecked(ctx.settings.songbook_auto)
        tools_body = QWidget()
        tl = QVBoxLayout(tools_body)
        tl.setContentsMargins(12, 0, 0, 0)
        tl.addWidget(self.songbook_auto)
        self.tool_rows = {
            "maestro": ToolRow(ctx, "maestro", "maestro_path", "Turns MIDI files into ABC songs, and plays them back.",
                               self._music_changed),
            "brute": ToolRow(ctx, "brute", "brute_path", "Another MIDI → ABC converter, for band arrangements.",
                             self._music_changed),
            "wan": ToolRow(ctx, "wan", "wan_path", "Songbook list builder for big or network-shared Music "
                           "folders (Windows program, runs through your runner). Mithlond's own "
                           "'Update Songbook list' does the same job for normal folders.", self._music_changed),
        }
        for row in self.tool_rows.values():
            tl.addWidget(row)
        self.tools_section = Collapsible("Music tools (Maestro, BruTE, WAN Songbook Filler)", tools_body)
        lay.addWidget(self.tools_section)

        self.import_files.clicked.connect(self._pick_files)
        self.import_dir.clicked.connect(self._pick_dir)
        self.new_folder.clicked.connect(self._new_folder)
        self.delete_btn.clicked.connect(self._delete)
        self.folder_btn.clicked.connect(lambda: self.music_dir() and open_path(self.music_dir()))
        self.songbook_btn.clicked.connect(lambda: self.update_songbook(announce=True))
        self.songbook_auto.toggled.connect(self._save_auto)
        self.tree.itemDoubleClicked.connect(self._open_item)
        ctx.music_changed.connect(self._music_changed)
        ctx.settings_changed.connect(self.refresh)
        self.refresh()

    def music_dir(self) -> Path | None:
        return self.ctx.settings.subdir("Music")

    # ---- listing --------------------------------------------------------------------
    def refresh(self) -> None:
        md = self.music_dir()
        self.tree.clear()
        cur = self.dest.currentData()
        self.dest.clear()
        if md is None:
            self.status.setText("Set your LOTRO documents folder on the Settings tab.")
            return
        dirs, found = songs.scan_music(md)
        self.dest.addItem("Music (top level)", "")
        for d in dirs[1:]:
            self.dest.addItem(d.strip("/"), d.strip("/"))
        i = self.dest.findData(cur)
        self.dest.setCurrentIndex(max(i, 0))
        folders: dict[str, QTreeWidgetItem] = {}

        def folder_item(rel: str) -> QTreeWidgetItem | None:
            if rel in ("", "."):
                return None
            if rel not in folders:
                parent = folder_item(str(Path(rel).parent))
                it = QTreeWidgetItem([Path(rel).name, "", ""])
                it.setData(0, Qt.UserRole, str(md / rel))
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
                (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
                folders[rel] = it
            return folders[rel]

        for d in dirs[1:]:
            folder_item(d.strip("/"))
        for s in found:
            rel = s.path.parent.relative_to(md).as_posix()
            parent = folder_item(rel)
            it = QTreeWidgetItem([s.title, str(len(s.parts)), s.path.name])
            it.setToolTip(0, "\n".join(f"X:{p.id}  {p.name}" for p in s.parts))
            it.setToolTip(2, f"In game: /play {s.path.relative_to(md).with_suffix('').as_posix()}")
            it.setData(0, Qt.UserRole, str(s.path))
            (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
        self.tree.expandToDepth(0)
        accs = songbook_accounts(self.ctx.settings)
        self.status.setText(f"{len(found)} songs in {md}")
        if not songbook_installed(self.ctx.settings):
            self.hint.setText("Tip: the Songbook plugin (Downloads → Plugins, search “Songbook”) lets you pick and "
                              "play these songs in game.")
        elif not accs:
            self.hint.setText("Log in once (or add your account on the Play tab) so the Songbook list can be written.")
        else:
            self.hint.setText(f"Songbook list is written for: {', '.join(accs)}")

    # ---- import ------------------------------------------------------------------------
    def _pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Import songs", str(Path.home()),
                                                "Songs (*.abc *.txt *.zip);;All files (*)")
        if paths:
            self.import_paths([Path(p) for p in paths])

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Import a folder of songs", str(Path.home()))
        if d:
            self.import_paths([Path(d)])

    def import_paths(self, paths: list[Path]) -> None:
        md = self.music_dir()
        if md is None:
            QMessageBox.warning(self, "Music", "Set your LOTRO documents folder on the Settings tab first.")
            return
        sub = self.dest.currentData() or ""
        try:
            added = songs.import_songs(paths, md, sub)
        except Exception as e:  # noqa: BLE001 - OSError, or a corrupt zip
            QMessageBox.warning(self, "Import", f"Import failed: {e}")
            return
        self.ctx.log(f"Imported {len(added)} song file(s) into {md / sub if sub else md}")
        self._music_changed()
        self.status.setText(f"Imported {len(added)} song file(s)." + ("" if added else " (Nothing new.)"))

    def _music_changed(self) -> None:
        self.refresh()
        if self.ctx.settings.songbook_auto:
            self.update_songbook(announce=False)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.import_paths(paths)

    # ---- management ---------------------------------------------------------------------
    def _new_folder(self) -> None:
        md = self.music_dir()
        if md is None:
            return
        name, ok = QInputDialog.getText(self, "New folder", "Folder name (inside Music):")
        name = name.strip().strip("/")
        if ok and name and ".." not in Path(name).parts:
            (md / name).mkdir(parents=True, exist_ok=True)
            self.refresh()
            self.dest.setCurrentIndex(max(self.dest.findData(name), 0))

    def _delete(self) -> None:
        md = self.music_dir()
        items = self.tree.selectedItems()
        if md is None or not items:
            return
        paths = [Path(i.data(0, Qt.UserRole)) for i in items]
        listing = "\n".join(f"  • {p.relative_to(md)}{'/ (folder and everything in it)' if p.is_dir() else ''}"
                            for p in paths[:15])
        more = f"\n  … and {len(paths) - 15} more" if len(paths) > 15 else ""
        if QMessageBox.question(self, "Delete", f"Delete from {md}?\n\n{listing}{more}") != QMessageBox.Yes:
            return
        for p in paths:
            try:
                p.resolve().relative_to(md.resolve())
            except ValueError:
                continue
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
        self.ctx.log(f"Deleted {len(paths)} item(s) from Music")
        self._music_changed()

    def _open_item(self, item: QTreeWidgetItem) -> None:
        p = Path(item.data(0, Qt.UserRole))
        if p.is_file():
            open_path(p)

    def update_songbook(self, announce: bool) -> None:
        s = self.ctx.settings
        md, pd = self.music_dir(), s.subdir("PluginData")
        if md is None or pd is None:
            return
        accs = songbook_accounts(s)
        if not accs:
            if announce:
                QMessageBox.information(self, "Songbook", "No accounts found in PluginData yet. Log in to the game "
                                        "once, or add your account on the Play tab, then try again.")
            return

        def done(r):
            count, files = r
            self.ctx.log(f"Songbook list updated ({count} songs) for {', '.join(accs)}")
            if announce:
                self.status.setText(f"Songbook list updated: {count} songs, for {', '.join(accs)}. "
                                    "In game, reload the plugin or relog to see changes.")

        run_task(lambda: songs.write_songbook(md, pd, accs), on_done=done,
                 on_error=lambda e: self.status.setText(f"Songbook update failed: {e}"))

    def _save_auto(self, on: bool) -> None:
        self.ctx.settings.songbook_auto = on
        self.ctx.save()


class ToolRow(QWidget):
    """One music tool: path, Start, Download (or project page), and how old its latest release is."""

    def __init__(self, ctx: AppContext, key: str, setting: str, blurb: str, on_exit, parent=None):
        super().__init__(parent)
        self.ctx, self.key, self.setting, self.on_exit = ctx, key, setting, on_exit
        self.info = tools.TOOLS[key]
        self.latest: tools.Latest | None = None
        title = QLabel(f"<b>{self.info.name}</b> — {blurb}")
        title.setWordWrap(True)
        self.path = PathPicker(directory=False, placeholder=f"Path to {self.info.name} (.jar or .exe)",
                               file_filter="Programs (*.jar *.exe);;All files (*)")
        self.path.set_text(getattr(ctx.settings, setting))
        self.start = QPushButton("Start")
        self.download = QPushButton("Download")
        self.page = QPushButton("Project page")
        self.note = QLabel("Checking latest release…")
        self.note.setProperty("subtle", True)
        self.note.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.path, 1)
        row.addWidget(self.start)
        row.addWidget(self.download)
        row.addWidget(self.page)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.addWidget(title)
        lay.addLayout(row)
        lay.addWidget(self.note)
        self.path.changed.connect(self._save)
        self.start.clicked.connect(self._start)
        self.download.clicked.connect(self._download)
        self.page.clicked.connect(lambda: open_url(self.info.page))
        self.download.setEnabled(False)
        run_task(lambda: tools.latest(key), on_done=self._got_latest,
                 on_error=lambda e: self.note.setText(f"Couldn't check for releases: {e}"))

    def _save(self, text: str) -> None:
        setattr(self.ctx.settings, self.setting, text)
        self.ctx.save()

    def _got_latest(self, rel: tools.Latest) -> None:
        self.latest = rel
        have = tools.installed_version(self.key, self.ctx.settings.downloads_path())
        self.note.setText(rel.describe() + (f" · downloaded: {have}" if have else ""))
        self.download.setEnabled(bool(rel.download))
        if not rel.download:
            self.download.setToolTip("Nothing to download: this project publishes no ready-to-run release")
        elif have and have == rel.version:
            self.download.setText("Re-download")

    def _start(self) -> None:
        path = self.path.text()
        if not path:
            QMessageBox.information(self, self.info.name, f"Download {self.info.name} first, or Browse… to it.")
            return
        try:
            argv, env, cwd = runner.tool_command(self.ctx.settings, path)
            proc = runner.ManagedProcess(self.info.name, argv, env, cwd, self)
        except (runner.RunnerError, OSError) as e:
            QMessageBox.warning(self, self.info.name, str(e))
            return
        proc.output.connect(lambda l: self.ctx.log(f"{self.info.name}: {l}"))
        proc.finished.connect(lambda _: self.on_exit())
        self.ctx.log(f"Started {self.info.name}")

    def _download(self) -> None:
        dl = self.ctx.settings.downloads_path()
        self.download.setEnabled(False)
        self.note.setText(f"Downloading into {dl / self.info.folder}…")

        def prog(p):
            stage, d, t = p
            self.note.setText(f"{stage}… {d * 100 // t}%" if t else f"{stage}…")

        def done(path):
            self.path.set_text(str(path), emit=True)
            self.ctx.log(f"Downloaded {self.info.name} to {path}")
            self._got_latest(self.latest)
            self.download.setEnabled(True)

        def failed(e):
            self.download.setEnabled(True)
            self.note.setText(f"Download failed: {e}")

        run_task(lambda progress: tools.install(self.key, dl, lambda *a: progress(a)),
                 on_done=done, on_error=failed, on_progress=prog)
