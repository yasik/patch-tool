"""Concurrency tests for the per-file mutation lock.

These tests are timing-sensitive and use small sleeps to encourage interleaving.
They verify that:

* Two threads editing the *same* file do not interleave (no lost updates).
* Two threads editing *different* files run independently (do not block).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from patch_tool import Edit, apply_edits


def test_same_file_sequential_no_lost_updates(tmp_file):
    """N threads each apply one unique edit to the same file. All should succeed."""
    # Zero-pad so no name is a substring of another (line_01 vs line_010).
    path = tmp_file("a.txt", "\n".join(f"line_{i:02d}" for i in range(50)) + "\n")

    def worker(i: int):
        return apply_edits(path, [Edit(f"line_{i:02d}", f"DONE_{i:02d}")])

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker, i) for i in range(50)]
        results = [f.result() for f in as_completed(futures)]

    assert all(r.written for r in results)
    final = path.read_bytes().decode()
    for i in range(50):
        assert f"DONE_{i:02d}" in final
        assert f"line_{i:02d}" not in final


def test_different_files_run_in_parallel(tmp_file):
    """Two threads on two different files should not block each other.

    We use a barrier inside a hooked operation: each thread, while holding
    the lock for its own file, waits on a barrier that the other thread
    must reach. If the locks were global the test would deadlock.
    """
    path_a = tmp_file("a.txt", "x\n")
    path_b = tmp_file("b.txt", "x\n")

    barrier = threading.Barrier(parties=2, timeout=2.0)

    # We need a way to make each apply pause inside the locked section.
    # Easiest: monkey-patch generate_diff to wait on the barrier on first call.
    from patch_tool import apply as apply_module

    real_generate_diff = apply_module.generate_diff
    call_count = {"n": 0}
    lock = threading.Lock()

    def hooked_generate_diff(*args, **kwargs):
        with lock:
            call_count["n"] += 1
        # Both threads should reach this point without deadlocking.
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pytest.fail("Different-file edits did not run in parallel")
        return real_generate_diff(*args, **kwargs)

    apply_module.generate_diff = hooked_generate_diff
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_a = pool.submit(apply_edits, path_a, [Edit("x", "A")])
            f_b = pool.submit(apply_edits, path_b, [Edit("x", "B")])
            f_a.result(timeout=5)
            f_b.result(timeout=5)
    finally:
        apply_module.generate_diff = real_generate_diff

    assert path_a.read_bytes() == b"A\n"
    assert path_b.read_bytes() == b"B\n"


def test_symlinked_paths_share_lock(tmp_path: Path):
    """Two paths pointing to the same real file must share the lock.

    We can't easily prove "share lock" without timing, so we instead verify
    the *behavioral* consequence: 50 concurrent edits via mixed paths still
    converge to a consistent result with no lost updates.
    """
    real = tmp_path / "real.txt"
    real.write_bytes(b"\n".join(f"row_{i:02d}".encode() for i in range(50)) + b"\n")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    def worker(i: int):
        target = real if i % 2 == 0 else link
        return apply_edits(target, [Edit(f"row_{i:02d}", f"OK_{i:02d}")])

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(50)))

    final = real.read_bytes().decode()
    for i in range(50):
        assert f"OK_{i:02d}" in final


def test_cross_process_lock_disabled_by_default(tmp_file):
    path = tmp_file("a.txt", "x\n")

    apply_edits(path, [Edit("x", "y")])

    assert not (path.parent / ".a.txt.lock").exists()


def test_cross_process_lock_uses_sibling_lock_file(tmp_file):
    pytest.importorskip("fcntl")
    path = tmp_file("a.txt", "x\n")

    apply_edits(path, [Edit("x", "y")], cross_process_lock=True)

    assert (path.parent / ".a.txt.lock").exists()
    assert path.read_bytes() == b"y\n"
