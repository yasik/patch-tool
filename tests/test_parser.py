import pytest

from patch_tool import Edit, ParseError, parse_aider_blocks, parse_blocks


class TestParseBlocks:
    def test_single_block(self):
        text = (
            "<<<<<<< SEARCH\n" "old line\n" "=======\n" "new line\n" ">>>>>>> REPLACE\n"
        )
        edits = parse_blocks(text)
        assert edits == [Edit(old="old line", new="new line")]

    def test_multiple_blocks(self):
        text = (
            "<<<<<<< SEARCH\n"
            "a\n"
            "=======\n"
            "A\n"
            ">>>>>>> REPLACE\n"
            "some commentary in between\n"
            "<<<<<<< SEARCH\n"
            "b\n"
            "=======\n"
            "B\n"
            ">>>>>>> REPLACE\n"
        )
        edits = parse_blocks(text)
        assert edits == [Edit("a", "A"), Edit("b", "B")]

    def test_multiline_search_replace(self):
        text = (
            "<<<<<<< SEARCH\n"
            "def foo():\n"
            "    return 1\n"
            "=======\n"
            "def foo():\n"
            "    return 2\n"
            ">>>>>>> REPLACE\n"
        )
        edits = parse_blocks(text)
        assert edits == [Edit("def foo():\n    return 1", "def foo():\n    return 2")]

    def test_empty_replace(self):
        text = "<<<<<<< SEARCH\n" "delete me\n" "=======\n" ">>>>>>> REPLACE\n"
        edits = parse_blocks(text)
        assert edits == [Edit("delete me", "")]

    def test_empty_search_parses_but_will_fail_when_applied(self):
        # The parser doesn't reject empty SEARCH — that's the apply layer's job.
        text = "<<<<<<< SEARCH\n" "=======\n" "new\n" ">>>>>>> REPLACE\n"
        edits = parse_blocks(text)
        assert edits == [Edit("", "new")]

    def test_unterminated_search_raises(self):
        text = "<<<<<<< SEARCH\nold\n"
        with pytest.raises(ParseError, match="missing '======='") as exc:
            parse_blocks(text)
        assert exc.value.line == 1

    def test_unterminated_replace_raises(self):
        text = "<<<<<<< SEARCH\nold\n=======\nnew\n"
        with pytest.raises(ParseError, match="missing '>>>>>>> REPLACE'") as exc:
            parse_blocks(text)
        assert exc.value.line == 1

    def test_no_blocks(self):
        assert parse_blocks("just commentary\nno blocks here\n") == []

    def test_trailing_whitespace_on_markers(self):
        text = (
            "<<<<<<< SEARCH   \n" "old\n" "=======   \n" "new\n" ">>>>>>> REPLACE\t\n"
        )
        edits = parse_blocks(text)
        assert edits == [Edit("old", "new")]

    def test_crlf_block_body_is_normalized_to_lf(self):
        text = (
            "<<<<<<< SEARCH\r\n"
            "old line 1\r\n"
            "old line 2\r\n"
            "=======\r\n"
            "new line 1\r\n"
            "new line 2\r\n"
            ">>>>>>> REPLACE\r\n"
        )
        edits = parse_blocks(text)
        assert edits == [Edit("old line 1\nold line 2", "new line 1\nnew line 2")]

    def test_paths_ignored_in_bare_parser(self):
        text = (
            "src/foo.py\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
        )
        edits = parse_blocks(text)
        assert edits == [Edit("old", "new")]


class TestParseAiderBlocks:
    def test_single_block_with_path(self):
        text = (
            "src/foo.py\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
        )
        result = parse_aider_blocks(text)
        assert result == {"src/foo.py": [Edit("old", "new")]}

    def test_multiple_blocks_same_file(self):
        text = (
            "src/foo.py\n"
            "<<<<<<< SEARCH\n"
            "a\n"
            "=======\n"
            "A\n"
            ">>>>>>> REPLACE\n"
            "src/foo.py\n"
            "<<<<<<< SEARCH\n"
            "b\n"
            "=======\n"
            "B\n"
            ">>>>>>> REPLACE\n"
        )
        result = parse_aider_blocks(text)
        assert result == {"src/foo.py": [Edit("a", "A"), Edit("b", "B")]}

    def test_multiple_files(self):
        text = (
            "a.py\n"
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
            "b.py\n"
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
        )
        result = parse_aider_blocks(text)
        assert set(result.keys()) == {"a.py", "b.py"}
        assert result["a.py"] == [Edit("old", "new")]
        assert result["b.py"] == [Edit("old", "new")]

    def test_path_separated_by_blank_lines(self):
        text = (
            "src/foo.py\n"
            "\n"
            "\n"
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
        )
        result = parse_aider_blocks(text)
        assert result == {"src/foo.py": [Edit("old", "new")]}

    def test_path_skips_markdown_fence(self):
        text = (
            "src/foo.py\n"
            "```python\n"
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
            "```\n"
        )
        result = parse_aider_blocks(text)
        assert result == {"src/foo.py": [Edit("old", "new")]}

    def test_crlf_aider_block_body_is_normalized_to_lf(self):
        text = (
            "src/foo.py\r\n"
            "<<<<<<< SEARCH\r\n"
            "old\r\n"
            "=======\r\n"
            "new\r\n"
            ">>>>>>> REPLACE\r\n"
        )
        result = parse_aider_blocks(text)
        assert result == {"src/foo.py": [Edit("old", "new")]}

    def test_missing_path_raises(self):
        text = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
        with pytest.raises(ParseError, match="no preceding file path") as exc:
            parse_aider_blocks(text)
        assert exc.value.line == 1

    def test_prose_before_block_is_not_treated_as_path(self):
        text = (
            "Here are the edits I'm making:\n"
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
        )
        with pytest.raises(ParseError, match="no preceding file path"):
            parse_aider_blocks(text)

    def test_path_with_internal_whitespace_is_rejected(self):
        text = "src/my file.py\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
        with pytest.raises(ParseError, match="no preceding file path"):
            parse_aider_blocks(text)

    def test_path_ending_with_prose_punctuation_is_rejected(self):
        text = "src/foo.py:\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
        with pytest.raises(ParseError, match="no preceding file path"):
            parse_aider_blocks(text)

    def test_path_not_reused_across_blocks(self):
        # Second block has no path before it. Should fail.
        text = (
            "src/foo.py\n"
            "<<<<<<< SEARCH\nA\n=======\nB\n>>>>>>> REPLACE\n"
            "<<<<<<< SEARCH\nC\n=======\nD\n>>>>>>> REPLACE\n"
        )
        with pytest.raises(ParseError, match="no preceding file path"):
            parse_aider_blocks(text)
