"""Unified-style diff with line numbers and bounded context.

Output looks like::

      1 unchanged line
    -42 removed line
    +42 added line
      ...
     99 trailing context

Designed for terminal display. Not a valid ``patch(1)`` input — use ``difflib``
if you need that. The point here is human (and LLM) readable change summaries.
"""

import difflib

DEFAULT_CONTEXT_LINES = 4


def generate_diff(
    old: str,
    new: str,
    *,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> tuple[str, int | None]:
    """Return ``(diff_text, first_changed_line_in_new)``.

    ``first_changed_line_in_new`` is ``None`` when ``old == new``.
    """
    if old == new:
        return "", None

    old_lines = old.split("\n")
    new_lines = new.split("\n")
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)

    max_line = max(len(old_lines), len(new_lines))
    width = len(str(max(max_line, 1)))

    out: list[str] = []
    first_changed: int | None = None

    opcodes = matcher.get_opcodes()
    for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        next_is_change = idx + 1 < len(opcodes) and opcodes[idx + 1][0] != "equal"
        prev_is_change = idx > 0 and opcodes[idx - 1][0] != "equal"

        if tag == "equal":
            block = old_lines[i1:i2]
            if prev_is_change and next_is_change:
                if len(block) <= context_lines * 2:
                    for k, line in enumerate(block):
                        out.append(f" {str(i1 + 1 + k).rjust(width)} {line}")
                else:
                    head = block[:context_lines]
                    tail = block[-context_lines:]
                    for k, line in enumerate(head):
                        out.append(f" {str(i1 + 1 + k).rjust(width)} {line}")
                    out.append(f" {' ' * width} ...")
                    tail_start = i1 + len(block) - context_lines
                    for k, line in enumerate(tail):
                        out.append(f" {str(tail_start + 1 + k).rjust(width)} {line}")
            elif prev_is_change:
                shown = block[:context_lines]
                for k, line in enumerate(shown):
                    out.append(f" {str(i1 + 1 + k).rjust(width)} {line}")
                if len(block) > context_lines:
                    out.append(f" {' ' * width} ...")
            elif next_is_change:
                if len(block) > context_lines:
                    out.append(f" {' ' * width} ...")
                shown = block[-context_lines:]
                shown_start = i1 + len(block) - len(shown)
                for k, line in enumerate(shown):
                    out.append(f" {str(shown_start + 1 + k).rjust(width)} {line}")
            # else: equal block at start/end with no adjacent changes — skip
        else:
            if first_changed is None:
                first_changed = j1 + 1
            if tag in ("delete", "replace"):
                for k, line in enumerate(old_lines[i1:i2]):
                    out.append(f"-{str(i1 + 1 + k).rjust(width)} {line}")
            if tag in ("insert", "replace"):
                for k, line in enumerate(new_lines[j1:j2]):
                    out.append(f"+{str(j1 + 1 + k).rjust(width)} {line}")

    return "\n".join(out), first_changed
