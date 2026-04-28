from patch_tool.normalization import (
    BOM,
    detect_line_ending,
    normalize_for_fuzzy_match,
    normalize_to_lf,
    restore_line_endings,
    strip_bom,
)


class TestStripBom:
    def test_with_bom(self):
        bom, body = strip_bom(BOM + "hello")
        assert bom == BOM
        assert body == "hello"

    def test_without_bom(self):
        bom, body = strip_bom("hello")
        assert bom == ""
        assert body == "hello"

    def test_empty(self):
        bom, body = strip_bom("")
        assert bom == ""
        assert body == ""


class TestDetectLineEnding:
    def test_lf_only(self):
        assert detect_line_ending("a\nb\nc") == "\n"

    def test_crlf_only(self):
        assert detect_line_ending("a\r\nb\r\nc") == "\r\n"

    def test_no_newlines(self):
        assert detect_line_ending("hello") == "\n"

    def test_crlf_first_then_lf(self):
        # Mixed, but CRLF appears first → CRLF wins.
        assert detect_line_ending("a\r\nb\nc") == "\r\n"

    def test_lf_first_then_crlf(self):
        # LF appears first → LF wins.
        assert detect_line_ending("a\nb\r\nc") == "\n"


class TestNormalizeToLf:
    def test_crlf_to_lf(self):
        assert normalize_to_lf("a\r\nb") == "a\nb"

    def test_lone_cr_to_lf(self):
        assert normalize_to_lf("a\rb") == "a\nb"

    def test_mixed(self):
        assert normalize_to_lf("a\r\nb\rc\nd") == "a\nb\nc\nd"

    def test_idempotent(self):
        text = "a\nb\nc"
        assert normalize_to_lf(text) == text


class TestRestoreLineEndings:
    def test_to_crlf(self):
        assert restore_line_endings("a\nb\n", "\r\n") == "a\r\nb\r\n"

    def test_keep_lf(self):
        assert restore_line_endings("a\nb\n", "\n") == "a\nb\n"


class TestFuzzyNormalize:
    def test_smart_single_quotes(self):
        assert normalize_for_fuzzy_match("it\u2019s") == "it's"

    def test_smart_double_quotes(self):
        assert normalize_for_fuzzy_match("\u201chello\u201d") == '"hello"'

    def test_em_dash(self):
        assert normalize_for_fuzzy_match("a\u2014b") == "a-b"

    def test_en_dash(self):
        assert normalize_for_fuzzy_match("a\u2013b") == "a-b"

    def test_minus_sign(self):
        assert normalize_for_fuzzy_match("a\u2212b") == "a-b"

    def test_nbsp(self):
        assert normalize_for_fuzzy_match("a\u00a0b") == "a b"

    def test_trailing_whitespace_stripped(self):
        assert normalize_for_fuzzy_match("hello   \nworld\t") == "hello\nworld"

    def test_nfkc(self):
        # \u00e9 (é precomposed) and \u0065\u0301 (e + combining acute)
        # both normalize to \u00e9 under NFKC.
        assert normalize_for_fuzzy_match("\u0065\u0301") == "\u00e9"

    def test_combination(self):
        text = "\u201chello\u2019s\u201d \u2014 world\u00a0!  "
        assert normalize_for_fuzzy_match(text) == '"hello\'s" - world !'
