from pathlib import Path

import pytest


@pytest.fixture
def tmp_file(tmp_path: Path):
    """Factory that writes a file under tmp_path and returns its Path."""

    def _make(name: str, content: str, *, encoding: str = "utf-8") -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Use binary write so newlines are not translated by the platform.
        path.write_bytes(content.encode(encoding))
        return path

    return _make


@pytest.fixture
def read_bytes():
    def _read(path: Path) -> bytes:
        return path.read_bytes()

    return _read


@pytest.fixture(autouse=True)
def _ensure_no_lingering_locks():
    """Sanity check: file locks are in-process, but ensure no orphan state."""
    yield
    # Module-level lock map is fine to leave populated; locks themselves
    # are not held. Nothing to assert here, but keeping the hook makes it
    # easy to extend later if needed.
