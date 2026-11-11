"""Password storage in the desktop keyring through the Secret Service API (`secret-tool`).

The keyring daemon (KWallet's ksecretd, GNOME Keyring, KeePassXC…) keeps the password encrypted.
Passwords never touch Mithlond's config file. If no keyring is available, nothing is saved and the
launcher asks for the password each time.
"""

from __future__ import annotations

import shutil
import subprocess

from .hostenv import host_env

SERVICE = "mithlond-lotro"
# Generous: the keyring may show an unlock prompt the first time in a session.
TIMEOUT = 120


class KeyringError(Exception):
    pass


def available() -> bool:
    return shutil.which("secret-tool") is not None


def _run(args: list[str], password: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["secret-tool", *args], input=password, capture_output=True, text=True,
                              timeout=TIMEOUT, env=host_env())
    except subprocess.TimeoutExpired as e:
        raise KeyringError("The keyring did not answer (was an unlock prompt dismissed?)") from e
    except OSError as e:
        raise KeyringError(str(e)) from e


def _attrs(username: str) -> list[str]:
    return ["service", SERVICE, "username", username.lower()]


def get_password(username: str) -> str | None:
    if not available():
        return None
    try:
        r = _run(["lookup", *_attrs(username)])
    except KeyringError:
        return None
    return r.stdout if r.returncode == 0 and r.stdout else None


def set_password(username: str, password: str) -> None:
    """Store and read back the password. Raises KeyringError if it didn't stick."""
    if not available():
        raise KeyringError("secret-tool (libsecret) is not installed")
    r = _run(["store", f"--label=LOTRO account {username} (Mithlond)", *_attrs(username)], password)
    if r.returncode != 0:
        raise KeyringError(r.stderr.strip() or "no Secret Service keyring is running")
    if get_password(username) != password:
        raise KeyringError("the keyring accepted the password but did not return it")


def delete_password(username: str) -> None:
    if available():
        try:
            _run(["clear", *_attrs(username)])
        except KeyringError:
            pass
