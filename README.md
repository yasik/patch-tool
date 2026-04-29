# patch-tool

Robust search/replace file editing for LLM-driven code changes.

A small, focused Python library that takes a file path and a list of
`{old, new}` text replacements and applies them safely. No line numbers, no
hunk headers, no diff syntax for the model to get wrong — just exact text the
model already knows is in the file.

The design follows the consensus that emerged from
[Aider](https://aider.chat/), [Claude Code](https://claude.ai/code),
[Cursor](https://cursor.sh/), [Cline](https://cline.bot/), and
[pi-mono](https://github.com/badlogic/pi-mono): structured search/replace
beats unified diffs for LLM-generated edits, both in success rate and in
recoverability when something goes wrong.

This package gives you the core engine. Wrapping it in an LLM tool (JSON
schema, descriptions, error formatting) is left to the caller.

---

## Why search/replace instead of diffs?

Unified diffs (`patch(1)`-style hunks with `@@ -42,7 +42,7 @@` headers) look
appealing — they're standard, compact, and have battle-tested tooling. They
fail badly under LLM generation though:

- **Line numbers are a curse for LLMs.** Models miscount, files drift between
  read and write, off-by-one errors silently corrupt code.
- **Fuzz semantics are opaque.** When a hunk fails to apply, the model has to
  understand patch internals to fix it.
- **Context lines are wasted tokens.** A diff redundantly transmits unchanged
  lines for disambiguation; search/replace uses just enough text to be unique.
- **Diff syntax is itself error-prone.** Headers, prefixes, whitespace —
  models get them wrong constantly.

Search/replace gives you binary outcomes (matched or not), human-readable
errors, and a format the model produces fluently. It costs more tokens for
very large changes, but the failure rate at the same model is meaningfully
lower in practice.

---

## Install

```bash
# With uv (recommended)
uv add llm-patch-tool

# Or pip
pip install llm-patch-tool
```

Requires Python 3.12+.

---

## Quick start

```python
from patch_tool import apply_edits, Edit

result = apply_edits(
    "src/foo.py",
    [
        Edit(old="def greet():", new="def greet(name: str):"),
        Edit(old="    print('hi')", new="    print(f'hi {name}')"),
    ],
)

print(result.diff)
print(f"Applied {result.edits_applied} edits to {result.path}")
```

If you'd rather not import the dataclass, tuples and dicts work too:

```python
apply_edits("src/foo.py", [("old text", "new text")])
apply_edits("src/foo.py", [{"old": "old text", "new": "new text"}])
```

To preview without writing:

```python
from patch_tool import preview_edits

result = preview_edits("src/foo.py", [Edit("x = 1", "x = 2")])
print(result.diff)              # diff is computed
assert not result.written       # but file is untouched
```

---

## Search/replace block formats

There are two parser entry points because wrappers get paths in two different
ways:

- Use `parse_blocks(text)` when the LLM tool call already has a
  structured `path` argument. The wrapper owns path dispatch and should pass the
  parsed edits to `apply_edits(path, edits)`.
- Use `parse_path_blocks(text)` only when the model output is a
  free-form text blob that includes path lines and may edit multiple files.
  The parser owns path dispatch and returns `path -> edits`.

For free-form path-prefixed text:

```python
from patch_tool import parse_path_blocks, apply_edits

blob = """
src/foo.py
<<<<<<< SEARCH
def greet():
    print('hi')
=======
def greet(name: str):
    print(f'hi {name}')
>>>>>>> REPLACE
"""

for path, edits in parse_path_blocks(blob).items():
    apply_edits(path, edits)
```

The grammar is:

```
<filepath on its own line>
<<<<<<< SEARCH
<exact text to find>
=======
<replacement text>
>>>>>>> REPLACE
```

- The path line precedes each block. Markdown fences (` ``` `, ` ```python `)
  and blank lines between path and block are tolerated.
- Path lines must not contain whitespace and must not end with prose
  punctuation (`:`, `.`, or `,`). This avoids treating explanatory text as a
  filename.
- Multiple blocks targeting the same path are grouped.
- Trailing whitespace on marker lines is ignored.
- The markers are exactly seven `<`, `=`, or `>` characters.

For structured tool wrappers, omit the path line and parse only edits:

```python
from patch_tool import parse_blocks, apply_edits

def tool_wrapper(path: str, edit_text: str) -> None:
    edits = parse_blocks(edit_text)
    apply_edits(path, edits)
```

---

## API

### `apply_edits(path, edits, *, dry_run=False, encoding="utf-8", cross_process_lock=False) -> EditResult`

Apply one or more edits to a single file. All-or-nothing: either every edit
matches and the file is rewritten atomically, or nothing changes.

**Arguments:**
- `path` — file to edit (str or PathLike). Must exist.
- `edits` — sequence of `Edit`, `(old, new)` tuples, or `{"old", "new"}` dicts.
- `dry_run` — if `True`, computes the diff without writing.
  No-change dry-runs return `diff=""`, `first_changed_line=None`,
  `edits_applied=0`, and `written=False` instead of raising.
- `encoding` — text encoding. Default `"utf-8"`.
- `cross_process_lock` — if `True`, also acquire an advisory process-level
  lock with `fcntl.flock` on supported platforms. Default `False` keeps the
  hot path to in-process thread serialization only.

**Returns** `EditResult` with:
- `path: Path` — resolved absolute path.
- `diff: str` — unified-style diff with line numbers and 4 lines of context.
- `first_changed_line: int | None` — 1-indexed line number of the first
  change in the new file (handy for editor navigation).
- `edits_applied: int` — number of edits matched and applied.
- `used_fuzzy_match: bool` — `True` if at least one edit required Unicode
  normalization (see *Fuzzy matching* below).
- `written: bool` — `False` for `dry_run`.

**Raises:**
- `FileNotFoundError` — path does not exist.
- `EmptyOldTextError` — an edit has empty `old`.
- `TextNotFoundError` — `old` is not in the file.
- `AmbiguousMatchError` — `old` matches more than once. Carries
  `.occurrences` and `.positions`.
- `OverlappingEditsError` — two edits target overlapping regions.
- `NoChangesError` — a write would not change the file, or an individual
  write edit has identical `old` and `new` text.

Semantic exceptions expose stable metadata for tool wrappers where relevant:
`path`, `edit_index`, `old`, `occurrences`, `positions`, `other_edit_index`,
and parser `line`.

### `preview_edits(path, edits, *, encoding="utf-8", cross_process_lock=False) -> EditResult`

Convenience wrapper: `apply_edits(..., dry_run=True)`.

### `parse_blocks(text: str) -> list[Edit]`

Extract bare SEARCH/REPLACE blocks. Use when the caller already has the target
path from structured tool input. Path lines are ignored.

### `parse_path_blocks(text: str) -> dict[str, list[Edit]]`

Extract path-prefixed SEARCH/REPLACE blocks. Use only when file paths are part
of the model text. Each block must be preceded by a path line.

---

## Design

### Algorithm

1. **Read** the file as UTF-8 (or the supplied encoding).
2. **Strip BOM** if present; remember it for restoration.
3. **Detect line ending** — CRLF if it appears before the first bare LF,
   else LF.
4. **Normalize to LF** for matching (handles files written on Windows by an
   LLM that emitted LF-only edits, and vice versa).
5. **Probe** each edit. If any probe needs fuzzy matching, the file base is
   normalized into fuzzy space before matching and applying edits — see below.
6. **Match** each edit against the (possibly fuzzy) base. Reject if any
   `old` is missing or matches more than once.
7. **Sort by position** and reject overlapping edits.
8. **Apply in reverse order** so earlier match indices stay valid as later
   edits modify the string.
9. **Reject** if the result equals the base (no-op edits are bugs).
10. **Restore line endings**, prepend the BOM, **atomically write** to disk.

### Match-against-original semantics

Every `old` is matched against the **original file content**, not the
intermediate state after preceding edits. This prevents the LLM from making
edits that depend on each other's effects — a common source of bugs in
naive multi-edit implementations.

The practical consequence: if two edits would touch the same region, the
model must merge them into one edit instead.

### Fuzzy matching

Pure exact matching breaks on a long tail of LLM transcription errors:
smart quotes, em/en dashes, non-breaking spaces, trailing whitespace,
combining characters. Pure fuzzy matching is too lenient — it can change
semantically meaningful whitespace.

The compromise:

1. Try `str.find` first (exact).
2. If that misses, normalize both strings via NFKC + a curated set of
   substitutions (smart quotes → ASCII, exotic dashes → `-`, special
   spaces → regular space, trailing whitespace stripped per line) and try
   again.
3. If **any** edit needed fuzzy matching, normalize the **file base** into
   fuzzy space before applying any edits.

The all-or-nothing file-base fuzzy rewrite is intentional. Mixing exact and
fuzzy regions from the original file produces surprising diffs (parts of the
file change normalization, parts don't). Replacement text is inserted exactly
as supplied by the caller; it is not fuzzy-normalized. This matches the
prior-art behavior while keeping any incidental normalization visible in the
diff for review.

### Line ending preservation

CRLF files stay CRLF. LF files stay LF. The model can emit either kind in
its `old`/`new` strings — both get normalized to LF for matching, then the
output is re-encoded to the file's original ending.

This means an LLM that has internalized "always emit LF" will Just Work on
Windows-edited files, and vice versa.

### BOM handling

If the file starts with a UTF-8 BOM (`\ufeff`), it's stripped before
matching and restored on write. The model never has to know the BOM exists
— its `old` strings can ignore it.

### Atomic writes

Edits go through `tempfile + os.fsync + os.replace` in the same directory.
This means:

- A failure mid-write never leaves a half-written file.
- Concurrent readers see either the old content or the new content,
  never a torn intermediate.
- File mode bits are preserved (the destination's mode is copied to the
  tempfile before the rename).

`open(..., newline="")` ensures Python performs no line-ending translation
of its own — we have already encoded the desired endings into the content.

### Per-file locking

A `threading.Lock` per resolved real path serializes concurrent edits to
the same file. Edits to different files run in parallel. Symlinks pointing
to the same file share a lock.

By default this is in-process only, which fits the typical LLM agent use case
(single process, possibly many threads). Pass `cross_process_lock=True` to also
use a sibling advisory lock file for process-level serialization on platforms
with `fcntl.flock`.

### What we don't do

- **No diff/patch parsing.** This is a search/replace tool. If you want
  unified-diff input, parse it externally and convert to `Edit` objects.
- **No file creation or deletion.** Edits operate on existing files. Use
  the standard `pathlib` for create/delete.
- **No line-number-based addressing.** The whole point is to avoid them.
- **No retry on failure.** If an edit doesn't match, the caller (or the
  LLM that emitted it) gets a precise error and decides what to do.
- **No GitHub-style three-way merge.** This is for editing files you have
  read, not reconciling divergent versions.

---

## Failure modes & error messages

The errors are specific so the LLM (or the human caller) can recover:

| Error | When | What to do |
|---|---|---|
| `TextNotFoundError` | `old` not in file | Re-read the file, regenerate the edit |
| `AmbiguousMatchError` | `old` appears more than once (carries `.occurrences`) | Add more surrounding lines to `old` to make it unique |
| `OverlappingEditsError` | Two edits' matches overlap | Merge the edits into one |
| `EmptyOldTextError` | `old == ""` | Provide actual text to find |
| `NoChangesError` | `new == old` (effectively) | Something's wrong with the edit; re-examine |
| `FileNotFoundError` | path missing | The file needs to be created first; use `pathlib.Path.write_text` |
| `PermissionError` | filesystem says no | Check filesystem perms |

For `AmbiguousMatchError`, the message includes the occurrence count and
the file path. For multi-edit failures, the message identifies the failing
edit by index (`edits[3]`).

---

## Comparison with alternatives

| | This | unified diff (`patch`) | full file rewrite |
|---|---|---|---|
| Token cost (small change) | Low | Medium | High |
| Token cost (large change) | High | Low | High |
| LLM error rate | Low | High | Medium |
| Recoverable failures | Yes | No | N/A |
| Line numbers required | No | Yes | No |
| Handles whitespace quirks | Yes (fuzzy) | No (strict) | N/A |
| Multi-edit batching | Yes | Yes | N/A |
| Atomicity | Yes | Yes (with `--atomic`) | Yes |

For the typical "LLM edits a few regions of a code file" workload, this
design wins on every axis except very large changes (where a full rewrite
or a true diff is better). Most LLM agents handle "very large change" by
calling `write` instead, which is the right answer.

---

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# With coverage
uv run pytest --cov=patch_tool --cov-report=term-missing
```
