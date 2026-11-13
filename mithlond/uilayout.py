"""The game's saved interface layouts: <documents>/ui/layouts/<name>.layout, written by `/ui layout save <name>` and
applied in game with `/ui layout load <name>`.

A layout file has three parts: window positions and sizes (fractions of the screen), interface options, and chat
colors/font sizes per message type. Saving rewrites only the changed tags in place, so everything else in the
file (order, spacing, CRLF line endings, sections Mithlond doesn't know) stays exactly as the game wrote it.
"""

from __future__ import annotations

import re
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

SUFFIX = ".layout"
BACKUP_DIR = ".mithlond-backups"


@dataclass
class Window:
    id: str
    group: str
    x: float
    y: float
    w: float
    h: float

    @property
    def name(self) -> str:
        return pretty_window(self.id)

    @property
    def core(self) -> bool:
        return self.id in CORE_WINDOWS or self.id.startswith("NewChatWindow")

    @property
    def hud(self) -> bool:
        """Always-on-screen parts of the interface (shown on the canvas by default)."""
        i = self.id.lower()
        return i.startswith(("gameplay", "gp_")) or i.startswith(("avatarpanel", "opponentpanel", "newchatwindow",
                                                                   "radar", "toolbar", "vitals"))


# Shown on the canvas by default: what's on screen while playing.
CORE_WINDOWS = {
    "AvatarPanel", "OpponentPanel", "GamePlay_SelectionTarget", "GamePlay_Radar", "GamePlay_RadarBox",
    "GamePlay_QuestTrackerBox", "GamePlay_Undocked_ShiftBar", "GamePlay_Undocked_CtrlBar", "GamePlay_Undocked_AltBar",
    "GamePlay_Undocked_ExtraShortcutBar1", "GamePlay_Undocked_ExtraShortcutBar2", "GamePlay_PetShortcutBar",
    "GamePlay_ItemRollBox", "GamePlay_AlertField", "GamePlay_ProgressBar_Dragbox",
    "GamePlay_Opponent_ProgressBar_Dragbox", "FellowMiniPanel_1", "FellowMiniPanel_2", "FellowMiniPanel_3",
    "FellowMiniPanel_4", *(f"PlayerBag{i}_Template" for i in range(1, 7)),
}


@dataclass
class ChatFont:
    type: str
    color: tuple[float, float, float, float]
    size: str


@dataclass
class Layout:
    path: Path
    windows: list[Window] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)
    chat: list[ChatFont] = field(default_factory=list)


# ---- files ----------------------------------------------------------------------------------------------
def layouts_dir(docs: Path) -> Path:
    return docs / "ui" / "layouts"


def list_layouts(docs: Path) -> list[Path]:
    d = layouts_dir(docs)
    return sorted(d.glob(f"*{SUFFIX}"), key=lambda p: p.name.lower()) if d.is_dir() else []


def valid_name(name: str) -> bool:
    """The name typed after `/ui layout load`: letters, digits, - and _."""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name))


def backup(path: Path, why: str = "") -> Path:
    d = path.parent / BACKUP_DIR
    d.mkdir(exist_ok=True)
    b = d / f"{path.stem}.{time.strftime('%Y-%m-%d-%H%M%S')}{('-' + why) if why else ''}{SUFFIX}"
    shutil.copy2(path, b)
    for old in sorted(d.glob(f"{path.stem}.*{SUFFIX}"))[:-10]:  # keep the last ten per layout
        old.unlink(missing_ok=True)
    return b


def latest_backup(path: Path) -> Path | None:
    d = path.parent / BACKUP_DIR
    found = sorted(d.glob(f"{path.stem}.20*{SUFFIX}")) if d.is_dir() else []
    return found[-1] if found else None


def copy_layout(src: Path, name: str) -> Path:
    dst = src.with_name(name + SUFFIX)
    if dst.exists():
        raise FileExistsError(f"{dst.name} already exists")
    shutil.copy2(src, dst)
    return dst


def rename_layout(src: Path, name: str) -> Path:
    dst = src.with_name(name + SUFFIX)
    if dst.exists():
        raise FileExistsError(f"{dst.name} already exists")
    src.rename(dst)
    return dst


def delete_layout(path: Path) -> Path:
    """Moves the file into the backup folder (so it can be recovered) instead of deleting it."""
    b = backup(path, "deleted")
    path.unlink()
    return b


# ---- reading ----------------------------------------------------------------------------------------------
def _color(text: str) -> tuple[float, float, float, float]:
    parts = [float(p) for p in text.split()] + [1.0] * 4
    return tuple(parts[:4])  # type: ignore[return-value]


def read(path: Path) -> Layout:
    root = ET.fromstring(path.read_bytes())
    lay = Layout(path)
    for group in root.iter("Layout"):
        for e in group.iter("Element"):
            try:
                lay.windows.append(Window(e.get("ID", ""), group.get("ID", ""), float(e.get("X", 0)),
                                          float(e.get("Y", 0)), float(e.get("Width", 0)), float(e.get("Height", 0))))
            except ValueError:
                continue
    opts = root.find("Options")
    if opts is not None:
        lay.options = {o.get("Name"): o.get("Value", "") for o in opts.iter("Option") if o.get("Name")}
    chat = root.find("ChatColors")
    if chat is not None:
        lay.chat = [ChatFont(c.get("TextType", ""), _color(c.get("Color", "1 1 1 1")), c.get("Size", "Medium"))
                    for c in chat.iter("ChatFont") if c.get("TextType")]
    return lay


# ---- saving ------------------------------------------------------------------------------------------------
def _decimals(old: str, default: int) -> int:
    m = re.search(r"\.(\d+)", old)
    return len(m.group(1)) if m else default


def _set_attr(tag: str, attr: str, value: str) -> str:
    return re.sub(rf'(\b{attr}=")[^"]*(")', lambda m: m.group(1) + value + m.group(2), tag, count=1)


def color_text(c: tuple[float, float, float, float]) -> str:
    return " ".join(f"{v:.3f}" for v in c)


def save(original: Layout, edited: Layout) -> Path | None:
    """Write the differences between `original` and `edited` into the file (backup first). Returns the backup."""
    path = edited.path
    text = path.read_bytes().decode("utf-8", errors="surrogateescape")
    changed = 0
    old_w = {w.id: w for w in original.windows}
    for w in edited.windows:
        o = old_w.get(w.id)
        if o and (o.x, o.y, o.w, o.h) == (w.x, w.y, w.w, w.h):
            continue
        pat = re.compile(rf'<Element\b[^>]*\bID="{re.escape(w.id)}"[^>]*/>')

        def fix(m, w=w):
            tag = m.group(0)
            for attr, val in (("X", w.x), ("Y", w.y), ("Width", w.w), ("Height", w.h)):
                old = re.search(rf'\b{attr}="([^"]*)"', tag)
                tag = _set_attr(tag, attr, f"{val:.{_decimals(old.group(1) if old else '', 6)}f}")
            return tag
        text, n = pat.subn(fix, text, count=1)
        changed += n
    for name, value in edited.options.items():
        if original.options.get(name) == value:
            continue
        pat = re.compile(rf'<Option\b[^>]*\bName="{re.escape(name)}"[^>]*/>')
        text, n = pat.subn(lambda m: _set_attr(m.group(0), "Value", value), text, count=1)
        changed += n
    old_c = {c.type: c for c in original.chat}
    for c in edited.chat:
        o = old_c.get(c.type)
        if o and o.color == c.color and o.size == c.size:
            continue
        pat = re.compile(rf'<ChatFont\b[^>]*\bTextType="{re.escape(c.type)}"[^>]*/>')
        text, n = pat.subn(lambda m, c=c: _set_attr(_set_attr(m.group(0), "Color", color_text(c.color)),
                                                      "Size", c.size), text, count=1)
        changed += n
    if not changed:
        return None
    b = backup(path)
    path.write_bytes(text.encode("utf-8", errors="surrogateescape"))
    return b


# ---- names and groups -----------------------------------------------------------------------------------
def _words(s: str) -> str:
    s = re.sub(r"[_]+", " ", s)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return re.sub(r"\s+", " ", s).strip()


WINDOW_NAMES = {
    "AvatarPanel": "Your vitals", "OpponentPanel": "Target", "GamePlay_SelectionTarget": "Selection target",
    "GamePlay_Radar": "Minimap", "GamePlay_RadarBox": "Minimap frame", "GamePlay_Undocked_ShiftBar": "Quickslot bar (Shift)",
    "GamePlay_Undocked_CtrlBar": "Quickslot bar (Ctrl)", "GamePlay_Undocked_AltBar": "Quickslot bar (Alt)",
    "GamePlay_Undocked_ExtraShortcutBar1": "Extra quickslot bar 1", "GamePlay_Undocked_ExtraShortcutBar2":
    "Extra quickslot bar 2", "GamePlay_PetShortcutBar": "Pet quickslot bar", "GamePlay_ProgressBar_Dragbox":
    "Casting bar", "GamePlay_Opponent_ProgressBar_Dragbox": "Target casting bar", "GamePlay_ItemRollBox": "Loot rolls",
    "GamePlay_AlertField": "Alerts", "GamePlay_ErrorSpewBoxBox": "Error messages", "GamePlay_RaidShoutSpewBoxBox":
    "Raid warnings", "GamePlay_GlobalBroadcastSpewBoxBox": "Server announcements", "MapPanel": "World map",
    "GamePlay_FrameRateDisplayDragBox": "Frame rate display", "Gameplay_ConnectionStatus": "Connection status",
}


def pretty_window(wid: str) -> str:
    """'GamePlay_QuestTrackerBox' -> 'Quest Tracker', 'NewChatWindow1' -> 'Chat Window 1'."""
    if wid in WINDOW_NAMES:
        return WINDOW_NAMES[wid]
    m = re.fullmatch(r"PlayerBag(\d)_Template", wid)
    if m:
        return f"Bag {m.group(1)}"
    m = re.fullmatch(r"FellowMiniPanel_(\d)", wid)
    if m:
        return f"Fellowship member {m.group(1)}"
    s = re.sub(r"^(GamePlay|Gameplay|GP)_", "", wid)
    s = re.sub(r"(_?Window|Box|_MainField|_Dragbox|_Activatable|Panel)$", lambda m: "" if "Panel" not in m.group(0)
               else " Panel", s)
    s = s.replace("NewChatWindow", "Chat Window ")
    out = _words(s)
    return out or wid


def pretty_option(name: str) -> str:
    return _words(name).replace("UI Scale", "scale").replace("UI Toggle", "shown")


OPTION_GROUPS = [
    ("Social", ("Accept", "Allow", "Friend", "Kinship", "Fellowship", "Duel", "Trade", "Invite", "Adopt", "Emote")),
    ("Chat", ("Chat", "IMTab", "Tell")),
    ("Scale", ("UIScale",)),
    ("Toolbars", ("Toolbar", "Quickslot", "Shortcut", "Bar")),
    ("Show/hide", ("Show", "Hide", "Toggle", "Display", "Visible")),
]


def option_group(name: str) -> str:
    for group, keys in OPTION_GROUPS:
        if any(k.lower() in name.lower() for k in keys):
            return group
    return "Other"


CHAT_GROUPS = {
    "Combat": {"CombatEnemy", "CombatPlayer", "Death"},
    "Game messages": {"Admin", "Advancement", "Error", "EventBroadcast", "Loot", "FellowLoot", "Narration", "Quest",
                      "Standard", "Log", "Leaderboard"},
}


def chat_group(text_type: str) -> str:
    for group, types in CHAT_GROUPS.items():
        if text_type in types:
            return group
    return "Social"


CHAT_NAMES = {"Guild": "Kinship", "GuildMP": "Kinship (monster play)", "Auction": "Trade", "FRAuction": "Trade (FR)",
              "DEAuction": "Trade (DE)", "FRWorld": "World (FR)", "DEWorld": "World (DE)", "OOC": "Out of character",
              "RP": "Role-play", "LFG": "Looking for group", "CombatEnemy": "Combat (enemies)",
              "CombatPlayer": "Combat (you)", "FellowLoot": "Fellowship loot", "Standard": "Standard (system)"}


def pretty_chat(text_type: str) -> str:
    if text_type in CHAT_NAMES:
        return CHAT_NAMES[text_type]
    m = re.fullmatch(r"UserChat(\d)", text_type)
    if m:
        return f"User channel {m.group(1)}"
    m = re.fullmatch(r"Localized(\d)", text_type)
    if m:
        return f"Regional channel {m.group(1)}"
    return _words(text_type)


CHAT_SIZES = ["Small", "Medium", "Large", "XLarge"]
