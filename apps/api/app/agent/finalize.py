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
       - the question names a crop and a cited passage's
         document is not a curated source for it (ADR-0014) -> abstain
  4. Irrigation (ADR-0015):
       - the water balance is cannot_assess                -> abstain with
         the balance's own reason; the farmer reads a code-authored message
         that says what to do. Every earlier abstention yields to it EXCEPT an
         injection or a dose refusal, which keep their own message.
       - (only when nothing above decided) the model claims a verdict code
         never computed                                    -> abstain
       - the model's verdict differs from code's, or its text uses a number
         the evidence does not contain                     -> answered, but in
         code's words (built from the computed numbers)
  Then the farmer-facing text: an abstention the model left blank gets the
  code-authored message for its reason (bilingual, Hindi + English).
  5. Interim dose guard LAST, over everything text-shaped the farmer would
     read, including quotes -- so nothing earlier can route around it.

When code overrides the model, the model's own recommendation is replaced,
never shown: an answer that failed its evidence check must not reach the
farmer just because it was well written.
"""
from app.agent.tools.farm_context import FarmContextData
from app.agent.tools.weather import WeatherData
from app.agronomy.messages import irrigation_message
from app.agronomy.water_balance import WaterBalanceResult
from app.retrieval.citations import check_citations
from app.retrieval.hybrid import RetrievedChunk
from app.safety import crop_scope, interim_dose_guard, irrigation_guard
from app.schemas.advisory import AdvisoryResponse, DraftAdvisory, EvidenceItem

# abstained_because values set by code (the model may also set its own text).
MODEL_ABSTAINED = "model_abstained"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
INVALID_CITATION = "invalid_citation"
NO_VALID_CITATION = "no_valid_citation"
CROP_NOT_COVERED = "crop_not_covered"

CANNOT_ASSESS = "cannot_assess"  # fallback if a cannot_assess result somehow has no reason
# Refusals for safety, which no irrigation message may replace.
_SAFETY_REFUSALS = {"injection_attempt", interim_dose_guard.SAFE_ABSTAIN_REASON}
EMPTY_ANSWER = "empty_answer"
INJECTION_ATTEMPT = "injection_attempt"  # the reason Turn B's prompt tells the model to use

# Farmer-facing messages are bilingual, Hindi first then English: the app has
# no reliable language detection, and a farmer who asked in Hindi or Hinglish
# must still be able to read why there is no answer.
ABSTAIN_MESSAGE = (
    "इस सवाल का पक्का जवाब देने के लिए AgriAI के पास जाँची हुई जानकारी नहीं है, इसलिए यह "
    "कोई सलाह नहीं दे रहा। कृपया अपने नज़दीकी कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर "
    "(1800-180-1551) से पूछें।\n\n"
    "AgriAI does not have verified information to answer this reliably, so it is not "
    "giving advice. Please ask your nearest Krishi Vigyan Kendra (KVK) or the Kisan Call "
    "Centre (1800-180-1551)."
)

# Worded so the farmer is never blamed: planted instructions usually come from
# a retrieved document, not from the person asking.
INJECTION_MESSAGE = (
    "जवाब तैयार करते समय AgriAI को कुछ गलत निर्देश मिले, इसलिए सुरक्षा के लिए यह जवाब नहीं "
    "दे रहा। कृपया अपना खेती का सवाल दोबारा पूछें, या कृषि विज्ञान केंद्र (KVK) या किसान कॉल "
    "सेंटर (1800-180-1551) से पूछें।\n\n"
    "While preparing an answer, AgriAI came across instructions it should not follow, so "
    "for safety it is not answering. Please ask your farming question again, or ask your "
    "Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551)."
)


def abstain_message_for(reason: str | None) -> str:
    """The code-authored text shown when there is no model text to show."""
    if reason == interim_dose_guard.SAFE_ABSTAIN_REASON:
        return interim_dose_guard.SAFE_MESSAGE
    if reason == INJECTION_ATTEMPT:
        return INJECTION_MESSAGE
    return ABSTAIN_MESSAGE


def finalize_advisory(
    draft: DraftAdvisory,
    *,
    farm_data: FarmContextData,
    live_data: WeatherData | None,
    passages: list[RetrievedChunk],
    named_crops: frozenset[str],
    water_balance: WaterBalanceResult | None = None,
    question_text: str = "",
) -> AdvisoryResponse:
    """`named_crops`: crops the farmer's question names (crop_scope). Required,
    not defaulted, so a new caller cannot skip the crop check by omission.

    `water_balance`: the result of get_irrigation_status, if it ran. None is
    safe as a default: with no result the model cannot claim an irrigation
    verdict at all (irrigation_guard). `question_text` is evidence too: a
    number the farmer typed may be repeated back."""
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
    elif not draft.recommendation.strip():
        # An "answer" with no text is not an answer.
        abstain_reason = EMPTY_ANSWER
    elif not citations_valid:
        abstain_reason = INVALID_CITATION
    elif draft.evidence_basis == "retrieved_passages" and not evidence:
        abstain_reason = NO_VALID_CITATION
    elif named_crops and any(
        not crop_scope.covers(c.chunk, named_crops) for c in checks if c.ok and c.chunk is not None
    ):
        # Defence in depth: run_agent already hides out-of-scope passages from
        # Turn B, so this only fires if that filtering is ever bypassed. It
        # checks every piece of evidence the farmer would be shown, whatever
        # evidence_basis the model claimed.
        abstain_reason = CROP_NOT_COVERED

    # Irrigation (ADR-0015). Only when nothing above already decided: an
    # injection, a dose, a bad citation or a crop mismatch keeps priority.
    irrigation_text: str | None = None  # code-authored message shown instead of the model's
    irrigation_override: str | None = None
    if (
        water_balance is not None
        and water_balance.verdict == "cannot_assess"
        and abstain_reason not in _SAFETY_REFUSALS
    ):
        # The specific reason ("add your soil type") helps the farmer more than
        # a generic "no verified information", whether the model answered,
        # abstained for its own reason, or said it had no evidence.
        abstain_reason = water_balance.reason or CANNOT_ASSESS
        irrigation_text = irrigation_message(water_balance)
    elif abstain_reason is None:
        irrigation_override = irrigation_guard.check_irrigation_answer(
            claimed_verdict=draft.irrigation_verdict,
            water_balance=water_balance,
            texts=[draft.recommendation, draft.model_inference],
            evidence=_evidence_texts(farm_data, live_data, water_balance, evidence, question_text),
        )
        if irrigation_override == irrigation_guard.IRRIGATION_VERDICT_UNSUPPORTED:
            abstain_reason = irrigation_override  # nothing to say it with: generic message
        elif irrigation_override is not None and water_balance is not None:
            irrigation_text = irrigation_message(water_balance)

    # Decide the farmer-facing text BEFORE building the response, so the
    # AdvisoryResponse validator (no blank recommendation / model_inference)
    # checks the final values -- model_copy() would skip validation.
    recommendation, model_inference, shown_evidence = (
        draft.recommendation, draft.model_inference, evidence
    )
    code_overrode_model = abstain_reason is not None and not draft.abstained
    if irrigation_text is not None and abstain_reason is not None:
        # cannot_assess: code's message, whatever the model wrote or abstained with.
        recommendation = irrigation_text
        model_inference = f"Answer withheld by code: {abstain_reason}."
        shown_evidence = []
    elif code_overrode_model:
        # The model answered, but its answer did not pass the evidence check:
        # its text is replaced, never shown. An irrigation reason has its own,
        # more specific code-authored message.
        recommendation = irrigation_text if irrigation_text is not None else ABSTAIN_MESSAGE
        model_inference = f"Answer withheld by code: {abstain_reason}."
        shown_evidence = []
    elif irrigation_text is not None:
        # Still an answer (code's verdict is known), but in code's words.
        recommendation = irrigation_text
        model_inference = f"Model text replaced by code: {irrigation_override}."
        shown_evidence = []
    elif draft.abstained:
        # inj-003 bug (agent eval 2026-09-27): a model that abstains usually
        # leaves both texts EMPTY (23 of 25 abstentions), and the farmer saw a
        # blank answer. Keep the model's own text when it wrote one; otherwise
        # show the code-authored message for its reason.
        if not recommendation.strip():
            recommendation = abstain_message_for(abstain_reason)
        if not model_inference.strip():
            model_inference = f"Model abstained: {abstain_reason}."
    elif not model_inference.strip():
        model_inference = "The model gave no reasoning for this answer."

    response = AdvisoryResponse(
        structured_data=farm_data,
        live_data=live_data,
        water_balance=water_balance,
        retrieved_evidence=shown_evidence,
        model_inference=model_inference,
        recommendation=recommendation,
        confidence=draft.confidence,
        abstained=abstain_reason is not None,
        abstained_because=abstain_reason,
        citations_valid=citations_valid,
    )

    return _apply_interim_dose_guard(response)


def _evidence_texts(
    farm_data: FarmContextData,
    live_data: WeatherData | None,
    water_balance: WaterBalanceResult | None,
    evidence: list[EvidenceItem],
    question_text: str,
) -> list[str]:
    """Everything the model was allowed to take a number from (number_grounding)."""
    texts = [farm_data.model_dump_json(), question_text]
    if live_data is not None:
        texts.append(live_data.model_dump_json())
    if water_balance is not None:
        texts.append(water_balance.model_dump_json())
    texts += [e.quote for e in evidence]
    return texts


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
