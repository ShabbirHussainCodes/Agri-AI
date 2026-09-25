"""Turns the model's DraftAdvisory into the AdvisoryResponse the farmer sees.

Pure function, no I/O -- every rule below is unit-tested in
tests/test_finalize.py without a database or an LLM.

Order matters, and each step can only make the answer MORE cautious:

  1. Copy what the model may not author: farm record, weather, provenance.
  2. Validate every citation against the passages actually shown.
  3. Decide abstention from EVIDENCE (ADR-0013), not from a similarity score:
       - the model chose to abstain                       -> abstain
       - evidence_basis == "none"                          -> abstain
       - any citation failed validation                    -> abstain
       - basis is "retrieved_passages" but no valid cite   -> abstain
  4. Interim dose guard LAST, over everything text-shaped the farmer would
     read, including quotes -- so nothing earlier can route around it.

When code overrides the model, the model's own recommendation is replaced,
never shown: an answer that failed its evidence check must not reach the
farmer just because it was well written.
"""
from app.agent.tools.farm_context import FarmContextData
from app.agent.tools.weather import WeatherData
from app.retrieval.citations import check_citations
from app.retrieval.hybrid import RetrievedChunk
from app.safety import interim_dose_guard
from app.schemas.advisory import AdvisoryResponse, DraftAdvisory, EvidenceItem

# abstained_because values set by code (the model may also set its own text).
MODEL_ABSTAINED = "model_abstained"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
INVALID_CITATION = "invalid_citation"
NO_VALID_CITATION = "no_valid_citation"

ABSTAIN_MESSAGE = (
    "AgriAI could not find verified information to answer this reliably, so it is not "
    "giving a recommendation. Please ask your local KVK or the Kisan Call Centre "
    "(1800-180-1551)."
)


def finalize_advisory(
    draft: DraftAdvisory,
    *,
    farm_data: FarmContextData,
    live_data: WeatherData | None,
    passages: list[RetrievedChunk],
) -> AdvisoryResponse:
    checks = check_citations(draft.citations, passages)
    citations_valid = all(c.ok for c in checks)
    evidence = [
        EvidenceItem(
            chunk_id=c.chunk.chunk_id,
            source_org=c.chunk.publisher,
            doc_title=c.chunk.doc_title,
            doc_type=c.chunk.doc_type,
            published_year=c.chunk.published_year,
            page=c.chunk.page_no,
            licence=c.chunk.licence,
            url=c.chunk.url,
            quote=c.citation.quote,
        )
        for c in checks
        if c.ok and c.chunk is not None
    ]

    abstain_reason: str | None = None
    if draft.abstained:
        abstain_reason = draft.abstained_because or MODEL_ABSTAINED
    elif draft.evidence_basis == "none":
        abstain_reason = INSUFFICIENT_EVIDENCE
    elif not citations_valid:
        abstain_reason = INVALID_CITATION
    elif draft.evidence_basis == "retrieved_passages" and not evidence:
        abstain_reason = NO_VALID_CITATION

    response = AdvisoryResponse(
        structured_data=farm_data,
        live_data=live_data,
        retrieved_evidence=evidence,
        model_inference=draft.model_inference,
        recommendation=draft.recommendation,
        confidence=draft.confidence,
        abstained=abstain_reason is not None,
        abstained_because=abstain_reason,
        citations_valid=citations_valid,
    )

    code_overrode_model = abstain_reason is not None and not draft.abstained
    if code_overrode_model:
        # The model answered, but its answer did not pass the evidence check.
        response = response.model_copy(update={
            "recommendation": ABSTAIN_MESSAGE,
            "model_inference": f"Answer withheld by code: {abstain_reason}.",
            "retrieved_evidence": [],
        })

    return _apply_interim_dose_guard(response)


def _apply_interim_dose_guard(response: AdvisoryResponse) -> AdvisoryResponse:
    texts = [response.recommendation, response.model_inference]
    texts += [e.quote for e in response.retrieved_evidence]
    if any(interim_dose_guard.find_dose_statement(t) for t in texts):
        return response.model_copy(update={
            "recommendation": interim_dose_guard.SAFE_MESSAGE,
            "model_inference": "Withheld by the interim dose guard (CLAUDE.md rule 1).",
            "retrieved_evidence": [],
            "abstained": True,
            "abstained_because": interim_dose_guard.SAFE_ABSTAIN_REASON,
        })
    return response
