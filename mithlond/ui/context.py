"""State shared by all tabs: settings, logging, running game clients and LotRO Companion."""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QObject, QTimer, Signal

from .. import runner
from ..config import CACHE_DIR, Settings


class AppContext(QObject):
    log_line = Signal(str)
    settings_changed = Signal()
    games_changed = Signal(int)  # number of running game clients
    companion_changed = Signal(bool)
    music_changed = Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.games: list[runner.ManagedProcess] = []
        self.companion: runner.ManagedProcess | None = None
        self._companion_timer: QTimer | None = None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._logfile = open(CACHE_DIR / "mithlond.log", "a", encoding="utf-8")

    # ---- logging -------------------------------------------------------------
    def log(self, msg: str) -> None:
        line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
        self._logfile.write(line + "\n")
        self._logfile.flush()
        self.log_line.emit(line)

    def save(self) -> None:
        self.settings.save()
        self.settings_changed.emit()

    # ---- game clients --------------------------------------------------------
    def add_game(self, proc: runner.ManagedProcess) -> None:
        self.games.append(proc)
        proc.output.connect(lambda l: self.log(f"game: {l}"))
        proc.finished.connect(lambda code, p=proc: self._game_finished(p, code))
        self.games_changed.emit(len(self.games))
        s = self.settings
        if s.companion_with_game and s.companion_path().exists() and not self.companion_running():
            delay = max(0, s.companion_delay)
            self.log(f"Starting LotRO Companion in {delay}s")
            self._companion_timer = QTimer(self)
            self._companion_timer.setSingleShot(True)
            self._companion_timer.timeout.connect(self._start_companion_if_game_running)
            self._companion_timer.start(delay * 1000)

    def _start_companion_if_game_running(self) -> None:
        if self.games and not self.companion_running():
            self.start_companion()

    def _game_finished(self, proc: runner.ManagedProcess, code: int) -> None:
        if proc in self.games:
            self.games.remove(proc)
        self.log(f"Game client exited (code {code})")
        self.games_changed.emit(len(self.games))
        if not self.games:
            if self._companion_timer:
                self._companion_timer.stop()
            if self.settings.companion_close_with_game and self.companion_running():
                self.log("Closing LotRO Companion (game closed)")
                self.stop_companion()

    # ---- LotRO Companion -----------------------------------------------------
    def companion_running(self) -> bool:
        return self.companion is not None and self.companion.running()

    def start_companion(self) -> bool:
        if self.companion_running():
            return True
        try:
            argv, env, cwd = runner.companion_command(self.settings)
        except runner.RunnerError as e:
            self.log(f"LotRO Companion: {e}")
            return False
        how = "Java" if self.settings.companion_mode == "native" else self.settings.runner
        if self.settings.companion_mode != "native" and runner.proton_uses_start_unix(self.settings):
            how += "; this Proton build can't start Companion's Java directly, so it uses Companion's own launcher"
        self.log(f"Starting LotRO Companion ({how})")
        try:
            self.companion = runner.ManagedProcess("companion", argv, env, cwd, self)
        except OSError as e:
            self.log(f"LotRO Companion failed to start: {e}")
            return False
        self.companion.output.connect(lambda l: self.log(f"companion: {l}"))
        self.companion.finished.connect(self._companion_finished)
        self.companion_changed.emit(True)
        return True

    def _companion_finished(self, code: int) -> None:
        self.log(f"LotRO Companion exited (code {code})")
        self.companion_changed.emit(False)

    def stop_companion(self) -> None:
        if self.companion_running():
            self.companion.stop()

    def shutdown(self) -> None:
        self._logfile.close()
