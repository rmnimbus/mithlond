"""LotRO Companion install management: version, updates from SourceForge, and starting it directly.

Companion's own updater ("kickstarter", delta-updates-manager 1.0) can hang forever on a download
(seen 2026-11: it stops after ~24 KB of a 28 KB package description), and then Companion never opens.
So Mithlond starts Companion's main class directly and updates it by swapping in the full release.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

import requests

from .config import CACHE_DIR

RSS = "https://sourceforge.net/projects/lotrocompanion/rss?path=/"
RELEASE_URL = "https://sourceforge.net/projects/lotrocompanion/files/{name}/download"
TOP = "LotRO Companion"  # folder name inside release zips


class CompanionError(Exception):
    pass


@dataclass
class Release:
    version: str
    name: str  # lotro-companion-24.11.0.50.0.zip

    @property
    def url(self) -> str:
        return RELEASE_URL.format(name=self.name)


def app_dir(base: Path) -> Path:
    return base / "app" if (base / "app").is_dir() else base


def installed_version(base: Path) -> str:
    cfg = app_dir(base) / "LotRO Companion.cfg"
    try:
        for line in cfg.read_text(errors="replace").splitlines():
            if line.startswith("app.version="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def is_newer(latest: str, installed: str) -> bool:
    if not latest:
        return False
    if not installed:
        return True
    a, b = _vkey(latest), _vkey(installed)
    n = min(len(a), len(b))  # release names carry an extra build digit: 24.11.0.50.0 vs 24.11.0.50
    return a[:n] > b[:n]


def latest_release() -> Release:
    try:
        r = requests.get(RSS, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError) as e:
        raise CompanionError(f"Could not check for LotRO Companion updates: {e}") from e
    best: Release | None = None
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip().lstrip("/")
        m = re.fullmatch(r"lotro-companion-([\d.]+?)\.zip", title)
        if m and (best is None or _vkey(m.group(1)) > _vkey(best.version)):
            best = Release(m.group(1), title)
    if best is None:
        raise CompanionError("No LotRO Companion release found on SourceForge")
    return best


def update(base: Path, release: Release, progress: Callable[[str, int, int], None] | None = None) -> Path | None:
    """Download the full release into `base` (installing it, or swapping out an existing copy, which is kept
    as '<folder>.old-<version>'; older Mithlond backups are removed). Companion must not be running.
    Returns the backup path, if there was a previous install."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    base.parent.mkdir(parents=True, exist_ok=True)
    archive = CACHE_DIR / release.name
    try:
        with requests.get(release.url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total, done = int(r.headers.get("Content-Length") or 0), 0
            with open(archive, "wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress("Downloading", done, total)
    except requests.RequestException as e:
        raise CompanionError(f"Download failed: {e}") from e
    if progress:
        progress("Checking", 0, 0)
    try:
        z = zipfile.ZipFile(archive)
        if z.testzip() is not None:
            raise CompanionError("The download is damaged; try again.")
    except zipfile.BadZipFile as e:
        raise CompanionError("The download is not a valid zip; try again.") from e
    names = z.namelist()
    if f"{TOP}/app/LotRO Companion.cfg" not in names:
        raise CompanionError("Unexpected archive layout (no LotRO Companion/app/LotRO Companion.cfg).")
    for n in names:
        if n.startswith("/") or ".." in n.split("/"):
            raise CompanionError(f"Unsafe path in archive: {n}")
    staging = base.parent / f".{base.name}.staging"
    shutil.rmtree(staging, ignore_errors=True)
    if progress:
        progress("Extracting", 0, 0)
    z.extractall(staging)
    exe = staging / TOP / "LotRO Companion.exe"
    if exe.exists():
        exe.chmod(0o755)
    backup = None
    if base.exists():
        old_version = installed_version(base) or "previous"
        backup = base.parent / f"{base.name}.old-{old_version}"
        for stale in base.parent.glob(f"{base.name}.old-*"):
            if stale != backup:
                shutil.rmtree(stale, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        base.rename(backup)
    (staging / TOP).rename(base)
    shutil.rmtree(staging, ignore_errors=True)
    archive.unlink(missing_ok=True)
    return backup


def direct_launch(base: Path, windows: bool) -> tuple[str, list[str], Path]:
    """(java executable, args, cwd) to start Companion's main class without its updater.
    `windows`: use the bundled Windows Java under Wine/Proton (classpath with backslashes)."""
    app = app_dir(base)
    try:
        root = ET.parse(app / "launcher.xml").getroot()
    except (OSError, ET.ParseError) as e:
        raise CompanionError(f"Can't read {app / 'launcher.xml'}: {e}") from e
    main, lib = root.get("mainClass"), root.get("rootDir") or "lib"
    entries = [e.get("path") for e in root.iter("classpathEntry") if e.get("path")]
    if not main or not entries:
        raise CompanionError("launcher.xml has no main class or classpath")
    opts = ["-Xms256m", "-Xmx1024m", "-Dlogback.configurationFile=runtime_logback.xml"]
    if windows:
        java = base / "runtime" / "bin" / "javaw.exe"
        if not java.exists():
            raise CompanionError(f"{java} not found")
        cp = ";".join(f"{lib}\\{p.replace('/', chr(92))}" for p in entries)
        return str(java), [*opts, "-cp", cp, main], app
    java = shutil.which("java")
    if not java:
        raise CompanionError("Java is not installed")
    cp = ":".join(str(app / lib / p) for p in entries)
    return java, [*opts, "-Duser.language=en", "-cp", cp, main], app
