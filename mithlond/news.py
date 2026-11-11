"""The official launcher news feed (lotro.com), including the current sale and weekly coupon code."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

import requests

from .config import CACHE_DIR

DEFAULT_FEED = "https://www.lotro.com/{lang}/launcher-feed.xml"
LANG_CODES = {"english": "en", "de": "de", "deutsch": "de", "german": "de", "fr": "fr", "french": "fr"}


@dataclass
class NewsItem:
    title: str
    link: str
    html: str  # sanitized
    text: str  # plain text
    date: str  # "Nov 05, 2026" or ""


@dataclass
class Coupon:
    code: str
    item: str
    until: str
    sale: str  # title of the sales post
    link: str


def feed_url(launcher_cfg: dict[str, str] | None, language: str) -> str:
    template = (launcher_cfg or {}).get("URL.NewsFeed") or DEFAULT_FEED
    return template.replace("{lang}", LANG_CODES.get(language.lower(), "en"))


# ---- sanitizing ------------------------------------------------------------------

class _Sanitizer(HTMLParser):
    """Keep simple formatting and http(s) links; drop everything else (scripts, images, styles, attributes)."""

    KEEP = {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "a", "h3", "h4"}
    VOID = {"br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.text: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
            return
        if tag in ("br", "p", "li") and self.text and not self.text[-1].endswith("\n"):
            self.text.append("\n")
        if tag not in self.KEEP:
            return
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.startswith(("https://", "http://")):
                self.out.append(f'<a href="{html.escape(href, quote=True)}">')
            else:
                self.out.append("<a>")
        else:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if tag == "p":
            self.text.append("\n")
        if tag in self.KEEP and tag not in self.VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip:
            return
        self.out.append(html.escape(data))
        self.text.append(data)


def sanitize(fragment: str) -> tuple[str, str]:
    p = _Sanitizer()
    p.feed(fragment)
    p.close()
    text = re.sub(r"[ \t\xa0]+", " ", "".join(p.text))
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return "".join(p.out).strip(), text


# ---- parsing ---------------------------------------------------------------------

def parse_feed(xml_bytes: bytes) -> list[NewsItem]:
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip()).replace("\xa0", " ").strip()
        link = (it.findtext("link") or "").strip()
        body_html, body_text = sanitize(it.findtext("description") or "")
        date = ""
        if pd := it.findtext("pubDate"):
            try:
                date = parsedate_to_datetime(pd).strftime("%b %d, %Y")
            except (TypeError, ValueError):
                date = ""
        items.append(NewsItem(title, link if link.startswith(("https://", "http://")) else "", body_html, body_text,
                              date))
    return items


_CODE = re.compile(r"coupon\s*code\s*:?\s*([A-Z0-9][A-Z0-9_-]{2,})", re.I)


def find_coupon(items: list[NewsItem]) -> Coupon | None:
    """The newest coupon code in the feed. Sales posts look like:
    'Weekly Coupon:' / '<item>' / 'Coupon Code: WARMFEELING' / 'Now through November 12th!'"""
    for it in items:
        lines = it.text.splitlines()
        for i, line in enumerate(lines):
            m = _CODE.search(line)
            if not m:
                continue
            prev = lines[i - 1].strip() if i > 0 else ""
            item = "" if prev.lower().rstrip(":").endswith("coupon") else prev
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            until = nxt if re.match(r"(now )?(through|until|thru|ends)", nxt, re.I) else ""
            return Coupon(m.group(1).upper(), item, until, it.title, it.link)
    return None


def fetch(url: str) -> tuple[list[NewsItem], bool]:
    """Returns (items, from_cache). Falls back to the last good copy when offline."""
    cache = CACHE_DIR / ("news-" + re.sub(r"[^\w.-]+", "_", url)[-80:])
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Mithlond"})
        r.raise_for_status()
        items = parse_feed(r.content)
    except (requests.RequestException, ET.ParseError):
        if cache.exists():
            return parse_feed(cache.read_bytes()), True
        raise
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(r.content)
    return items, False
