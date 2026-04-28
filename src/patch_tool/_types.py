"""Public data types."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Edit:
    """A single targeted text replacement.

    Attributes:
        old: Exact (or fuzzy-equivalent) text to find. Must be unique in the
            file and non-empty.
        new: Replacement text. May be empty (deletes the matched region).
    """

    old: str
    new: str


@dataclass(frozen=True, slots=True)
class EditResult:
    """Outcome of a successful (or dry-run) edit operation."""

    path: Path
    """Resolved absolute path of the file."""

    diff: str
    """Unified-style diff with line numbers and 4 lines of context."""

    first_changed_line: int | None
    """1-indexed line number of the first change in the new file, or ``None``
    when there are no changes (only possible in dry-run for a no-op edit, which
    otherwise raises ``NoChangesError``)."""

    edits_applied: int
    """Number of edits successfully matched and applied."""

    used_fuzzy_match: bool
    """``True`` if at least one edit required Unicode/whitespace fuzzy
    matching. When ``True``, the *entire file* was fuzzy-normalized before
    the edits were applied."""

    written: bool
    """``True`` if the file was written. ``False`` for dry-runs."""
