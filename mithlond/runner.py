"""Running Windows programs (game, patcher, Companion) through Wine or umu-run/Proton,
and native programs (Companion on system Java, Maestro/BruTE jars)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .config import (
    LOTRO_STEAM_APPID, Settings, prefix_problem, proton_problem, umu_command, wine_prefix_problem,
)
from .gameprefs import set_preference
from .hostenv import host_env


class RunnerError(Exception):
    pass


def dos_path(path: str | Path) -> str:
    """'/home/me/Games/x/game.exe' -> 'Z:\\home\\me\\Games\\x\\game.exe' (Wine/Proton map Z: to /). Windows paths pass through."""
    p = str(path)
    return "Z:" + p.replace("/", "\\") if p.startswith("/") else p


def proton_uses_start_unix(s: Settings) -> bool:
    """True for Proton builds (e.g. Proton-EM) that start Linux paths with `start.exe /unix`. Those can't
    run LotRO Companion's bundled javaw.exe directly (c0000135), so Companion goes through its own launcher."""
    if s.runner != "umu" or not s.proton_path:
        return False
    try:
        return "start.exe\", \"/unix" in (Path(s.proton_path).expanduser() / "proton").read_text(errors="replace")
    except OSError:
        return False


def prefs_args(s: Settings) -> list[str]:
    """`--prefs <documents>\\UserPreferences.ini`: the client then uses that folder as its documents folder
    (settings, Plugins, Music, PluginData, screenshots) instead of the one inside the Wine prefix."""
    docs = s.docs_path
    if not s.use_prefs or not docs:
        return []
    try:
        docs.mkdir(parents=True, exist_ok=True)
        seed_preferences(s, docs)
    except OSError as e:
        raise RunnerError(f"Can't prepare the documents folder {docs}: {e}") from e
    return ["--prefs", dos_path(docs / "UserPreferences.ini")]


MINIMAL_PREFS = "[Render]\nD3DVersionPromptedForAtStartup=11\nGraphicsCore=D3D11\n"


def seed_preferences(s: Settings, docs: Path) -> str | None:
    """A folder without UserPreferences.ini makes the client stop at a 'which DirectX?' prompt. Copy the newest
    settings (and key bindings) from the prefix's own documents folders, or write minimal DirectX 11 defaults
    like OneLauncher does. Returns what was done, or None if the folder already had settings."""
    prefs = docs / "UserPreferences.ini"
    if prefs.exists():
        return None
    from .config import DOCS_FOLDER_NAME
    users = s.prefix_path() / "drive_c" / "users"
    found = sorted((p for p in users.glob(f"*/Documents/{DOCS_FOLDER_NAME}/UserPreferences.ini")
                    if p.resolve() != prefs.resolve()), key=lambda p: p.stat().st_mtime, reverse=True) \
        if users.is_dir() else []
    if found:
        shutil.copy2(found[0], prefs)
        keymap = found[0].parent / "lotro.keymap"
        if keymap.exists() and not (docs / "lotro.keymap").exists():
            shutil.copy2(keymap, docs / "lotro.keymap")
        return f"copied game settings from {found[0].parent}"
    prefs.write_text(MINIMAL_PREFS)
    return "wrote default game settings (DirectX 11)"


SKIPPED = ".mithlond-skipped"


def apply_intro_skip(s: Settings) -> list[str]:
    """With skip_intro: set the start-up logo videos (raw/<language>/logo/*.bik, played at every start) aside and
    mark the intro cinematic as seen in the documents folder's UserPreferences.ini. Without it: put the videos
    back. Problems are reported, never fatal. Returns what was done, for the log."""
    notes = []
    game = s.game_path
    raw = game / "raw" if game else None
    for video in sorted(raw.glob("*/logo/*.bik*")) if raw and raw.is_dir() else []:
        try:
            if s.skip_intro and video.suffix == ".bik":
                aside = video.with_name(video.name + SKIPPED)
                aside.unlink(missing_ok=True)  # a patch brought the video back: keep the new one aside
                video.rename(aside)
                notes.append(f"set aside {video.relative_to(game)}")
            elif not s.skip_intro and video.name.endswith(".bik" + SKIPPED):
                back = video.with_name(video.name[: -len(SKIPPED)])
                if not back.exists():
                    video.rename(back)
                    notes.append(f"restored {back.relative_to(game)}")
        except OSError as e:
            notes.append(f"couldn't move {video.name}: {e.strerror}")
    prefs = s.docs_path / "UserPreferences.ini" if s.docs_path else None
    if s.skip_intro and prefs and prefs.is_file():
        try:
            if set_preference(prefs, "Misc", "PlayedIntroMovie", "True"):
                notes.append("marked the intro cinematic as seen")
        except OSError as e:
            notes.append(f"couldn't update {prefs.name}: {e.strerror}")
    return notes


def windows_command(s: Settings, exe: str | Path, args: list[str],
                    join: bool = False, dos: bool = True) -> tuple[list[str], dict[str, str]]:
    """argv and environment to run a Windows executable with the configured runner.

    `join`: start alongside programs already running in the prefix. Proton's default verb
    (waitforexitandrun) otherwise waits until everything else in the prefix has exited."""
    env = host_env()
    env.setdefault("WINEDEBUG", "-all")
    env.setdefault("DXVK_LOG_LEVEL", "error")
    prefix = s.prefix_path()
    if s.runner == "umu":
        umu = umu_command()
        if not umu:  # only when running from source: the AppImage brings its own
            raise RunnerError("umu-run was not found. Install umu-launcher, or use the Mithlond AppImage, "
                              "which includes it.")
        if problem := prefix_problem(prefix):
            raise RunnerError(f"Prefix problem: {problem}. Change it in Settings.")
        env["WINEPREFIX"] = str(prefix)
        env.setdefault("GAMEID", f"umu-{LOTRO_STEAM_APPID}")
        env.setdefault("STORE", "none")
        if s.proton_path:
            if problem := proton_problem(Path(s.proton_path).expanduser()):
                raise RunnerError(f"{problem}. Pick another Proton in Settings → Runners and Prefix.")
            env["PROTONPATH"] = s.proton_path
        if join:
            env["PROTON_VERB"] = "run"
        # Hand Proton a Windows path: some builds (Proton-EM) start Linux paths with `start.exe /unix`, which
        # runs the program from its own folder instead of ours. lotroclient64.exe then misses corestrings.dll,
        # which lives in the game folder, not in x64/ ("corestrings.dll not found").
        argv = [*umu, dos_path(exe) if dos else str(exe), *args]
    else:
        wine = shutil.which(s.wine_binary or "wine") or s.wine_binary
        if not wine or not Path(wine).exists():
            raise RunnerError(f"Wine binary '{s.wine_binary}' was not found.")
        if problem := wine_prefix_problem(prefix):
            raise RunnerError(f"Prefix problem: {problem}. Change it in Settings.")
        env["WINEPREFIX"] = str(prefix)
        argv = [wine, str(exe), *args]
    env.update({k: v for k, v in s.extra_env.items() if k})
    return argv, env


# Common options for the game client: (setting, label, tooltip, required program or None)
GAME_OPTIONS = [
    ("opt_gamescope", "Run in gamescope", "Valve's micro-compositor: fixes fullscreen/scaling issues, enables FSR.\n"
     "Arguments are set next to this box (default -f = fullscreen).", "gamescope"),
    ("opt_mangohud", "MangoHud overlay", "FPS, frame time, CPU/GPU load overlay (MANGOHUD=1).", "mangohud"),
    ("opt_gamemode", "Feral GameMode", "Asks the system for performance mode while playing (gamemoderun).\n"
     "Needs your user in the 'gamemode' group to have any effect.", "gamemoderun"),
    ("opt_dxvk_hud", "DXVK FPS counter", "Small FPS counter from DXVK (DXVK_HUD=fps).", None),
    ("opt_proton_wayland", "Native Wayland (Proton)", "PROTON_ENABLE_WAYLAND=1 asks Proton for its Wayland driver.\n"
     "Newer Protons only, and Proton may still keep a game on XWayland (LOTRO did with GE-Proton 11-6).", None),
    ("opt_proton_log", "Proton debug log", "PROTON_LOG=1: writes steam-<id>.log to your home folder for troubleshooting.",
     None),
]


def gamemode_problem() -> str | None:
    """GameMode needs polkit permission to change CPU settings; its rule only allows the 'gamemode' group.
    Distributions without systemd-sysusers (Artix, …) don't create that group, and then GameMode silently
    does nothing."""
    import grp
    import pwd
    try:
        g = grp.getgrnam("gamemode")
    except KeyError:
        return ("the 'gamemode' group doesn't exist, so GameMode can't change CPU settings. Fix: "
                "sudo groupadd -r gamemode && sudo usermod -aG gamemode $USER")
    user = pwd.getpwuid(os.getuid())
    if user.pw_name not in g.gr_mem and user.pw_gid != g.gr_gid:
        return ("you're not in the 'gamemode' group, so GameMode can't change CPU settings. Fix: "
                "sudo usermod -aG gamemode $USER")
    return None


def gamemode_register(pid: int) -> bool:
    """Register a running process with GameMode (used when gamescope keeps gamemoderun's preload from
    reaching the game)."""
    exe = shutil.which("gamemoded")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, f"-r{pid}"], env=host_env(), capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def backup_preferences(s: Settings) -> Path | None:
    """Copy UserPreferences.ini to UserPreferences.ini.before-safe-mode-<time>. --safe permanently rewrites the
    graphics settings (tested: 1024x768 windowed, DirectX 9, medium detail), so this is the way back."""
    import time as _time
    prefs = s.docs_path / "UserPreferences.ini" if s.docs_path else None
    if not prefs or not prefs.is_file():
        return None
    backup = prefs.with_name(f"UserPreferences.ini.before-safe-mode-{_time.strftime('%Y-%m-%d-%H%M%S')}")
    shutil.copy2(prefs, backup)
    return backup


def client_option_args(s: Settings, safe: bool = False) -> list[str]:
    """Game client options from the Play tab: --voiceoff, and --safe (safe display settings) for one start."""
    return (["--voiceoff"] if s.voice_off else []) + (["--safe"] if safe else [])


effect_notes: list[str] = []  # what apply_game_options set up from the Visual effects tab (for the log)


def apply_game_options(s: Settings, argv: list[str], env: dict[str, str],
                       screen: tuple[int, int] | None = None) -> tuple[list[str], dict[str, str]]:
    """Add the ticked game options and visual effects (env variables, config files, wrapper programs) to a game
    client command. `screen` is the monitor size, for gamescope's render scale."""
    from . import effects
    for key, label, _tip, needs in GAME_OPTIONS:
        if getattr(s, key) and needs and not shutil.which(needs):
            where = "Visual effects" if key == "opt_gamescope" else "Settings"
            raise RunnerError(f"'{label}' is ticked in {where}, but {needs} is not installed.")
    if s.opt_dxvk_hud:
        env.setdefault("DXVK_HUD", "fps")
    if s.opt_proton_wayland:
        env.setdefault("PROTON_ENABLE_WAYLAND", "1")
    if s.opt_proton_log:
        env.setdefault("PROTON_LOG", "1")
    if s.opt_mangohud:
        env["MANGOHUD"] = "1"
    if s.fps_limit > 0:
        env.setdefault("DXVK_FRAME_RATE", str(s.fps_limit))
    global effect_notes
    effect_notes = effects.apply_env(s, env)  # vkBasalt, dxvk.conf
    # gamescope goes outermost: it drops LD_PRELOAD for its children, so gamemoderun has to sit inside it
    # (gamescope -- gamemoderun <game>) for GameMode's library to reach the game.
    wrap: list[str] = []
    if s.opt_gamescope:
        wrap += effects.gamescope_command(s, screen)
    if s.opt_gamemode:
        wrap.append(shutil.which("gamemoderun") or "gamemoderun")
    return wrap + argv, env


def companion_command(s: Settings) -> tuple[list[str], dict[str, str], Path]:
    """How to start LotRO Companion: (argv, env, cwd)."""
    from . import companion
    base = s.companion_path()
    if not base.exists():
        raise RunnerError(f"LotRO Companion is not installed in {base}. Use 'Download Companion' on the Companion tab.")
    app = companion.app_dir(base)
    native = s.companion_mode == "native"
    # Companion is started with a Linux path (dos=False): that route handles its folder name with a space and
    # the bundled Java on every Proton tested; Windows paths fail for it on Proton-EM.
    if s.companion_skip_updater and not (not native and proton_uses_start_unix(s)):
        try:
            java, args, cwd = companion.direct_launch(base, windows=not native)
        except companion.CompanionError:
            pass  # unusual layout: fall back to the normal start below
        else:
            if native:
                return [java, *args], host_env(), cwd
            argv, env = windows_command(s, java, args, join=True, dos=False)
            return argv, env, cwd
    if native:
        java = shutil.which("java")
        if not java:
            raise RunnerError("Java is not installed; install a JRE or use the Wine/Proton mode.")
        kick = app / "kickstarter"
        if not kick.is_dir():
            raise RunnerError(f"{kick} not found; is this a LotRO Companion folder?")
        cp = ":".join(str(j) for j in sorted(kick.glob("*.jar")))
        argv = [java, "-Xms256M", "-Xmx1024M", "-Duser.language=en",
                "-Dlogback.configurationFile=runtime_logback.xml",
                "-classpath", cp, "delta.kickstarter.Kickstarter"]
        return argv, host_env(), app
    exe = next((p for p in (base / "LotRO Companion.exe", base.parent / "LotRO Companion.exe") if p.exists()), None)
    if exe is None:
        raise RunnerError(f"'LotRO Companion.exe' not found in {base}")
    argv, env = windows_command(s, exe, [], join=True, dos=False)
    return argv, env, exe.parent


def tool_command(s: Settings, path: str) -> tuple[list[str], dict[str, str], Path]:
    """Start an external music tool (Maestro, BruTE): .jar via Java, .exe via the runner, else directly."""
    p = Path(path).expanduser()
    if not p.exists():
        raise RunnerError(f"{p} does not exist")
    if p.suffix.lower() == ".jar":
        java = shutil.which("java")
        if not java:
            raise RunnerError("Java is not installed.")
        opts = []
        patch = p.parent / "java.midi.patch.jar"
        if patch.exists():  # Maestro's own Linux start options
            opts = [f"--patch-module=java.desktop={patch}", "--enable-native-access=ALL-UNNAMED",
                    "--add-exports=java.desktop/com.sun.media.sound=ALL-UNNAMED"]
        return [java, *opts, "-jar", str(p)], host_env(), p.parent.parent if patch.exists() else p.parent
    if p.suffix.lower() in (".exe", ".bat"):
        argv, env = windows_command(s, p, [])
        return argv, env, p.parent
    return [str(p)], host_env(), p.parent


class ManagedProcess(QObject):
    """A child process in its own session, so the whole tree can be stopped together.
    Output lines are forwarded through `output`, exit through `finished`."""

    output = Signal(str)
    finished = Signal(int)

    def __init__(self, name: str, argv: list[str], env: dict[str, str], cwd: Path, parent=None):
        super().__init__(parent)
        self.name = name
        self.proc = subprocess.Popen(
            argv, env=env, cwd=str(cwd), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
        )
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(500)

    def _read(self) -> None:
        assert self.proc.stdout
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self.output.emit(line)

    def _poll(self) -> None:
        code = self.proc.poll()
        if code is not None:
            self._timer.stop()
            self.finished.emit(code)

    def running(self) -> bool:
        return self.proc.poll() is None

    def stop(self, timeout: float = 5.0) -> None:
        if not self.running():
            return
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        def _kill():
            if self.running():
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        QTimer.singleShot(int(timeout * 1000), _kill)


def patch_phases(patch_server: str, language: str, product_code: str, high_res: bool) -> list[list[str]]:
    """Argument lists for patchclient.dll's Patch entry point. File patching runs twice because
    the first pass can update the patcher itself."""
    base = [patch_server, "--language", language, "--productcode", product_code]
    if high_res:
        base.append("--highres")
    return [base + ["--filesonly"], base + ["--filesonly"], base + ["--dataonly"]]


def patch_command(s: Settings, args: list[str]) -> tuple[list[str], dict[str, str]]:
    """patchclient.dll is 32-bit, so it is loaded with the 32-bit rundll32 from SysWOW64."""
    return windows_command(s, r"C:\windows\syswow64\rundll32.exe", ["patchclient.dll,Patch", *args])
