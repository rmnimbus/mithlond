#!/usr/bin/env python3
"""Bundle every shared library an AppDir needs, except the ones on the AppImage excludelist.

    bundle_libs.py <AppDir> <lib dir inside it> <excludelist> <patchelf>

Scans every ELF file in the AppDir. For each needed library that is neither in the AppDir nor on the
excludelist (glibc, GPU drivers, libX11/libxcb, fontconfig…, which must come from the host), it downloads the
Debian 11 "bullseye" package that provides it, checks it against the pinned package index, and copies the
library into <lib dir>. It repeats until nothing is missing.

Debian 11 is a final release on archive.debian.org, so the index (and every package's SHA-256 in it) never
changes, and its libraries need at most glibc 2.31, below what PySide6 itself needs. Bundled libraries get
RUNPATH $ORIGIN so they find each other without LD_LIBRARY_PATH, which would leak into the game and other
programs Mithlond starts.
"""

from __future__ import annotations

import hashlib
import io
import lzma
import os
import re
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

MIRRORS = ("https://archive.debian.org/debian/", "https://deb.debian.org/debian/")
INDEX = "dists/bullseye/main/binary-amd64/Packages.xz"
INDEX_SHA256 = "1c3405444297ead864711c18e64bce4810db63b48340a2f9d81182d9f235ad71"
MAX_GLIBC = (2, 34)  # PySide6 6.12 itself needs 2.34 (Linux Mint 21, Ubuntu 22.04, Debian 12, Fedora 35)
LIB_DIRS = ("usr/lib/x86_64-linux-gnu/", "lib/x86_64-linux-gnu/")
# Libraries whose Debian package name doesn't follow the soname rule in package_for().
PACKAGE = {
    "libglib-2.0.so.0": "libglib2.0-0",
    "libgthread-2.0.so.0": "libglib2.0-0",
    "libgobject-2.0.so.0": "libglib2.0-0",
    "libgio-2.0.so.0": "libglib2.0-0",
    "libgmodule-2.0.so.0": "libglib2.0-0",
    "libpcre.so.3": "libpcre3",
}


def package_for(soname: str) -> str:
    """Debian policy: libfoo.so.1 is in libfoo1, libfoo2.so.0 in libfoo2-0, names lowercased."""
    if soname in PACKAGE:
        return PACKAGE[soname]
    m = re.fullmatch(r"(lib.+?)\.so\.(\d+)", soname)
    if not m:
        raise SystemExit(f"can't derive a package name for {soname}; add it to PACKAGE")
    base, n = m.groups()
    return (base + ("-" if base[-1].isdigit() else "") + n).lower()


def fetch(path: str, sha256: str) -> bytes:
    for mirror in MIRRORS:
        for _ in range(3):
            try:
                with urllib.request.urlopen(mirror + path, timeout=120) as r:
                    data = r.read()
            except OSError:
                continue
            if hashlib.sha256(data).hexdigest() == sha256:
                return data
            break  # wrong content from this mirror: try the next one
    raise SystemExit(f"couldn't download {path} with the expected SHA-256")


def read_index() -> dict[str, tuple[str, str, str]]:
    text = lzma.decompress(fetch(INDEX, INDEX_SHA256)).decode()
    pkgs = {}
    for stanza in text.split("\n\n"):
        f = dict(re.findall(r"^(Package|Version|Filename|SHA256): (.+)$", stanza, re.M))
        if "Package" in f:
            pkgs[f["Package"]] = (f["Version"], f["Filename"], f["SHA256"])
    return pkgs


def deb_libraries(deb: bytes) -> dict[str, bytes]:
    """Shared libraries in a .deb, by file name, with symlinks resolved."""
    assert deb.startswith(b"!<arch>\n")
    pos, data = 8, None
    while pos < len(deb):
        name, size = deb[pos:pos + 16].decode().strip().rstrip("/"), int(deb[pos + 48:pos + 58])
        if name.startswith("data.tar"):
            data = deb[pos + 60:pos + 60 + size]
        pos += 60 + size + (size & 1)
    files, links = {}, {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar:
            path = m.name.removeprefix("./")
            if not path.startswith(LIB_DIRS) or ".so" not in path:
                continue
            if m.isfile():
                files[os.path.basename(path)] = tar.extractfile(m).read()
            elif m.issym():
                links[os.path.basename(path)] = os.path.basename(m.linkname)
    for name, target in links.items():
        while target in links:
            target = links[target]
        if target in files:
            files[name] = files[target]
    return files


def elf_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            with open(p, "rb") as f:
                if f.read(4) == b"\x7fELF":
                    yield p


def dynamic(path: Path) -> tuple[list[str], list[str]]:
    out = subprocess.run(["readelf", "-dW", str(path)], capture_output=True, text=True).stdout
    paths = re.findall(r"\((?:RUNPATH|RPATH)\).*\[(.+?)\]", out)
    return re.findall(r"\(NEEDED\).*\[(.+?)\]", out), [d for p in paths for d in p.split(":")]


def qt_files(appdir: Path):
    """PySide6/Qt and the libraries bundled next to it. Python's own modules and libraries come with the
    relocatable Python build, which already carries what they need."""
    for f in elf_files(appdir):
        if "/PySide6/" in str(f) or "/shiboken6/" in str(f):
            yield f


def unreachable(f: Path, excluded: set[str]) -> list[str]:
    """Needed libraries that are neither excluded (host) nor in a directory of f's own RUNPATH."""
    needed, paths = dynamic(f)
    dirs = [Path(d.replace("$ORIGIN", str(f.parent))) for d in paths]
    return [n for n in needed if n not in excluded and not any((d / n).exists() for d in dirs)]


def glibc_needed(path: Path) -> tuple[int, int]:
    out = subprocess.run(["readelf", "-VW", str(path)], capture_output=True, text=True).stdout
    return max(((int(a), int(b)) for a, b in re.findall(r"Name: GLIBC_(\d+)\.(\d+)", out)), default=(0, 0))


def main() -> None:
    appdir, libdir, excludelist, patchelf = (Path(a).resolve() for a in sys.argv[1:5])
    excluded = {line.split()[0] for line in excludelist.read_text().splitlines()
                if line.strip() and not line.startswith("#")}
    index, debs, bundled = None, {}, []
    while True:
        missing = {}
        for f in qt_files(appdir):
            for n in unreachable(f, excluded):
                missing.setdefault(n, f)
        if not missing:
            break
        index = index or read_index()
        for soname, wanted_by in sorted(missing.items()):
            pkg = package_for(soname)
            if pkg not in index:
                raise SystemExit(f"{soname} (needed by {wanted_by.relative_to(appdir)}): no package {pkg}")
            version, filename, sha256 = index[pkg]
            if pkg not in debs:
                debs[pkg] = deb_libraries(fetch(filename, sha256))
            if soname not in debs[pkg]:
                raise SystemExit(f"{soname}: not in {pkg} {version}")
            target = libdir / soname
            if target.exists():
                raise SystemExit(f"{soname} is in {libdir} but {wanted_by} can't reach it through its RUNPATH")
            target.write_bytes(debs[pkg][soname])
            target.chmod(0o755)
            subprocess.run([str(patchelf), "--set-rpath", "$ORIGIN", str(target)], check=True)
            bundled.append(f"{soname} ({pkg} {version})")

    floor = max(glibc_needed(f) for f in elf_files(appdir))
    if floor > MAX_GLIBC:
        worst = [str(f.relative_to(appdir)) for f in elf_files(appdir) if glibc_needed(f) == floor]
        raise SystemExit(f"needs glibc {floor[0]}.{floor[1]} (> {MAX_GLIBC}): {worst[:5]}")
    print(f"Bundled {len(bundled)} libraries; needs glibc >= {floor[0]}.{floor[1]}")
    for b in bundled:
        print("  " + b)


if __name__ == "__main__":
    main()
