"""Pure unit tests for code-level citation validation (ADR-0013)."""
from app.retrieval.citations import MIN_QUOTE_WORDS, Citation, check_citation, normalise

from ._chunks import make_chunk

PASSAGES = [
    make_chunk("Two eggplant accessions, EG 203 and TS 03, were used as\nbacterial wilt resistant rootstocks."),
    make_chunk("Mandla district receives about 1,300 millimetres of rainfall a year."),
]


def test_exact_quote_passes():
    check = check_citation(Citation(passage=1, quote="EG 203 and TS 03, were used"), PASSAGES)
    assert check.ok and check.chunk is PASSAGES[0]


def test_line_breaks_case_and_curly_quotes_are_forgiven():
    check = check_citation(Citation(passage=1, quote="“Were used as Bacterial wilt resistant”"), PASSAGES)
    assert check.ok


def test_fabricated_quote_fails():
    check = check_citation(Citation(passage=1, quote="EG 203 doubled the yield of tomato"), PASSAGES)
    assert not check.ok and "not found" in check.reason


def test_right_quote_wrong_passage_fails():
    check = check_citation(Citation(passage=2, quote="EG 203 and TS 03, were used"), PASSAGES)
    assert not check.ok


def test_passage_number_that_was_never_shown_fails():
    for n in (0, 3, -1):
        assert not check_citation(Citation(passage=n, quote="Mandla district receives about"), PASSAGES).ok


def test_too_short_quote_fails():
    short = " ".join(["EG", "203", "and"][: MIN_QUOTE_WORDS - 1])
    check = check_citation(Citation(passage=1, quote=short), PASSAGES)
    assert not check.ok and "shorter" in check.reason


def test_a_changed_word_is_a_mismatch():
    # "roughly" instead of "about": same meaning, not a verbatim quote.
    assert not check_citation(Citation(passage=2, quote="receives roughly 1,300 millimetres of rainfall"), PASSAGES).ok


def test_normalise_collapses_whitespace_and_case():
    assert normalise("  EG\n203\t AND ") == "eg 203 and"
