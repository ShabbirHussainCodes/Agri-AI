"""Banned-molecule guard (CLAUDE.md rules 1-2, ADR-0005, ADR-0016).

Runs inside finalize_advisory, AFTER the model, in code: no model output and no
planted instruction can make the farmer read advice about a molecule on the
denylist (data/denylists/). Pure functions plus one cached file read.

Semantics, decided in ADR-0016:

  * EVERY listed molecule blocks, verified or not. Blocking advice about a
    molecule that turns out to be legal costs the farmer one answer; advising
    on a banned one is harm.
  * `status` only changes the WORDING. A verified entry lets the message say
    "banned / restricted in India (source)". An unverified one says only that
    AgriAI cannot advise, because claiming a legal status nobody has checked
    would itself be misinformation.
  * The message is written by code. The model's text is never shown.

Matching is by name, so it is a lexicon, not understanding. It folds case and
Unicode, matches whole words (Hindi included, like crop_scope), and accepts a
one-letter slip in names of 7+ letters ("endosulfen"). A brand name that is not
in `aliases` is NOT detected: that gap is stated in data/denylists/README.md and
measured by evals/chemical_guard_eval.py.
"""
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.safety.crop_scope import _find_phrase, _tokens  # same tokenizer as crop detection

DEFAULT_DENYLIST_PATH = Path(__file__).resolve().parents[4] / "data" / "denylists" / "banned-central-v1.json"

BANNED_MOLECULE = "banned_molecule"

Category = Literal["banned", "restricted", "refused", "unclassified"]

# Words shorter than this must match exactly: a one-letter slip in a short word
# is more likely a different word than a typo.
_MIN_FUZZY_LEN = 7


class DenylistError(ValueError):
    """The denylist file is malformed. Raised, never swallowed: with no list
    the guard cannot promise anything, so the answer is an honest error."""


class DenylistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    molecule: str
    aliases: list[str] = []
    category: Category
    status: Literal["unverified", "verified"]
    verified_by: str | None = None
    verified_on: date | None = None
    source_ref: str | None = None
    note: str = ""

    @model_validator(mode="after")
    def _check(self) -> "DenylistEntry":
        if not self.molecule.strip() or self.molecule != self.molecule.strip().lower():
            raise ValueError("molecule must be a non-empty lower-case name")
        if len({a.casefold() for a in self.aliases}) != len(self.aliases):
            raise ValueError("duplicate alias")
        if self.status == "verified":
            if self.category == "unclassified":
                raise ValueError("a verified entry needs a category read from the official list")
            if not (self.verified_by or "").strip() or self.verified_on is None or not (self.source_ref or "").strip():
                raise ValueError("a verified entry needs verified_by, verified_on and source_ref")
        return self

    @property
    def forms(self) -> list[str]:
        return [self.molecule, *self.aliases]


class Denylist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    list_version: str
    scope: str
    primary_source: str
    entries: list[DenylistEntry]

    @model_validator(mode="after")
    def _unambiguous(self) -> "Denylist":
        seen: dict[str, str] = {}
        for entry in self.entries:
            for form in entry.forms:
                key = " ".join(_tokens(form))
                if seen.setdefault(key, entry.molecule) != entry.molecule:
                    raise ValueError(f"{form!r} names both {seen[key]!r} and {entry.molecule!r}")
        return self


def load_denylist(path: Path | None = None) -> Denylist:
    target = path or DEFAULT_DENYLIST_PATH
    try:
        return Denylist.model_validate(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise DenylistError(f"denylist {target} is unusable: {exc}") from exc


@lru_cache(maxsize=4)
def _cached(path: Path | None) -> Denylist:
    return load_denylist(path)


def get_denylist(path: Path | None = None) -> Denylist:
    """Cached per path: the file is read once per process (restart after editing)."""
    return _cached(path)


def _within_one_edit(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(short == long_[:i] + long_[i + 1:] for i in range(len(long_)))


def _form_matches(tokens: list[str], form: list[str]) -> bool:
    if len(form) == 1:
        word = form[0]
        if len(word) < _MIN_FUZZY_LEN:
            return word in tokens
        return any(len(t) >= _MIN_FUZZY_LEN - 1 and _within_one_edit(t, word) for t in tokens)
    return _find_phrase(tokens, form, [False] * len(tokens))


def find_banned(texts: list[str], denylist: Denylist) -> list[DenylistEntry]:
    """Entries named in any of `texts`, in the list's own order, each once."""
    token_lists = [_tokens(t) for t in texts if t]
    hits = []
    for entry in denylist.entries:
        forms = [_tokens(f) for f in entry.forms]
        if any(_form_matches(tokens, form) for tokens in token_lists for form in forms):
            hits.append(entry)
    return hits


# Chemical vocabulary in English, Hindi and Hinglish. Deliberately broad: a false
# match only adds a tool description to a prompt and makes the number rule stricter.
_CHEMICAL_VOCAB = re.compile(
    r"\b(?:spray(?:ed|ing|s)?|sprayer|pesticides?|fungicides?|insecticides?|herbicides?|weedicides?|chemicals?"
    r"|dose|dosage|dilut\w*|molecule|pest control|medicine|keetnashak|chhidkav|chhidak\w*|dawai|dawa|ghol)\b"
    r"|छिड़काव|छिड़क|दवा|दवाई|कीटनाशक|फफूंदनाशक|फफूँदनाशक|खरपतवारनाशक|मात्रा|रसायन|घोल",
    re.I,
)


def is_chemical_text(text: str, denylist: "Denylist") -> bool:
    """True if the text talks about chemicals or names a listed molecule."""
    return bool(_CHEMICAL_VOCAB.search(text)) or bool(find_banned([text], denylist))


# ---- farmer-facing wording (Hindi first, then English; written by code) ----

_HELP_HI = "ज़्यादा जानकारी के लिए कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।"
_HELP_EN = "For more help, ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551)."

_VERIFIED_HI = {
    "banned": "पर भारत में पाबंदी है",
    "restricted": "के इस्तेमाल पर भारत में कुछ पाबंदियाँ हैं",
    "refused": "को भारत में बेचने की मंज़ूरी नहीं मिली",
}
_VERIFIED_EN = {
    "banned": "is banned in India",
    "restricted": "has restricted use in India (rules govern how it may be used)",
    "refused": "was refused registration in India",
}


def banned_message(entries: list[DenylistEntry]) -> str:
    """The code-authored answer when a listed molecule was named."""
    lines_hi: list[str] = []
    lines_en: list[str] = []
    unverified = [e.molecule for e in entries if e.status != "verified"]
    for e in entries:
        if e.status == "verified":
            src = f"{e.source_ref}, {e.verified_on}"
            lines_hi.append(f"{e.molecule} {_VERIFIED_HI[e.category]} ({src})।")
            lines_en.append(f"{e.molecule} {_VERIFIED_EN[e.category]} ({src}).")
    if unverified:
        names = ", ".join(unverified)
        lines_hi.append(f"AgriAI {names} पर सलाह नहीं दे सकता। दवा खरीदने से पहले पैकेट का लेबल और उसका रजिस्ट्रेशन नंबर ज़रूर जाँचें।")
        lines_en.append(f"AgriAI cannot advise on {names}. Before buying any pesticide, check its label and registration.")
    lines_hi.append("इसलिए AgriAI इस दवा की कोई सलाह नहीं दे रहा।")
    lines_en.append("So AgriAI is not giving advice on it.")
    return "\n".join([*lines_hi, _HELP_HI, "", *lines_en, _HELP_EN])
