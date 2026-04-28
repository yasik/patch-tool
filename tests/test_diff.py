from patch_tool._diff import generate_diff


def test_no_changes():
    diff, first = generate_diff("same\n", "same\n")
    assert diff == ""
    assert first is None


def test_single_line_change():
    old = "line 1\nline 2\nline 3\n"
    new = "line 1\nLINE 2\nline 3\n"
    diff, first = generate_diff(old, new)
    assert first == 2
    assert "-2 line 2" in diff
    assert "+2 LINE 2" in diff
    assert " 1 line 1" in diff
    assert " 3 line 3" in diff


def test_insertion_at_end():
    old = "a\nb\n"
    new = "a\nb\nc\n"
    diff, first = generate_diff(old, new)
    assert first == 3
    assert "+3 c" in diff


def test_deletion():
    old = "a\nb\nc\n"
    new = "a\nc\n"
    diff, first = generate_diff(old, new)
    assert first == 2
    assert "-2 b" in diff


def test_context_lines_truncated():
    # Two changes far apart should show ... between.
    old_lines = [f"line {i}" for i in range(1, 21)]
    new_lines = old_lines.copy()
    new_lines[1] = "EDITED 2"
    new_lines[18] = "EDITED 19"
    diff, first = generate_diff("\n".join(old_lines), "\n".join(new_lines))
    assert first == 2
    assert "..." in diff
    assert "EDITED 2" in diff
    assert "EDITED 19" in diff


def test_line_numbers_aligned():
    # 100 lines → 3-char width.
    old = "\n".join(f"l{i}" for i in range(1, 101))
    new = old.replace("l50", "EDITED")
    diff, first = generate_diff(old, new)
    assert first == 50
    # Line 50 entries should have 3-digit padding.
    assert " 50 EDITED" in diff or "+50 EDITED" in diff
