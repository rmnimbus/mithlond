"""'Export logs': one zip with what's needed to diagnose a problem, with personal data removed.

Contents: a system and setup summary, Mithlond's log and settings, the game client's own log, the game's settings
(without account/world history), installed plugins, the visual-effects configs, and LotRO Companion's and
Proton's logs if there are any. Every text goes through `redact()`: the user's name and home folder, LOTRO
account names, session tickets and other long tokens, and e-mail addresses are removed.
"""

from __future__ import annotations

import datetime as dt
import getpass
import json
import os
import platform
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import __version__, config, effects, gameprefs, logfile, procs
from .config import CONFIG_DIR, HOME, Settings

TAIL = 512 * 1024  # bytes kept from the end of big logs


# ---- redaction --------------------------------------------------------------------------------------------
class Redactor:
    def __init__(self, s: Settings):
        self.words = sorted({a.username for a in s.accounts if a.username} | {s.last_account} - {""}, key=len,
                            reverse=True)
        self.user = getpass.getuser()
        self.home = str(HOME)

    def __call__(self, text: str) -> str:
        t = text.replace(self.home, "~")
        t = re.sub(r"(?im)^(\s*Command:).*$", r"\1 <removed: contains the session ticket>", t)
        t = re.sub(r"(--glsticketdirect|--glsticket|-z)(\s+|=)\S+", r"\1\2<ticket>", t)
        t = re.sub(r"(?<!\S)(-a)(\s+)\S+", r"\1\2<subscription>", t)
        t = re.sub(r"(?i)(ticket[\"']?\s*[:=]\s*[\"']?)[^\s\"'<]+", r"\1<ticket>", t)
        t = re.sub(r"[A-Za-z0-9+/_-]{40,}={0,2}", "<token>", t)
        t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", t)
        for w in self.words:
            t = re.sub(rf"(?i)\b{re.escape(w)}\b", "<account>", t)
        if self.user and len(self.user) > 2:
            t = re.sub(rf"\b{re.escape(self.user)}\b", "<user>", t)
        return t


# ---- helpers ------------------------------------------------------------------------------------------------
def _run(argv: list[str], timeout: float = 10) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=_host_env())
        return re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr).strip()  # drop terminal colours
    except (OSError, subprocess.SubprocessError) as e:
        return f"({type(e).__name__})"


def _host_env() -> dict[str, str]:
    from .hostenv import host_env
    return host_env()


def _tail(path: Path, limit: int = TAIL) -> str:
    try:
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            f.seek(max(0, size - limit))
            data = f.read()
        text = data.decode("utf-8", errors="replace")
        return (f"[… first {size - limit} bytes left out …]\n" if size > limit else "") + text
    except OSError as e:
        return f"(can't read: {e})"


def _newest(paths) -> Path | None:
    paths = [p for p in paths if p.is_file()]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0] if text.strip() else "(no output)"


# ---- the summary ----------------------------------------------------------------------------------------------
def summary(s: Settings) -> str:
    out: list[str] = []
    add = out.append

    def section(title: str) -> None:
        add(f"\n== {title}")

    add(f"Mithlond {__version__} diagnostics, {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    section("Mithlond")
    appimage = os.environ.get("APPIMAGE")
    add(f"running from: {'AppImage ' + appimage if appimage else 'source'}")
    add(f"python {platform.python_version()}")
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        add(f"PySide6 {PySide6.__version__}, Qt {qVersion()}")
    except ImportError:
        pass

    section("System")
    osr = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            k, _, v = line.partition("=")
            osr[k] = v.strip('"')
    except OSError:
        pass
    add(f"OS: {osr.get('PRETTY_NAME', '?')} | kernel {platform.release()} | glibc {platform.libc_ver()[1]}")
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines() if l.startswith("model name"))
        mem = next(int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemTotal")) // 1024
        add(f"CPU: {cpu} ({os.cpu_count()} threads) | RAM: {mem} MB")
    except (OSError, StopIteration, ValueError):
        pass
    env = _host_env()
    add("session: " + ", ".join(f"{k}={env.get(k, '')}" for k in ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP",
                                                                   "WAYLAND_DISPLAY", "DISPLAY")))
    if shutil.which("lspci"):
        gpus = [l for l in _run(["lspci"]).splitlines() if re.search(r"VGA|3D|Display", l)]
        add("GPU: " + (" | ".join(gpus) or "(none listed)"))
    if shutil.which("nvidia-smi"):
        add("NVIDIA: " + _first_line(_run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])))
    if shutil.which("vulkaninfo"):
        vk = [l.strip() for l in _run(["vulkaninfo", "--summary"], 20).splitlines()
              if re.search(r"deviceName|driverName|driverInfo|apiVersion|deviceType", l)]
        add("Vulkan: " + " | ".join(dict.fromkeys(vk)) if vk else "Vulkan: vulkaninfo gave no devices")
    add("SELinux: " + (config.selinux_problem() or "no problem found"))

    section("Programs")
    for name, argv in (("wine", ["wine", "--version"]), ("gamescope", ["gamescope", "--version"]),
                       ("mangohud", None), ("gamemoderun", None), ("java", ["java", "-version"]),
                       ("secret-tool", None), ("bsdtar", None), ("7z", None)):
        path = shutil.which(name)
        add(f"{name}: " + ((_first_line(_run(argv)) if argv else path) if path else "not installed"))
    add("vkBasalt layer: " + ("installed" if effects.vkbasalt_installed() else "not installed"))
    umu = config.umu_command()
    add("umu-run: " + (_first_line(_run([*umu, "--version"], 30)) + f" ({'bundled' if config.bundled_umu_run() else umu[0]})"
                       if umu else "not found"))

    section("Game")
    ok, msg = config.check_game_dir(s.game_path) if s.game_dir else (False, "not set")
    add(f"game folder: {s.game_dir or '(not set)'} -> {msg}")
    add(f"client: {s.client} | language: {s.language} | high-res: {s.high_res}")
    add(f"documents folder: {s.documents_dir or '(not set)'} (exists: {bool(s.docs_path and s.docs_path.is_dir())})"
        f" | start with --prefs: {s.use_prefs}")
    add(f"runner: {s.runner} | wine binary: {s.wine_binary} | proton: {s.proton_path or '(umu default)'}")
    if s.runner == "umu" and s.proton_path:
        add("proton check: " + (config.proton_problem(Path(s.proton_path).expanduser()) or "ok"))
    pfx = s.prefix_path()
    add(f"prefix: {pfx} (exists: {pfx.is_dir()}, has system.reg: {(pfx / 'system.reg').exists()})")
    for f in ("version", "config_info"):
        p = pfx / f
        if p.is_file():
            add(f"prefix {f}: {_first_line(p.read_text(errors='replace'))}")
    add("prefix check: " + ((config.prefix_problem(pfx) if s.runner == "umu" else config.wine_prefix_problem(pfx))
                            or "ok"))
    add(f"environment variables set in Mithlond: {sorted(s.extra_env)}")
    add("game options: " + ", ".join(k for k in ("opt_gamescope", "opt_mangohud", "opt_gamemode", "opt_dxvk_hud",
                                                   "opt_proton_wayland", "opt_proton_log") if getattr(s, k)) or "none")
    add(f"play options: fps limit {s.fps_limit or 'off'}, voice off {s.voice_off}, skip intro {s.skip_intro}")
    add(f"gamescope command: gamescope {' '.join(effects.gamescope_args(s))} --" if s.opt_gamescope else
        "gamescope: off")
    add(f"vkBasalt: {'on: ' + ':'.join(effects.vkbasalt_effects(s)) if s.vkb_enabled else 'off'}")
    add(f"DXVK options: {effects.dxvk_options(s) or 'none'}")
    add(f"LotRO Companion: folder {s.companion_path()} (exists: {s.companion_path().is_dir()}), mode "
        f"{s.companion_mode}, with game {s.companion_with_game}")

    section("Running now")
    try:
        rel = procs.related(s)
        add("\n".join(f"{p.pid} {p.describe()}" for p in rel) or "nothing LOTRO-related is running")
    except Exception as e:  # noqa: BLE001 - diagnostics must not fail
        add(f"(process scan failed: {e})")
    return "\n".join(out) + "\n"


# ---- the zip -------------------------------------------------------------------------------------------------
def default_path() -> Path:
    downloads = HOME / "Downloads"
    try:
        dirs = (Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "user-dirs.dirs").read_text()
        m = re.search(r'XDG_DOWNLOAD_DIR="([^"]+)"', dirs)
        if m:
            downloads = Path(m.group(1).replace("$HOME", str(HOME)))
    except OSError:
        pass
    base = downloads if downloads.is_dir() else HOME
    return base / f"mithlond-logs-{dt.datetime.now():%Y%m%d-%H%M%S}.zip"


README = """Mithlond diagnostic logs
========================

Made with Mithlond's "Export logs" button, to help find what went wrong. Send this zip to whoever helps you.

What's inside:
  summary.txt              Mithlond version, system, graphics, installed programs, game/runner/prefix setup
  mithlond.log(.1)         Mithlond's log, including errors with their full details
  settings.json            Mithlond's settings (without account names)
  game/lotroclient.log     the game client's own log from the last start
  game/UserPreferences.txt the game's settings (without account and world history)
  plugins.txt              installed plugins and their versions
  game/Script.log          plugin (Lua) errors the game logged
  effects/                 the vkBasalt and DXVK settings Mithlond writes (if used)
  companion.log            LotRO Companion's newest log (if any)
  proton.log               Proton's debug log (if "Proton debug log" was on)

Removed from everything: your user name and home folder (shown as ~), your LOTRO account names, login and
session tickets, other long security tokens, and e-mail addresses. Passwords are never stored by Mithlond, so
they can't be in here. You can open the files and check before sending.
"""


def export(s: Settings, dest: Path) -> Path:
    red = Redactor(s)
    files: dict[str, str] = {"README.txt": README, "summary.txt": red(summary(s))}
    for p in (logfile.LOG.with_name(logfile.LOG.name + ".1"), logfile.LOG):
        if p.is_file():
            files[p.name] = red(_tail(p, 2 * TAIL))
    try:
        cfg = json.loads((CONFIG_DIR / "config.json").read_text())
        cfg["accounts"] = f"<{len(cfg.get('accounts') or [])} account(s)>"
        cfg["last_account"] = "<account>" if cfg.get("last_account") else ""
        files["settings.json"] = red(json.dumps(cfg, indent=2))
    except (OSError, ValueError) as e:
        files["settings.json"] = f"(can't read: {e})"
    users = s.prefix_path() / "drive_c" / "users"
    client_log = _newest(list(users.glob("*/AppData/Local/The Lord of the Rings Online/lotroclient*.log"))) \
        if users.is_dir() else None
    if client_log:
        files["game/lotroclient.log"] = red(f"# {client_log}\n" + _tail(client_log))
    pf = gameprefs.prefs_file(s)
    if pf and pf.is_file():
        values = gameprefs.read(pf)
        files["game/UserPreferences.txt"] = red(f"# {pf}\n" + "".join(
            f"{k} = {v}\n" for k, v in values.items() if not gameprefs.hidden(*k.split(".", 1))))
    files["plugins.txt"] = _plugins(s)
    script_log = s.docs_path / "Script.log" if s.docs_path else None
    if script_log and script_log.is_file():
        files["game/Script.log"] = red(f"# {script_log}\n" + _tail(script_log))
    for p in (effects.VKBASALT_CONF, effects.DXVK_CONF):
        if p.is_file():
            files[f"effects/{p.name}"] = red(p.read_text(errors="replace"))
    comp = _newest([*(HOME / ".lotrocompanion/data/logs").glob("*.log"),
                    *(users.glob("*/.lotrocompanion/data/logs/*.log") if users.is_dir() else [])])
    if comp:
        files["companion.log"] = red(f"# {comp}\n" + _tail(comp, TAIL // 2))
    proton = _newest(list(HOME.glob("steam-*.log")))
    if proton:
        files["proton.log"] = red(f"# {proton}\n" + _tail(proton, TAIL // 2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    logfile.write(f"Exported logs to {dest}")
    return dest


def _plugins(s: Settings) -> str:
    lines = []
    try:
        from .addons import _load_manifest
        for key, info in sorted(_load_manifest().items()):
            if isinstance(info, dict):
                lines.append(f"{info.get('name', key)} {info.get('version', '')} [{info.get('kind', '')}"
                             + (f", lotrointerface #{info['id']}" if info.get("id") else "") + "]")
    except Exception as e:  # noqa: BLE001
        lines.append(f"(manifest unreadable: {e})")
    plugins = s.subdir("Plugins") if s.docs_path else None
    if plugins and plugins.is_dir():
        lines.append("\nFolders in Plugins/: " + ", ".join(sorted(p.name for p in plugins.iterdir() if p.is_dir())))
    return "\n".join(lines) + "\n"
