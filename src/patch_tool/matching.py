"""Exact-then-fuzzy text matching."""

from __future__ import annotations

from dataclasses import dataclass

from .normalization import normalize_for_fuzzy_match


@dataclass(frozen=True, slots=True)
class MatchResult:
    found: bool
    index: int  # -1 when not found
    length: int  # length of the matched span
    used_fuzzy: bool  # True if fuzzy normalization was needed


def fuzzy_find(haystack: str, needle: str) -> MatchResult:
    """Find ``needle`` in ``haystack``.

    First tries exact ``str.find``. If that misses, both inputs are
    fuzzy-normalized and the search is retried. The returned ``index`` and
    ``length`` are valid against ``haystack`` *if* ``used_fuzzy`` is False,
    or against ``normalize_for_fuzzy_match(haystack)`` if True.
    """
    idx = haystack.find(needle)
    if idx != -1:
        return MatchResult(True, idx, len(needle), used_fuzzy=False)

    fuzzy_haystack = normalize_for_fuzzy_match(haystack)
    fuzzy_needle = normalize_for_fuzzy_match(needle)
    idx = fuzzy_haystack.find(fuzzy_needle)
    if idx == -1:
        return MatchResult(False, -1, 0, used_fuzzy=False)
    return MatchResult(True, idx, len(fuzzy_needle), used_fuzzy=True)


def count_occurrences(haystack: str, needle: str) -> int:
    """Count occurrences of ``needle`` in ``haystack`` in fuzzy space.

    We always count in fuzzy space because *any* successful match (exact or
    fuzzy) implies the canonical identity is the fuzzy form.
    """
    fuzzy_haystack = normalize_for_fuzzy_match(haystack)
    fuzzy_needle = normalize_for_fuzzy_match(needle)
    if not fuzzy_needle:
        return 0
    return fuzzy_haystack.count(fuzzy_needle)
