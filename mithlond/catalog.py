"""The complete lotrointerface.com LOTRO catalogue, read from the site's category listings.

lotrointerface has no API for its full catalogue (the MMOUI API only serves WoW and ESO, and the
api.lotrointerface.com XML files are curated lists). The download section's category pages list
every addon (25 per page) with name, author, size, downloads and last-update date; versions and
descriptions are only on each addon's own page and are fetched when needed (addons.addon_from_link).
About 70 pages; cached for a day.
"""

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Callable

import requests

from .config import CACHE_DIR

BASE = "https://www.lotrointerface.com/downloads/"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Mithlond-LOTRO-Launcher"}
CACHE = CACHE_DIR / "catalog.json"
TTL = 24 * 3600
DELAY = 0.3  # between requests; be gentle with a community site
OUTDATED = "Outdated LotRO Interfaces"
# Categories whose addons are skins (UI graphics) rather than Lua plugins.
SKIN_CATEGORIES = {"LotRO Complete Sets", "LotRO Compilations", "LotRO Beta Interfaces",
                   "Graphical Modifications (Skins)", "Unit Frames (Character, Fellowship, Target)",
                   "Action Bars & Main Bar"}


class CatalogError(Exception):
    pass


@dataclass
class Entry:
    id: str
    name: str
    category: str
    author: str
    size: int  # bytes
    downloads: int
    updated: int  # unix time

    @property
    def outdated(self) -> bool:
        return self.category == OUTDATED


def _size(text: str) -> int:
    m = re.match(r"([\d.,]+)\s*(KB|MB|GB|B)", text.strip(), re.I)
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}[m.group(2).lower()])


def parse_categories(page: str) -> list[tuple[str, str]]:
    """(id, name) of LOTRO categories in page order; DDO's start at 'DDO Complete Sets' and are skipped."""
    found: dict[str, str] = {}
    pat = r'href="(?:index\.php\?[^"]*?cid=(\d+)&amp;dp=0[^"]*|cat(\d+)\.html)"[^>]*>(.*?)</a>'
    for a, b, inner in re.findall(pat, page, re.S):
        name = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if name:
            found.setdefault(a or b, name)
    out = []
    for cid, name in found.items():
        if name.startswith("DDO"):
            break  # everything after this heading belongs to Dungeons & Dragons Online
        out.append((cid, name))
    return out


def parse_listing(page: str, category: str) -> tuple[list[Entry], int, int]:
    """Entries on one category page, plus (page, pages)."""
    entries = []
    for row in re.split(r"<tr[ >]", page):
        m = re.search(r'href="(?:fileinfo\.php\?[^"]*?id=|info)(\d+)[^"]*"[^>]*>\s*([^<]+?)\s*</a>', row)
        if not m:
            continue
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r'<div class="smallfont">(.*?)</div>', row, re.S)]
        date = re.search(r"(\d\d-\d\d-\d{4})\s*(?:<[^>]+>\s*)*(\d\d?:\d\d [AP]M)", row)
        try:
            updated = int(time.mktime(time.strptime(f"{date.group(1)} {date.group(2)}", "%m-%d-%Y %I:%M %p"))) \
                if date else 0
        except ValueError:
            updated = 0
        downloads = next((int(c.replace(",", "")) for c in cells[1:4] if c.replace(",", "").isdigit()), 0)
        entries.append(Entry(m.group(1), html.unescape(m.group(2)), category, cells[0] if cells else "",
                             _size(cells[1]) if len(cells) > 1 else 0, downloads, updated))
    pm = re.search(r"Page (\d+) of (\d+)", page)
    return entries, int(pm.group(1)) if pm else 1, int(pm.group(2)) if pm else 1


def crawl(progress: Callable[[str], None] | None = None) -> list[Entry]:
    s = requests.Session()
    s.headers.update(UA)

    def get(url: str) -> str:
        time.sleep(DELAY)
        try:
            r = s.get(url, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            raise CatalogError(f"lotrointerface.com: {e}") from e
        return r.text

    cats = parse_categories(get(BASE + "index.php"))
    if not cats:
        raise CatalogError("Couldn't read lotrointerface.com's category list (the site layout may have changed).")
    seen_cats = {c for c, _ in cats}
    entries: dict[str, Entry] = {}
    queue = list(cats)
    while queue:
        cid, name = queue.pop(0)
        page = 1
        while True:
            if progress:
                progress(f"Reading lotrointerface.com: {name} (page {page})")
            text = get(BASE + f"index.php?cid={cid}&sb=lastupdate&so=desc&sh=full&pt=f&page={page}")
            rows, cur, total = parse_listing(text, name)
            for e in rows:
                entries.setdefault(e.id, e)
            if page == 1:  # sub-categories (e.g. Class Specific → Burglar, Captain, …)
                for sub_id, sub_name in parse_categories(text):
                    if sub_id not in seen_cats:
                        seen_cats.add(sub_id)
                        queue.append((sub_id, sub_name))
            if cur >= total:
                break
            page += 1
    if not entries:
        raise CatalogError("lotrointerface.com's listings had no addons (the site layout may have changed).")
    return list(entries.values())


def load(force: bool = False, progress: Callable[[str], None] | None = None) -> list[Entry]:
    """The catalogue, from a day-old cache when possible; a stale cache is used if the site can't be read."""
    if not force and CACHE.exists() and time.time() - CACHE.stat().st_mtime < TTL:
        try:
            return [Entry(**e) for e in json.loads(CACHE.read_text())]
        except (ValueError, TypeError):
            pass
    try:
        entries = crawl(progress)
    except CatalogError:
        if CACHE.exists():
            return [Entry(**e) for e in json.loads(CACHE.read_text())]
        raise
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps([asdict(e) for e in entries]))
    return entries
