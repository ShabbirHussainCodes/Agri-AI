"""Code-level citation validation (docs/rag/rag-design.md section 6, ADR-0013).

The model is asked to back every claim drawn from the knowledge base with
{passage number, verbatim quote}. This module checks each one mechanically:

  1. the passage number refers to a passage that was actually shown, and
  2. the quote really appears in that passage's text.

A model can invent a plausible-sounding quote or cite passage [7] when only
[1]-[6] exist; both are caught here, deterministically, no LLM involved.

What this does NOT catch (stated plainly, because it matters): a REAL quote
used to support a claim it does not actually support. That is a meaning
question, measured by Ragas Faithfulness in the eval, not by string matching.
"""
import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.retrieval.hybrid import RetrievedChunk

# A quote must carry enough words to actually support a claim. Two or three
# words ("the trial", "EG 203") appear in many passages and prove nothing
# about which one was used. Four is the smallest length that still allows
# short factual quotes like "EG 203 and TS 03" (five tokens).
MIN_QUOTE_WORDS = 4

_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_WS = re.compile(r"\s+")


class Citation(BaseModel):
    """What the model writes. Source metadata is deliberately NOT here: the
    model never authors provenance -- code copies it from the database row
    of the passage it cited (ADR-0013)."""

    model_config = ConfigDict(extra="forbid")

    passage: int = Field(description="The [n] number of the passage being quoted.")
    quote: str = Field(description="Exact words copied from that passage.")


@dataclass(frozen=True)
class CitationCheck:
    citation: Citation
    ok: bool
    chunk: RetrievedChunk | None
    reason: str | None  # why it failed; None when ok


def normalise(text: str) -> str:
    """Forgive differences that do not change what was quoted: Unicode forms
    (NFKC), curly vs straight quotes and dashes, case, and whitespace/line
    breaks (Docling chunks keep PDF line breaks; a model re-flows them).
    Anything beyond that -- a changed word, a fixed typo -- is a mismatch."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTE_CHARS).casefold()
    return _WS.sub(" ", text).strip()


def check_citation(citation: Citation, passages: list[RetrievedChunk]) -> CitationCheck:
    if not 1 <= citation.passage <= len(passages):
        return CitationCheck(citation, False, None, f"passage [{citation.passage}] was not shown")
    chunk = passages[citation.passage - 1]
    # Normalise FIRST, then strip surrounding quote marks: curly quotes only
    # become strippable straight quotes after normalisation.
    quote = normalise(citation.quote).strip("\"' ")
    if len(quote.split()) < MIN_QUOTE_WORDS:
        return CitationCheck(citation, False, chunk, f"quote shorter than {MIN_QUOTE_WORDS} words")
    if quote not in normalise(chunk.content):
        return CitationCheck(citation, False, chunk, "quote not found in the cited passage")
    return CitationCheck(citation, True, chunk, None)


def check_citations(citations: list[Citation], passages: list[RetrievedChunk]) -> list[CitationCheck]:
    return [check_citation(c, passages) for c in citations]
