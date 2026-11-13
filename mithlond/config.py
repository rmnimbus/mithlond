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
    use_prefs: bool = True  # start the game with --prefs <documents_dir>\UserPreferences.ini
    downloads_dir: str = ""  # empty: <documents_dir>/Downloads (Maestro, WAN Songbook Filler, Companion…)

    # How Windows programs are run
    runner: str = "umu"  # "umu" (Proton via umu-run, proton_path) or "wine" (wine_binary)
    wine_binary: str = "wine"
    wine_prefix: str = ""  # empty: the runner's default (~/Games/umu/umu-default, or ~/.wine for Wine)
    proton_path: str = ""  # empty: umu's default (UMU-Proton, downloaded automatically)
    extra_env: dict[str, str] = field(default_factory=dict)
    # Common game options (game client only)
    opt_gamescope: bool = False
    # Visual effects tab: gamescope (upscaling and display), see effects.gamescope_args
    gs_fullscreen: bool = True
    gs_borderless: bool = False
    gs_output_w: int = 0  # 0 = the monitor's size
    gs_output_h: int = 0
    gs_render: str = "native"  # effects.RENDER_SCALES key
    gs_render_w: int = 0
    gs_render_h: int = 0
    gs_filter: str = "linear"
    gs_sharpness: int = 5  # 0 = sharpest … 20 = softest (FSR/NIS/SGSR)
    gs_scaler: str = "auto"
    gs_refresh: int = 0  # game frame rate inside gamescope (-r), 0 = default
    gs_unfocused_refresh: int = 0  # frame rate while not focused (-o)
    gs_adaptive_sync: bool = False
    gs_mangoapp: bool = False
    gs_hdr: bool = False
    gs_hdr_itm: bool = False
    gs_grab_keyboard: bool = False
    gs_force_grab_cursor: bool = False
    # vkBasalt
    vkb_enabled: bool = False
    vkb_on_launch: bool = True
    vkb_toggle_key: str = "Home"
    vkb_cas: bool = True
    vkb_cas_sharpness: float = 0.4
    vkb_dls: bool = False
    vkb_dls_sharpness: float = 0.5
    vkb_dls_denoise: float = 0.17
    vkb_fxaa: bool = False
    vkb_fxaa_subpix: float = 0.75
    vkb_fxaa_edge: float = 0.125
    vkb_fxaa_edge_min: float = 0.0312
    vkb_smaa: bool = False
    vkb_smaa_edge: str = "luma"
    vkb_smaa_threshold: float = 0.05
    vkb_smaa_steps: int = 32
    vkb_smaa_steps_diag: int = 16
    vkb_smaa_corner: int = 25
    vkb_lut: bool = False
    vkb_lut_file: str = ""
    vkb_reshade_dir: str = ""  # contains Shaders/ and Textures/
    vkb_reshade_effects: str = ""  # .fx names from Shaders/, space separated
    # DXVK (dxvk.conf)
    dxvk_aniso: int = 0  # 0 = the game's setting
    dxvk_lod_bias: float = 0.0
    dxvk_latency: int = 0  # 0 = DXVK's default
    dxvk_vsync: str = "game"  # game | on | off
    dxvk_tearfree: str = "Auto"  # Auto | True | False
    gamescope_args: str = ""  # extra gamescope arguments (Visual effects tab)
    opt_mangohud: bool = False
    opt_gamemode: bool = False
    opt_dxvk_hud: bool = False
    opt_proton_wayland: bool = False
    opt_proton_log: bool = False

    # Game
    client: str = "win64"  # "win64" or "win32"
    language: str = "English"
    high_res: bool = True
    skip_intro: bool = True  # Turbine logo video every start + the one-time intro cinematic
    fps_limit: int = 0  # 0 = no limit; DXVK_FRAME_RATE (Direct3D 11 through DXVK, i.e. Wine/Proton)
    voice_off: bool = False  # --voiceoff: the game's voice chat system
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

    # Mithlond itself
    check_updates_on_start: bool = True
    skipped_version: str = ""  # "Skip this version" on the update banner

    # Layouts tab: mouse moves in steps of 1/5/10 px; snap to other windows' edges
    layout_grid: int = 1
    layout_snap_windows: bool = False

    # Plugins: characters added by hand on Plugins → Load plugins, per "<account>/<server>"
    known_characters: dict[str, list[str]] = field(default_factory=dict)

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
        """A folder inside the documents folder (Plugins, Music, PluginData, ui/skins)."""
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

FAUGUS_FLATPAK = HOME / ".var/app/io.github.Faugus.faugus-launcher"
# Faugus's data folder: native/AppImage/distro package, then the Flatpak's.
FAUGUS_DATA_DIRS = (HOME / ".local/share/faugus-launcher", FAUGUS_FLATPAK / "data/faugus-launcher")


def _faugus_games() -> list[dict]:
    games: list[dict] = []
    for p in [d / "games.json" for d in FAUGUS_DATA_DIRS] + [HOME / ".config/faugus-launcher/games.json"]:
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, list):
            games += [g for g in data if isinstance(g, dict)]
    return games


def faugus_lotro() -> dict | None:
    """The user's LOTRO entry in Faugus (most recently played first), if any."""
    lotro = [g for g in _faugus_games()
             if str(g.get("path", "")).lower().endswith(("lotrolauncher.exe", "lotroclient.exe", "lotroclient64.exe"))]
    return max(lotro, key=lambda g: str(g.get("last_played", "")), default=None)


# Where the official installer puts the game inside a Wine prefix.
GAME_SUBDIRS = (
    "drive_c/Program Files (x86)/StandingStoneGames/The Lord of the Rings Online",
    "drive_c/Program Files/StandingStoneGames/The Lord of the Rings Online",
    "drive_c/Program Files (x86)/Turbine/The Lord of the Rings Online",
)


def detect_game_dirs(extra_prefixes: list[Path] = ()) -> list[Path]:
    cands: list[Path] = []
    for g in _faugus_games():
        exe = str(g.get("path", ""))
        if exe.lower().endswith(("lotrolauncher.exe", "lotroclient.exe")):
            cands.append(Path(exe).parent)
    prefixes = list(extra_prefixes) + [HOME / ".wine"] + [Path(g["prefix"]) for g in _faugus_games() if g.get("prefix")]
    for pfx in prefixes:
        for sub in GAME_SUBDIRS:
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


COMPAT_DIRS = (
    HOME / ".local/share/Steam/compatibilitytools.d",
    HOME / ".steam/root/compatibilitytools.d",
    HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam/compatibilitytools.d",  # Steam Flatpak
    Path("/usr/share/steam/compatibilitytools.d"),  # distro packages (e.g. proton-cachyos)
    HOME / ".local/share/Steam/steamapps/common",
)


def proton_versions() -> list[Path]:
    out = []
    for base in COMPAT_DIRS:
        if base.is_dir():
            out += sorted(p for p in base.iterdir() if (p / "proton").exists())
    seen, uniq = set(), []
    for p in out:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            uniq.append(p)
    return uniq


_ELF_MACHINES = {0x3E: "x86_64", 0xB7: "aarch64", 0x03: "i386"}


def host_arch() -> str:
    import platform
    m = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(m, m)


def proton_arch(proton_dir: Path) -> str | None:
    """CPU architecture a Proton build was made for, read from its wineserver binary's ELF header."""
    for name in ("files/bin/wineserver", "files/bin/wine64", "files/bin/wine", "dist/bin/wineserver"):
        f = proton_dir / name
        try:
            with open(f, "rb") as fh:
                head = fh.read(20)
        except OSError:
            continue
        if head[:4] == b"\x7fELF":
            return _ELF_MACHINES.get(int.from_bytes(head[18:20], "little"))
    return None


def proton_problem(proton_dir: Path) -> str | None:
    arch = proton_arch(proton_dir)
    if arch and arch != host_arch():
        article = "an" if arch[0] in "aeiou" else "a"
        return f"{proton_dir.name} is {article} {arch} build and can't run on this {host_arch()} computer"
    return None


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


def bundled_umu_run() -> Path | None:
    """umu-run shipped inside the AppImage (packaging/build-appimage.sh), run with the AppImage's Python."""
    appdir = os.environ.get("APPDIR")
    if appdir and (p := Path(appdir) / "opt/umu/umu-run").is_file():
        return p
    return None


def detect_umu_run() -> str:
    """A umu-run on the system (running from source): PATH, pip/pipx, or the one Faugus downloads."""
    for c in (shutil.which("umu-run"), HOME / ".local/bin/umu-run", "/usr/bin/umu-run",
              *(d / "umu-run" for d in FAUGUS_DATA_DIRS)):
        if c and Path(c).is_file():
            return str(c)
    return ""


def umu_command() -> list[str]:
    """How to start umu-run: the bundled copy inside the AppImage, otherwise one found on the system."""
    import sys
    if bundled := bundled_umu_run():
        return [sys.executable, "-I", str(bundled)]
    found = detect_umu_run()
    return [found] if found else []


SELINUX_FS = Path("/sys/fs/selinux")


def selinux_problem(root: Path = SELINUX_FS) -> str | None:
    """SELinux in enforcing mode with `selinuxuser_execmod` off (openSUSE's default) stops Wine/Proton from
    making ntdll executable: the game exits within seconds with nothing but 'failed to set … protection on
    ntdll.dll … noexec filesystem?' in a Wine debug log. Both files are readable by normal users."""
    try:
        enforcing = (root / "enforce").read_text().strip() == "1"
        execmod = (root / "booleans/selinuxuser_execmod").read_text().split()[0] == "1"
    except (OSError, IndexError):
        return None
    if enforcing and not execmod:
        return ("SELinux blocks Wine/Proton on this system (selinuxuser_execmod is off), so the game closes right "
                "after starting. Allow it with: sudo setsebool -P selinuxuser_execmod 1")
    return None


def wine_installed(s: Settings) -> bool:
    w = s.wine_binary or "wine"
    return bool(shutil.which(w) or (os.sep in w and Path(w).is_file()))


def best_proton() -> str:
    """The Proton to start with: Faugus's choice for LOTRO, else the newest usable one, else '' (umu's default)."""
    usable = [p for p in proton_versions() if not proton_problem(p)]
    if (g := faugus_lotro()) and g.get("runner"):
        for p in usable:
            if p.name == g["runner"]:
                return str(p)
    usable = [p for p in usable if "steamapps" not in str(p)]  # Steam's own Protons need Steam's runtime layout
    if usable:
        return str(max(usable, key=lambda p: p.stat().st_mtime))
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
        elif not s.documents_dir:
            # Nothing found (first LOTRO on this computer): use the usual place. The game is started with
            # --prefs there and gets seeded settings, so it doesn't stop at its first-run DirectX prompt.
            s.documents_dir = str(HOME / "Documents" / DOCS_FOLDER_NAME)
            notes.append(f"Documents folder (new): {s.documents_dir}")
    fresh = not CONFIG_FILE.exists()
    if s.gamescope_args.strip() == "-f":  # before 1.4.9 fullscreen was this argument; now it's gs_fullscreen
        s.gamescope_args = ""
    if s.runner not in ("wine", "umu"):  # e.g. the removed "onelauncher" mode
        s.runner = "umu"
    if s.runner == "wine" and not wine_installed(s) and umu_command():
        fresh = True
        # Nothing to run Wine with (e.g. a Faugus user: Faugus only uses Proton). Proton via umu always works.
        s.runner = "umu"
        if s.wine_prefix and (Path(s.wine_prefix).expanduser() / "system.reg").exists() \
                and not is_proton_prefix(Path(s.wine_prefix).expanduser()):
            s.wine_prefix = ""  # a plain-Wine prefix: Proton would convert it, so use umu's own instead
        notes.append("Runner: Proton (Wine isn't installed)")
    if fresh and s.runner == "umu" and not s.proton_path and not s.wine_prefix:
        # Fresh setup: start where Faugus already plays LOTRO, if it does.
        if (g := faugus_lotro()) and g.get("prefix") and Path(g["prefix"]).is_dir():
            s.wine_prefix = g["prefix"]
            notes.append(f"Prefix (from Faugus): {g['prefix']}")
        s.proton_path = best_proton()
        if s.proton_path:
            notes.append(f"Proton: {Path(s.proton_path).name}")
    if s.game_path and s.language not in game_languages(s.game_path):
        s.language = game_languages(s.game_path)[0]
    return notes
