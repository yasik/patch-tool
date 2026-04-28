"""Shared test-only types."""

from pathlib import Path
from typing import Protocol


class TmpFileFactory(Protocol):
    """Factory fixture that writes a text file and returns its path."""

    def __call__(self, name: str, content: str, *, encoding: str = "utf-8") -> Path:
        """Create a file under the pytest temporary directory."""
        ...


class ReadBytes(Protocol):
    """Reader fixture that returns raw file bytes."""

    def __call__(self, path: Path) -> bytes:
        """Read bytes from ``path``."""
        ...
