"""Robust search/replace file editing for LLM-driven code changes.

Quick start::

    from patch_tool import apply_edits, Edit

    result = apply_edits(
        "src/foo.py",
        [Edit(old="x = 1", new="x = 2")],
    )
    print(result.diff)
"""

from ._types import Edit, EditResult
from .apply import apply_edits, preview_edits
from .errors import (
    AmbiguousMatchError,
    EmptyOldTextError,
    NoChangesError,
    OverlappingEditsError,
    ParseError,
    PatchError,
    TextNotFoundError,
)
from .parser import parse_path_search_replace_blocks, parse_search_replace_blocks

__all__ = [
    "Edit",
    "EditResult",
    "apply_edits",
    "preview_edits",
    "parse_search_replace_blocks",
    "parse_path_search_replace_blocks",
    "PatchError",
    "EmptyOldTextError",
    "TextNotFoundError",
    "AmbiguousMatchError",
    "OverlappingEditsError",
    "NoChangesError",
    "ParseError",
]
