"""INTERIM dose / waiting-period guard -- Phase 4 stop-gap, NOT the Phase 6
safety layer, and not a substitute for it (decision, 2026-09-25).

Why it exists now: Phase 4 puts retrieved corpus text in front of the model,
and that corpus contains a research trial's real application rates
(B. subtilis @ 4 g/L, Tilt 25% EC @ 1 mL/L, ...). CLAUDE.md rule 1 allows a
dose or waiting period ONLY from the deterministic CIB&RC lookup, which does
not exist yet. So until Phase 6, ANY dose-shaped or waiting-period-shaped
statement in an answer -- recommendation, reasoning, or quoted evidence --
turns the whole answer into an abstention.

It is deliberately blunt. It will sometimes block harmless text (say, a
fertiliser quantity); that is the right direction to fail in. It is pattern
matching, so it can also MISS a dose phrased in a way the patterns do not
cover -- which is exactly why Phase 6 replaces it with positive verification
instead of pattern blocking. The dose_safety_abstention eval bucket measures
how often it misses.
"""
import re

_NUM = r"\d+(?:[.,]\d+)*"
# Units of an amount applied (mass / volume), English and Hindi.
_AMOUNT = (
    r"(?:mg|g|gm|gms|grams?|kgs?|kilo(?:gram)?s?|ml|mls|millilit(?:re|er)s?|l|lit(?:re|er)s?|ltrs?|lt|oz"
    r"|ग्राम|किलो(?:ग्राम)?|मिली(?:लीटर)?|लीटर)"
)
# What the amount is applied per / into.
_BASE = (
    r"(?:l|lit(?:re|er)s?|ltrs?|lt|ha|hectares?|acres?|bigha|kgs?|plants?|tanks?|pumps?|m2|sq\.?\s*m"
    r"|लीटर|हेक्टेयर|एकड़|पौधा|पौधे|टंकी)"
)
# A unit must end at the end of a word. \b is unreliable for Devanagari
# (vowel signs are not \w), so an explicit lookahead is used instead.
_END = r"(?![A-Za-zऀ-ॿ])"

_PATTERNS = [
    # 4 g/L · 5 ml per litre · 2 kg/ha · 4 ग्राम प्रति लीटर
    re.compile(rf"{_NUM}\s*{_AMOUNT}{_END}\s*(?:/|per|प्रति)\s*(?:{_NUM}\s*)?{_BASE}{_END}", re.I),
    # 10 ml in 10 litres of water · 10 मिली 10 लीटर में
    re.compile(rf"{_NUM}\s*{_AMOUNT}{_END}\s*(?:in|into|with|में)\s*{_NUM}\s*{_BASE}{_END}", re.I),
    # @ 4 g · @1 mL -- the trial protocol's own notation
    re.compile(rf"@\s*{_NUM}\s*{_AMOUNT}{_END}", re.I),
]

_DOSE_WORDS = re.compile(r"\b(?:dose|dosage|spray|apply|application rate)\b|मात्रा|छिड़काव|डालें|डालूँ", re.I)
_AMOUNT_ALONE = re.compile(rf"{_NUM}\s*{_AMOUNT}{_END}", re.I)

_WAITING_WORDS = re.compile(
    r"waiting period|pre-?harvest interval|\bPHI\b|before harvest|प्रतीक्षा अवधि|कटाई से पहले", re.I
)
_DAYS = re.compile(rf"{_NUM}\s*(?:days?|दिन)", re.I)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")

SAFE_ABSTAIN_REASON = "no_verified_dose_source"
SAFE_MESSAGE = (
    "AgriAI cannot give pesticide doses or waiting periods yet -- these must come from the "
    "official product label, and a verified label table is not part of the system yet. "
    "Please follow the label on the product, or ask your local KVK or the Kisan Call "
    "Centre (1800-180-1551)."
)


def find_dose_statement(text: str) -> str | None:
    """Returns the first offending fragment, or None if the text looks clean.
    Returning the fragment (not just True) makes a block explainable in logs
    and tests."""
    for pattern in _PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    for sentence in _SENTENCE_SPLIT.split(text):
        if _DOSE_WORDS.search(sentence):
            m = _AMOUNT_ALONE.search(sentence)
            if m:
                return m.group(0)
        if _WAITING_WORDS.search(sentence):
            m = _DAYS.search(sentence)
            if m:
                return m.group(0)
    return None
