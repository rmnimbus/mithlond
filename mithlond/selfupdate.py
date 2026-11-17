"""Updating Mithlond itself from its releases on gitgud.io (a GitLab instance).

Only the AppImage can update itself: the new AppImage is downloaded next to the running one, verified
(size, AppImage header, the SHA-256 from the release's SHA256SUMS file), made executable, and replaces the
old file. Running from source, the user is pointed at the release page instead.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from . import __version__

HOST = "gitgud.io"
REPO = "Realmonster/mithlond"
API = f"https://{HOST}/api/v4/projects/{REPO.replace('/', '%2F')}/releases/permalink/latest"
RELEASES_PAGE = f"https://{HOST}/{REPO}/-/releases"
UA = {"User-Agent": f"Mithlond/{__version__}", "Accept": "application/json"}
SUMS = "SHA256SUMS"


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str  # "1.4.0"
    tag: str  # "v1.4.0"
    notes: str
    page: str
    asset_name: str | None
    asset_url: str | None
    asset_size: int
    sha256: str | None


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def is_newer(candidate: str, current: str = __version__) -> bool:
    return _vkey(candidate) > _vkey(current)


def arch() -> str:
    m = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(m, m)


def _links(data: dict) -> list[dict]:
    return [ln for ln in (data.get("assets") or {}).get("links") or [] if ln.get("name")]


def _url(link: dict) -> str:
    return link.get("direct_asset_url") or link.get("url") or ""


def parse_sums(text: str) -> dict[str, str]:
    """`sha256sum` output: '<hex>  <name>' (or '<hex> *<name>') per line."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def parse_release(data: dict, sums: dict[str, str] | None = None) -> Release:
    """A GitLab release (GET /projects/:id/releases/...) plus the parsed SHA256SUMS of that release."""
    tag = data.get("tag_name") or ""
    asset = next((a for a in _links(data) if a["name"].endswith(f"-{arch()}.AppImage")), None)
    return Release(
        version=tag.lstrip("vV"), tag=tag, notes=(data.get("description") or "").strip(),
        page=(data.get("_links") or {}).get("self") or RELEASES_PAGE,
        asset_name=asset["name"] if asset else None, asset_url=_url(asset) if asset else None,
        asset_size=0, sha256=(sums or {}).get(asset["name"]) if asset else None,
    )


def latest_release(timeout: float = 15) -> Release:
    try:
        r = requests.get(API, headers=UA, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        sums = None
        link = next((a for a in _links(data) if a["name"] == SUMS), None)
        if link:
            s = requests.get(_url(link), headers=UA, timeout=timeout)
            s.raise_for_status()
            sums = parse_sums(s.text)
        rel = parse_release(data, sums)
        if rel.asset_url:  # GitLab's release links carry no size
            h = requests.head(rel.asset_url, headers=UA, timeout=timeout, allow_redirects=True)
            if h.ok:
                rel.asset_size = int(h.headers.get("Content-Length") or 0)
        return rel
    except (requests.RequestException, ValueError) as e:
        raise UpdateError(f"Couldn't check {HOST} for updates: {e}") from e


def running_appimage() -> Path | None:
    """The .AppImage file Mithlond is running from (the AppImage runtime sets $APPIMAGE), or None."""
    p = os.environ.get("APPIMAGE")
    return Path(p) if p and Path(p).is_file() else None


def can_self_update() -> tuple[bool, str]:
    current = running_appimage()
    if current is None:
        return False, "Mithlond isn't running from an AppImage, so it can't replace itself."
    if not os.access(current.parent, os.W_OK):
        return False, f"{current.parent} isn't writable, so the AppImage there can't be replaced."
    return True, ""


def _check_appimage(path: Path) -> None:
    with open(path, "rb") as f:
        head = f.read(11)
    if head[:4] != b"\x7fELF" or head[8:11] != b"AI\x02":
        raise UpdateError("The download isn't an AppImage; the update was cancelled.")


def update(release: Release, progress: Callable[[int, int], None] | None = None,
           current: Path | None = None) -> Path:
    """Download and install `release` next to the running AppImage. Returns the new AppImage's path.
    The old file is removed (the running copy keeps working until Mithlond exits)."""
    current = current or running_appimage()
    if current is None:
        raise UpdateError("Mithlond isn't running from an AppImage.")
    if not release.asset_url or not release.asset_name:
        raise UpdateError(f"Release {release.tag} has no AppImage for {arch()}.")
    target = current.parent / release.asset_name
    part = current.parent / f".{release.asset_name}.part"
    sha = hashlib.sha256()
    try:
        with requests.get(release.asset_url, headers={"User-Agent": UA["User-Agent"]}, stream=True,
                          timeout=60) as r:
            r.raise_for_status()
            total, done = int(r.headers.get("Content-Length") or release.asset_size or 0), 0
            with open(part, "wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        if release.asset_size and part.stat().st_size != release.asset_size:
            raise UpdateError("The download is incomplete; the update was cancelled.")
        if release.sha256 and sha.hexdigest() != release.sha256:
            raise UpdateError("The download doesn't match the release's checksum; the update was cancelled.")
        _check_appimage(part)
        part.chmod(0o755)
        part.replace(target)
    except requests.RequestException as e:
        raise UpdateError(f"Download failed: {e}") from e
    finally:
        part.unlink(missing_ok=True)
    if target.resolve() != current.resolve():
        current.unlink(missing_ok=True)  # Linux keeps the running (mounted) copy alive until exit
    from . import desktopentry
    try:
        desktopentry.refresh(target)  # the menu entry follows the new file name
    except OSError:
        pass
    return target
