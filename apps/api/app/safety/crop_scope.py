"""Crop scope: which crop a question is about, and which documents may be
used to answer it (ADR-0014).

Why this exists (unans-001, agent eval 2026-09-27): asked "When should I sow
wheat in Madhya Pradesh?", the model quoted two REAL sentences about Mandla
rainfall from a kitchen-garden manual and turned them into "sow wheat June-
September" -- the wrong season. Every citation validated, because citation
checking (app/retrieval/citations.py) proves a quote EXISTS, not that the
source is about the crop being asked. This module adds that second check,
deterministically, from human-curated metadata:

  * every document carries `crops_covered` -- the crops a human decided the
    document is actually a source FOR (ingest/sources.yaml, like the
    ADR-0012 domain review). Incidental mentions do not count: the kitchen-
    garden manual mentions wheat only as a PDS ration, and "black cotton
    soil" is a soil type, not cotton.
  * a question that names a crop may only be answered from passages of
    documents that cover that crop.

Deliberately NOT done here:
  * no crop is inferred from the farm record. "How much rain does Mandla
    get?" asked by a wheat farmer is not a wheat question.
  * no LLM. A crop word the lexicon does not know is not detected, so the
    check does not apply (fail-open for unknown words -- stated in ADR-0014).
    The lexicon is broad on purpose, and field crops the corpus does NOT
    cover are listed too, because detecting those is the point.

Pure functions, no I/O; tests/test_crop_scope.py.
"""
import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Protocol, TypeVar

# Canonical crop key -> surface forms (English incl. plurals, Hindi, Hinglish).
# Matching is on whole tokens (see _tokens), so short forms cannot match
# inside longer words.
#
# Left out on purpose because they are ambiguous in farmers' language:
#   "gram" (also a weight unit: "100 gram"), "आम" (mango, but also "common":
#   "आम तौर पर"), "sem" (bean, but a common Hinglish/English token), "lime"
#   (also agricultural lime for acid soils).
# Kept although ambiguous, because a false match only makes the answer MORE
# cautious: "chilly" (the manual's own spelling of chilli, also "chilly
# weather"), "dhan" (paddy, also "wealth").
CROP_LEXICON: dict[str, tuple[str, ...]] = {
    # Field crops -- none of these is covered by the current corpus, which is
    # exactly why they must be recognised.
    "wheat": ("wheat", "गेहूं", "गेहूँ", "gehun", "gehu", "gehoon", "gehoo"),
    "rice": ("rice", "paddy", "धान", "चावल", "dhan", "dhaan", "chawal"),
    "cotton": ("cotton", "कपास", "kapas"),
    "sugarcane": ("sugarcane", "गन्ना", "गन्ने", "ganna", "ganne"),
    "maize": ("maize", "corn", "मक्का", "makka", "makki"),
    "soybean": ("soybean", "soybeans", "soya", "सोयाबीन"),
    "mustard": ("mustard", "सरसों", "sarson"),
    "chickpea": ("chickpea", "chickpeas", "bengal gram", "चना", "chana"),
    "pigeon_pea": ("pigeon pea", "pigeon peas", "arhar", "tur", "toor", "अरहर", "तुअर"),
    "groundnut": ("groundnut", "groundnuts", "peanut", "peanuts", "मूंगफली", "moongfali"),
    "millet": ("millet", "millets", "bajra", "jowar", "sorghum", "ragi", "kodo", "kutki",
               "बाजरा", "ज्वार", "रागी", "कोदो", "कुटकी"),
    "pulses_moong_urad": ("moong", "urad", "मूंग", "उड़द"),
    "barley": ("barley", "जौ"),
    # Vegetables, spices, fruit.
    "tomato": ("tomato", "tomatoes", "टमाटर", "tamatar", "tamater"),
    "eggplant": ("eggplant", "eggplants", "brinjal", "brinjals", "बैंगन", "baingan", "bengan"),
    "potato": ("potato", "potatoes", "आलू", "aloo", "alu"),
    "sweet_potato": ("sweet potato", "sweet potatoes", "शकरकंद", "shakarkand"),
    "chilli": ("chilli", "chillies", "chili", "chilies", "chilly", "मिर्च", "मिर्ची", "mirch", "mirchi"),
    "okra": ("okra", "bhindi", "भिंडी"),
    "onion": ("onion", "onions", "प्याज", "pyaz", "pyaj"),
    "garlic": ("garlic", "लहसुन", "lahsun"),
    "cabbage": ("cabbage", "पत्तागोभी", "bandgobhi", "patta gobhi"),
    "cauliflower": ("cauliflower", "फूलगोभी", "phool gobhi", "phoolgobhi"),
    "radish": ("radish", "मूली", "mooli", "muli"),
    "carrot": ("carrot", "carrots", "गाजर", "gajar"),
    "pea": ("pea", "peas", "मटर", "matar"),
    "pumpkin": ("pumpkin", "कद्दू", "kaddu"),
    "gourd": ("gourd", "gourds", "bottle gourd", "bitter gourd", "ridge gourd",
              "लौकी", "करेला", "lauki", "karela"),
    "cucumber": ("cucumber", "cucumbers", "खीरा", "kheera", "khira"),
    "amaranth": ("amaranth", "चौलाई", "chaulai"),
    "spinach": ("spinach", "पालक", "palak"),
    "fenugreek": ("fenugreek", "मेथी", "methi"),
    "coriander": ("coriander", "धनिया", "dhaniya", "dhania"),
    "cowpea": ("cowpea", "cowpeas", "लोबिया", "lobia"),
    "beans": ("bean", "beans", "french bean", "french beans"),
    "turmeric": ("turmeric", "हल्दी", "haldi"),
    "ginger": ("ginger", "अदरक", "adrak"),
    "taro": ("taro", "colocasia", "अरबी", "arbi"),
    "papaya": ("papaya", "पपीता", "papita"),
    "moringa": ("moringa", "drumstick", "drumsticks", "सहजन", "sahjan"),
    "banana": ("banana", "bananas", "केला", "केले", "kela", "kele"),
    "citrus": ("citrus", "lemon", "lemons", "नींबू", "nimbu", "neembu"),
    "guava": ("guava", "अमरूद", "amrood"),
}

# Phrases whose crop word does not name a crop. Removed before matching.
NOT_A_CROP_PHRASES: tuple[str, ...] = (
    "black cotton soil",
    "black cotton soils",
    "cotton cloth",
)

# In a grafting question the rootstock species is a tool, not the crop being
# asked about: "Which eggplant rootstock performed best in the tomato trial?"
# is a tomato question. Treating it as an eggplant question would either
# block legitimate trial questions or -- if eggplant were marked covered by
# the tomato trial -- let brinjal questions be answered from tomato data.
ROOTSTOCK_WORDS = frozenset({"rootstock", "rootstocks", "graft", "grafted", "grafting", "कलम"})
ROOTSTOCK_ONLY_IN_GRAFTING = frozenset({"eggplant"})

KNOWN_CROPS = frozenset(CROP_LEXICON)

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
# Hindi oblique plural (टमाटरों, गन्नों) -> stem, so "टमाटरों में" still matches.
_HI_OBLIQUE_PLURAL = "ों"


def _tokens(text: str) -> list[str]:
    """NFKC + casefold, punctuation (incl. the danda) becomes space, then
    split. Token-based rather than regex word boundaries because Devanagari
    vowel signs are not regex word characters, so `\\b` breaks inside Hindi
    words."""
    text = unicodedata.normalize("NFKC", text).casefold().replace("।", " ")
    # Keep combining marks: _PUNCT's [^\w\s] would otherwise delete matras.
    text = "".join(
        " " if (_PUNCT.match(ch) and not unicodedata.category(ch).startswith("M")) else ch
        for ch in text
    )
    return [t.removesuffix(_HI_OBLIQUE_PLURAL) if t.endswith(_HI_OBLIQUE_PLURAL) else t
            for t in text.split()]


def _find_phrase(tokens: list[str], phrase: list[str], used: list[bool]) -> bool:
    n = len(phrase)
    found = False
    for i in range(len(tokens) - n + 1):
        if tokens[i:i + n] == phrase and not any(used[i:i + n]):
            for j in range(i, i + n):
                used[j] = True
            found = True
    return found


# Longest forms first, so "sweet potato" is consumed before "potato" is tried.
_FORMS: list[tuple[list[str], str]] = sorted(
    ((_tokens(form), key) for key, forms in CROP_LEXICON.items() for form in forms),
    key=lambda pair: -len(pair[0]),
)
_NOT_A_CROP: list[list[str]] = [_tokens(p) for p in NOT_A_CROP_PHRASES]


def crops_named_in(text: str) -> frozenset[str]:
    """The canonical crop keys a question explicitly names."""
    tokens = _tokens(text)
    used = [False] * len(tokens)
    for phrase in _NOT_A_CROP:
        _find_phrase(tokens, phrase, used)
    found = {key for form, key in _FORMS if _find_phrase(tokens, form, used)}
    if ROOTSTOCK_WORDS.intersection(tokens):
        found -= ROOTSTOCK_ONLY_IN_GRAFTING
    return frozenset(found)


class _HasCoverage(Protocol):
    doc_crops_covered: list[str]


def covers(chunk: _HasCoverage, crops: Iterable[str]) -> bool:
    """True when the chunk's DOCUMENT is a curated source for every crop."""
    return set(crops) <= set(chunk.doc_crops_covered)


C = TypeVar("C", bound=_HasCoverage)


def scope_passages(chunks: Sequence[C], crops: frozenset[str]) -> list[C]:
    """Passages the answering turn may see. A question that names no crop is
    not filtered. A question that names crops keeps only passages from
    documents covering ALL of them -- "tomato after wheat?" needs a source
    for both, and no current document is one."""
    if not crops:
        return list(chunks)
    return [c for c in chunks if covers(c, crops)]


def unknown_keys(keys: Iterable[str]) -> list[str]:
    """Coverage keys that are not in the lexicon (a typo in sources.yaml
    would otherwise silently cover nothing)."""
    return sorted(set(keys) - KNOWN_CROPS)
