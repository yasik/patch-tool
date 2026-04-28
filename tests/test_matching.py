from patch_tool._matching import count_occurrences, fuzzy_find, occurrence_positions


class TestFuzzyFind:
    def test_exact_hit(self):
        m = fuzzy_find("hello world", "world")
        assert m.found
        assert m.index == 6
        assert m.length == 5
        assert m.used_fuzzy is False

    def test_exact_miss(self):
        m = fuzzy_find("hello world", "goodbye")
        assert not m.found
        assert m.index == -1
        assert m.used_fuzzy is False

    def test_fuzzy_smart_quotes(self):
        haystack = 'print("it\u2019s working")'
        needle = 'print("it\'s working")'
        m = fuzzy_find(haystack, needle)
        assert m.found
        assert m.used_fuzzy is True

    def test_fuzzy_em_dash(self):
        haystack = "result\u2014final"
        needle = "result-final"
        m = fuzzy_find(haystack, needle)
        assert m.found
        assert m.used_fuzzy is True

    def test_fuzzy_trailing_whitespace(self):
        # The file has trailing whitespace; the needle does not.
        haystack = "hello   \nworld"
        needle = "hello\nworld"
        m = fuzzy_find(haystack, needle)
        assert m.found
        assert m.used_fuzzy is True

    def test_accepts_precomputed_fuzzy_values(self):
        m = fuzzy_find(
            "unrelated",
            "needle",
            fuzzy_haystack="prefix needle suffix",
            fuzzy_needle="needle",
        )
        assert m.found
        assert m.index == 7
        assert m.used_fuzzy is True

    def test_exact_preferred_over_fuzzy(self):
        # When exact would match, fuzzy is not even considered.
        m = fuzzy_find("foo bar", "bar")
        assert m.used_fuzzy is False


class TestCountOccurrences:
    def test_unique(self):
        assert count_occurrences("a foo b", "foo") == 1

    def test_multiple(self):
        assert count_occurrences("foo foo foo", "foo") == 3

    def test_overlapping(self):
        assert count_occurrences("aaa", "aa") == 2

    def test_zero(self):
        assert count_occurrences("abc", "xyz") == 0

    def test_exact_count_does_not_include_fuzzy_equivalents(self):
        haystack = "it\u2019s and it's"
        assert count_occurrences(haystack, "it's") == 1

    def test_counted_in_fuzzy_space_when_requested(self):
        # Two occurrences that look different but are equivalent fuzzy.
        haystack = "it\u2019s and it's"
        assert count_occurrences(haystack, "it's", use_fuzzy=True) == 2

    def test_empty_needle(self):
        assert count_occurrences("anything", "") == 0


class TestOccurrencePositions:
    def test_returns_overlapping_positions(self):
        assert occurrence_positions("aaaa", "aa") == [0, 1, 2]

    def test_accepts_precomputed_fuzzy_values(self):
        assert occurrence_positions(
            "unrelated",
            "needle",
            use_fuzzy=True,
            fuzzy_haystack="needle needle",
            fuzzy_needle="needle",
        ) == [0, 7]
