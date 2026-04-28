"""Typed exceptions raised by the patch tool.

Filesystem errors (missing file, permission denied) propagate as standard
``OSError`` / ``FileNotFoundError`` / ``PermissionError`` — we only define
exceptions for *edit-semantic* failures.
"""

from pathlib import Path


class PatchError(Exception):
    """Base class for all edit-semantic failures."""


class EmptyOldTextError(PatchError):
    """Raised when an edit's ``old`` text is the empty string."""

    def __init__(
        self, message: str, *, path: Path | None = None, edit_index: int | None = None
    ) -> None:
        super().__init__(message)
        self.path = path
        self.edit_index = edit_index


class TextNotFoundError(PatchError):
    """Raised when an edit's ``old`` text is not present in the file."""

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
        edit_index: int | None = None,
        old: str | None = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.edit_index = edit_index
        self.old = old


class AmbiguousMatchError(PatchError):
    """Raised when an edit's ``old`` text matches more than once.

    The ``occurrences`` and ``positions`` attributes carry match details.
    """

    def __init__(
        self,
        message: str,
        *,
        occurrences: int,
        positions: list[int] | None = None,
        path: Path | None = None,
        edit_index: int | None = None,
        old: str | None = None,
    ) -> None:
        super().__init__(message)
        self.occurrences = occurrences
        self.positions = positions or []
        self.path = path
        self.edit_index = edit_index
        self.old = old


class OverlappingEditsError(PatchError):
    """Raised when two edits target overlapping regions of the same file."""

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
        edit_index: int | None = None,
        other_edit_index: int | None = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.edit_index = edit_index
        self.other_edit_index = other_edit_index


class NoChangesError(PatchError):
    """Raised when applying the edits would produce identical content."""

    def __init__(
        self, message: str, *, path: Path | None = None, edit_index: int | None = None
    ) -> None:
        super().__init__(message)
        self.path = path
        self.edit_index = edit_index


class ParseError(PatchError):
    """Raised by the search/replace block parser on malformed input."""

    def __init__(self, message: str, *, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line
