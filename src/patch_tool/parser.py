"""Parser for Aider-style search/replace blocks.

Two entry points:

* :func:`parse_blocks` — extracts bare ``<<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE``
  blocks. File paths are ignored; you supply the path separately.

* :func:`parse_aider_blocks` — full Aider format, where each block is preceded
  by a path on its own line. Returns a mapping of path → ``[Edit, ...]``.

Both parsers tolerate:

* Surrounding markdown fences (```` ``` ````, ```` ```python ````, etc.) on
  the lines immediately around a block.
* Arbitrary commentary between blocks.
* Trailing whitespace on marker lines.
* The exact 7-char marker form ``<<<<<<<`` / ``=======`` / ``>>>>>>>`` (Aider's).

We refuse to escape markers inside the SEARCH/REPLACE bodies — if your code
genuinely contains those strings, use the structured ``Edit`` API instead.
"""

from __future__ import annotations

import re

from ._types import Edit
from .errors import ParseError

_SEARCH_RE = re.compile(r"^<{7}\s*SEARCH\s*$")
_DIVIDER_RE = re.compile(r"^={7}\s*$")
_REPLACE_RE = re.compile(r"^>{7}\s*REPLACE\s*$")
_FENCE_RE = re.compile(r"^\s*```")
_PROSE_TERMINAL_PUNCTUATION = ":.,"


def _strip_trailing_eol(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized[:-1] if normalized.endswith("\n") else normalized


def parse_blocks(text: str) -> list[Edit]:
    """Parse one or more bare SEARCH/REPLACE blocks. Paths are ignored."""
    return [edit for _, edit in _iter_blocks(text, require_path=False)]


def parse_aider_blocks(text: str) -> dict[str, list[Edit]]:
    """Parse Aider-style blocks where each block is preceded by a file path.

    Multiple blocks targeting the same path are grouped in order.

    Raises:
        ParseError: if any block is not preceded by a path.
    """
    grouped: dict[str, list[Edit]] = {}
    for path, edit in _iter_blocks(text, require_path=True):
        assert path is not None
        grouped.setdefault(path, []).append(edit)
    return grouped


def _iter_blocks(text: str, *, require_path: bool):
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if not _SEARCH_RE.match(lines[i].rstrip("\r\n")):
            i += 1
            continue

        # Block found at line i. Walk back to find a path candidate.
        path = _scan_back_for_path(lines, i) if require_path else None

        # Find divider.
        divider = None
        for j in range(i + 1, len(lines)):
            if _DIVIDER_RE.match(lines[j].rstrip("\r\n")):
                divider = j
                break
        if divider is None:
            raise ParseError(
                f"Unterminated SEARCH block at line {i + 1}: missing '======='"
            )

        # Find replace marker.
        replace = None
        for j in range(divider + 1, len(lines)):
            if _REPLACE_RE.match(lines[j].rstrip("\r\n")):
                replace = j
                break
        if replace is None:
            raise ParseError(
                f"Unterminated SEARCH block at line {i + 1}: missing '>>>>>>> REPLACE'"
            )

        old = _strip_trailing_eol("".join(lines[i + 1 : divider]))
        new = _strip_trailing_eol("".join(lines[divider + 1 : replace]))

        if require_path and path is None:
            raise ParseError(f"SEARCH block at line {i + 1} has no preceding file path")

        yield path, Edit(old=old, new=new)
        i = replace + 1


def _scan_back_for_path(lines: list[str], block_start: int) -> str | None:
    """Walk backwards from ``block_start`` to find a file path line.

    Skips: blank lines, lines that look like markdown fences, and lines
    that are themselves block markers from a previous block.
    """
    j = block_start - 1
    while j >= 0:
        candidate = lines[j].rstrip("\r\n").strip()
        if candidate == "":
            j -= 1
            continue
        if _FENCE_RE.match(candidate):
            j -= 1
            continue
        # If we hit a previous REPLACE marker, the previous block has no path
        # adjacent to *this* one — give up.
        if _REPLACE_RE.match(candidate):
            return None
        # A path candidate. Reject obvious non-paths.
        if _SEARCH_RE.match(candidate) or _DIVIDER_RE.match(candidate):
            return None
        if not _is_path_candidate(candidate):
            return None
        return candidate
    return None


def _is_path_candidate(candidate: str) -> bool:
    if any(char.isspace() for char in candidate):
        return False
    return not candidate.endswith(tuple(_PROSE_TERMINAL_PUNCTUATION))
