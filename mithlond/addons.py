"""Plugins, skins (themes) and music packs from lotrointerface.com.

Compatible with LOTRO Plugin Compendium: installed plugins are found through their
`.plugincompendium` files, and plugins installed here get one written if the archive has none.
Every install is also recorded in a manifest so uninstalling removes exactly what was added.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import requests

from .config import CACHE_DIR, DATA_DIR
from .hostenv import host_env

# lotrointerface.com publishes curated lists rather than one full catalogue. The OneLauncher and
# Plugin Compendium plugin lists overlap only partly (412 + 335 entries, 474 together in Nov 2026),
# so plugins come from both.
FEEDS = {
    "plugin": ["https://api.lotrointerface.com/fav/OneLauncher-Plugins.xml",
               "https://api.lotrointerface.com/fav/plugincompendium.xml"],
    "skin": ["https://api.lotrointerface.com/fav/OneLauncher-Themes.xml"],
    "music": ["https://api.lotrointerface.com/fav/OneLauncher-Music.xml"],
}
INFO_URL = "https://www.lotrointerface.com/downloads/info{id}"
DOWNLOAD_URL = "https://www.lotrointerface.com/downloads/download{id}"
FEED_TTL = 3600
JUNK = {"__MACOSX", ".DS_Store", "Thumbs.db", "desktop.ini"}
MANIFEST = DATA_DIR / "installed.json"

ProgressFn = Callable[[int, int], None]


class AddonError(Exception):
    pass


@dataclass
class RemoteAddon:
    id: str
    kind: str
    name: str
    author: str
    version: str
    updated: int
    downloads: int
    category: str
    description: str
    file: str
    size: int
    url: str
    site_only: bool = False  # from the site catalogue: version/description load on demand
    curated: bool = True  # on a curated list (OneLauncher / Plugin Compendium); False = only in the site catalogue

    @property
    def info_url(self) -> str:
        return INFO_URL.format(id=self.id)


@dataclass
class InstalledAddon:
    kind: str
    name: str
    version: str = ""
    author: str = ""
    id: str = ""
    path: str = ""  # main folder or descriptor, for display / opening
    descriptors: list[str] = field(default_factory=list)  # .plugin paths relative to Plugins
    dependencies: list[str] = field(default_factory=list)
    managed: bool = False  # recorded in our manifest


# ---- feed -------------------------------------------------------------------

def _num(s: str) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def parse_feed(xml_bytes: bytes, kind: str) -> list[RemoteAddon]:
    root = ET.fromstring(xml_bytes)
    out = []
    for ui in root.iter("Ui"):
        g = lambda t: (ui.findtext(t) or "").strip()  # noqa: E731
        if not g("UID"):
            continue
        out.append(RemoteAddon(
            id=g("UID"), kind=kind, name=g("UIName"), author=g("UIAuthorName"), version=g("UIVersion"),
            updated=_num(g("UIUpdated")), downloads=_num(g("UIDownloads")), category=g("UICategory"),
            description=g("UIDescription"), file=g("UIFile"), size=_num(g("UISize")),
            url=g("UIFileURL") or DOWNLOAD_URL.format(id=g("UID")),
        ))
    return out


def merge_feeds(lists: list[list[RemoteAddon]]) -> list[RemoteAddon]:
    """Union by lotrointerface id; when an addon is in several lists, keep the most recently updated entry."""
    by_id: dict[str, RemoteAddon] = {}
    for addons in lists:
        for a in addons:
            if a.id not in by_id or a.updated > by_id[a.id].updated:
                by_id[a.id] = a
    return list(by_id.values())


def _fetch_one(url: str, kind: str, force: bool) -> list[RemoteAddon]:
    cache = CACHE_DIR / ("feed-" + url.rsplit("/", 1)[-1])
    if not force and cache.exists() and time.time() - cache.stat().st_mtime < FEED_TTL:
        try:
            return parse_feed(cache.read_bytes(), kind)
        except ET.ParseError:
            pass
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        addons = parse_feed(r.content, kind)
    except (requests.RequestException, ET.ParseError) as e:
        if cache.exists():  # offline: fall back to a stale cache
            return parse_feed(cache.read_bytes(), kind)
        raise AddonError(f"Could not load {url}: {e}") from e
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(r.content)
    return addons


def fetch_all(kind: str, force: bool = False, progress=None) -> list[RemoteAddon]:
    """The curated lists plus every other addon from lotrointerface.com's full catalogue.
    If the catalogue can't be read, the curated lists alone are returned."""
    from . import catalog
    listed = fetch_feed(kind, force)
    try:
        entries = catalog.load(force, progress)
    except catalog.CatalogError:
        return listed
    have = {a.id for a in listed}
    # Site-only entries: skins from skin categories on the Skins tab, everything else on Plugins.
    want_skin = kind == "skin"
    if kind == "music":
        return listed
    extra = [RemoteAddon(id=e.id, kind=kind, name=e.name, author=e.author, version="", updated=e.updated,
                         downloads=e.downloads, category=e.category, description="", file=f"{e.id}.zip",
                         size=e.size, url=DOWNLOAD_URL.format(id=e.id), site_only=True, curated=False)
             for e in entries if e.id not in have and (e.category in catalog.SKIN_CATEGORIES) == want_skin]
    return listed + extra


def fill_details(a: RemoteAddon) -> RemoteAddon:
    """Load version and description of a site-only addon from its page (in place)."""
    d = addon_from_link(a.id, a.kind)
    a.version, a.description = d.version, d.description or a.description
    a.author = a.author or d.author
    a.site_only = False
    return a


def fetch_feed(kind: str, force: bool = False) -> list[RemoteAddon]:
    """All addons of a kind from every list; works as long as at least one list loads."""
    lists, errors = [], []
    for url in FEEDS[kind]:
        try:
            lists.append(_fetch_one(url, kind, force))
        except AddonError as e:
            errors.append(str(e))
    if not lists:
        raise AddonError("Could not load the lotrointerface.com lists: " + "; ".join(errors))
    return merge_feeds(lists)


# ---- manifest ---------------------------------------------------------------

def _load_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        return {}


def _save_manifest(m: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1))
    tmp.replace(MANIFEST)


def _mkey(kind: str, base: Path, addon_id: str) -> str:
    return f"{kind}:{base.resolve()}:{addon_id}"


# ---- installed scan ------------------------------------------------------------

def _xml(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError):
        return None


def _t(el: ET.Element | None, tag: str) -> str:
    if el is None:
        return ""
    for c in el.iter():
        if c.tag.rsplit("}", 1)[-1].lower() == tag.lower():
            return (c.text or "").strip()
    return ""


def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").strip("/")


def scan_plugins(plugins_dir: Path) -> list[InstalledAddon]:
    if not plugins_dir.is_dir():
        return []
    manifest = _load_manifest()
    managed_ids = {k.rsplit(":", 1)[1] for k in manifest if k.startswith(f"plugin:{plugins_dir.resolve()}:")}
    out: list[InstalledAddon] = []
    claimed: set[str] = set()
    for comp in sorted(plugins_dir.rglob("*.plugincompendium")):
        root = _xml(comp)
        if root is None:
            continue
        descs = [_norm_rel(d.text or "") for d in root.iter() if d.tag.lower() == "descriptor" and d.text]
        deps = [(d.text or "").strip() for d in root.iter() if d.tag.lower() == "dependency" and d.text]
        claimed.update(d.lower() for d in descs)
        aid = _t(root, "Id")
        out.append(InstalledAddon(
            kind="plugin", name=_t(root, "Name") or comp.stem, version=_t(root, "Version"),
            author=_t(root, "Author"), id=aid if aid and aid != "0" else "",
            path=str(comp.parent), descriptors=descs, dependencies=deps, managed=aid in managed_ids,
        ))
    owned = {f.lower() for k, v in manifest.items() if k.startswith(f"plugin:{plugins_dir.resolve()}:")
             for f in v.get("files", [])}
    for desc in sorted(plugins_dir.rglob("*.plugin")):
        rel = desc.relative_to(plugins_dir).as_posix()
        if rel.lower() in claimed or rel.lower() in owned:  # part of another (managed) plugin's files
            continue
        root = _xml(desc)
        info = root.find("Information") if root is not None else None
        out.append(InstalledAddon(
            kind="plugin", name=_t(info, "Name") or desc.stem, version=_t(info, "Version"),
            author=_t(info, "Author"), path=str(desc.parent), descriptors=[rel],
        ))
    return out


def scan_skins(skins_dir: Path) -> list[InstalledAddon]:
    """One entry per skin installed through this launcher (all its folders), plus one per other folder."""
    if not skins_dir.is_dir():
        return []
    prefix = f"skin:{skins_dir.resolve()}:"
    out, owned = [], set()
    for key, entry in _load_manifest().items():
        if key.startswith(prefix):
            folders = [f for f in entry.get("folders", []) if (skins_dir / f).is_dir()]
            if not folders:
                continue
            owned.update(folders)
            out.append(InstalledAddon(kind="skin", name=entry.get("name", ""), version=entry.get("version", ""),
                                      author=entry.get("author", ""), id=key.rsplit(":", 1)[1],
                                      path=str(skins_dir / folders[0]), managed=True))
    for d in sorted(p for p in skins_dir.iterdir() if p.is_dir() and p.name not in owned):
        comp = next(d.glob("*.skincompendium"), None)
        root = _xml(comp) if comp else None
        skin = _xml(d / "SkinDefinition.xml")
        aid = _t(root, "Id")
        out.append(InstalledAddon(
            kind="skin", name=_t(root, "Name") or (skin.get("name") if skin is not None else "") or d.name,
            version=_t(root, "Version"), author=_t(root, "Author"), id=aid if aid != "0" else "", path=str(d),
        ))
    return out


def scan_music(music_dir: Path) -> list[InstalledAddon]:
    """Music packs installed through this launcher, plus the other top-level folders in Music
    (loose .abc files are shown on the Music tab)."""
    out, owned = [], set()
    prefix = f"music:{music_dir.resolve()}:" if music_dir.exists() else None
    for key, entry in _load_manifest().items():
        if prefix and key.startswith(prefix):
            owned.add(entry.get("folder", ""))
            out.append(InstalledAddon(kind="music", name=entry.get("name", ""), version=entry.get("version", ""),
                                      author=entry.get("author", ""), id=key.rsplit(":", 1)[1],
                                      path=str(music_dir / entry.get("folder", "")), managed=True))
    if music_dir.is_dir():
        for d in sorted(p for p in music_dir.iterdir() if p.is_dir() and p.name not in owned):
            out.append(InstalledAddon(kind="music", name=d.name, path=str(d)))
    return out


def adopt_plugins(plugins_dir: Path) -> list[str]:
    """Record plugins installed by hand / by Plugin Compendium (those with a lotrointerface id) in the
    manifest, so updates and uninstalls know exactly which files belong to them. Returns adopted names."""
    if not plugins_dir.is_dir():
        return []
    m = _load_manifest()
    claimed = {f for k, v in m.items() if k.startswith(f"plugin:{plugins_dir.resolve()}:") for f in v.get("files", [])}
    adopted = []
    for inst in scan_plugins(plugins_dir):
        key = _mkey("plugin", plugins_dir, inst.id) if inst.id else None
        if not key or key in m:
            continue
        files: set[str] = set()
        for d in inst.descriptors:
            desc = plugins_dir / d
            if not desc.exists():
                continue
            files.add(desc.relative_to(plugins_dir).as_posix())
            parts = (_t(_xml(desc), "Package") or "").split(".")[:2]
            pkg = plugins_dir.joinpath(*parts) if len(parts) == 2 else None
            if pkg and pkg.is_dir():
                files.update(f.relative_to(plugins_dir).as_posix() for f in pkg.rglob("*") if f.is_file())
        comp_dir = Path(inst.path)
        for comp in comp_dir.glob("*.plugincompendium"):
            root = _xml(comp)
            if root is not None and _t(root, "Id") == inst.id:
                files.add(comp.relative_to(plugins_dir).as_posix())
        files -= claimed  # never take over files another entry owns
        if not files:
            continue
        claimed |= files
        m[key] = {"name": inst.name, "version": inst.version, "author": inst.author, "updated": 0,
                  "files": sorted(files), "installed": int(time.time()), "adopted": True}
        adopted.append(inst.name)
    if adopted:
        _save_manifest(m)
    return adopted


# ---- version compare -------------------------------------------------------------

def _vkey(v: str) -> tuple:
    parts = re.findall(r"\d+|[a-zA-Z]+", v or "")
    return tuple((0, int(p)) if p.isdigit() else (1, p.lower()) for p in parts)


def is_newer(remote: str, installed: str) -> bool:
    if not remote or remote.strip() == (installed or "").strip():
        return False
    if not installed:
        return True
    try:
        return _vkey(remote) > _vkey(installed)
    except TypeError:
        return remote.strip().lower() != installed.strip().lower()


# ---- download & extract --------------------------------------------------------

def download(addon: RemoteAddon, progress: ProgressFn | None = None) -> Path:
    dest_dir = CACHE_DIR / "downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", addon.file or f"{addon.id}.zip")
    dest = dest_dir / f"{addon.id}-{safe}"
    try:
        with requests.get(addon.url, stream=True, timeout=60, allow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or addon.size or 0)
            done = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(64 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except requests.RequestException as e:
        raise AddonError(f"Download of {addon.name} failed: {e}") from e
    return dest


def extract_archive(archive: Path, dest: Path) -> None:
    """Extract zip (natively) or 7z/rar (with bsdtar or 7z) into `dest`, refusing unsafe paths."""
    dest.mkdir(parents=True, exist_ok=True)
    with open(archive, "rb") as f:
        magic = f.read(8)
    if magic.startswith(b"PK"):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                pp = PurePosixPath(name)
                if pp.is_absolute() or ".." in pp.parts:
                    raise AddonError(f"Archive contains an unsafe path: {name}")
                target = dest.joinpath(*pp.parts)
                if info.is_dir() or name.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    else:
        tool = shutil.which("bsdtar")
        cmd = [tool, "-xf", str(archive), "-C", str(dest)] if tool else None
        if cmd is None and shutil.which("7z"):
            cmd = ["7z", "x", "-y", f"-o{dest}", str(archive)]
        if cmd is None:
            raise AddonError("This archive is not a zip; install libarchive (bsdtar) or 7zip to extract it.")
        r = subprocess.run(cmd, capture_output=True, text=True, env=host_env())
        if r.returncode != 0:
            raise AddonError(f"Could not extract {archive.name}: {r.stderr.strip()[:300]}")
    # Never follow links planted by an archive.
    for p in list(dest.rglob("*")):
        if p.is_symlink():
            p.unlink()
        elif p.name in JUNK:
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)


# ---- install / uninstall -----------------------------------------------------

def _copy_tree(src: Path, dst: Path) -> list[str]:
    """Merge-copy src into dst; returns file paths relative to dst."""
    written = []
    for p in sorted(src.rglob("*")):
        if p.is_dir() or any(part in JUNK for part in p.parts):
            continue
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        written.append(rel.as_posix())
    return written


def _plugin_root(tmp: Path) -> Path:
    """Find the folder in an extracted archive that corresponds to the game's Plugins folder.
    A plugin's <Package>Author.Name.Main</Package> lives at Plugins/Author/Name/Main.lua."""
    descs = list(tmp.rglob("*.plugin"))
    if not descs:
        raise AddonError("No .plugin file in the archive; this doesn't look like a LOTRO plugin.")
    roots = []
    for d in descs:
        pkg = _t(_xml(d), "Package")
        found = None
        if pkg:
            parts = pkg.split(".")[:-1] or pkg.split(".")
            for cand in [d.parent, *d.parents]:
                if cand == tmp.parent:
                    break
                if (cand.joinpath(*parts)).is_dir():
                    found = cand
                    break
        if found is None:
            found = d.parent.parent if d.parent != tmp else tmp
        roots.append(found)
    # The shallowest root covers the others.
    return min(roots, key=lambda p: len(p.parts))


def _write_compendium(plugins_dir: Path, addon: RemoteAddon, descriptors: list[str]) -> str:
    author_dir = descriptors[0].split("/")[0] if "/" in descriptors[0] else ""
    safe = re.sub(r'[<>:"/\\|?*]+', "_", addon.name).strip() or addon.id
    rel = f"{author_dir}/{safe}.plugincompendium" if author_dir else f"{safe}.plugincompendium"
    descs = "".join(f"\n    <descriptor>{escape(d.replace('/', chr(92)))}</descriptor>" for d in descriptors)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<PluginConfig xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
        f"  <Id>{escape(addon.id)}</Id>\n  <Name>{escape(addon.name)}</Name>\n"
        f"  <Version>{escape(addon.version)}</Version>\n  <Author>{escape(addon.author)}</Author>\n"
        f"  <InfoUrl>{escape(addon.info_url)}</InfoUrl>\n  <DownloadUrl>{escape(addon.url)}</DownloadUrl>\n"
        f"  <Descriptors>{descs}\n  </Descriptors>\n  <Dependencies />\n</PluginConfig>\n"
    )
    (plugins_dir / rel).write_text(xml, encoding="utf-8")
    return rel


def _record(kind: str, base: Path, addon: RemoteAddon, files: list[str], **extra) -> None:
    m = _load_manifest()
    m[_mkey(kind, base, addon.id)] = {
        "name": addon.name, "version": addon.version, "author": addon.author,
        "updated": addon.updated, "files": sorted(set(files)), "installed": int(time.time()), **extra,
    }
    _save_manifest(m)


def _remove_files(base: Path, files: list[str]) -> None:
    dirs = set()
    for rel in files:
        p = (base / rel)
        try:
            p.resolve().relative_to(base.resolve())
        except ValueError:
            continue  # never delete outside base
        if p.is_file() or p.is_symlink():
            p.unlink()
        dirs.update(p.parents)
    for d in sorted(dirs, key=lambda x: len(x.parts), reverse=True):
        if d != base and base in d.parents:
            try:
                d.rmdir()  # only removes empty folders
            except OSError:
                pass


def install_archive(kind: str, archive: Path, addon: RemoteAddon, target: Path) -> list[str]:
    """Install an archive. `target` is Plugins/, ui/skins/ or Music/. Returns written files."""
    target.mkdir(parents=True, exist_ok=True)
    key = _mkey(kind, target, addon.id)
    old = _load_manifest().get(key)
    with tempfile.TemporaryDirectory(prefix="mithlond-") as td:
        tmp = Path(td) / "x"
        extract_archive(archive, tmp)
        extra = {}
        if kind == "plugin":
            root = _plugin_root(tmp)
            files = _copy_tree(root, target)
            descs = [f for f in files if f.lower().endswith(".plugin")]
            if not any(f.lower().endswith(".plugincompendium") for f in files) and descs:
                files.append(_write_compendium(target, addon, descs))
        elif kind == "skin":
            defs = list(tmp.rglob("SkinDefinition.xml"))
            if not defs:
                listing = ", ".join(sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file())[:5])
                raise AddonError("No SkinDefinition.xml in the archive, so it can't be installed as a skin "
                                 f"(it contains: {listing or 'nothing'}). Check its lotrointerface page.")
            # Compilations ship several skins; install every top-most folder with a SkinDefinition.xml.
            srcs = sorted({d.parent for d in defs}, key=lambda p: len(p.parts))
            tops = [p for i, p in enumerate(srcs) if not any(q in p.parents for q in srcs[:i])]
            files, folders = [], []
            for src in tops:
                folder = src.name if src != tmp else (re.sub(r"[^\w .\-]+", "_", addon.name).strip() or addon.id)
                files += [f"{folder}/{f}" for f in _copy_tree(src, target / folder)]
                folders.append(folder)
            extra["folders"] = folders
        elif kind == "music":
            songs = [p for p in tmp.rglob("*") if p.is_file() and p.suffix.lower() in (".abc", ".txt")]
            if not songs:
                raise AddonError("No .abc song files in the archive.")
            top = [p for p in tmp.iterdir()]
            if len(top) == 1 and top[0].is_dir():
                src, folder = top[0], top[0].name
            else:
                src, folder = tmp, re.sub(r"[^\w .\-]+", "_", addon.name).strip() or addon.id
            files = []
            for p in songs:
                rel = Path(folder) / p.relative_to(src)
                (target / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target / rel)
                files.append(rel.as_posix())
            extra["folder"] = folder
        else:
            raise AddonError(f"Unknown addon kind {kind}")
    # Updating: remove files the old version had that the new one doesn't.
    if old:
        stale = set(old.get("files", [])) - set(files)
        _remove_files(target, sorted(stale))
    _record(kind, target, addon, files, **extra)
    return files


def uninstall(addon: InstalledAddon, target: Path) -> None:
    m = _load_manifest()
    key = _mkey(addon.kind, target, addon.id) if addon.id else None
    if key and key in m:
        # Files another installed addon also lists (shared libraries) stay.
        base = key.rsplit(":", 1)[0] + ":"
        shared = {f for k, v in m.items() if k != key and k.startswith(base) for f in v.get("files", [])}
        _remove_files(target, [f for f in m[key]["files"] if f not in shared])
        if addon.kind == "skin":
            for folder in m[key].get("folders", []):
                if folder and ".." not in Path(folder).parts:
                    shutil.rmtree(target / folder, ignore_errors=True)
        del m[key]
        _save_manifest(m)
        return
    if addon.kind in ("skin", "music"):
        p = Path(addon.path)
        try:
            p.resolve().relative_to(target.resolve())
        except ValueError:
            raise AddonError(f"{p} is outside {target}") from None
        if p != target:
            shutil.rmtree(p, ignore_errors=True)
        return
    if addon.kind != "plugin":
        raise AddonError("Nothing recorded for this addon; remove its files by hand.")
    # Not installed by us: remove descriptors, their package folders (if no other plugin uses them)
    # and the compendium file.
    remaining_pkgs = []
    removing_pkgs = []
    mine = {d.lower() for d in addon.descriptors}
    for desc in target.rglob("*.plugin"):
        pkg = _t(_xml(desc), "Package")
        parts = pkg.split(".")[:2] if pkg else []
        rel = desc.relative_to(target).as_posix().lower()
        (removing_pkgs if rel in mine else remaining_pkgs).append(tuple(parts))
    for d in addon.descriptors:
        (target / d).unlink(missing_ok=True)
    for parts in set(removing_pkgs):
        if len(parts) == 2 and parts not in remaining_pkgs:
            shutil.rmtree(target / parts[0] / parts[1], ignore_errors=True)
    for comp in target.rglob("*.plugincompendium"):
        root = _xml(comp)
        descs = {_norm_rel(e.text or "").lower() for e in root.iter() if e.tag.lower() == "descriptor"} if root is not None else set()
        if descs and descs <= mine:
            comp.unlink()
    for d in {(target / x).parent for x in addon.descriptors}:
        try:
            if d != target and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass


def match_remote(inst: InstalledAddon, remote: list[RemoteAddon]) -> RemoteAddon | None:
    if inst.id:
        for r in remote:
            if r.id == inst.id:
                return r
    name = inst.name.lower().strip()
    hits = [r for r in remote if r.name.lower().strip() == name]
    if len(hits) == 1:
        return hits[0]
    return None


def parse_link(text: str) -> str | None:
    """The lotrointerface id from a link (…/info1218-Name.html, …/download1218, fileinfo.php?id=1218) or a number."""
    text = text.strip()
    m = re.search(r"(?:info|download|fileinfo\.php\?id=|downloads/)(\d+)", text) or re.fullmatch(r"#?(\d+)", text)
    return m.group(1) if m else None


def parse_info_page(addon_id: str, page: str, kind: str) -> RemoteAddon:
    import html as _html
    title = re.search(r"<title>\s*LoTROInterface\s*:\s*(.*?)\s*</title>", page, re.S | re.I)
    if not title:
        raise AddonError(f"lotrointerface.com has no addon #{addon_id}")
    name = _html.unescape(title.group(1).split(" : ")[-1]).strip()
    text = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))
    ver = re.search(r"Version:\s*(\S+)", text)
    author = re.search(r"(?:Author|Uploaded By):\s*(.+?)\s*\[", text)
    cat = re.search(r"Category\s*:\s*(.+?)\s+" + re.escape(name), text)
    date = re.search(r"Date:\s*(\d\d-\d\d-\d{4} \d\d?:\d\d [AP]M)", text)
    try:
        updated = int(time.mktime(time.strptime(date.group(1), "%m-%d-%Y %I:%M %p"))) if date else 0
    except ValueError:
        updated = 0
    desc = ""
    dm = re.search(r"<b>Description</b>.*?</div>\s*</div>\s*<div[^>]*>(.*?)(?:<div class=\"thead\"|$)", page, re.S)
    if dm:
        body = re.sub(r"<br\s*/?>", "\n", re.sub(r"\s*\n\s*", " ", dm.group(1)))
        desc = _html.unescape(re.sub(r"<[^>]+>", "", body))
        desc = re.split(r"\s*Archive List \(Old Versions\)|\s*File Statistics", desc)[0]
        desc = re.sub(r"\n{3,}", "\n\n", desc).strip()
    return RemoteAddon(id=addon_id, kind=kind, name=name, author=author.group(1).strip() if author else "",
                       version=ver.group(1) if ver else "", updated=updated, downloads=0,
                       category=cat.group(1).strip() if cat else "", description=desc[:20000], file=f"{addon_id}.zip",
                       size=0, url=DOWNLOAD_URL.format(id=addon_id))


def addon_from_link(text: str, kind: str) -> RemoteAddon:
    """Look up any lotrointerface addon by link or id (for addons that aren't in the curated lists)."""
    addon_id = parse_link(text)
    if not addon_id:
        raise AddonError("That doesn't look like a lotrointerface.com link or addon number.")
    try:
        r = requests.get(INFO_URL.format(id=addon_id), timeout=30, headers={"User-Agent": "Mozilla/5.0 Mithlond"})
        r.raise_for_status()
    except requests.RequestException as e:
        raise AddonError(f"Could not open lotrointerface.com: {e}") from e
    return parse_info_page(addon_id, r.text, kind)


def local_addon(path: Path, kind: str) -> RemoteAddon:
    """A RemoteAddon stand-in for installing an archive from disk."""
    return RemoteAddon(id=f"local-{re.sub(r'[^\w]+', '_', path.stem)}", kind=kind, name=path.stem, author="",
                       version="", updated=int(path.stat().st_mtime), downloads=0, category="Local file",
                       description="", file=path.name, size=path.stat().st_size, url=path.as_uri())


def dependencies_of(files: list[str], target: Path) -> list[str]:
    deps = []
    for f in files:
        if f.lower().endswith(".plugincompendium"):
            root = _xml(target / f)
            if root is not None:
                deps += [(d.text or "").strip() for d in root.iter() if d.tag.lower() == "dependency" and d.text]
    return [d for d in deps if d and d != "0"]


def to_dict(a) -> dict:
    return asdict(a)
