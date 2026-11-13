"""Installing the game itself: download the official installer from lotro.com and run it in the prefix.

The download page (https://www.lotro.com/en/game/download) links the Windows installer below. It sets up
the official launcher and a small part of the game; the rest of the game data is downloaded by patching
(Play → Check for game updates, or the official launcher)."""

from __future__ import annotations

from pathlib import Path

import requests

from .config import CACHE_DIR, GAME_SUBDIRS, check_game_dir

INSTALLER_URL = "https://akamai.lotro.com/lotro/lotrolive.exe"
DOWNLOAD_PAGE = "https://www.lotro.com/en/game/download"
INSTALLER = CACHE_DIR / "lotrolive.exe"
UA = {"User-Agent": "Mithlond-LOTRO-Launcher"}


class InstallError(Exception):
    pass


def download(progress=None, dest: Path = INSTALLER) -> Path:
    """Download the installer (about 46 MB). `progress(done, total)` is called as it arrives."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        with requests.get(INSTALLER_URL, headers=UA, stream=True, timeout=60) as r:
            r.raise_for_status()
            total, done = int(r.headers.get("Content-Length") or 0), 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except (requests.RequestException, OSError) as e:
        tmp.unlink(missing_ok=True)
        raise InstallError(f"Couldn't download the installer: {e}") from e
    with open(tmp, "rb") as f:
        head = f.read(2)
    if head != b"MZ" or tmp.stat().st_size < 1_000_000 or (total and tmp.stat().st_size != total):
        tmp.unlink(missing_ok=True)
        raise InstallError("The download isn't a complete Windows installer. Try again later, or download it "
                           f"from {DOWNLOAD_PAGE}")
    tmp.replace(dest)
    return dest


def installed_in(prefix: Path) -> list[Path]:
    """Game folders the installer created in this prefix (complete ones first). Right after installing, the
    folder may hold only the launcher until patching has downloaded the rest."""
    found = [prefix / sub for sub in GAME_SUBDIRS if (prefix / sub).is_dir() and (
        any((prefix / sub).glob("*.launcherconfig")) or (prefix / sub / "LotroLauncher.exe").exists())]
    return sorted(found, key=lambda d: not check_game_dir(d)[0])


# /SILENT: progress window only, no questions; /DIR: the usual folder inside the prefix.
INSTALL_DIR = r"C:\Program Files (x86)\StandingStoneGames\The Lord of the Rings Online"
SILENT_ARGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/DIR={INSTALL_DIR}"]
ACCOUNT_URL = "https://myaccount.standingstonegames.com/index.php"
