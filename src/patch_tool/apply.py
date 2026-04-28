"""Core edit application logic.

Algorithm (mirrors pi-mono / Aider semantics):

1. Read the file as UTF-8.
2. Strip the UTF-8 BOM if present; remember it for restoration.
3. Detect the file's dominant line ending (CRLF or LF).
4. Normalize the file content to LF for matching.
5. Probe each edit. If any probe required fuzzy normalization, rewrite the
   *entire file* (in LF space) into fuzzy space before continuing — the
   diff base becomes the fuzzy-normalized content.
6. For each edit, find the unique match in the (possibly fuzzy) base. If
   ``old`` is missing or matches >1 times, raise.
7. Sort matches by position; verify no two edits overlap.
8. Apply edits in *reverse* order so earlier match indices stay valid.
9. Reject if the result equals the base (no-op edits are bugs).
10. Restore line endings, prepend the BOM, atomically write to disk.
"""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Union

from ._file_lock import file_mutation_lock
from ._types import Edit, EditResult
from .diff import generate_diff
from .errors import (
    AmbiguousMatchError,
    EmptyOldTextError,
    NoChangesError,
    OverlappingEditsError,
    TextNotFoundError,
)
from .matching import count_occurrences, fuzzy_find
from .normalization import (
    detect_line_ending,
    normalize_for_fuzzy_match,
    normalize_to_lf,
    restore_line_endings,
    strip_bom,
)

EditLike = Union[Edit, tuple[str, str], Mapping[str, str]]


def _coerce_edit(value: EditLike, index: int) -> Edit:
    if isinstance(value, Edit):
        return value
    if isinstance(value, tuple):
        if len(value) != 2:
            raise TypeError(
                f"edits[{index}]: tuple must be (old, new), got length {len(value)}"
            )
        old, new = value
        if not isinstance(old, str) or not isinstance(new, str):
            raise TypeError(f"edits[{index}]: tuple items must be str")
        return Edit(old=old, new=new)
    if isinstance(value, Mapping):
        try:
            old = value["old"]
            new = value["new"]
        except KeyError as exc:
            raise TypeError(
                f"edits[{index}]: mapping must have 'old' and 'new' keys"
            ) from exc
        if not isinstance(old, str) or not isinstance(new, str):
            raise TypeError(f"edits[{index}]: 'old' and 'new' must be str")
        return Edit(old=old, new=new)
    raise TypeError(
        f"edits[{index}]: expected Edit | tuple[str, str] | Mapping, got {type(value).__name__}"
    )


def _atomic_write(path: Path, content: str, encoding: str) -> None:
    """Write ``content`` to ``path`` via a same-directory tempfile + rename.

    Preserves the destination file's mode bits when it already exists.
    Uses ``newline=""`` so Python performs no line-ending translation —
    we have already encoded the desired ending into ``content``.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    try:
        existing_mode: int | None = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        existing_mode = None

    tmp_name = f".{path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    tmp = parent / tmp_name
    try:
        with open(tmp, "w", encoding=encoding, newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        if existing_mode is not None:
            os.chmod(tmp, existing_mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _apply_in_memory(
    base_content: str, edits: Sequence[Edit], path_hint: str
) -> tuple[str, str, bool, int]:
    """Match and apply ``edits`` against ``base_content`` (LF-normalized).

    Returns ``(diff_base, new_content, used_fuzzy, edits_applied)``.

    ``diff_base`` may differ from ``base_content`` if any edit required
    fuzzy normalization — the entire file is rewritten in fuzzy space then.
    """
    if not edits:
        raise ValueError("edits must contain at least one entry")

    # All edit text gets normalized to LF too — the LLM might emit \r\n
    # in either oldText or newText.
    normalized = [
        Edit(old=normalize_to_lf(e.old), new=normalize_to_lf(e.new)) for e in edits
    ]

    for i, e in enumerate(normalized):
        if e.old == "":
            label = "old" if len(normalized) == 1 else f"edits[{i}].old"
            raise EmptyOldTextError(f"{label} must not be empty in {path_hint}")

    # Probe — if any single edit needs fuzzy matching, the whole file goes fuzzy.
    probes = [fuzzy_find(base_content, e.old) for e in normalized]
    used_fuzzy = any(p.used_fuzzy for p in probes)
    diff_base = normalize_for_fuzzy_match(base_content) if used_fuzzy else base_content

    # Re-find every edit against ``diff_base`` and assert uniqueness.
    matches: list[tuple[int, int, int, str]] = []  # (edit_index, start, length, new)
    for i, e in enumerate(normalized):
        m = fuzzy_find(diff_base, e.old)
        if not m.found:
            label = "the text" if len(normalized) == 1 else f"edits[{i}]"
            raise TextNotFoundError(
                f"Could not find {label} in {path_hint}. The old text must "
                "match exactly including all whitespace and newlines."
            )
        n = count_occurrences(diff_base, e.old)
        if n > 1:
            label = "the text" if len(normalized) == 1 else f"edits[{i}]"
            raise AmbiguousMatchError(
                f"Found {n} occurrences of {label} in {path_hint}. "
                "Each old text must be unique. Add more context to disambiguate.",
                occurrences=n,
            )
        matches.append((i, m.index, m.length, e.new))

    # Overlap detection.
    matches.sort(key=lambda t: t[1])
    for prev, curr in zip(matches, matches[1:]):
        prev_idx, prev_start, prev_len, _ = prev
        curr_idx, curr_start, _, _ = curr
        if prev_start + prev_len > curr_start:
            raise OverlappingEditsError(
                f"edits[{prev_idx}] and edits[{curr_idx}] overlap in {path_hint}. "
                "Merge them into one edit or target disjoint regions."
            )

    # Apply in reverse so earlier indices stay valid.
    new_content = diff_base
    for _, start, length, new in reversed(matches):
        new_content = new_content[:start] + new + new_content[start + length :]

    if new_content == diff_base:
        raise NoChangesError(
            f"No changes made to {path_hint}. The replacements produced "
            "identical content."
        )

    return diff_base, new_content, used_fuzzy, len(normalized)


def apply_edits(
    path: str | os.PathLike[str],
    edits: Sequence[EditLike],
    *,
    dry_run: bool = False,
    encoding: str = "utf-8",
) -> EditResult:
    """Apply one or more search/replace edits to ``path``.

    Args:
        path: File to edit. Must exist.
        edits: Sequence of ``Edit`` instances, ``(old, new)`` tuples, or
            ``{"old": ..., "new": ...}`` mappings. At least one is required.
            Each ``old`` text must be unique within the file and must not
            overlap any other edit's match.
        dry_run: If ``True``, computes the diff without writing the file.
        encoding: Text encoding (default ``"utf-8"``).

    Returns:
        ``EditResult`` describing the change.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        EmptyOldTextError: If any ``old`` is the empty string.
        TextNotFoundError: If any ``old`` is not in the file.
        AmbiguousMatchError: If any ``old`` matches more than once.
        OverlappingEditsError: If two edits target overlapping regions.
        NoChangesError: If the resulting content equals the original.
    """
    if not edits:
        raise ValueError("edits must contain at least one entry")

    coerced: list[Edit] = [_coerce_edit(e, i) for i, e in enumerate(edits)]
    target = Path(path).resolve(strict=False)

    with file_mutation_lock(target):
        with open(target, "rb") as fh:
            raw_bytes = fh.read()
        raw_content = raw_bytes.decode(encoding)

        bom, body = strip_bom(raw_content)
        line_ending = detect_line_ending(body)
        lf_body = normalize_to_lf(body)

        diff_base, new_lf, used_fuzzy, applied = _apply_in_memory(
            lf_body, coerced, str(target)
        )

        diff_text, first_changed = generate_diff(diff_base, new_lf)

        if not dry_run:
            final = bom + restore_line_endings(new_lf, line_ending)
            _atomic_write(target, final, encoding=encoding)

    return EditResult(
        path=target,
        diff=diff_text,
        first_changed_line=first_changed,
        edits_applied=applied,
        used_fuzzy_match=used_fuzzy,
        written=not dry_run,
    )


def preview_edits(
    path: str | os.PathLike[str],
    edits: Sequence[EditLike],
    *,
    encoding: str = "utf-8",
) -> EditResult:
    """Convenience wrapper for ``apply_edits(..., dry_run=True)``."""
    return apply_edits(path, edits, dry_run=True, encoding=encoding)
