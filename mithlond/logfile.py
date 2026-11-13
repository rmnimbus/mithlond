"""Mithlond's log file (~/.cache/mithlond/mithlond.log): every log line with its date and time, a header per session,
and full tracebacks of crashes and failed background tasks (those only go to the file, not the log panel).
The file is moved to mithlond.log.1 once it passes 2 MB, so the two together hold the last ~4 MB."""

from __future__ import annotations

import datetime as dt
import platform
import sys
import threading
import traceback

from .config import CACHE_DIR

LOG = CACHE_DIR / "mithlond.log"
MAX_BYTES = 2 * 1024 * 1024
_fh = None
_lock = threading.Lock()


def _open():
    global _fh
    if _fh is None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if LOG.exists() and LOG.stat().st_size > MAX_BYTES:
                LOG.replace(LOG.with_name(LOG.name + ".1"))
        except OSError:
            pass
        _fh = open(LOG, "a", encoding="utf-8")
    return _fh


def write(msg: str) -> None:
    """One log line, stamped with date and time."""
    with _lock:
        try:
            f = _open()
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
            f.flush()
        except OSError:
            pass


def close() -> None:
    global _fh
    with _lock:
        if _fh is not None:
            _fh.close()
            _fh = None


def detail(title: str, text: str) -> None:
    """A multi-line block (e.g. a traceback), indented under a title line."""
    write(title + "\n" + "\n".join("    " + line for line in text.rstrip().splitlines()))


def session_header(version: str, extra: str = "") -> None:
    write(f"===== Mithlond {version} started | Python {platform.python_version()} | {platform.platform()}"
          + (f" | {extra}" if extra else ""))


def install_crash_hooks() -> None:
    """Write uncaught exceptions (main thread and other threads) to the log with their traceback."""
    old = sys.excepthook

    def hook(kind, value, tb):
        detail(f"CRASH: {kind.__name__}: {value}", "".join(traceback.format_exception(kind, value, tb)))
        old(kind, value, tb)

    def thread_hook(args):
        detail(f"CRASH in thread {getattr(args.thread, 'name', '?')}: {args.exc_type.__name__}: {args.exc_value}",
               "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    sys.excepthook = hook
    threading.excepthook = thread_hook
