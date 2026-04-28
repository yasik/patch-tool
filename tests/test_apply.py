from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from patch_tool import (
    AmbiguousMatchError,
    Edit,
    EmptyOldTextError,
    NoChangesError,
    OverlappingEditsError,
    TextNotFoundError,
)
from patch_tool import apply as apply_module
from patch_tool import (
    apply_edits,
    preview_edits,
)


class TestSingleEdit:
    def test_basic_replacement(self, tmp_file):
        path = tmp_file("a.txt", "hello world\n")
        result = apply_edits(path, [Edit("hello", "goodbye")])
        assert result.written
        assert result.edits_applied == 1
        assert result.used_fuzzy_match is False
        assert path.read_bytes() == b"goodbye world\n"
        assert "-1 hello world" in result.diff
        assert "+1 goodbye world" in result.diff

    def test_tuple_form(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        apply_edits(path, [("x", "y")])
        assert path.read_bytes() == b"y\n"

    def test_dict_form(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        apply_edits(path, [{"old": "x", "new": "y"}])
        assert path.read_bytes() == b"y\n"

    def test_deletion(self, tmp_file):
        path = tmp_file("a.txt", "before\nDELETE_ME\nafter\n")
        apply_edits(path, [Edit("DELETE_ME\n", "")])
        assert path.read_bytes() == b"before\nafter\n"

    def test_insertion(self, tmp_file):
        path = tmp_file("a.txt", "a\nc\n")
        apply_edits(path, [Edit("a\nc\n", "a\nb\nc\n")])
        assert path.read_bytes() == b"a\nb\nc\n"


class TestMultipleEdits:
    def test_disjoint_edits(self, tmp_file):
        path = tmp_file("a.txt", "alpha\nbeta\ngamma\n")
        apply_edits(
            path,
            [Edit("alpha", "ALPHA"), Edit("gamma", "GAMMA")],
        )
        assert path.read_bytes() == b"ALPHA\nbeta\nGAMMA\n"

    def test_edits_apply_against_original_not_incrementally(self, tmp_file):
        # If edits applied incrementally, the second edit's "FIRST" wouldn't
        # exist (the first edit replaced it). But edits match the original,
        # so this fails as text-not-found, not as incremental drift.
        path = tmp_file("a.txt", "FIRST\nSECOND\n")
        with pytest.raises(TextNotFoundError):
            apply_edits(
                path,
                [Edit("FIRST", "ONE"), Edit("ONE", "DONE")],
            )

    def test_overlapping_edits_rejected(self, tmp_file):
        path = tmp_file("a.txt", "foobar\n")
        with pytest.raises(OverlappingEditsError) as exc:
            apply_edits(
                path,
                [Edit("foob", "X"), Edit("ooba", "Y")],
            )
        assert exc.value.path == path.resolve()
        assert exc.value.edit_index == 0
        assert exc.value.other_edit_index == 1

    def test_adjacent_non_overlapping_ok(self, tmp_file):
        path = tmp_file("a.txt", "abcdef\n")
        apply_edits(
            path,
            [Edit("abc", "ABC"), Edit("def", "DEF")],
        )
        assert path.read_bytes() == b"ABCDEF\n"

    def test_ten_edits(self, tmp_file):
        body = "\n".join(f"line{i}" for i in range(10)) + "\n"
        path = tmp_file("a.txt", body)
        edits = [Edit(f"line{i}", f"LINE{i}") for i in range(10)]
        result = apply_edits(path, edits)
        assert result.edits_applied == 10
        for i in range(10):
            assert f"LINE{i}".encode() in path.read_bytes()


class TestErrors:
    def test_empty_old_rejected(self, tmp_file):
        path = tmp_file("a.txt", "stuff\n")
        with pytest.raises(EmptyOldTextError) as exc:
            apply_edits(path, [Edit("", "x")])
        assert exc.value.path == path.resolve()
        assert exc.value.edit_index == 0

    def test_text_not_found(self, tmp_file):
        path = tmp_file("a.txt", "stuff\n")
        with pytest.raises(TextNotFoundError, match="structural whitespace") as exc:
            apply_edits(path, [Edit("missing", "x")])
        assert exc.value.path == path.resolve()
        assert exc.value.edit_index == 0
        assert exc.value.old == "missing"

    def test_ambiguous_match(self, tmp_file):
        path = tmp_file("a.txt", "foo foo foo\n")
        with pytest.raises(AmbiguousMatchError) as exc:
            apply_edits(path, [Edit("foo", "FOO")])
        assert exc.value.occurrences == 3
        assert exc.value.positions == [0, 4, 8]
        assert exc.value.path == path.resolve()
        assert exc.value.edit_index == 0
        assert exc.value.old == "foo"

    def test_overlapping_occurrences_are_ambiguous(self, tmp_file):
        path = tmp_file("a.txt", "aaa\n")
        with pytest.raises(AmbiguousMatchError) as exc:
            apply_edits(path, [Edit("aa", "X")])
        assert exc.value.occurrences == 2
        assert exc.value.positions == [0, 1]

    def test_exact_unique_match_ignores_fuzzy_equivalent_occurrences(self, tmp_file):
        path = tmp_file("a.txt", 'print(\u201chello\u201d)\nprint("hello")\n')
        result = apply_edits(path, [Edit('print("hello")', 'print("HELLO")')])
        assert result.used_fuzzy_match is False
        assert path.read_text(encoding="utf-8") == (
            'print(\u201chello\u201d)\nprint("HELLO")\n'
        )

    def test_fuzzy_equivalent_occurrences_are_ambiguous_for_fuzzy_match(self, tmp_file):
        path = tmp_file("a.txt", "print(\u201chello\u201d)\nprint(\u201ehello\u201f)\n")
        with pytest.raises(AmbiguousMatchError) as exc:
            apply_edits(path, [Edit('print("hello")', 'print("HELLO")')])
        assert exc.value.occurrences == 2

    def test_no_changes(self, tmp_file):
        path = tmp_file("a.txt", "stuff\n")
        with pytest.raises(NoChangesError) as exc:
            apply_edits(path, [Edit("stuff", "stuff")])
        assert exc.value.path == path.resolve()
        assert exc.value.edit_index == 0

    def test_noop_edit_in_multi_edit_write_rejected(self, tmp_file):
        path = tmp_file("a.txt", "alpha\nbeta\n")
        with pytest.raises(NoChangesError, match=r"edits\[0\]"):
            apply_edits(
                path,
                [Edit("alpha", "alpha"), Edit("beta", "BETA")],
            )
        assert path.read_bytes() == b"alpha\nbeta\n"

    def test_fuzzy_equivalent_noop_write_rejected(self, tmp_file):
        path = tmp_file("a.txt", "before\u2014after\n")
        with pytest.raises(NoChangesError, match="fuzzy normalization"):
            apply_edits(path, [Edit("before-after", "before\u2014after")])
        assert path.read_text(encoding="utf-8") == "before\u2014after\n"

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            apply_edits(tmp_path / "missing.txt", [Edit("a", "b")])

    def test_empty_edits_list(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        with pytest.raises(ValueError):
            apply_edits(path, [])

    def test_invalid_edit_type(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        with pytest.raises(TypeError, match="expected Edit"):
            apply_edits(path, [42])  # type: ignore[list-item]

    def test_invalid_tuple_length(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        with pytest.raises(TypeError, match="tuple must be"):
            apply_edits(path, [("only-one",)])  # type: ignore[list-item]

    def test_invalid_tuple_item_types(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        with pytest.raises(TypeError, match="tuple items must be str"):
            apply_edits(path, [("a", 42)])  # type: ignore[list-item]

    def test_mapping_missing_keys(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        with pytest.raises(TypeError, match="mapping must have"):
            apply_edits(path, [{"old": "x"}])  # type: ignore[list-item]

    def test_mapping_non_str_values(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        with pytest.raises(TypeError, match="must be str"):
            apply_edits(path, [{"old": "x", "new": 42}])  # type: ignore[list-item]

    def test_failed_edit_does_not_modify_file(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "untouched\n")
        with pytest.raises(TextNotFoundError):
            apply_edits(path, [Edit("missing", "x")])
        assert read_bytes(path) == b"untouched\n"


class TestLineEndings:
    def test_lf_preserved(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "a\nb\nc\n")
        apply_edits(path, [Edit("b", "B")])
        assert read_bytes(path) == b"a\nB\nc\n"

    def test_crlf_preserved(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "a\r\nb\r\nc\r\n")
        apply_edits(path, [Edit("b", "B")])
        assert read_bytes(path) == b"a\r\nB\r\nc\r\n"

    def test_crlf_with_lf_in_edit_text(self, tmp_file, read_bytes):
        # The edit text uses LF; the file uses CRLF. Should still match
        # and the output should use CRLF throughout.
        path = tmp_file("a.txt", "alpha\r\nbeta\r\ngamma\r\n")
        apply_edits(path, [Edit("alpha\nbeta", "ALPHA\nBETA")])
        assert read_bytes(path) == b"ALPHA\r\nBETA\r\ngamma\r\n"

    def test_no_trailing_newline(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "no eol")
        apply_edits(path, [Edit("no eol", "yes eol")])
        assert read_bytes(path) == b"yes eol"


class TestBom:
    def test_bom_preserved(self, tmp_file, read_bytes):
        bom = b"\xef\xbb\xbf"
        path = tmp_file("a.txt", "")
        # Write raw with BOM.
        path.write_bytes(bom + b"hello\n")
        apply_edits(path, [Edit("hello", "world")])
        assert read_bytes(path) == bom + b"world\n"

    def test_bom_not_required_in_old_text(self, tmp_file):
        bom = b"\xef\xbb\xbf"
        path = Path(tmp_file("a.txt", ""))
        path.write_bytes(bom + b"start text\n")
        # The LLM-emitted oldText would not include the invisible BOM.
        apply_edits(path, [Edit("start", "begin")])
        assert path.read_bytes() == bom + b"begin text\n"


class TestFuzzyMatching:
    def test_smart_quotes(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "print(\u201chello\u201d)\n")
        result = apply_edits(path, [Edit('print("hello")', 'print("HELLO")')])
        assert result.used_fuzzy_match is True
        # Output is in fuzzy space — quotes are normalized.
        assert read_bytes(path) == b'print("HELLO")\n'

    def test_em_dash(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "before\u2014after\n")
        apply_edits(path, [Edit("before-after", "BEFORE-AFTER")])
        assert read_bytes(path) == b"BEFORE-AFTER\n"

    def test_nbsp(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "hello\u00a0world\n")
        apply_edits(path, [Edit("hello world", "HELLO WORLD")])
        assert read_bytes(path) == b"HELLO WORLD\n"

    def test_one_fuzzy_normalizes_whole_file(self, tmp_file, read_bytes):
        # Edit 1 needs fuzzy (smart quote), edit 2 is exact. The file's
        # OTHER smart quotes (not in either edit) get normalized too.
        path = tmp_file(
            "a.txt",
            "first \u201cfuzzy\u201d\nsecond exact\nthird \u2014 dash\n",
        )
        apply_edits(
            path,
            [
                Edit('"fuzzy"', "FUZZY"),
                Edit("second exact", "SECOND EXACT"),
            ],
        )
        # The em-dash on the third line should also be normalized to "-".
        assert read_bytes(path) == b"first FUZZY\nSECOND EXACT\nthird - dash\n"

    def test_fuzzy_match_inserts_new_text_verbatim(self, tmp_file):
        path = tmp_file(
            "a.txt",
            "before\u2014after\nother \u201cquote\u201d\n",
        )
        result = apply_edits(
            path, [Edit("before-after", "replacement \u201cvalue\u201d")]
        )
        assert result.used_fuzzy_match is True
        assert path.read_text(encoding="utf-8") == (
            'replacement \u201cvalue\u201d\nother "quote"\n'
        )

    def test_fuzzy_flag_false_when_all_exact(self, tmp_file):
        path = tmp_file("a.txt", "ascii only\n")
        result = apply_edits(path, [Edit("ascii", "ASCII")])
        assert result.used_fuzzy_match is False


class TestDryRun:
    def test_dry_run_does_not_write(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "before\n")
        result = apply_edits(path, [Edit("before", "after")], dry_run=True)
        assert result.written is False
        assert "before" in result.diff and "after" in result.diff
        assert read_bytes(path) == b"before\n"

    def test_preview_alias(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "x\n")
        result = preview_edits(path, [Edit("x", "y")])
        assert result.written is False
        assert read_bytes(path) == b"x\n"

    def test_dry_run_no_changes_returns_no_change_result(self, tmp_file, read_bytes):
        path = tmp_file("a.txt", "same\n")
        result = apply_edits(path, [Edit("same", "same")], dry_run=True)
        assert result.diff == ""
        assert result.first_changed_line is None
        assert result.edits_applied == 0
        assert result.written is False
        assert read_bytes(path) == b"same\n"

    def test_dry_run_fuzzy_equivalent_noop_returns_no_change_result(self, tmp_file):
        path = tmp_file("a.txt", "before\u2014after\n")
        result = apply_edits(
            path,
            [Edit("before-after", "before\u2014after")],
            dry_run=True,
        )
        assert result.used_fuzzy_match is True
        assert result.diff == ""
        assert result.first_changed_line is None
        assert result.edits_applied == 0


class TestAtomicWrite:
    def test_no_temp_file_left_behind_on_success(self, tmp_file):
        path = tmp_file("a.txt", "hello\n")
        apply_edits(path, [Edit("hello", "world")])
        siblings = list(path.parent.iterdir())
        assert siblings == [path]

    def test_file_mode_preserved(self, tmp_file):
        path = tmp_file("a.txt", "hello\n")
        os.chmod(path, 0o640)
        apply_edits(path, [Edit("hello", "world")])
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o640

    def test_temp_file_removed_when_replace_fails(self, tmp_file, monkeypatch):
        path = tmp_file("a.txt", "hello\n")

        def fail_replace(src, dst):
            raise OSError("replace failed")

        monkeypatch.setattr(apply_module.os, "replace", fail_replace)

        with pytest.raises(OSError, match="replace failed"):
            apply_edits(path, [Edit("hello", "world")])

        assert path.read_bytes() == b"hello\n"
        assert list(path.parent.iterdir()) == [path]

    def test_parent_directory_fsynced_after_replace(self, tmp_file, monkeypatch):
        path = tmp_file("a.txt", "hello\n")

        synced = []

        def record_fsync_directory(parent):
            synced.append(parent)

        monkeypatch.setattr(apply_module, "_fsync_directory", record_fsync_directory)

        apply_edits(path, [Edit("hello", "world")])

        assert synced == [path.parent]

    def test_replaces_in_place(self, tmp_file):
        path = tmp_file("a.txt", "old\n")
        # Capture inode before. After atomic replace it will change, which
        # is fine — we just want to verify the path still resolves.
        apply_edits(path, [Edit("old", "new")])
        assert path.exists()
        assert path.read_bytes() == b"new\n"


class TestPathHandling:
    def test_str_path_accepted(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        apply_edits(str(path), [Edit("x", "y")])
        assert path.read_bytes() == b"y\n"

    def test_relative_path_resolves(self, tmp_path, monkeypatch):
        path = tmp_path / "a.txt"
        path.write_bytes(b"x\n")
        monkeypatch.chdir(tmp_path)
        result = apply_edits("a.txt", [Edit("x", "y")])
        assert result.path == path.resolve()
        assert path.read_bytes() == b"y\n"

    def test_returned_path_is_resolved(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        result = apply_edits(path, [Edit("x", "y")])
        assert result.path.is_absolute()


class TestErrorMessages:
    def test_single_edit_uses_singular_phrasing(self, tmp_file):
        path = tmp_file("a.txt", "x\n")
        with pytest.raises(TextNotFoundError, match="the text"):
            apply_edits(path, [Edit("missing", "y")])

    def test_multi_edit_indexes_in_messages(self, tmp_file):
        path = tmp_file("a.txt", "alpha\n")
        with pytest.raises(TextNotFoundError, match=r"edits\[1\]"):
            apply_edits(
                path,
                [Edit("alpha", "ALPHA"), Edit("missing", "x")],
            )
