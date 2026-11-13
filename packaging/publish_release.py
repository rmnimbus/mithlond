#!/usr/bin/env python3
"""Release helper for packaging/release.sh (standard library only).

  publish_release.py notes X.Y.Z               print the CHANGELOG section for X.Y.Z
  publish_release.py publish X.Y.Z APPIMAGE    Gitea release + asset, wait for the mirrored tag on GitHub,
                                               GitHub release (latest) + asset, then check what the updater sees

Every step looks first and skips what already exists, so a failed run can simply be repeated.
Tokens are read from ~/.config/gitea/token and ~/.config/github/token and never printed."""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITEA = "https://gitea.foamdisk.com/api/v1/repos/realmonster/mithlond"
GITHUB = "https://api.github.com/repos/rmnimbus/mithlond"
GITHUB_UPLOADS = "https://uploads.github.com/repos/rmnimbus/mithlond"


def notes(ver: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text()
    head = f"## {ver}\n"
    if head not in text:
        sys.exit(f"CHANGELOG.md has no '## {ver}' section")
    return text.split(head, 1)[1].split("\n## ", 1)[0].strip()


def token(name: str) -> str:
    p = Path.home() / ".config" / name / "token"
    try:
        return p.read_text().strip()
    except OSError:
        sys.exit(f"missing token file {p}")


def call(url: str, headers: dict, method: str = "GET", payload=None, raw: bytes | None = None,
         ctype: str = "application/json"):
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(url, data=data, method=method, headers={**headers, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = r.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        # the message from the server only; request headers (with the token) are never shown
        raise SystemExit(f"{method} {url.split('?')[0]} failed: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gitea_release(ver: str, asset: Path, body: str) -> None:
    hdr = {"Authorization": f"token {token('gitea')}", "Accept": "application/json"}
    tag = f"v{ver}"
    rel = call(f"{GITEA}/releases/tags/{tag}", hdr)
    if rel is None:
        rel = call(f"{GITEA}/releases", hdr, "POST", {"tag_name": tag, "name": f"Mithlond {ver}", "body": body})
        print(f"Gitea: created release {rel['html_url']}")
    else:
        print(f"Gitea: release {tag} already exists")
    if any(a["name"] == asset.name for a in rel.get("assets") or []):
        print(f"Gitea: {asset.name} already attached")
        return
    b = uuid.uuid4().hex
    mp = (f'--{b}\r\nContent-Disposition: form-data; name="attachment"; filename="{asset.name}"\r\n'
          "Content-Type: application/octet-stream\r\n\r\n").encode() + asset.read_bytes() + f"\r\n--{b}--\r\n".encode()
    a = call(f"{GITEA}/releases/{rel['id']}/assets?name={urllib.parse.quote(asset.name)}", hdr, "POST", raw=mp,
             ctype=f"multipart/form-data; boundary={b}")
    print(f"Gitea: attached {a['name']} ({a['size']} bytes)")


def github_release(ver: str, asset: Path, body: str, digest: str) -> None:
    hdr = {"Authorization": f"Bearer {token('github')}", "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28"}
    tag = f"v{ver}"
    for i in range(60):  # Gitea's push mirror usually takes seconds, at most its sync interval
        if call(f"{GITHUB}/git/ref/tags/{tag}", hdr) is not None:
            break
        if i == 0:
            print("GitHub: waiting for the push mirror to bring the tag…")
        time.sleep(10)
    else:
        sys.exit("GitHub: the tag didn't arrive within 10 minutes; check the Gitea push mirror, then run again")
    rel = call(f"{GITHUB}/releases/tags/{tag}", hdr)
    if rel is None:
        rel = call(f"{GITHUB}/releases", hdr, "POST", {"tag_name": tag, "name": f"Mithlond {ver}", "body": body,
                                                       "make_latest": "true"})
        print(f"GitHub: created release {rel['html_url']}")
    else:
        print(f"GitHub: release {tag} already exists")
    existing = next((a for a in rel.get("assets") or [] if a["name"] == asset.name), None)
    if existing is None:
        existing = call(f"{GITHUB_UPLOADS}/releases/{rel['id']}/assets?name={urllib.parse.quote(asset.name)}", hdr,
                        "POST", raw=asset.read_bytes(), ctype="application/octet-stream")
        print(f"GitHub: uploaded {existing['name']} ({existing['size']} bytes)")
    else:
        print(f"GitHub: {asset.name} already uploaded")
    if existing.get("digest") and existing["digest"] != f"sha256:{digest}":
        sys.exit(f"GitHub: the uploaded file's checksum {existing['digest']} doesn't match the local file")


def check_updater(ver: str, digest: str) -> None:
    sys.path.insert(0, str(ROOT))
    from mithlond import selfupdate
    for _ in range(12):  # GitHub's "latest" can lag a few seconds behind
        rel = selfupdate.latest_release()
        if rel.version == ver and rel.sha256:
            break
        time.sleep(5)
    if rel.version != ver:
        sys.exit(f"Updater check: GitHub's latest release is {rel.version}, not {ver}")
    if rel.sha256 != digest:
        sys.exit("Updater check: the checksum GitHub reports doesn't match the local AppImage")
    print(f"Updater check: latest release is {rel.version}, asset {rel.asset_name}, checksum matches")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "notes":
        print(notes(sys.argv[2]))
    elif len(sys.argv) == 4 and sys.argv[1] == "publish":
        ver, asset = sys.argv[2], Path(sys.argv[3])
        body = notes(ver)
        digest = sha256(asset)
        gitea_release(ver, asset, body)
        github_release(ver, asset, body, digest)
        check_updater(ver, digest)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
