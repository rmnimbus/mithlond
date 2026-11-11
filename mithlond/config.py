"""Settings storage and auto-detection of the LOTRO install, documents folder and runner."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_ID = "mithlond"
APP_NAME = "Mithlond"

HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / APP_ID
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / APP_ID
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local" / "share") / APP_ID
CONFIG_FILE = CONFIG_DIR / "config.json"

DOCS_FOLDER_NAME = "The Lord of the Rings Online"
LOTRO_STEAM_APPID = "212500"


@dataclass
class Account:
    username: str
    world: str = ""
    subscription: str = ""  # last used subscription name (accounts can have several)


@dataclass
class Settings:
    # Locations
    game_dir: str = ""
    documents_dir: str = ""
    plugins_dir: str = ""  # empty: <documents_dir>/Plugins
    downloads_dir: str = ""  # empty: <documents_dir>/Downloads (Maestro, WAN Songbook Filler, Companion…)

    # How Windows programs are run
    runner: str = "wine"  # "wine" (wine_binary) or "umu" (Proton via umu-run, proton_path)
    wine_binary: str = "wine"
    wine_prefix: str = ""  # empty: wine's default (~/.wine)
    umu_run: str = ""
    proton_path: str = ""
    extra_env: dict[str, str] = field(default_factory=dict)
    # Common game options (game client only)
    opt_gamescope: bool = False
    gamescope_args: str = "-f"
    opt_mangohud: bool = False
    opt_gamemode: bool = False
    opt_dxvk_hud: bool = False
    opt_proton_wayland: bool = False
    opt_proton_log: bool = False

    # Game
    client: str = "win64"  # "win64" or "win32"
    language: str = "English"
    high_res: bool = True
    on_game_start: str = "stay"  # "stay", "minimize" or "close"
    accounts: list[Account] = field(default_factory=list)
    last_account: str = ""
    remember_password: bool = True

    # LotRO Companion
    companion_dir: str = ""  # empty: <downloads>/LotRO Companion
    companion_mode: str = "runner"  # "runner" (Wine/Proton, same prefix as game) or "native" (system Java)
    companion_with_game: bool = False
    companion_delay: int = 10
    companion_close_with_game: bool = True
    companion_skip_updater: bool = True  # start its main class directly; its own updater can hang

    # Music
    songbook_auto: bool = True
    maestro_path: str = ""
    brute_path: str = ""
    wan_path: str = ""

    # ---- persistence -------------------------------------------------------
    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(CONFIG_FILE.read_text())
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in raw.items() if k in known}
        data["accounts"] = [
            Account(**{k: v for k, v in a.items() if k in Account.__dataclass_fields__})
            for a in raw.get("accounts", [])
            if isinstance(a, dict) and a.get("username")
        ]
        return cls(**data)

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        tmp.replace(CONFIG_FILE)

    # ---- helpers -----------------------------------------------------------
    def account(self, username: str) -> Account | None:
        for a in self.accounts:
            if a.username.lower() == username.lower():
                return a
        return None

    @property
    def game_path(self) -> Path | None:
        return Path(self.game_dir).expanduser() if self.game_dir else None

    @property
    def docs_path(self) -> Path | None:
        return Path(self.documents_dir).expanduser() if self.documents_dir else None

    def subdir(self, name: str) -> Path | None:
        """A folder inside the documents folder (Plugins, Music, PluginData, ui/skins).
        Plugins can be pointed elsewhere with `plugins_dir`."""
        if name.lower() == "plugins" and self.plugins_dir:
            return Path(self.plugins_dir).expanduser()
        docs = self.docs_path
        if docs is None:
            return None
        return find_case_insensitive(docs, name) or docs / name

    def downloads_path(self) -> Path:
        if self.downloads_dir:
            return Path(self.downloads_dir).expanduser()
        docs = self.docs_path
        return docs / "Downloads" if docs else DATA_DIR / "downloads"

    def companion_path(self) -> Path:
        return Path(self.companion_dir).expanduser() if self.companion_dir else self.downloads_path() / "LotRO Companion"

    def default_plugins_path(self) -> Path | None:
        docs = self.docs_path
        return (find_case_insensitive(docs, "Plugins") or docs / "Plugins") if docs else None

    def prefix_path(self) -> Path:
        if self.wine_prefix:
            return Path(self.wine_prefix).expanduser()
        if self.runner == "umu":
            return HOME / "Games" / "umu" / "umu-default"
        return Path(os.environ.get("WINEPREFIX") or HOME / ".wine")


def prefix_problem(prefix: Path) -> str | None:
    """Why Wine can't use this prefix, or None if it can (an absent prefix is fine if it can be created)."""
    if prefix.exists():
        if not prefix.is_dir():
            return f"{prefix} is not a folder"
        if not os.access(prefix, os.W_OK):
            return f"{prefix} is not writable"
        return None
    parent = next((p for p in prefix.parents if p.exists()), None)
    if parent is None or not os.access(parent, os.W_OK):
        return f"{prefix} can't be created"
    return None


def is_proton_prefix(prefix: Path) -> bool:
    """Proton (and umu/Faugus) leave these markers in prefixes they create."""
    return any((prefix / m).exists() for m in ("config_info", "creation_sync_guard", "tracked_files"))


def wine_prefix_problem(prefix: Path) -> str | None:
    """prefix_problem, plus: plain Wine must not take over a Proton prefix."""
    if problem := prefix_problem(prefix):
        return problem
    if is_proton_prefix(prefix):
        return (f"{prefix} was created by Proton (Faugus/umu/Steam). Plain Wine would convert it to its own "
                "version and can break it for Proton. Pick a Proton runner for this prefix, or "
                "another prefix")
    return None


def find_case_insensitive(base: Path, rel: str) -> Path | None:
    """Resolve `rel` under `base`, matching each component case-insensitively."""
    cur = base
    for part in Path(rel).parts:
        nxt = cur / part
        if not nxt.exists():
            try:
                match = next((c for c in cur.iterdir() if c.name.lower() == part.lower()), None)
            except OSError:
                return None
            if match is None:
                return None
            nxt = match
        cur = nxt
    return cur


# ---- validation ------------------------------------------------------------

def check_game_dir(path: Path) -> tuple[bool, str]:
    """Return (ok, message) describing whether `path` looks like a LOTRO install."""
    if not path.is_dir():
        return False, "Folder does not exist"
    clients = [c for c in ("lotroclient.exe", "x64/lotroclient64.exe") if find_case_insensitive(path, c)]
    has_cfg = any(path.glob("*.launcherconfig"))
    if not clients:
        return False, "No lotroclient.exe found here"
    if not has_cfg:
        return False, "lotroclient.exe found, but no lotro.launcherconfig"
    return True, "Found " + ", ".join(clients)


def game_languages(game_dir: Path) -> list[str]:
    """Languages installed, from client_local_<Language>.dat files."""
    langs = sorted(p.name[len("client_local_"):-4] for p in game_dir.glob("client_local_*.dat"))
    return langs or ["English"]


# ---- auto-detection --------------------------------------------------------

def _faugus_games() -> list[dict]:
    for p in (HOME / ".local/share/faugus-launcher/games.json", HOME / ".config/faugus-launcher/games.json"):
        try:
            data = json.loads(p.read_text())
            if isinstance(data, list):
                return data
        except (OSError, ValueError):
            continue
    return []


def detect_game_dirs() -> list[Path]:
    cands: list[Path] = []
    for g in _faugus_games():
        exe = str(g.get("path", ""))
        if exe.lower().endswith(("lotrolauncher.exe", "lotroclient.exe")):
            cands.append(Path(exe).parent)
    prefixes = [HOME / ".wine"] + [Path(g["prefix"]) for g in _faugus_games() if g.get("prefix")]
    for pfx in prefixes:
        for sub in (
            "drive_c/Program Files (x86)/StandingStoneGames/The Lord of the Rings Online",
            "drive_c/Program Files/StandingStoneGames/The Lord of the Rings Online",
            "drive_c/Program Files (x86)/Turbine/The Lord of the Rings Online",
        ):
            cands.append(pfx / sub)
    for steam in (HOME / ".local/share/Steam", HOME / ".steam/steam"):
        cands.append(steam / "steamapps/common/Lord of the Rings Online")
    seen, out = set(), []
    for c in cands:
        try:
            key = c.resolve()
        except OSError:
            continue
        if key not in seen and check_game_dir(c)[0]:
            seen.add(key)
            out.append(c)
    return out


def detect_documents_dirs(settings: Settings | None = None) -> list[Path]:
    """Candidate documents folders, the most recently used (newest UserPreferences.ini) first."""
    cands = [HOME / "Documents" / DOCS_FOLDER_NAME]
    prefixes = {HOME / ".wine"}
    if settings is not None:
        prefixes.add(settings.prefix_path())
    prefixes.update(Path(g["prefix"]) for g in _faugus_games() if g.get("prefix"))
    for pfx in prefixes:
        users = pfx / "drive_c" / "users"
        if users.is_dir():
            for u in users.iterdir():
                cands.append(u / "Documents" / DOCS_FOLDER_NAME)
    found: dict[Path, tuple[float, Path]] = {}
    for c in cands:
        if not c.is_dir():
            continue
        real = c.resolve()
        prefs = c / "UserPreferences.ini"
        mtime = prefs.stat().st_mtime if prefs.exists() else c.stat().st_mtime - 1e9
        if real not in found or found[real][0] < mtime:
            found[real] = (mtime, c)
    return [p for _, p in sorted(found.values(), key=lambda t: t[0], reverse=True)]


def proton_versions() -> list[Path]:
    out = []
    for base in (HOME / ".local/share/Steam/compatibilitytools.d", HOME / ".steam/root/compatibilitytools.d",
                 HOME / ".local/share/Steam/steamapps/common"):
        if base.is_dir():
            out += sorted(p for p in base.iterdir() if (p / "proton").exists())
    seen, uniq = set(), []
    for p in out:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            uniq.append(p)
    return uniq


def detect_prefixes() -> list[Path]:
    """Existing Wine/Proton prefixes worth offering: Faugus prefixes, umu's, and ~/.wine if it's a real prefix."""
    cands = [Path(g["prefix"]) for g in _faugus_games() if g.get("prefix")]
    for base in (HOME / "Faugus", HOME / "Games" / "umu"):
        if base.is_dir():
            cands += sorted(p for p in base.iterdir() if p.is_dir())
    cands.append(HOME / ".wine")
    seen, out = set(), []
    for c in cands:
        try:
            key = c.resolve()
        except OSError:
            continue
        if key not in seen and (c / "system.reg").exists():
            seen.add(key)
            out.append(c)
    return out


def detect_umu_run() -> str:
    for c in (shutil.which("umu-run"), HOME / ".local/bin/umu-run", "/usr/bin/umu-run",
              HOME / ".local/share/faugus-launcher/umu-run"):
        if c and Path(c).exists():
            return str(c)
    return ""


def autodetect(s: Settings) -> list[str]:
    """Fill in empty settings. Returns a list of human readable notes about what was detected."""
    notes = []
    if not s.game_dir or not check_game_dir(Path(s.game_dir))[0]:
        dirs = detect_game_dirs()
        if dirs:
            s.game_dir = str(dirs[0])
            notes.append(f"Game folder: {dirs[0]}")
    if not s.documents_dir or not Path(s.documents_dir).is_dir():
        docs = detect_documents_dirs(s)
        if docs:
            s.documents_dir = str(docs[0])
            notes.append(f"Documents folder: {docs[0]}")
    if not s.umu_run:
        s.umu_run = detect_umu_run()
    if s.runner not in ("wine", "umu"):  # e.g. the removed "onelauncher" mode
        s.runner = "wine"
    if s.game_path and s.language not in game_languages(s.game_path):
        s.language = game_languages(s.game_path)[0]
    return notes
