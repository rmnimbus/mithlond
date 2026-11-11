"""Music tools that can be downloaded into the Downloads folder: Maestro, BruTE, WAN Songbook Filler."""

from __future__ import annotations

import datetime as dt
import email.utils
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

UA = {"User-Agent": "Mithlond-LOTRO-Launcher"}
Progress = Callable[[str, int, int], None]


class ToolError(Exception):
    pass


@dataclass
class ToolInfo:
    key: str
    name: str
    page: str  # project page
    folder: str  # folder inside Downloads


@dataclass
class Latest:
    version: str
    date: dt.date | None
    download: str | None  # None: nothing installable (e.g. source code only)
    note: str = ""

    def describe(self) -> str:
        when = self.date.strftime("%b %d, %Y") if self.date else "unknown date"
        age = ""
        if self.date:
            days = (dt.date.today() - self.date).days
            age = f" ({days // 365} years ago)" if days >= 730 else f" ({days // 30} months ago)" if days >= 60 \
                else f" ({days} days ago)"
        text = f"Latest: {self.version}, {when}{age}" if self.version else f"Last updated {when}{age}"
        return text + (f" · {self.note}" if self.note else "")


TOOLS = {
    "maestro": ToolInfo("maestro", "Maestro", "https://github.com/NikolaiVChr/maestro/releases", "Maestro"),
    "brute": ToolInfo("brute", "BruTE", "https://github.com/bruzo/BruTE-", "BruTE"),
    "wan": ToolInfo("wan", "WAN Songbook Filler", "https://lotro.hanft.de/wansongbookfiller/", "WANSongBookFiller"),
}
WAN_EXE = "https://lotro.hanft.de/wansongbookfiller/WANSongBookFiller.exe"


def _gh(path: str) -> dict | list:
    try:
        r = requests.get(f"https://api.github.com/{path}", headers=UA, timeout=20)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        raise ToolError(f"GitHub: {e}") from e


def _date(iso: str | None) -> dt.date | None:
    try:
        return dt.datetime.fromisoformat((iso or "").replace("Z", "+00:00")).date()
    except ValueError:
        return None


def latest(key: str) -> Latest:
    if key == "maestro":
        rel = _gh("repos/NikolaiVChr/maestro/releases/latest")
        asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".zip")), None)
        return Latest(rel.get("tag_name", ""), _date(rel.get("published_at")),
                      asset["browser_download_url"] if asset else None)
    if key == "brute":
        repo = _gh("repos/bruzo/BruTE-")
        rels = _gh("repos/bruzo/BruTE-/releases?per_page=1")
        if rels:
            r = rels[0]
            asset = next((a for a in r.get("assets", []) if a["name"].lower().endswith((".zip", ".exe"))), None)
            return Latest(r.get("tag_name", ""), _date(r.get("published_at")),
                          asset["browser_download_url"] if asset else None)
        return Latest("", _date(repo.get("pushed_at")), None,
                      "no releases: source code only (BruTE++, C++), must be compiled")
    if key == "wan":
        try:
            h = requests.head(WAN_EXE, headers=UA, timeout=20, allow_redirects=True)
            h.raise_for_status()
            page = requests.get(TOOLS["wan"].page, headers=UA, timeout=20).text
        except requests.RequestException as e:
            raise ToolError(str(e)) from e
        lm = h.headers.get("Last-Modified")
        date = email.utils.parsedate_to_datetime(lm).date() if lm else None
        m = re.search(r"Revision History:.*?(\d+\.\d+):", re.sub(r"<[^>]+>", " ", page), re.S)
        return Latest(m.group(1) if m else "", date, WAN_EXE)
    raise ToolError(f"unknown tool {key}")


def _download(url: str, dest: Path, progress: Progress | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, headers=UA, stream=True, timeout=60) as r:
            r.raise_for_status()
            total, done = int(r.headers.get("Content-Length") or 0), 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress("Downloading", done, total)
    except requests.RequestException as e:
        raise ToolError(f"Download failed: {e}") from e


def install(key: str, downloads: Path, progress: Progress | None = None) -> Path:
    """Download the latest version into <downloads>/<folder>, replacing an older copy.
    Returns the file to start (Maestro.jar when Java is available, else Maestro.exe; the .exe for WAN)."""
    info, rel = TOOLS[key], latest(key)
    if not rel.download:
        raise ToolError(f"{info.name} has no downloadable release. See {info.page}")
    target = downloads / info.folder
    staging = downloads / f".{info.folder}.staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        if key == "wan":
            _download(rel.download, staging / "WANSongBookFiller.exe", progress)
        else:
            archive = staging / "download.zip"
            _download(rel.download, archive, progress)
            if progress:
                progress("Extracting", 0, 0)
            try:
                with zipfile.ZipFile(archive) as z:
                    for n in z.namelist():
                        if n.startswith("/") or ".." in n.split("/"):
                            raise ToolError(f"Unsafe path in archive: {n}")
                    z.extractall(staging)
            except zipfile.BadZipFile as e:
                raise ToolError("The download is not a valid zip; try again.") from e
            archive.unlink()
            for exe in staging.rglob("*.exe"):
                exe.chmod(0o755)
            for sh in staging.rglob("*.sh"):
                sh.chmod(0o755)
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    (target / ".mithlond-version").write_text(rel.version)
    return launch_file(key, target)


def launch_file(key: str, folder: Path) -> Path:
    if key == "wan":
        return folder / "WANSongBookFiller.exe"
    jar = next(folder.rglob("Maestro.jar"), None)
    if jar and shutil.which("java"):
        return jar
    exe = next(folder.rglob("Maestro.exe"), None)
    if exe:
        return exe
    raise ToolError(f"Maestro not found in {folder}")


def installed_version(key: str, downloads: Path) -> str:
    f = downloads / TOOLS[key].folder / ".mithlond-version"
    try:
        return f.read_text().strip()
    except OSError:
        return ""
