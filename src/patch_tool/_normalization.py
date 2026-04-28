"""Text normalization helpers.

The matcher works in two spaces:

* **Exact space** — the file content as read from disk, with line endings
  normalized to LF and any UTF-8 BOM stripped.
* **Fuzzy space** — the exact-space content with Unicode quirks ironed out:
  smart quotes, exotic dashes, non-breaking and special spaces, NFKC
  normalization, and per-line trailing whitespace stripping.

Fuzzy matching is *all-or-nothing per file*: if any edit needs fuzzy
matching, the whole file is rewritten in fuzzy space before applying edits.
That is intentional — mixing exact and fuzzy regions in the same file is
hard to reason about and produces surprising diffs.
"""

from __future__ import annotations

import re
import unicodedata

BOM = "\ufeff"

# Smart single quotes:  ‘ ’ ‚ ‛  →  '
_SMART_SINGLE_QUOTES = re.compile(r"[\u2018\u2019\u201A\u201B]")
# Smart double quotes:  “ ” „ ‟  →  "
_SMART_DOUBLE_QUOTES = re.compile(r"[\u201C\u201D\u201E\u201F]")
# Various dashes/hyphens/minus:  ‐ ‑ ‒ – — ― −  →  -
_FANCY_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")
# Special spaces: NBSP, en/em quads, hair/thin/zero-width-style spaces, etc.
_SPECIAL_SPACES = re.compile(r"[\u00A0\u2002-\u200A\u202F\u205F\u3000]")


def strip_bom(text: str) -> tuple[str, str]:
    """Return the optional UTF-8 BOM and the remaining body text."""
    if text.startswith(BOM):
        return BOM, text[1:]
    return "", text


def detect_line_ending(text: str) -> str:
    """Return CRLF if it appears before a bare LF, else LF.

    Files with no newlines default to LF.
    """
    crlf = text.find("\r\n")
    lf = text.find("\n")
    if lf == -1:
        return "\n"
    if crlf == -1:
        return "\n"
    return "\r\n" if crlf < lf else "\n"


def normalize_to_lf(text: str) -> str:
    """Convert any CRLF / lone CR to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def restore_line_endings(text: str, ending: str) -> str:
    """Re-encode an LF-normalized string back to ``ending``."""
    if ending == "\r\n":
        return text.replace("\n", "\r\n")
    return text


def normalize_for_fuzzy_match(text: str) -> str:
    """Apply NFKC + quote/dash/space normalization + trailing-whitespace strip."""
    text = unicodedata.normalize("NFKC", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _SMART_SINGLE_QUOTES.sub("'", text)
    text = _SMART_DOUBLE_QUOTES.sub('"', text)
    text = _FANCY_DASHES.sub("-", text)
    text = _SPECIAL_SPACES.sub(" ", text)
    return text
