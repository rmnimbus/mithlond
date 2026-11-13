#!/bin/sh
# Release Mithlond in two steps, with the per-build check (tests + one real launch) in between:
#
#   packaging/release.sh build X.Y.Z        set the version in mithlond/__init__.py, turn CHANGELOG's
#                                           "## Unreleased" into "## X.Y.Z", build dist/Mithlond-X.Y.Z-x86_64.AppImage
#   packaging/release.sh publish X.Y.Z [-F message-file]
#                                           commit, tag vX.Y.Z, push to Gitea, create the Gitea release with the
#                                           AppImage, wait for the push mirror, create the GitHub release (latest)
#                                           with the AppImage, and check that the updater sees X.Y.Z with the right
#                                           checksum. Safe to run again after a failure: finished steps are skipped.
#
# Tokens: ~/.config/gitea/token and ~/.config/github/token (never printed).
# The commit message is "X.Y.Z" plus the changelog section, or the file given with -F.
set -eu
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SRC"

die() { echo "release.sh: $*" >&2; exit 1; }
[ $# -ge 2 ] || die "usage: release.sh build|publish X.Y.Z [-F message-file]"
STEP="$1"; VER="$2"; shift 2
echo "$VER" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || die "version must look like 1.2.3"
TAG="v$VER"
ASSET="dist/Mithlond-$VER-x86_64.AppImage"
CUR="$(sed -n 's/__version__ = "\(.*\)"/\1/p' mithlond/__init__.py)"
[ "$(git rev-parse --abbrev-ref HEAD)" = master ] || die "not on master"

case "$STEP" in
build)
    git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && die "tag $TAG already exists"
    if [ "$CUR" != "$VER" ]; then
        grep -q '^## Unreleased$' CHANGELOG.md || die "CHANGELOG.md has no '## Unreleased' section"
        sed -i "s/^__version__ = \".*\"/__version__ = \"$VER\"/" mithlond/__init__.py
        sed -i "0,/^## Unreleased\$/s//## $VER/" CHANGELOG.md
        echo "Version $CUR -> $VER; CHANGELOG 'Unreleased' is now '$VER'."
    fi
    grep -q "^## $VER\$" CHANGELOG.md || die "CHANGELOG.md has no '## $VER' section"
    packaging/build-appimage.sh
    echo "Next: test $ASSET (tests + one real launch), then: packaging/release.sh publish $VER"
    ;;
publish)
    MSGFILE=""
    if [ "${1:-}" = "-F" ]; then [ -f "${2:-}" ] || die "message file not found"; MSGFILE="$2"; fi
    [ "$CUR" = "$VER" ] || die "mithlond/__init__.py says $CUR; run 'release.sh build $VER' first"
    [ -f "$ASSET" ] || die "$ASSET is missing; run 'release.sh build $VER' first"
    NOTES="$(python3 packaging/publish_release.py notes "$VER")"
    if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
        git add -A
        if [ -n "$MSGFILE" ]; then git commit -q -F "$MSGFILE"
        else printf '%s\n\n%s\n' "$VER" "$NOTES" | git commit -q -F -
        fi
        git tag -a "$TAG" -m "Mithlond $VER"
    fi
    [ -z "$(git status --porcelain)" ] || die "uncommitted changes after tagging; commit or stash them first"
    git push -q origin master "$TAG"
    python3 packaging/publish_release.py publish "$VER" "$ASSET"
    ;;
*) die "unknown step '$STEP' (build or publish)" ;;
esac
