"""Public text editing reuses the file engine without filesystem access."""

from pathlib import Path

import pytest

from patch_tool import (
    Edit,
    NoChangesError,
    TextNotFoundError,
    apply_edits,
    apply_edits_to_text,
)


@pytest.mark.parametrize(
    "content", ["old\n", "old\r\n", "\ufeffold\r\n", "old", "before\nold\nafter\n"]
)
def test_text_and_file_operations_have_identical_results(
    tmp_path: Path, content: str
) -> None:
    target = tmp_path / "note"
    target.write_bytes(content.encode())
    edits = [Edit("old", "new")]
    text_result = apply_edits_to_text(content, edits)
    file_result = apply_edits(target, edits)
    assert target.read_bytes() == text_result.content.encode()
    assert file_result.diff == text_result.diff
    assert file_result.first_changed_line == text_result.first_changed_line
    assert file_result.edits_applied == text_result.edits_applied
    assert file_result.used_fuzzy_match == text_result.used_fuzzy_match


def test_text_operation_never_resolves_or_opens_a_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("local file access")

    monkeypatch.setattr("builtins.open", unexpected)
    monkeypatch.setattr(Path, "resolve", unexpected)
    result = apply_edits_to_text("old\n", [Edit("old", "new")], path_hint="tenant/note")
    assert result.content == "new\n"


def test_text_operation_preserves_failures_and_preview_behavior() -> None:
    with pytest.raises(TextNotFoundError):
        apply_edits_to_text("old", [Edit("missing", "new")])
    with pytest.raises(NoChangesError):
        apply_edits_to_text("old", [Edit("old", "old")])
    assert (
        apply_edits_to_text(
            "old", [Edit("old", "old")], allow_no_changes=True
        ).edits_applied
        == 0
    )
