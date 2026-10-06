"""Dose / waiting-period guard (CLAUDE.md rule 1, ADR-0016).

Born as the Phase 4 stop-gap; since Phase 6 (ADR-0016) it is the PERMANENT
backstop of a positive design: the model never writes a dose, so any
dose-shaped or waiting-period-shaped statement in text the farmer would read,
whether the recommendation, the reasoning or a quoted passage, turns the whole
answer into an abstention. A dose reaches a farmer only as a structured label
entry the code itself copied from a verified table (app/safety/agrochemical_lookup.py),
never as prose.

Why a research trial's rates are blocked too: the ingested corpus contains
real application rates (B. subtilis @ 4 g/L, Tilt 25% EC @ 1 mL/L, ...) as a
trial protocol, not label recommendations.

It is pattern matching, so it can MISS a phrasing it does not know. Phase 6
measured that (tests/test_dose_guard_adversarial.py): the Phase 4 patterns
caught 14 of 44 adversarial phrasings (household measures, percentages, "per
acre 500 g", "wait 21 days before you harvest", Hinglish). Two layers now:

  1. find_dose_statement(text): context-free patterns, widened by that
     measurement. Applied to the model's prose AND to quoted passages.
  2. find_ungrounded_application_number(text, allowed): in any sentence that
     talks about applying a chemical (or in EVERY sentence when the whole
     conversation is about chemicals), every number must already be in the
     evidence the model was given (the farmer's question, the farm record,
     weather, a computed water balance, a code-copied label entry), never in a
     retrieved passage. A phrasing no pattern knows still carries a number, and
     that number has no legitimate source. Applied to the model's prose only.

It is deliberately blunt: it will sometimes block harmless text. That is the
right direction to fail in. A vague quantity ("a little", "some") with no
number, number word or household unit is not seen.
"""
import re

from app.safety import number_grounding

_NUM = r"\d+(?:[.,]\d+)*"
_NUMWORD = (
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen"
    r"|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|half|quarter"
    r"|ek|do|teen|char|paanch|panch|chhe|chah|saat|aath|nau|das|bees|tees|chalis|pachas|sau|aadha|dedh|dhai"
    r"|एक|दो|तीन|चार|पांच|पाँच|छह|छः|सात|आठ|नौ|दस|बीस|तीस|चालीस|पचास|सौ|आधा|आधी|डेढ़|ढाई)"
)
_QTY = rf"(?:{_NUM}|{_NUMWORD})"
# A quantity: digits, or one or more number words ("two hundred", "thirty-five", "दो सौ").
_QTYS = rf"(?:{_NUM}|{_NUMWORD}(?:[\s-]+{_NUMWORD})*)"
# Units of an amount applied (mass / volume), English, Hinglish and Hindi.
_AMOUNT = (
    r"(?:mg|g|gm|gms|grams?|kgs?|kilo(?:gram)?s?|ml|mls|cc|millilit(?:re|er)s?|l|lit(?:re|er)s?|ltrs?|lt|oz"
    r"|ग्राम|किलो(?:ग्राम)?|मिली(?:लीटर)?|लीटर)"
)
# What the amount is applied per / into.
_BASE = (
    r"(?:l|lit(?:re|er)s?|ltrs?|lt|ha|hectares?|acres?|bigha|kgs?|plants?|tanks?|pumps?|m2|sq\.?\s*m|gallons?"
    r"|लीटर|हेक्टेयर|एकड़|पौधा|पौधे|टंकी|पंप)"
)
# A unit must end at the end of a word. \b is unreliable for Devanagari
# (vowel signs are not \w), so an explicit lookahead is used instead.
_END = r"(?![A-Za-zऀ-ॿ])"
_PER = r"(?:/|per|prati|प्रति)"
_IN = r"(?:in|into|with|for|me|mein|ke\s+liye|में|के\s+लिए)"
_ART = r"(?:(?:a|an|the)\s+)?"
_AI = r"(?:a\.?i\.?\s*)?"

_PATTERNS = [
    # 4 g/L · 5 ml per litre · 2 kg/ha · 1.5 kg a.i./ha · 3 gm prati litre · 4 ग्राम प्रति लीटर
    re.compile(rf"{_QTYS}\s*{_AMOUNT}{_END}\s*{_AI}{_PER}\s*(?:{_QTYS}\s*)?{_BASE}{_END}", re.I),
    # 10 ml in 10 litres of water · 20 ml for 10 litres · 30 grams for a 15 L pump
    re.compile(rf"{_QTYS}\s*{_AMOUNT}{_END}\s*{_IN}\s*{_ART}{_QTYS}\s*{_BASE}{_END}", re.I),
    # @ 4 g · @1 mL -- the trial protocol's own notation
    re.compile(rf"@\s*{_NUM}\s*{_AMOUNT}{_END}", re.I),
    # per acre 500 g · प्रति एकड़ 250 मिली · prati acre 500 gm
    re.compile(rf"{_PER}\s+(?:{_QTYS}\s*)?{_BASE}{_END}\s*(?:{_IN}\s*)?{_QTYS}\s*{_AMOUNT}{_END}", re.I),
    # एक एकड़ में 500 ग्राम · in one acre 500 g
    re.compile(rf"{_BASE}{_END}\s*{_IN}\s*{_QTYS}\s*{_AMOUNT}{_END}", re.I),
    # 0.1% solution · 2 percent solution · 0.5 प्रतिशत घोल · solution of 0.2 %
    re.compile(
        rf"{_NUM}\s*(?:%|percent|per\s*cent|प्रतिशत)\s*(?:w/v\s*|v/v\s*)?(?:solution|घोल|spray|mixture|concentration|strength)",
        re.I,
    ),
    re.compile(rf"(?:solution|घोल)\s+(?:of\s+|का\s+)?{_NUM}\s*(?:%|percent|per\s*cent|प्रतिशत)", re.I),
    # 100 ppm
    re.compile(rf"{_NUM}\s*ppm{_END}", re.I),
]

_DOSE_WORDS = re.compile(
    r"\b(?:dose|dosage|spray(?:ed|ing)?|apply|application rate|dalo|daalo|daalein|dalna|milao|milayein|chhidkav)\b"
    r"|मात्रा|छिड़काव|डालें|डालूँ|डालो|मिलाएं|मिलाकर",
    re.I,
)
_AMOUNT_ALONE = re.compile(rf"{_QTYS}\s*{_AMOUNT}{_END}", re.I)

# Kitchen measures used as doses ("two spoons per tank", "आधी बोतल प्रति एकड़").
_HOUSEHOLD = re.compile(
    r"\b(?:tsp|tbsp|teaspoons?|tablespoons?|spoons?|caps?|bottles?|cups?|glass|handful|pinch|sachets?|packets?"
    r"|chammach|dhakkan)\b|चम्मच|ढक्कन|बोतल|गिलास|मुट्ठी|पुड़िया",
    re.I,
)
_HOUSEHOLD_CONTEXT = re.compile(
    rf"{_BASE}{_END}|\b(?:tank|pump|litre|liter|acre|hectare)s?\b|{_DOSE_WORDS.pattern}", re.I
)

# Waiting periods. STRONG words mean a waiting period by themselves; WEAK words
# (harvest, pick, eat) only count in a sentence that also mentions spraying.
_WAITING_STRONG = re.compile(
    r"waiting period|pre-?\s?harvest|\bphi\b|withholding|re-?entry"
    r"|before\s+(?:you\s+|the\s+|we\s+)?(?:harvest|pick|picking|pluck|eat)|before harvest"
    r"|प्रतीक्षा अवधि|कटाई से पहले|तुड़ाई से पहले",
    re.I,
)
_WAITING_WEAK = re.compile(
    r"\b(?:harvest(?:ed|ing)?|pick(?:ed|ing)?|pluck(?:ed|ing)?|fruit|eat|khana|harvest)\b|तोड़|तुड़ाई|कटाई",
    re.I,
)
_SPRAY_WORDS = re.compile(
    r"\b(?:spray(?:ed|ing|s)?|sprayer|chhidkav|dawai|dawa)\b|छिड़काव|छिड़क|दवा|दवाई|कीटनाशक", re.I
)
_DAYS = re.compile(
    rf"{_QTY}\s*(?:days?|din|dino|दिन|hours?|hrs?|ghante|घंटे|weeks?|hafte|हफ्ते|हफ़्ते|सप्ताह)", re.I
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")

# "Talks about applying a chemical", for the grounded-number rule.
#
# "tank", "pump", "टंकी" and "पंप" are deliberately NOT here (removed 2026-10-05).
# They made a water-harvesting tank an application sentence: en-fact-007's valid
# answer ("a small water-harvesting tank (Jal Kund) ... 8-15 raised beds about
# 1 m wide") was withheld as a dose. A replay of the Phase 4 drafts caught it
# (behaviour accuracy 53/55 -> 51/55). Sprayer-tank doses are still caught by
# layer 1 (_BASE and the household-measure rule), and a chemical conversation
# checks every sentence regardless of this list. What is no longer caught is
# listed as gap-004 in evals/chemical_guard_cases.jsonl.
#
# The bare Hindi stem "मिला" is NOT here either (removed 2026-10-06). It matched every form of
# the verb, so a Hindi answer about a trial ("EG 203 को IPDM के साथ मिलाकर", "T4 में ... मिलाया
# गया") became an application sentence and its trial labels (203, 4) became "ungrounded doses":
# en-fact-001 and tab-003 were withheld in the `--language hi` run (the grounded-number rule counts
# no corpus numbers). Only the instruction forms stay (मिलाएं, मिलाओ, मिलाना, मिला दें ...).
# Removing the stem altogether leaked "१० लीटर पानी में २० मिली मिलाएँ।"
# (tests/test_dose_guard_hindi_digits.py), which is why the instruction forms are listed.
# What is no longer caught is recorded as gap-005 in evals/chemical_guard_cases.jsonl.
_APPLICATION_VOCAB = re.compile(
    r"\b(?:spray(?:ed|ing|s)?|sprayer|apply|applied|applying|application|drench(?:ed|ing)?|dose|dosage"
    r"|dilute[d]?|mix|mixing|pesticides?|fungicides?|insecticides?|herbicides?|chhidkav|dawai|dawa"
    r"|daalo|dalo|daalein|milao|ghol)\b"
    r"|छिड़काव|छिड़क|डाल|मिलाएं|मिलाएँ|मिलायें|मिलाओ|मिलाइए|मिलाना|मिला\s+दें|मिला\s+दो|घोल|दवा|दवाई|कीटनाशक|फफूंदनाशक|फफूँदनाशक|खरपतवारनाशक|मात्रा",
    re.I,
)

SAFE_ABSTAIN_REASON = "no_verified_dose_source"
# Bilingual, Hindi first (same convention as app/agent/finalize.py).
SAFE_MESSAGE = (
    "AgriAI अभी दवा (कीटनाशक) की मात्रा नहीं बता सकता, और न ही यह कि छिड़काव के बाद कितने "
    "दिन तक फसल न तोड़ें। यह जानकारी हमेशा दवा के पैकेट पर छपे लेबल से ही लें। ज़्यादा "
    "जानकारी के लिए कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।\n\n"
    "AgriAI cannot tell you a pesticide dose yet, or how many days to wait after spraying "
    "before harvesting. Always take this from the label printed on the product pack. For "
    "more help, ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551)."
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
        if _HOUSEHOLD.search(sentence) and _HOUSEHOLD_CONTEXT.search(sentence):
            return _HOUSEHOLD.search(sentence).group(0)  # type: ignore[union-attr]
        waiting = _WAITING_STRONG.search(sentence) or (
            _WAITING_WEAK.search(sentence) and _SPRAY_WORDS.search(sentence)
        )
        if waiting:
            m = _DAYS.search(sentence)
            if m:
                return m.group(0)
    return None


def find_ungrounded_application_number(
    text: str, allowed: frozenset[float], *, any_sentence: bool = False
) -> str | None:
    """In a sentence about applying a chemical, a number that is not in `allowed`
    (numbers the model may legitimately repeat: the farmer's question, the farm
    record, weather, a computed balance, a code-copied label entry; NOT
    retrieved passages). `any_sentence=True` (a chemical conversation) checks every
    sentence, because a dose can be phrased with no application word at all
    ("the product goes on at 750 over the plot"). Returns the sentence, or None."""
    allowed = allowed | number_grounding.HELPLINE_PARTS
    for sentence in _SENTENCE_SPLIT.split(text):
        if (any_sentence or _APPLICATION_VOCAB.search(sentence)) and number_grounding.numbers_in(sentence) - allowed:
            return sentence
    return None
