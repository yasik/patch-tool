"""Per-file in-process mutation lock.

Two threads editing the *same* file are serialized. Two threads editing
*different* files run in parallel.

We key the lock on the resolved real path so two routes to the same file
(symlink + canonical) get the same lock.

The lock is in-process only. Multi-process coordination would require
``fcntl.flock`` and is out of scope — an LLM edit tool typically runs as a
single process.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _key(path: Path) -> str:
    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path.absolute())


@contextmanager
def file_mutation_lock(path: Path) -> Iterator[None]:
    """Acquire the per-file lock for the duration of the block."""
    key = _key(path)
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        yield
