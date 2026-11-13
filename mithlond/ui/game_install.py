"""'Install the game…': download the official installer and run it in the prefix (Settings → Locations, and
the Play tab when no game folder is set)."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QProgressDialog, QWidget

from .. import gameinstall, runner
from ..config import check_game_dir
from .context import AppContext
from .workers import run_task


def install_game(parent: QWidget, ctx: AppContext) -> None:
    s = ctx.settings
    prefix = s.prefix_path()
    if QMessageBox.question(
            parent, "Install the game",
            "Mithlond downloads the official LOTRO installer (lotrolive.exe, about 46 MB, from lotro.com) and runs "
            f"it with your Wine/Proton setup, into the prefix\n\n{prefix}\n\n"
            "It installs the game launcher and part of the game. The rest of the game (many GB) downloads "
            "afterwards with Play → Check for game updates.\n\nInstall now?") != QMessageBox.Yes:
        return
    dlg = QProgressDialog("Downloading the installer…", "Cancel", 0, 100, parent)
    dlg.setWindowTitle("Install the game")
    dlg.setMinimumDuration(0)
    dlg.setValue(0)
    ctx.log(f"Downloading the LOTRO installer from {gameinstall.INSTALLER_URL}")

    def progress(p):
        done, total = p
        if total:
            dlg.setValue(int(done * 100 / total))

    def failed(e):
        dlg.close()
        ctx.log(f"Game install: {e}")
        QMessageBox.warning(parent, "Install the game", str(e))

    def downloaded(exe):
        if dlg.wasCanceled():
            return
        dlg.setLabelText("Installing… (the installer shows its own progress window)")
        dlg.setRange(0, 0)
        dlg.setCancelButton(None)
        try:
            argv, env = runner.windows_command(s, exe, gameinstall.SILENT_ARGS)
            proc = runner.ManagedProcess("installer", argv, env, exe.parent, parent)
        except (runner.RunnerError, OSError) as e:
            failed(e)
            return
        proc.output.connect(lambda line: ctx.log(f"installer: {line}"))
        proc.finished.connect(lambda code: finished(code))
        ctx.log("Started the LOTRO installer")

    def finished(code: int):
        dlg.close()
        found = gameinstall.installed_in(prefix)
        if not found:
            ctx.log(f"Game install: the installer ended (code {code}) but no game folder was found in {prefix}")
            QMessageBox.warning(parent, "Install the game",
                                f"The installer ended, but no game folder was found in {prefix}/drive_c. If it "
                                "installed somewhere else, choose that folder in Settings → Locations.")
            return
        game = found[0]
        current_ok = bool(s.game_dir) and check_game_dir(s.game_path)[0]
        if not current_ok or QMessageBox.question(
                parent, "Install the game", f"The game was installed in\n{game}\n\nUse it as Mithlond's game "
                f"folder instead of\n{s.game_dir}?") == QMessageBox.Yes:
            s.game_dir = str(game)
            ctx.save()
        ctx.log(f"Game installed in {game}")
        QMessageBox.information(parent, "Install the game",
                                f"Installed in\n{game}\n\nNext: on the Play tab press 'Check for game updates' to "
                                "download the rest of the game, then log in and play.")

    run_task(lambda report: gameinstall.download(lambda d, t: report((d, t))), on_done=downloaded,
             on_error=failed, on_progress=progress)
