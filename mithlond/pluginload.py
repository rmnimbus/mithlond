"""Which plugins the game loads for which characters, named sets of those choices, and plugin errors.

The game keeps one PluginOptions.xml per account and server: <documents>/PluginData/<account>/<server>/.
Its <AutoloadOptions> lists each auto-loaded plugin by the <Name> in its .plugin file, either for all
characters or for named ones:

    <Plugin AllCharacters="true" Name="Wallet"/>
    <Plugin AllCharacters="false" Name="MinstrelBuff II">
      <Character Name="Realmonster"/>
    </Plugin>

Other sections (<ScalingOptions>…) are left exactly as they are. Characters are known from their PluginData
folders (made the first time a character loads a plugin on this computer), from this file, and from names the
user adds."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import quoteattr

from .config import CONFIG_DIR
from .gameprefs import backup  # same backup scheme as UserPreferences.ini

FILE = "PluginOptions.xml"
SETS_FILE = CONFIG_DIR / "plugin-sets.json"
_HELPER = re.compile(r"do not (set this plugin to )?auto-?load|used internally", re.I)


@dataclass
class Loadable:
    """One .plugin file: what the game's plugin manager lists and loads."""
    name: str            # <Information><Name>, the key in PluginOptions.xml
    author: str = ""
    version: str = ""
    description: str = ""
    descriptor: str = ""  # path relative to Plugins/
    package: str = ""     # installed addon it belongs to (from the Get plugins list)

    @property
    def helper(self) -> bool:
        """Part of another plugin that must not be auto-loaded (its description says so)."""
        return bool(_HELPER.search(self.description))


@dataclass
class Autoload:
    all: bool = False
    characters: list[str] = field(default_factory=list)

    def label(self) -> str:
        if self.all:
            return "All characters"
        if not self.characters:
            return "Not loaded"
        if len(self.characters) == 1:
            return self.characters[0]
        return f"Multiple characters ({len(self.characters)})"

    def to_json(self) -> dict:
        return {"all": self.all, "characters": list(self.characters)}

    @classmethod
    def from_json(cls, d: dict) -> "Autoload":
        return cls(bool(d.get("all")), [str(c) for c in d.get("characters", [])])


# ---- installed plugins ----------------------------------------------------------------------------
def _text(node, tag: str) -> str:
    if node is None:
        return ""
    for child in node:
        if child.tag.lower() == tag.lower():
            return (child.text or "").strip()
    return ""


def loadables(plugins_dir: Path, packages: dict[str, str] | None = None) -> list[Loadable]:
    """Every .plugin under Plugins/. `packages` maps a descriptor path (relative, lower case) to the name
    of the installed addon it came with."""
    out = []
    if not plugins_dir or not plugins_dir.is_dir():
        return out
    for f in sorted(plugins_dir.rglob("*.plugin")):
        try:
            root = ET.parse(f).getroot()
        except (ET.ParseError, OSError):
            continue
        info = next((c for c in root if c.tag.lower() == "information"), None)
        rel = f.relative_to(plugins_dir).as_posix()
        out.append(Loadable(name=_text(info, "Name") or f.stem, author=_text(info, "Author"),
                            version=_text(info, "Version"), description=_text(info, "Description"),
                            descriptor=rel, package=(packages or {}).get(rel.lower(), "")))
    return out


# ---- accounts, servers, characters ----------------------------------------------------------------
def servers(plugindata: Path | None) -> list[tuple[str, str]]:
    """(account, server) folders in PluginData."""
    out = []
    if not plugindata or not plugindata.is_dir():
        return out
    for acc in sorted(p for p in plugindata.iterdir() if p.is_dir()):
        for srv in sorted(p for p in acc.iterdir() if p.is_dir() and p.name != "AllServers"):
            out.append((acc.name, srv.name))
    return out


def characters(folder: Path, autoload: dict[str, Autoload] | None = None, extra: list[str] = ()) -> list[str]:
    """Characters known for one account/server folder: their PluginData folders, names in PluginOptions.xml
    and names added by the user."""
    names = {p.name for p in folder.iterdir() if p.is_dir() and p.name != "AllCharacters"} if folder.is_dir() else set()
    for a in (autoload or {}).values():
        names.update(a.characters)
    names.update(extra)
    return sorted(names, key=str.lower)


# ---- PluginOptions.xml ----------------------------------------------------------------------------
def read(path: Path) -> dict[str, Autoload]:
    """Plugin name -> Autoload, in file order. A missing or unreadable file means nothing auto-loads."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return {}
    out: dict[str, Autoload] = {}
    for p in root.findall("./AutoloadOptions/Plugin"):
        name = p.get("Name")
        if name:
            out[name] = Autoload(p.get("AllCharacters", "").lower() == "true",
                                 [c.get("Name") for c in p.findall("Character") if c.get("Name")])
    return out


def render_autoload(autoload: dict[str, Autoload]) -> str:
    entries = [(n, a) for n, a in autoload.items() if a.all or a.characters]
    if not entries:
        return "  <AutoloadOptions/>"
    lines = ["  <AutoloadOptions>"]
    for name, a in entries:
        head = f"    <Plugin AllCharacters={quoteattr('true' if a.all else 'false')} Name={quoteattr(name)}"
        if a.all or not a.characters:
            lines.append(head + "/>")
        else:
            lines.append(head + ">")
            lines += [f"      <Character Name={quoteattr(c)}/>" for c in a.characters]
            lines.append("    </Plugin>")
    lines.append("  </AutoloadOptions>")
    return "\n".join(lines)


_BLOCK = re.compile(r"[ \t]*<AutoloadOptions\s*/>|[ \t]*<AutoloadOptions>.*?</AutoloadOptions>", re.S)


def render(original: str, autoload: dict[str, Autoload]) -> str:
    """The file with only its <AutoloadOptions> block replaced (or a new file in the game's own layout)."""
    block = render_autoload(autoload)
    if original and _BLOCK.search(original):
        return _BLOCK.sub(lambda _m: block, original, count=1)
    if original and "</PluginOptions>" in original:
        return original.replace("</PluginOptions>", f"{block}\n\n</PluginOptions>", 1)
    return f'<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n<PluginOptions>\n\n{block}\n\n</PluginOptions>\n'


def save(path: Path, autoload: dict[str, Autoload]) -> Path | None:
    """Write the autoload choices (backing up the current file first). Returns the backup, if any."""
    original = path.read_bytes().decode("utf-8", errors="replace") if path.exists() else ""
    crlf = "\r\n" in original  # the game writes CRLF; keep whatever the file uses
    text = render(original.replace("\r\n", "\n"), autoload)
    if crlf:
        text = text.replace("\n", "\r\n")
    b = backup(path) if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)
    return b


# ---- named sets -----------------------------------------------------------------------------------
def load_sets() -> dict[str, dict[str, Autoload]]:
    try:
        raw = json.loads(SETS_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return {name: {p: Autoload.from_json(a) for p, a in entries.items()}
            for name, entries in raw.items() if isinstance(entries, dict)}


def save_sets(sets: dict[str, dict[str, Autoload]]) -> None:
    SETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({n: {p: a.to_json() for p, a in e.items() if a.all or a.characters}
                               for n, e in sets.items()}, indent=2))
    tmp.replace(SETS_FILE)


# ---- plugin errors (Script.log) -------------------------------------------------------------------
@dataclass
class ScriptError:
    plugin: str   # folder under Plugins/ the error points at ("" if none)
    text: str


_PLUGIN_PATH = re.compile(r"Plugins[\\/]+([^\\/:]+)", re.I)


def script_errors(path: Path) -> list[ScriptError]:
    """The Lua errors the game wrote to Script.log, one entry per error (continuation lines joined)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[ScriptError] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line[:1].isspace() and out:  # stack traceback lines belong to the previous error
            out[-1].text += "\n" + line.rstrip()
            continue
        m = _PLUGIN_PATH.search(line)
        out.append(ScriptError(m[1] if m else "", line.rstrip()))
    return out
