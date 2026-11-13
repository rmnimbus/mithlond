"""The game's key bindings (<documents>/lotro.keymap).

The file is plain text. After a comment header come `Devices`, `MetaKeys` (modifier keys, numbered 1–32) and
`Bindings`, which holds one block per context (Main, MapPanel, MusicUI…) with one line per binding:

    QUICKSLOT_18 [ User [ 0 DIK_Q ] 0x00000001 ]
    action        kind   dev key    meta-key mask (bit n-1 = meta key n held; 1 = Shift on a default file)

`Old` lines are the game's defaults, `User` lines were changed by the player; `DoNothing` blocks a key.
Editing keeps every line that wasn't changed exactly as it was, so the game reads the file the same way."""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

# indent, action, kind, device, key, axis (wheel/stick direction), mask, trigger (Tap, Up/Tap, MouseDblClick…)
_BINDING = re.compile(r"^(\s+)(\S+) \[ (\w+) \[ (\d+) (\S+)(?: (\w+))? \](?: (0x[0-9A-Fa-f]+))?(?: (\S+))? \]\s*$")
_CONTEXT = re.compile(r"^  (\w+)\s*$")
NOTHING = "DoNothing"
KEYBOARD, MOUSE = 0, 1


@dataclass(frozen=True)
class Binding:
    context: str
    action: str
    kind: str          # "Old" (game default) or "User"
    device: int
    key: str           # DIK_* (keyboard), DIMOFS_* (mouse), …
    mask: int = 0      # meta keys held: bit (n-1) for meta key n
    axis: str = ""     # AxisPositive/AxisNegative for the mouse wheel and sticks
    trigger: str = ""  # when it fires: "" (press), Tap, Up/Tap, MouseDblClick…

    def text(self, indent: str = "    ") -> str:
        key = f"{self.key} {self.axis}" if self.axis else self.key
        m = f" 0x{self.mask:08X}" if self.mask or self.trigger else ""
        t = f" {self.trigger}" if self.trigger else ""
        return f"{indent}{self.action} [ {self.kind} [ {self.device} {key} ]{m}{t} ]"

    def chord(self) -> tuple:
        return self.context, self.device, self.key, self.axis, self.mask, self.trigger


@dataclass
class Keymap:
    lines: list[str]
    bindings: list[Binding]
    origin: list[int | None]                 # line index of each binding (None = added)
    context_end: dict[str, int]               # line index of each context's closing "  ]"
    meta: dict[int, list[tuple[int, str]]] = field(default_factory=dict)  # meta key n -> [(device, key)]
    binding_lines: set[int] = field(default_factory=set)  # every line that holds a binding in the file
    newline: str = "\n"                                   # the game writes CRLF; kept as found

    # ---- reading ---------------------------------------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> "Keymap":
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines()
        bindings, origin, ends, meta = [], [], {}, {}
        section, context = "", None
        for i, line in enumerate(lines):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if not line[0].isspace() and s not in ("[", "]"):
                section, context = s, None
                continue
            if section == "MetaKeys":
                m = re.match(r"^\s*(\d+) \[ (\d+) (\S+) \]", line)
                if m:
                    meta.setdefault(int(m[1]), []).append((int(m[2]), m[3]))
            elif section == "Bindings":
                m = _BINDING.match(line)
                if m and context:
                    bindings.append(_binding(context, m))
                    origin.append(i)
                elif _CONTEXT.match(line):
                    context = _CONTEXT.match(line)[1]
                elif s == "]" and line.startswith("  ]") and context:
                    ends[context] = i
                    context = None
        return cls(lines, bindings, origin, ends, meta, set(origin), newline)

    @classmethod
    def load(cls, path: Path) -> "Keymap":
        return cls.parse(path.read_bytes().decode("utf-8", errors="replace"))

    # ---- writing ---------------------------------------------------------------------------------
    def render(self) -> str:
        by_line = {ln: b for b, ln in zip(self.bindings, self.origin) if ln is not None}
        added: dict[str, list[Binding]] = {}
        for b, ln in zip(self.bindings, self.origin):
            if ln is None:
                added.setdefault(b.context, []).append(b)
        ends = {v: k for k, v in self.context_end.items()}
        out = []
        for i, line in enumerate(self.lines):
            if i in self.binding_lines:
                b = by_line.get(i)
                if b is not None:  # (a removed binding has no entry: its line is left out)
                    out.append(line if _same_line(line, b) else b.text(_BINDING.match(line)[1]))
                continue
            if i in ends:
                out += [b.text() for b in added.get(ends[i], [])]
            out.append(line)
        return self.newline.join(out) + self.newline

    # ---- editing ---------------------------------------------------------------------------------
    def contexts(self) -> list[str]:
        """Contexts that have a [ ] block (empty ones like MapPanel can't take new bindings)."""
        return list(self.context_end)

    def actions(self) -> list[tuple[str, str]]:
        """(context, action) pairs that have a binding, in file order."""
        seen, out = set(), []
        for b in self.bindings:
            if b.action != NOTHING and (b.context, b.action) not in seen:
                seen.add((b.context, b.action))
                out.append((b.context, b.action))
        return out

    def set_binding(self, index: int, device: int, key: str, mask: int) -> None:
        old = self.bindings[index]
        self.bindings[index] = replace(old, kind="User", device=device, key=key, mask=mask, axis="",
                                       trigger=old.trigger if device == MOUSE == old.device else "")

    def add_binding(self, context: str, action: str, device: int, key: str, mask: int) -> int:
        self.bindings.append(Binding(context, action, "User", device, key, mask))
        self.origin.append(None)
        return len(self.bindings) - 1

    def remove_binding(self, index: int) -> None:
        del self.bindings[index]
        del self.origin[index]

    def conflicts(self) -> set[int]:
        """Indexes of bindings whose key (with the same modifiers) also runs another action in the same context."""
        groups: dict[tuple, list[int]] = {}
        for i, b in enumerate(self.bindings):
            if b.action != NOTHING:
                groups.setdefault(b.chord(), []).append(i)
        out: set[int] = set()
        for idxs in groups.values():
            if len({self.bindings[i].action for i in idxs}) > 1:
                out.update(idxs)
        return out

    # ---- display ---------------------------------------------------------------------------------
    def meta_name(self, n: int) -> str:
        keys = self.meta.get(n, [])
        if keys:
            names = {key_name(d, k) for d, k in keys}
            for word in ("Shift", "Ctrl", "Alt", "Win"):
                if names and all(word in x for x in names):
                    return word
            return " / ".join(sorted(names))
        return f"Meta {n}"

    def chord_name(self, b: Binding) -> str:
        mods = [self.meta_name(n) for n in range(1, 33) if b.mask & (1 << (n - 1))]
        name = "+".join(mods + [key_name(b.device, b.key)])
        if b.axis:
            name += {"AxisPositive": " up", "AxisNegative": " down"}.get(b.axis, f" {b.axis}")
        if b.trigger:
            name += {"Tap": " (click)", "Up/Tap": " (release)", "MouseDblClick": " (double-click)"}.get(
                b.trigger, f" ({b.trigger})")
        return name

    def mask_for(self, names: set[str]) -> int:
        """Meta-key mask for modifier names like {"Shift", "Ctrl"} (as this file defines them)."""
        mask = 0
        for n in self.meta:
            if self.meta_name(n) in names:
                mask |= 1 << (n - 1)
        return mask


def _binding(context: str, m: re.Match) -> Binding:
    return Binding(context, m[2], m[3], int(m[4]), m[5], int(m[7], 16) if m[7] else 0, m[6] or "", m[8] or "")


def _same_line(line: str, b: Binding) -> bool:
    m = _BINDING.match(line)
    return bool(m) and _binding(b.context, m) == b


# ---- names ----------------------------------------------------------------------------------------
_KEY_NAMES = {
    "BACK": "Backspace", "RETURN": "Enter", "NUMPADENTER": "Num Enter", "SPACE": "Space", "TAB": "Tab",
    "ESCAPE": "Esc", "GRAVE": "`", "MINUS": "-", "EQUALS": "=", "LBRACKET": "[", "RBRACKET": "]",
    "BACKSLASH": "\\", "SEMICOLON": ";", "APOSTROPHE": "'", "COMMA": ",", "PERIOD": ".", "SLASH": "/",
    "UPARROW": "Up", "DOWNARROW": "Down", "LEFTARROW": "Left", "RIGHTARROW": "Right", "PGUP": "Page Up",
    "PGDN": "Page Down", "PRIOR": "Page Up", "NEXT": "Page Down", "HOME": "Home", "END": "End",
    "INSERT": "Insert", "DELETE": "Delete", "SYSRQ": "Print Screen", "PAUSE": "Pause", "SCROLL": "Scroll Lock",
    "NUMLOCK": "Num Lock", "CAPITAL": "Caps Lock", "NUMPADMINUS": "Num -", "NUMPADPLUS": "Num +",
    "NUMPADSLASH": "Num /", "NUMPADSTAR": "Num *", "NUMPADPERIOD": "Num .", "DECIMAL": "Num .",
    "LSHIFT": "Left Shift", "RSHIFT": "Right Shift", "LCONTROL": "Left Ctrl", "RCONTROL": "Right Ctrl",
    "LALT": "Left Alt", "RALT": "Right Alt", "LWIN": "Left Win", "RWIN": "Right Win", "APPS": "Menu",
}
_MOUSE_NAMES = {"BUTTON0": "Left mouse", "BUTTON1": "Right mouse", "BUTTON2": "Middle mouse",
                "BUTTON3": "Mouse 4", "BUTTON4": "Mouse 5", "BUTTON5": "Mouse 6", "BUTTON6": "Mouse 7",
                "BUTTON7": "Mouse 8", "X": "Mouse move (left/right)", "Y": "Mouse move (up/down)",
                "Z": "Mouse wheel"}


def key_name(device: int, key: str) -> str:
    if key.startswith("DIK_"):
        k = key[4:]
        if k in _KEY_NAMES:
            return _KEY_NAMES[k]
        if k.startswith("NUMPAD") and k[6:].isdigit():
            return f"Num {k[6:]}"
        return k.title() if len(k) > 1 and not k[1:].isdigit() else k
    if key.startswith("DIMOFS_"):
        return _MOUSE_NAMES.get(key[7:], key[7:].title())
    return key if device in (KEYBOARD, MOUSE) else f"Device {device} {key}"


def action_name(action: str) -> str:
    """QUICKSLOT_31 → "Quickslot 31", ToggleMapPanel → "Toggle map panel"."""
    if action == NOTHING:
        return "(blocked key)"
    s = action.replace("_", " ")
    if not s.isupper():
        s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    s = s.lower().strip()
    return s[:1].upper() + s[1:]


def context_name(context: str) -> str:
    return {"Main": "General", "EditControls": "Text fields", "SelectionUI": "Selection",
            "MusicUI": "Music mode", "MapPanel": "Map", "VendorBuyUI": "Vendor",
            "ScrollableControls": "Scrolling", "ScrollableControls_Mouse": "Scrolling (mouse)",
            "CopyAndPasteControls": "Copy and paste", "DialogBoxes": "Dialog boxes",
            "DebugConsole": "Debug console", "StringTokenDebugger": "String debugger"}.get(context, context)


# ---- files ----------------------------------------------------------------------------------------
def keymap_file(s) -> Path | None:
    d = s.docs_path
    return d / "lotro.keymap" if d else None


def backup(path: Path) -> Path:
    b = path.with_name(f"{path.name}.mithlond-{time.strftime('%Y-%m-%d-%H%M%S')}")
    shutil.copy2(path, b)
    for old in sorted(path.parent.glob(f"{path.name}.mithlond-*"))[:-5]:  # keep the last five
        old.unlink(missing_ok=True)
    return b


def latest_backup(path: Path) -> Path | None:
    found = sorted(path.parent.glob(f"{path.name}.mithlond-*"))
    return found[-1] if found else None


def save(path: Path, km: Keymap) -> Path | None:
    """Write the keymap (backing up the current file first)."""
    b = backup(path) if path.exists() else None
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(km.render().encode("utf-8"))
    tmp.replace(path)
    return b


def is_keymap(text: str) -> bool:
    return "Bindings" in text and bool(Keymap.parse(text).bindings)
