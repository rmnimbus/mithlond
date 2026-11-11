"""ABC song files: importing into the game's Music folder and building the Songbook plugin's
song list (PluginData/<account>/AllServers/SongbookData.plugindata), the same file
Chiran's songbook.hta / SongbookFiller.exe produce."""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

SONG_EXTS = (".abc", ".txt")


@dataclass
class Part:
    id: str
    name: str


@dataclass
class Song:
    path: Path
    parts: list[Part] = field(default_factory=list)

    @property
    def title(self) -> str:
        for p in self.parts:
            if p.name:
                return re.sub(r"\s*[\(\[].*?[\)\]]\s*$", "", p.name) or p.name
        return self.path.stem


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _field(line: str) -> str:
    val = line[2:]
    if "%" in val:
        val = val[: val.index("%")]
    return val.strip()


def parse_abc(path: Path) -> Song:
    """Parts are X: numbers; each part's name is its T: lines joined with ' - '."""
    song = Song(path)
    names: list[list[str]] = []
    pending: list[str] = []
    for line in _read_text(path).splitlines():
        if len(line) < 2 or line[1] != ":":
            continue
        if line[0] == "X":
            song.parts.append(Part(_field(line) or str(len(song.parts) + 1), ""))
            names.append(pending)
            pending = []
        elif line[0] == "T":
            (names[-1] if names else pending).append(_field(line))
    if not song.parts:
        song.parts.append(Part("1", ""))
        names.append(pending)
    for p, n in zip(song.parts, names):
        p.name = " - ".join(x for x in n if x)
    return song


def is_song(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in SONG_EXTS


def scan_music(music_dir: Path) -> tuple[list[str], list[Song]]:
    """Directories (as '/', '/sub/', ...) and songs, in the order the Songbook plugin expects:
    a folder's files first, then its subfolders, recursively."""
    dirs: list[str] = []
    songs: list[Song] = []

    def walk(d: Path) -> None:
        rel = d.relative_to(music_dir).as_posix()
        dirs.append("/" if rel == "." else f"/{rel}/")
        try:
            entries = sorted(d.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for f in entries:
            if is_song(f):
                try:
                    songs.append(parse_abc(f))
                except OSError:
                    pass
        for sub in entries:
            if sub.is_dir() and not sub.is_symlink():
                walk(sub)

    if music_dir.is_dir():
        walk(music_dir)
    return dirs, songs


def _lua(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", " ")


def songbook_data(music_dir: Path) -> tuple[str, int, int]:
    dirs, songs = scan_music(music_dir)
    T = "\t"
    out = ["return", "{", f'{T}["Directories"] =', f"{T}{{"]
    for i, d in enumerate(dirs, 1):
        out.append(f'{T*2}[{i}] = "{_lua(d)}"' + ("," if i < len(dirs) else ""))
    out += [f"{T}}},", f'{T}["Songs"] =', f"{T}{{"]
    for i, s in enumerate(songs, 1):
        rel = s.path.parent.relative_to(music_dir).as_posix()
        fp = "/" if rel == "." else f"/{rel}/"
        out += [
            f"{T*2}[{i}] = ", f"{T*2}{{",
            f'{T*3}["Filepath"] = "{_lua(fp)}",',
            f'{T*3}["Filename"] = "{_lua(s.path.stem)}",',
            f'{T*3}["Tracks"] =', f"{T*3}{{",
        ]
        for j, p in enumerate(s.parts, 1):
            out += [
                f"{T*4}[{j}] =", f"{T*4}{{",
                f'{T*5}["Id"] ="{_lua(p.id)}",',
                f'{T*5}["Name"] ="{_lua(p.name)}"',
                f"{T*4}}}" + ("," if j < len(s.parts) else ""),
            ]
        out += [f"{T*3}}}", f"{T*2}}}" + ("," if i < len(songs) else "")]
    out += [f"{T}}}", "}"]
    return "\r\n".join(out) + "\r\n", len(songs), len(dirs)


def plugindata_accounts(plugindata_dir: Path) -> list[str]:
    if not plugindata_dir.is_dir():
        return []
    return sorted(p.name for p in plugindata_dir.iterdir() if p.is_dir())


def write_songbook(music_dir: Path, plugindata_dir: Path, accounts: list[str]) -> tuple[int, list[Path]]:
    """Write SongbookData.plugindata for each account. Returns (song count, files written)."""
    text, count, _ = songbook_data(music_dir)
    written = []
    for acc in accounts:
        d = plugindata_dir / acc / "AllServers"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "SongbookData.plugindata"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(f)
        written.append(f)
    return count, written


def _unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 2
    while True:
        cand = dest.with_name(f"{dest.stem} ({i}){dest.suffix}")
        if not cand.exists():
            return cand
        i += 1


def import_songs(sources: list[Path], music_dir: Path, subfolder: str = "", overwrite: bool = False) -> list[Path]:
    """Copy .abc/.txt files, whole folders, or .zip archives of songs into the Music folder."""
    target = music_dir / subfolder if subfolder else music_dir
    target.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []

    def put(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not overwrite:
            if dest.read_bytes() == src.read_bytes():
                return
            dest = _unique(dest)
        shutil.copy2(src, dest)
        out.append(dest)

    for src in sources:
        if src.is_dir():
            for f in sorted(src.rglob("*")):
                if is_song(f):
                    put(f, target / src.name / f.relative_to(src))
        elif src.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory(prefix="mithlond-") as td, zipfile.ZipFile(src) as z:
                entries = []
                for info in z.infolist():
                    name = info.filename.replace("\\", "/")
                    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
                    if not info.is_dir() and parts and Path(parts[-1]).suffix.lower() in SONG_EXTS \
                            and "__MACOSX" not in parts:
                        entries.append((info, parts))
                # A zip with everything inside one folder: use that folder's name instead of the zip's.
                tops = {parts[0] for _, parts in entries if len(parts) > 1}
                strip = len(tops) == 1 and all(len(parts) > 1 for _, parts in entries)
                for n, (info, parts) in enumerate(entries):
                    tmpf = Path(td, str(n), parts[-1])
                    tmpf.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as zf, open(tmpf, "wb") as f:
                        shutil.copyfileobj(zf, f)
                    rel = Path(*parts) if strip else Path(src.stem, *parts)
                    put(tmpf, target / rel)
        elif is_song(src):
            put(src, target / src.name)
    return out
