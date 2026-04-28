"""Per-file mutation locks.

Two threads editing the *same* file are serialized. Two threads editing
*different* files run in parallel.

We key the lock on the resolved real path so two routes to the same file
(symlink + canonical) get the same lock.

The default lock is in-process only. Callers can opt into an advisory
cross-process ``fcntl.flock`` lock when they need process-level coordination.
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol


class _FcntlModule(Protocol):
    @property
    def LOCK_EX(self) -> int: ...

    @property
    def LOCK_UN(self) -> int: ...

    def flock(self, fd: int, operation: int, /) -> None: ...


_fcntl: _FcntlModule | None
try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _key(path: Path) -> str:
    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path.absolute())


def _lock_file_path(path: Path) -> Path:
    return path.parent / f".{path.name}.lock"


@contextmanager
def _cross_process_lock(path: Path) -> Generator[None, None, None]:
    if _fcntl is None:
        raise RuntimeError("cross_process_lock requires fcntl support")

    lock_path = _lock_file_path(path)
    with open(lock_path, "a", encoding="utf-8") as lock_file:
        _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_EX)
        try:
            yield
        finally:
            _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_UN)


@contextmanager
def file_mutation_lock(
    path: Path, *, cross_process: bool = False
) -> Generator[None, None, None]:
    """Acquire the per-file lock for the duration of the block."""
    key = _key(path)
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        if cross_process:
            with _cross_process_lock(path):
                yield
        else:
            yield
