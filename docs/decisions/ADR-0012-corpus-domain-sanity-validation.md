# ADR-0012: Licence and provenance are not sufficient; corpus content needs domain sanity validation

- **Status:** Accepted
- **Date:** 2026-09-08
- **Deciders:** Shabbir (+ Claude)

## Context
The corpus licence register (`ingest/sources.yaml`, ADR-0003 / `docs/rag/rag-design.md` §7) was built to answer one question: *are we allowed to use this?* Every Phase 3 source was checked item by item in a browser and only CC-BY-4.0 items were approved.

Phase 3 then produced a case the register was not designed to catch. Appendix 1 of *Organizing principles for agroecological kitchen gardens in Mandla, Central India* (handle `10568/180614`, CGIAR/Alliance of Bioversity & CIAT + ATREE, CC-BY-4.0) is a crop calendar: 64 crops × 12 months, each cell 0 or 1, with a printed legend stating that 1 means "months with suitable growing conditions for the crop".

The table was extracted structurally (`ingest/extract_calendar.py`), with months assigned by column position rather than by OCR'd header text, and then verified cell by cell against page 12 of the PDF by a human. The extraction is faithful.

The extracted values are nonetheless agronomically implausible. The table states that wheat is suitable June–October and unsuitable November–March, inverting the Indian rabi season; and it marks Kodo millet as unsuitable June–September while marking Kutki millet — the same kharif-season millet of the same region — as suitable, within the same table.

So the source is correctly licensed, institutionally credible, correctly parsed, correctly read — and still not safe to put in front of a farmer. Nothing in the pipeline up to this point was equipped to notice.

## Options considered
- **Ingest it; the source is reputable and the citation is honest.** Cheapest, and defensible on provenance grounds. But a wrong sowing month delivered *with* a real CC-BY citation is more dangerous than no answer: the citation increases the farmer's confidence in the error. Violates rule 3 in `CLAUDE.md`.
- **Correct the values from general agronomic knowledge and ingest the corrected table.** Produces a "better" calendar, but silently replaces a source's data with our own assumptions while continuing to cite the source. That makes the citation a lie and destroys the property the whole evidence-typed design exists to protect (ADR-0006).
- **Exclude the affected pages, record why, and change the corpus rule.** Loses the calendar, keeps everything else in the document, and turns a one-off catch into a standing check.

## Decision
Exclude Appendix 1 (pages 11–13 of `10568/180614`) from the corpus — from RAG chunks and from any structured production dataset alike — via `exclude_pages` in `sources.yaml`, with the reason written next to it.

Establish the corpus rule this case revealed:

> **Licence and provenance qualify a source for use. They do not qualify its content for advice.** Before any safety-relevant agricultural content enters the corpus — sowing and harvest windows, dosages, waiting periods, varietal or seasonal recommendations — it must also pass a domain sanity check. Content that fails is excluded and the reason recorded; it is never silently repaired.

And the distinction that follows from it:

> **Source content is not AgriAI-verified knowledge.** That a passage is in the corpus means it came from a licensed, provenance-tracked source and was not caught by a sanity check. It does not mean AgriAI vouches for it. The two must never be conflated in a response, in documentation, or in demo material.

`ingest/extract_calendar.py` is kept as a research and diagnostic tool. Its output is written to the gitignored `_cache/` directory under a name marking it as research-only, and no production path reads it.

## Why
`CLAUDE.md` rule 9 already says retrieved corpus text is untrusted, but it was written with prompt injection in mind — a hostile document. This is the other face of the same rule, and the more likely one: an entirely well-intentioned, properly licensed, institutionally published document that is simply wrong in one table. Trust in the publisher does not transfer to every cell it prints.

Not correcting the data is the harder half of the decision and the more important one. AgriAI's differentiation is that its recommendations are grounded in cited evidence. The moment we edit a source's values while keeping its citation, the citation stops meaning anything, and no reader can tell which numbers are the source's and which are ours. Omission is auditable; silent substitution is not.

## Consequences
- **Positive:** a documented, reviewable exclusion mechanism (`exclude_pages`) that fails loudly if bypassed; a corpus rule that scales to Phase 6 agrochemical data, where the same failure would be far more dangerous; a clean separation between "in the corpus" and "verified by AgriAI".
- **Negative / trade-offs:** the corpus loses the most directly practical content in that manual, and Phase 3 ships with less answerable material than planned (113 chunks from two documents). Domain sanity checking is manual and does not scale on its own — at present it is one person reading, not a test.
- **Follow-ups:**
  - The calendar stays out until an agronomist can adjudicate it. If validated or corrected *by a qualified source*, it may return as its own citable dataset — never as a silent edit of this one.
  - Phase 6 (agrochemical safety) must treat CIB&RC label data the same way: parse, verify against the source, and sanity check before it can drive any dose recommendation.
  - Consider adding a small set of agronomic sanity assertions (e.g. rabi/kharif season expectations for major Indian crops) to the eval set, so this class of error becomes measurable rather than dependent on someone noticing.

## Links
`ingest/sources.yaml` (the exclusion and its reason), `ingest/extract_calendar.py`, `docs/rag/rag-design.md` §7, `docs/decisions/ADR-0003-rag-pgvector-supabase.md`, `docs/decisions/ADR-0006-evidence-typed-response.md`, `CLAUDE.md` rules 3 and 9.
