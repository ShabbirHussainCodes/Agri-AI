"""Which numbers in a piece of text are NOT in the evidence the model was given.

Deterministic, no LLM. The Turn B prompt says "never state a number that is
not present in the evidence"; until now nothing checked it. Irrigation answers
(ADR-0015) are mostly numbers the farmer will act on (mm, days), so they are
checked here: a number in the answer that is nowhere in the farm record, the
weather, the water balance, a validated quote or the farmer's own question is
treated as invented.

What it can and cannot see:
  * DIGITS only, ASCII and Devanagari. A number written as a word ("two days")
    is not checked.
  * Comparison is exact on the numeric value: "50" matches "50.0", "49.96" does
    not match 50.0. The evidence numbers are already rounded for display, so the
    model is told to copy them. A rounded paraphrase is therefore flagged: that
    fails safe (the code-authored message is shown instead) and the eval
    measures how often it happens.
  * Not counted as numbers: digits glued to a letter before them ("ET0", "H2O"),
    list markers at the start of a line ("1." / "2)"), and the three groups of
    the Kisan Call Centre number 1800-180-1551, which every abstention message
    carries.
"""
import re
from collections.abc import Iterable

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_LIST_MARKER = re.compile(r"^\s*\d+[.)]\s+", re.M)
# A run of digits, dots and commas that starts at a digit not preceded by a
# letter and ends on a digit.
_TOKEN = re.compile(r"(?<![A-Za-z])\d(?:[\d.,]*\d)?")
_THOUSANDS = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")

# 1800-180-1551 (Kisan Call Centre), the helpline every code message carries.
HELPLINE_PARTS = frozenset({1800.0, 180.0, 1551.0})


def _parts(token: str) -> list[str]:
    """One matched run -> the numbers inside it. "1,200" is one number;
    "5,6" is two; "08.10.2026" (a date) is three; "3.5" is one."""
    if _THOUSANDS.match(token):
        return [token.replace(",", "")]
    parts: list[str] = []
    for piece in token.split(","):
        parts.extend(piece.split(".") if piece.count(".") > 1 else [piece])
    return parts


def numbers_in(text: str) -> set[float]:
    text = _LIST_MARKER.sub("", text.translate(_DEVANAGARI_DIGITS))
    found: set[float] = set()
    for token in _TOKEN.findall(text):
        for part in _parts(token):
            found.add(round(float(part), 6))
    return found


def ungrounded_numbers(texts: Iterable[str], evidence: Iterable[str]) -> list[float]:
    """Numbers used in `texts` that appear in none of `evidence`, sorted."""
    allowed = set(HELPLINE_PARTS)
    for e in evidence:
        allowed |= numbers_in(e)
    used: set[float] = set()
    for t in texts:
        used |= numbers_in(t)
    return sorted(used - allowed)
