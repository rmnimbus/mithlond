"""Finding (and stopping) the user's LOTRO-related processes by scanning /proc.

Under Wine/Proton a Windows program shows up with its Windows path as argv[0]
(e.g. `S:\\other\\lotro\\x64\\lotroclient64.exe -a …`), and the wrappers around it (umu-run, proton,
steam.exe) carry the .exe path in their arguments, so matching on argument basenames finds the whole chain.
Only processes owned by the current user are ever looked at.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings

GAME_EXES = {"lotroclient.exe", "lotroclient64.exe", "lotroclient_awesomium.exe"}
LAUNCHER_EXES = {"lotrolauncher.exe", "lotrobrowserhelper.exe"}
COMPANION_EXES = {"lotro companion.exe"}
# Wine's own background processes: not "programs" for our purposes.
WINE_SYSTEM = {"services.exe", "winedevice.exe", "plugplay.exe", "svchost.exe", "rpcss.exe", "explorer.exe",
               "tabtip.exe", "conhost.exe", "start.exe", "wineboot.exe", "steam.exe", "winemenubuilder.exe",
               "rundll32.exe", "mscorsvw.exe", "cmd.exe", "xalia.exe"}


@dataclass
class Proc:
    pid: int
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)

    @property
    def exe_name(self) -> str:
        return _base(self.argv[0]) if self.argv else ""

    @property
    def basenames(self) -> set[str]:
        return {_base(a) for a in self.argv}

    def describe(self) -> str:
        return f"{self.exe_name or '?'} (pid {self.pid})"


def _base(arg: str) -> str:
    return arg.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lower()


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def scan(with_env: bool = False) -> list[Proc]:
    uid, me = os.getuid(), os.getpid()
    out = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit() or int(d.name) == me:
            continue
        try:
            if d.stat().st_uid != uid:
                continue
        except OSError:
            continue
        raw = _read(d / "cmdline")
        if not raw:
            continue  # kernel thread or gone
        argv = [a.decode("utf-8", "replace") for a in raw.rstrip(b"\0").split(b"\0")]
        env = {}
        if with_env:
            for kv in _read(d / "environ").split(b"\0"):
                k, _, v = kv.decode("utf-8", "replace").partition("=")
                if k:
                    env[k] = v
        out.append(Proc(int(d.name), argv, env))
    return out


def _same(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


def windows_programs_in_prefix(prefix: Path) -> list[Proc]:
    """Windows programs (not Wine's own services) currently running in `prefix`."""
    return [p for p in scan(with_env=True)
            if p.exe_name.endswith(".exe") and p.exe_name not in WINE_SYSTEM
            and p.env.get("WINEPREFIX") and _same(p.env["WINEPREFIX"], prefix)]


def game_clients() -> list[Proc]:
    """Running LOTRO game clients (the Windows process itself, not wrappers)."""
    return [p for p in scan() if p.exe_name in GAME_EXES]


def related(s: Settings) -> list[Proc]:
    """Everything this launcher could have started: game clients, the official launcher and patcher,
    LotRO Companion (Windows or Java), Maestro, BruTE, plus the Wine/Proton wrappers around them."""
    names = GAME_EXES | LAUNCHER_EXES | COMPANION_EXES
    paths = [x for x in (s.maestro_path, s.brute_path, s.wan_path) if x]
    paths += [str(s.downloads_path() / d) for d in ("Maestro", "WANSongBookFiller")]
    names |= {"wansongbookfiller.exe", "maestro.exe", "abcplayer.exe", "maestro.jar", "abcplayer.jar"}
    comp = str(s.companion_path())
    found = []
    for p in scan():
        cmd = " ".join(p.argv)
        if (p.basenames & names
                or "delta.kickstarter.Kickstarter" in cmd or "delta.games.lotro.Main" in cmd or (comp and comp in cmd and "java" in p.exe_name)
                or "patchclient.dll" in cmd.lower()
                or any(x in cmd for x in paths)):
            found.append(p)
    return found


def terminate(procs: list[Proc], grace: float = 4.0) -> list[int]:
    """SIGTERM, then SIGKILL whatever is left after `grace` seconds. Returns pids that were signalled."""
    pids = [p.pid for p in procs if p.pid != os.getpid()]
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    end = time.time() + grace
    while time.time() < end and any(_alive(pid) for pid in pids):
        time.sleep(0.2)
    for pid in pids:
        if _alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    return pids


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie counts as gone.
    return b"State:\tZ" not in _read(Path(f"/proc/{pid}/status"))
