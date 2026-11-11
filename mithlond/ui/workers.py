"""Run blocking work (network, file copies) off the UI thread."""

from __future__ import annotations

import inspect
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    error = Signal(object)
    progress = Signal(object)


_live: set[_Signals] = set()


class _Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], signals: _Signals, with_progress: bool):
        super().__init__()
        self.fn, self.signals, self.with_progress = fn, signals, with_progress

    def run(self) -> None:
        try:
            result = self.fn(self.signals.progress.emit) if self.with_progress else self.fn()
        except Exception as e:  # noqa: BLE001 - reported to the UI
            e.__traceback_text__ = traceback.format_exc()  # type: ignore[attr-defined]
            self.signals.error.emit(e)
        else:
            self.signals.done.emit(result)


def run_task(
    fn: Callable[..., Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    on_progress: Callable[[Any], None] | None = None,
) -> None:
    """Run `fn` in the thread pool. If `on_progress` is given, `fn` receives a progress callback."""
    sig = _Signals()
    _live.add(sig)

    def finish(cb, value):
        _live.discard(sig)
        if cb:
            cb(value)

    sig.done.connect(lambda r: finish(on_done, r))
    sig.error.connect(lambda e: finish(on_error, e))
    if on_progress:
        sig.progress.connect(on_progress)
    with_progress = on_progress is not None
    if with_progress:
        params = inspect.signature(fn).parameters
        with_progress = len(params) >= 1
    QThreadPool.globalInstance().start(_Task(fn, sig, with_progress))
