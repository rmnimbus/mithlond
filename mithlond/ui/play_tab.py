"""Play tab: account, world, login, queue and launch."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QStyle, QVBoxLayout, QWidget,
)

from .. import config, gameinstall, gls, keystore, procs, runner
from ..config import Account, check_game_dir
from .context import AppContext
from .game_install import install_game
from .news_panel import NewsPanel
from .widgets import open_path, open_url, subtle
from .workers import run_task


class PlayTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.datacenter: gls.Datacenter | None = None
        self.local_cfg: gls.LocalLauncherConfig | None = None
        self.world_status: dict[str, str] = {}
        self._cancel = False
        self._busy = False
        self._patch_queue: list[list[str]] = []
        self._patch_proc: runner.ManagedProcess | None = None

        banner = QLabel("MITHLOND")
        banner.setObjectName("banner")
        banner.setAlignment(Qt.AlignCenter)
        sub = subtle("The Lord of the Rings Online — Linux launcher")
        sub.setAlignment(Qt.AlignCenter)

        self.account = QComboBox()
        self.account.setEditable(True)
        self.account.lineEdit().setPlaceholderText("Account name")
        self.account.setMinimumWidth(260)
        self.remove_acc = QPushButton("Forget")
        self.remove_acc.setToolTip("Remove this account and its saved password")
        acc_row = QHBoxLayout()
        acc_row.addWidget(self.account, 1)
        acc_row.addWidget(self.remove_acc)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Password")
        self.remember = QCheckBox("Save password in the system keyring (encrypted)")
        self.remember.setToolTip("Stored through the Secret Service API (KWallet, GNOME Keyring, KeePassXC…),\n"
                                 "never in Mithlond's config file.")
        self.pw_state = QLabel()
        self.pw_state.setProperty("subtle", True)
        if not keystore.available():
            self.remember.setEnabled(False)
            self.remember.setToolTip("secret-tool (libsecret) is not installed, so the password can't be saved")

        self.world = QComboBox()
        self.world.setMinimumWidth(260)
        self.refresh_worlds = QPushButton()
        self.refresh_worlds.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh_worlds.setToolTip("Refresh worlds and their status")
        world_row = QHBoxLayout()
        world_row.addWidget(self.world, 1)
        world_row.addWidget(self.refresh_worlds)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Account", acc_row)
        form.addRow("Password", self.password)
        form.addRow("", self.remember)
        form.addRow("", self.pw_state)
        form.addRow("World", world_row)
        # Play options: frame rate limit, voice chat, safe mode for one start
        self.fps = QSpinBox()
        self.fps.setRange(0, 500)
        self.fps.setSingleStep(10)
        self.fps.setSpecialValueText("No limit")
        self.fps.setSuffix(" FPS")
        self.fps.setToolTip("Caps the frame rate (less heat, fan noise and power use). Works with Wine/Proton's\n"
                            "DXVK (DirectX 11, the default); sets DXVK_FRAME_RATE.")
        self.skip_intro = QCheckBox("Skip intro")
        self.skip_intro.setToolTip("Skips the Turbine logo video that plays at every start (Mithlond sets the file\n"
                                   "aside; unticking puts it back) and marks the intro cinematic as already seen.")
        self.voice_off = QCheckBox("Voice chat off")
        self.voice_off.setToolTip("Starts the game without its voice chat system (--voiceoff).")
        self.safe_mode = QCheckBox("Safe mode")
        self.safe_mode.setToolTip("For the next start only (--safe): the game resets its graphics settings to safe\n"
                                  "values (1024x768 windowed, DirectX 9, medium detail) and keeps them. Use it when\n"
                                  "the game crashes or shows a black screen after a graphics change. Mithlond backs\n"
                                  "up UserPreferences.ini first (the log shows where). Unticks itself after the start.")
        opts_row = QHBoxLayout()
        opts_row.addWidget(QLabel("Frame rate"))
        opts_row.addWidget(self.fps)
        opts_row.addSpacing(12)
        opts_row.addWidget(self.skip_intro)
        opts_row.addStretch()
        opts_row2 = QHBoxLayout()
        opts_row2.addWidget(self.voice_off)
        opts_row2.addSpacing(12)
        opts_row2.addWidget(self.safe_mode)
        opts_row2.addStretch()
        form.addRow("Options", opts_row)
        form.addRow("", opts_row2)
        s0 = self.ctx.settings
        self.fps.setValue(max(0, s0.fps_limit))
        self.voice_off.setChecked(s0.voice_off)
        self.skip_intro.setChecked(s0.skip_intro)
        self.skip_intro.toggled.connect(self._options_changed)
        self.fps.valueChanged.connect(self._options_changed)
        self.voice_off.toggled.connect(self._options_changed)

        form_w = QWidget()
        form_w.setLayout(form)
        form_w.setMaximumWidth(520)

        self.play = QPushButton("PLAY")
        self.play.setObjectName("play")
        self.play.setDefault(True)
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(420)

        self.patch_btn = QPushButton("Check for game updates")
        self.patch_btn.setToolTip("Run the game's patcher (patchclient.dll) through your Wine/Proton runner")
        self.official_btn = QPushButton("Official launcher")
        self.official_btn.setToolTip("Run LotroLauncher.exe, e.g. if patching here fails")
        self.folder_btn = QPushButton("Game folder")
        self.account_btn = QPushButton("My LOTRO account")
        self.account_btn.setToolTip(f"Open the Standing Stone Games account page in your browser\n"
                                    f"({gameinstall.ACCOUNT_URL})")
        self.install_btn = QPushButton("Install the game…")
        self.install_btn.setToolTip("No game folder yet: download the official installer from lotro.com and "
                                    "install the game with your Wine/Proton setup")
        tools = QHBoxLayout()
        tools.addStretch()
        for b in (self.install_btn, self.patch_btn, self.official_btn, self.folder_btn, self.account_btn):
            tools.addWidget(b)
        tools.addStretch()

        main = QWidget()
        lay = QVBoxLayout(main)
        lay.addSpacing(18)
        lay.addWidget(banner)
        lay.addWidget(sub)
        lay.addSpacing(18)
        lay.addWidget(form_w, 0, Qt.AlignHCenter)
        lay.addSpacing(12)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("stop")
        self.stop_btn.setToolTip("Close every LOTRO game client, LotRO Companion, the official launcher/patcher,\n"
                                 "Maestro and BruTE, including ones started outside Mithlond")
        play_row = QHBoxLayout()
        play_row.addStretch()
        play_row.addWidget(self.play)
        play_row.addWidget(self.stop_btn)
        play_row.addStretch()
        lay.addLayout(play_row)
        lay.addWidget(self.progress, 0, Qt.AlignHCenter)
        lay.addWidget(self.status)
        lay.addStretch()
        lay.addLayout(tools)

        self.news = NewsPanel(ctx)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.news)
        split.addWidget(main)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([400, 600])
        split.setChildrenCollapsible(False)
        self.news.setMinimumWidth(260)
        outer = QHBoxLayout(self)
        outer.addWidget(split)

        self.account.currentTextChanged.connect(self._account_changed)
        self.remove_acc.clicked.connect(self._forget_account)
        self.refresh_worlds.clicked.connect(lambda: self.load_worlds(force=True))
        self.play.clicked.connect(self._play_clicked)
        self.password.returnPressed.connect(self._play_clicked)
        self.patch_btn.clicked.connect(self.start_patch)
        self.official_btn.clicked.connect(self.run_official_launcher)
        self.account_btn.clicked.connect(lambda: open_url(gameinstall.ACCOUNT_URL))
        self.install_btn.clicked.connect(lambda: install_game(self, self.ctx))
        self.ctx.settings_changed.connect(self._show_install)
        self._show_install()
        self.folder_btn.clicked.connect(lambda: self.ctx.settings.game_path and open_path(self.ctx.settings.game_path))
        self.world.currentIndexChanged.connect(self._world_changed)
        ctx.games_changed.connect(self._games_changed)
        self.stop_btn.clicked.connect(self.stop_all)
        self._join = False
        self._watch = QTimer(self)
        self._watch.setInterval(2000)
        self._watch.timeout.connect(self._check_clients)
        self._launched_at = 0.0
        self._gm_registered: set[int] = set()
        ctx.settings_changed.connect(self._settings_changed)

        self._fill_accounts()
        self.remember.setChecked(self.ctx.settings.remember_password and keystore.available())

    # ---- accounts ---------------------------------------------------------------
    def _fill_accounts(self) -> None:
        s = self.ctx.settings
        self.account.blockSignals(True)
        self.account.clear()
        for a in s.accounts:
            self.account.addItem(a.username)
        if s.last_account:
            self.account.setCurrentText(s.last_account)
        self.account.blockSignals(False)
        self._account_changed(self.account.currentText())

    def _pw_status(self, text: str, bad: bool = False) -> None:
        self.pw_state.setText(text)
        self.pw_state.setObjectName("bad" if bad else "")
        self.pw_state.style().unpolish(self.pw_state)
        self.pw_state.style().polish(self.pw_state)

    def _account_changed(self, name: str) -> None:
        self.password.clear()
        self._pw_status("" if keystore.available() else "No keyring tool found: the password is not saved.")
        acc = self.ctx.settings.account(name) if name else None
        if acc is None:
            return
        if acc.world:
            i = self.world.findData(acc.world)
            if i >= 0:
                self.world.setCurrentIndex(i)
        if keystore.available():
            def loaded(pw):
                if self.account.currentText() == name and pw:
                    self.password.setText(pw)
                    self._pw_status("🔒 Password loaded from your keyring")
            run_task(lambda: keystore.get_password(name), on_done=loaded)

    def _forget_account(self) -> None:
        name = self.account.currentText().strip()
        acc = self.ctx.settings.account(name)
        if not acc:
            return
        if QMessageBox.question(self, "Forget account", f"Remove {name} and its saved password?") != QMessageBox.Yes:
            return
        self.ctx.settings.accounts.remove(acc)
        keystore.delete_password(name)
        self.ctx.save()
        self._fill_accounts()

    # ---- worlds -------------------------------------------------------------------
    def _settings_changed(self) -> None:
        if self.datacenter is None and self.world.count() == 0:
            self.load_worlds()

    def load_worlds(self, force: bool = False) -> None:
        game = self.ctx.settings.game_path
        if not game or not check_game_dir(game)[0]:
            self.status.setText("Set your LOTRO folder on the Settings tab.")
            return
        if force:
            self.datacenter = None

        def work():
            local = gls.read_local_config(game)
            dc = gls.get_datacenter(local)
            with ThreadPoolExecutor(8) as ex:
                def st(w):
                    try:
                        ws = gls.get_world_status(w, local.gls_datacenter_url)
                        return w.name, "full" if ws.full else "open"
                    except gls.WorldUnavailable:
                        return w.name, "closed"
                    except Exception:  # noqa: BLE001
                        return w.name, "unknown"
                statuses = dict(ex.map(st, dc.worlds))
            return local, dc, statuses

        self.refresh_worlds.setEnabled(False)
        run_task(work, on_done=self._worlds_loaded, on_error=self._worlds_failed)

    def _worlds_loaded(self, res) -> None:
        self.local_cfg, self.datacenter, self.world_status = res
        self.refresh_worlds.setEnabled(True)
        acc = self.ctx.settings.account(self.account.currentText())
        current = self.world.currentData() or (acc.world if acc else "")
        self.world.blockSignals(True)
        self.world.clear()
        marks = {"open": "●  open", "full": "●  full", "closed": "○  closed", "unknown": "?"}
        for w in self.datacenter.worlds:
            self.world.addItem(f"{w.name}    {marks[self.world_status.get(w.name, 'unknown')]}", w.name)
        i = self.world.findData(current)
        self.world.setCurrentIndex(i if i >= 0 else 0)
        self.world.blockSignals(False)
        if not self._busy:
            self.status.setText("")

    def _worlds_failed(self, e: Exception) -> None:
        self.refresh_worlds.setEnabled(True)
        self.status.setText(f"Could not load worlds: {e}")
        self.ctx.log(f"World list failed: {e}")

    def _world_changed(self) -> None:
        acc = self.ctx.settings.account(self.account.currentText())
        if acc and self.world.currentData():
            acc.world = self.world.currentData()
            self.ctx.save()

    # ---- play -------------------------------------------------------------------------
    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._busy = busy
        self.play.setText("CANCEL" if busy else ("PLAY ANOTHER" if self.ctx.games else "PLAY"))
        self.status.setText(text)
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0)
        for w in (self.account, self.password, self.world, self.patch_btn, self.official_btn):
            w.setEnabled(not busy)

    def _games_changed(self, n: int) -> None:
        if not self._busy:
            self.play.setText("PLAY ANOTHER" if n else "PLAY")
            if n:
                self._check_clients()
            else:
                self._watch.stop()
                self.status.setText("")

    def _check_clients(self) -> None:
        """Report what's really running: the wrapper (umu-run/wine) can be alive long before
        (or without) lotroclient itself."""
        if self._busy:
            return
        if not self.ctx.games:
            self._watch.stop()
            return
        found = procs.game_clients()
        clients = len(found)
        s = self.ctx.settings
        if s.opt_gamemode and s.opt_gamescope:  # gamescope blocks gamemoderun's preload: register directly
            for c in found:
                if c.pid not in self._gm_registered:
                    self._gm_registered.add(c.pid)
                    ok = runner.gamemode_register(c.pid)
                    self.ctx.log(f"GameMode: {'registered' if ok else 'could not register'} game process {c.pid}")
        waited = time.monotonic() - self._launched_at
        if clients:
            self.status.setText(f"● Game running ({clients} client{'s' if clients != 1 else ''})")
        elif waited < 45:
            self.status.setText("Starting the game…")
        else:
            self.status.setText("The game hasn't appeared yet. If something else is running in the same prefix, "
                                "Proton waits for it to close. Use STOP and try again, or check the log.")

    def _prefix_ready(self, s) -> bool:
        """Proton's default verb waits until everything else in the prefix has exited, so a program left
        running there (e.g. Companion started by another launcher) silently blocks the game. Ask first."""
        prefix = s.prefix_path()
        others = procs.windows_programs_in_prefix(prefix)
        if not others:
            return True
        names = "\n".join(f"  • {p.describe()}" for p in others[:8])
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Prefix in use")
        box.setText(f"These programs are already running in {prefix}:\n\n{names}\n\n"
                    "Proton normally waits for them to close before it starts the game.")
        stop = box.addButton("Close them, then play", QMessageBox.AcceptRole)
        along = box.addButton("Start alongside them", QMessageBox.YesRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(stop)
        box.exec()
        if box.clickedButton() is stop:
            self.ctx.log("Closing programs in the prefix: " + ", ".join(p.describe() for p in others))
            procs.terminate(others)
            return True
        if box.clickedButton() is along:
            self._join = True
            return True
        return False

    def stop_all(self) -> None:
        found = procs.related(self.ctx.settings)
        mine = [p for p in (*self.ctx.games, self.ctx.companion) if p and p.running()]
        if not found and not mine:
            self.status.setText("Nothing to stop.")
            return
        names = sorted({p.exe_name for p in found if p.exe_name.endswith((".exe", "java"))} or {"game processes"})
        if QMessageBox.question(self, "Stop everything",
                                "Close all LOTRO game clients and the other programs this launcher can start?\n\n"
                                + ", ".join(names)) != QMessageBox.Yes:
            return
        self.stop_btn.setEnabled(False)
        self.status.setText("Stopping…")
        for p in mine:
            p.stop(timeout=3)

        def done(pids):
            self.stop_btn.setEnabled(True)
            self.ctx.log(f"Stopped {len(pids)} process(es)")
            self.status.setText(f"Stopped {len(pids)} process(es).")
        run_task(lambda: procs.terminate(procs.related(self.ctx.settings)), on_done=done,
                 on_error=lambda e: (self.stop_btn.setEnabled(True), self.status.setText(f"Stop failed: {e}")))

    def _play_clicked(self) -> None:
        if self._busy:
            self._cancel = True
            self.status.setText("Cancelling…")
            return
        s = self.ctx.settings
        game = s.game_path
        ok, msg = check_game_dir(game) if game else (False, "not set")
        if not ok:
            QMessageBox.warning(self, "Game folder", f"Your LOTRO folder is not set up correctly ({msg}).\n"
                                "Choose it on the Settings tab.")
            return
        try:  # catch runner problems (missing wine, unusable prefix, missing gamescope…) before logging in
            runner.apply_game_options(s, *runner.windows_command(s, "lotroclient.exe", []))
        except runner.RunnerError as e:
            QMessageBox.warning(self, "Can't start the game", f"{e}\n\nSee Settings → Runners and Prefix.")
            return
        self._join = bool(self.ctx.games)  # a second client joins the first one's session
        if s.runner == "umu" and not self._join and not self._prefix_ready(s):
            return
        user = self.account.currentText().strip()
        pw = self.password.text()
        world = self.world.currentData()
        if not user or not pw:
            QMessageBox.information(self, "Login", "Enter your account name and password.")
            return
        if not world:
            QMessageBox.information(self, "World", "No world selected (are the login servers reachable?).")
            return
        acc = s.account(user)
        if acc is None:
            acc = Account(user)
            s.accounts.append(acc)
            self.account.addItem(user)
        acc.world = world
        s.last_account = user
        s.remember_password = self.remember.isChecked()
        self.ctx.save()
        if self.remember.isChecked():
            def saved(_):
                self._pw_status("🔒 Password saved encrypted in your keyring")

            def not_saved(e):
                self._pw_status(f"Password not saved: {e}", bad=True)
                self.ctx.log(f"Could not save the password to the keyring: {e}")
            run_task(lambda: keystore.set_password(user, pw), on_done=saved, on_error=not_saved)
        elif keystore.available():
            run_task(lambda: keystore.delete_password(user),
                     on_done=lambda _: self._pw_status("Password not saved (any saved copy was removed)"))

        self._cancel = False
        self._set_busy(True, "Logging in…")
        self.ctx.log(f"Logging in as {user} to {world}")

        def work():
            local = self.local_cfg or gls.read_local_config(game)
            dc = self.datacenter or gls.get_datacenter(local)
            cfg = gls.get_launcher_config(dc.launcher_config_url)
            res = gls.login(dc.auth_server, user, pw)
            return local, dc, cfg, res

        run_task(work, on_done=lambda r: self._logged_in(user, world, *r), on_error=self._failed)

    def _logged_in(self, user: str, world_name: str, local, dc, cfg, res: gls.LoginResult) -> None:
        if self._cancel:
            return self._set_busy(False, "Cancelled")
        self.local_cfg, self.datacenter = local, dc
        subs = res.for_game(local.game_name)
        if not subs:
            return self._failed(gls.GLSError("This account has no LOTRO subscription."))
        acc = self.ctx.settings.account(user)
        sub = subs[0]
        if len(subs) > 1:
            labels = [f"{x.description or x.name}" for x in subs]
            last = next((i for i, x in enumerate(subs) if acc and x.name == acc.subscription), 0)
            label, ok = QInputDialog.getItem(self, "Subscription", "This account has several game subscriptions.\n"
                                             "Which one do you want to play?", labels, last, False)
            if not ok:
                return self._set_busy(False, "Cancelled")
            sub = subs[labels.index(label)]
            if acc:
                acc.subscription = sub.name
                self.ctx.save()
        world = next((w for w in dc.worlds if w.name == world_name), None)
        if world is None:
            return self._failed(gls.GLSError(f"World {world_name} not found"))
        self.status.setText(f"Joining {world_name}…")

        def work(progress):
            ws = gls.get_world_status(world, local.gls_datacenter_url)
            if not ws.allows(sub):
                raise gls.GLSError("Your subscription is not allowed on this world right now.")
            gls.wait_in_queue(cfg, sub.name, res.ticket, ws.queue_url,
                              on_position=lambda n: progress(n), cancelled=lambda: self._cancel)
            return ws

        run_task(work, on_done=lambda ws: self._launch(cfg, sub, world, ws, res.ticket),
                 on_error=self._failed, on_progress=lambda n: self.status.setText(f"Position in queue: {n}"))

    def _launch(self, cfg, sub: gls.Subscription, world: gls.World, ws: gls.WorldStatus, ticket: str) -> None:
        s = self.ctx.settings
        game = s.game_path
        try:
            exe = gls.client_executable(game, cfg, s.client)
            args = gls.client_arguments(cfg, sub.name, ws.login_server, ticket, world.chat_server,
                                        s.language, s.high_res) + runner.prefs_args(s)
            if self.safe_mode.isChecked():
                backup = runner.backup_preferences(s)
                self.ctx.log("Safe mode: the game will reset its graphics settings. "
                             + (f"Previous settings saved as {backup}" if backup else "No settings file to back up."))
            args += runner.client_option_args(s, safe=self.safe_mode.isChecked())
            for note in runner.apply_intro_skip(s):  # after prefs_args, which may have just seeded the settings
                self.ctx.log(f"Intro videos: {note}")
            argv, env = runner.windows_command(s, exe, args, join=self._join)
            scr = self.screen()
            size = scr.size() * scr.devicePixelRatio() if scr else None
            argv, env = runner.apply_game_options(s, argv, env, (size.width(), size.height()) if size else None)
            for note in runner.effect_notes:
                self.ctx.log(f"Visual effects: {note}")
            if s.opt_gamemode and (gm := runner.gamemode_problem()):
                self.ctx.log(f"GameMode warning: {gm}")
            if se := config.selinux_problem():
                self.ctx.log(f"Warning: {se}")
            self.ctx.log("Starting " + " ".join(gls.redact(argv, ticket, sub.name)))
            proc = runner.ManagedProcess("game", argv, env, game, self.ctx)
        except (gls.GLSError, runner.RunnerError, OSError) as e:
            return self._failed(e)
        self.ctx.add_game(proc)
        if self.safe_mode.isChecked():
            self.safe_mode.setChecked(False)  # one start only
        self._set_busy(False, "")
        self._launched_at = time.monotonic()
        self._check_clients()
        self._watch.start()
        if s.on_game_start == "minimize":
            self.window().showMinimized()

    def _options_changed(self, *_):
        s = self.ctx.settings
        s.fps_limit, s.voice_off = self.fps.value(), self.voice_off.isChecked()
        s.skip_intro = self.skip_intro.isChecked()
        self.ctx.save()

    def _failed(self, e: Exception) -> None:
        msg = str(e) or e.__class__.__name__
        if self._cancel:
            msg = "Cancelled"
        self.ctx.log(f"Launch failed: {msg}")
        self._set_busy(False, msg)
        if not self._cancel and isinstance(e, gls.LoginFailed):
            self.password.setFocus()
            self.password.selectAll()

    # ---- patching ----------------------------------------------------------------------
    def start_patch(self) -> None:
        s = self.ctx.settings
        game = s.game_path
        if not game or not check_game_dir(game)[0]:
            return
        if self.ctx.games:
            QMessageBox.information(self, "Patching", "Close the game before patching.")
            return
        if not (game / "patchclient.dll").exists():
            QMessageBox.warning(self, "Patching", "patchclient.dll is not in the game folder.")
            return
        self._set_busy(True, "Getting patch server…")
        self.play.setEnabled(False)

        def work():
            local = self.local_cfg or gls.read_local_config(game)
            dc = self.datacenter or gls.get_datacenter(local)
            cfg = gls.get_launcher_config(dc.launcher_config_url)
            return dc, cfg

        def go(r):
            dc, cfg = r
            self._patch_queue = runner.patch_phases(dc.patch_server, s.language,
                                                    cfg.get("Patching.ProductCode", "LOTRO"), s.high_res)
            self._patch_total = len(self._patch_queue)
            self._next_patch_phase(0)

        run_task(work, on_done=go, on_error=self._patch_failed)

    def _next_patch_phase(self, code: int) -> None:
        if code != 0:
            return self._patch_failed(RuntimeError(f"patcher exited with code {code}"))
        if not self._patch_queue:
            self.ctx.log("Patching finished")
            self.play.setEnabled(True)
            return self._set_busy(False, "Game is up to date.")
        args = self._patch_queue.pop(0)
        phase = self._patch_total - len(self._patch_queue)
        self.status.setText(f"Patching: phase {phase} of {self._patch_total} (see log for details)…")
        try:
            argv, env = runner.patch_command(self.ctx.settings, args)
            self.ctx.log("Patch phase %d: %s" % (phase, " ".join(args)))
            self._patch_proc = runner.ManagedProcess("patch", argv, env, self.ctx.settings.game_path, self)
        except (runner.RunnerError, OSError) as e:
            return self._patch_failed(e)
        self._patch_proc.output.connect(lambda l: self.ctx.log(f"patch: {l}"))
        self._patch_proc.finished.connect(self._next_patch_phase)

    def _patch_failed(self, e: Exception) -> None:
        self.play.setEnabled(True)
        self.ctx.log(f"Patching failed: {e}")
        self._set_busy(False, f"Patching failed: {e}. Try the official launcher.")

    def _show_install(self) -> None:
        """'Install the game…' only while there's no usable game folder."""
        s = self.ctx.settings
        self.install_btn.setVisible(not (s.game_dir and check_game_dir(s.game_path)[0]))

    def run_official_launcher(self) -> None:
        s = self.ctx.settings
        game = s.game_path
        exe = game / "LotroLauncher.exe" if game else None
        if not exe or not exe.exists():
            QMessageBox.warning(self, "Official launcher", "LotroLauncher.exe is not in the game folder.")
            return
        try:
            argv, env = runner.windows_command(s, exe, [])
            proc = runner.ManagedProcess("launcher", argv, env, game, self)
        except (runner.RunnerError, OSError) as e:
            QMessageBox.warning(self, "Official launcher", str(e))
            return
        proc.output.connect(lambda l: self.ctx.log(f"official launcher: {l}"))
        self.ctx.log("Started the official launcher")
