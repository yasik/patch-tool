"""Typed exceptions raised by the patch tool.

Filesystem errors (missing file, permission denied) propagate as standard
``OSError`` / ``FileNotFoundError`` / ``PermissionError`` — we only define
exceptions for *edit-semantic* failures.
"""

from __future__ import annotations


class PatchError(Exception):
    """Base class for all edit-semantic failures."""


class EmptyOldTextError(PatchError):
    """Raised when an edit's ``old`` text is the empty string."""


class TextNotFoundError(PatchError):
    """Raised when an edit's ``old`` text is not present in the file."""


class AmbiguousMatchError(PatchError):
    """Raised when an edit's ``old`` text matches more than once.

    The ``occurrences`` attribute carries the count.
    """

    def __init__(self, message: str, *, occurrences: int) -> None:
        super().__init__(message)
        self.occurrences = occurrences


class OverlappingEditsError(PatchError):
    """Raised when two edits target overlapping regions of the same file."""


class NoChangesError(PatchError):
    """Raised when applying the edits would produce identical content."""


class ParseError(PatchError):
    """Raised by the search/replace block parser on malformed input."""
