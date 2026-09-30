"""Pure unit tests for finalize_advisory (app/agent/finalize.py): the rules
that decide, in code, what the farmer finally sees (ADR-0013)."""
from app.agent import finalize
from app.agent.tools.farm_context import FarmContextData
from app.retrieval.citations import Citation
from app.safety import interim_dose_guard
from app.schemas.advisory import DraftAdvisory

from ._chunks import make_chunk

FARM = FarmContextData(farm_name="Test Farm", crop_name="Tomato")
PASSAGES = [
    make_chunk("Tomato grafted onto EG 203 rootstock combined with IPDM performed better than all other treatments."),
    make_chunk("Treatments: B. subtilis @ 4 g/L was applied as a soil drench.", page=4),
]


def draft(**overrides) -> DraftAdvisory:
    base = dict(
        evidence_basis="retrieved_passages",
        citations=[Citation(passage=1, quote="grafted onto EG 203 rootstock combined with IPDM")],
        model_inference="The study found EG 203 with IPDM performed best.",
        recommendation="In that study, EG 203-grafted tomato with IPDM did best.",
        confidence=0.7,
        abstained=False,
        abstained_because=None,
    )
    base.update(overrides)
    return DraftAdvisory(**base)


def run(d: DraftAdvisory, *, named_crops: frozenset[str] = frozenset(), passages=PASSAGES):
    return finalize.finalize_advisory(
        d, farm_data=FARM, live_data=None, passages=passages, named_crops=named_crops
    )


def test_valid_citation_answers_with_code_authored_provenance():
    r = run(draft())
    assert not r.abstained and r.citations_valid
    [ev] = r.retrieved_evidence
    assert ev.chunk_id == PASSAGES[0].chunk_id
    assert ev.doc_title == PASSAGES[0].doc_title and ev.licence == "CC-BY-4.0" and ev.page == 3
    assert r.structured_data == FARM  # copied by code, not written by the model


def test_fabricated_quote_withholds_the_answer():
    r = run(draft(citations=[Citation(passage=1, quote="EG 203 doubled tomato yield everywhere")]))
    assert r.abstained and r.abstained_because == finalize.INVALID_CITATION
    assert not r.citations_valid
    assert r.recommendation == finalize.ABSTAIN_MESSAGE
    assert r.retrieved_evidence == []


def test_one_bad_citation_among_good_ones_still_withholds():
    r = run(draft(citations=[
        Citation(passage=1, quote="grafted onto EG 203 rootstock combined with IPDM"),
        Citation(passage=9, quote="a passage that was never shown"),
    ]))
    assert r.abstained and r.abstained_because == finalize.INVALID_CITATION


def test_passage_basis_without_any_citation_withholds():
    r = run(draft(citations=[]))
    assert r.abstained and r.abstained_because == finalize.NO_VALID_CITATION


def test_basis_none_abstains():
    r = run(draft(evidence_basis="none", citations=[]))
    assert r.abstained and r.abstained_because == finalize.INSUFFICIENT_EVIDENCE


def test_farm_and_weather_answer_needs_no_citation():
    r = run(draft(evidence_basis="farm_and_weather_data", citations=[],
                  recommendation="No rain is forecast; check soil moisture before irrigating."))
    assert not r.abstained and r.citations_valid and r.retrieved_evidence == []


def test_model_abstention_keeps_its_own_reason_and_text():
    r = run(draft(abstained=True, abstained_because="out_of_corpus", citations=[],
                  recommendation="I don't have information on this."))
    assert r.abstained and r.abstained_because == "out_of_corpus"
    assert r.recommendation == "I don't have information on this."


def test_dose_in_recommendation_is_blocked_even_with_valid_citations():
    r = run(draft(recommendation="Apply B. subtilis at 4 g/L."))
    assert r.abstained and r.abstained_because == interim_dose_guard.SAFE_ABSTAIN_REASON
    assert r.recommendation == interim_dose_guard.SAFE_MESSAGE
    assert r.retrieved_evidence == []


def test_dose_inside_a_valid_quote_is_blocked_too():
    # The quote is genuine and correctly cited -- but it is a trial rate, and
    # rule 1 forbids putting it in front of a farmer before Phase 6.
    r = run(draft(citations=[Citation(passage=2, quote="B. subtilis @ 4 g/L was applied")],
                  recommendation="The study used B. subtilis as a soil drench."))
    assert r.abstained and r.abstained_because == interim_dose_guard.SAFE_ABSTAIN_REASON


def test_dose_in_a_model_abstention_text_is_still_scrubbed():
    r = run(draft(abstained=True, abstained_because="no_verified_dose_source", citations=[],
                  recommendation="I can't recommend a dose, but the trial used 4 g/L."))
    assert r.recommendation == interim_dose_guard.SAFE_MESSAGE


# --- Crop scope (ADR-0014) -------------------------------------------------

# The unans-001 shape: a real sentence about rainfall, from a document that is
# not a source for wheat, quoted to answer a wheat question.
RAIN = make_chunk(
    "In Mandla, where nearly 90% of rainfall is concentrated between June and September.",
    title="Kitchen gardens in Mandla",
    crops=("tomato", "okra"),
)


def test_real_quote_from_a_document_not_covering_the_crop_is_withheld():
    d = draft(
        citations=[Citation(passage=1, quote="nearly 90% of rainfall is concentrated between June and September")],
        recommendation="Sow wheat at the onset of the monsoon, between June and September.",
    )
    r = run(d, named_crops=frozenset({"wheat"}), passages=[RAIN])
    assert r.abstained and r.abstained_because == finalize.CROP_NOT_COVERED
    assert r.recommendation == finalize.ABSTAIN_MESSAGE  # the wrong season never reaches the farmer
    assert r.retrieved_evidence == []
    assert r.citations_valid  # the quote itself was genuine -- that is the whole point


def test_covered_crop_answers_normally():
    r = run(draft(), named_crops=frozenset({"tomato"}))
    assert not r.abstained and len(r.retrieved_evidence) == 1


def test_every_named_crop_must_be_covered():
    r = run(draft(), named_crops=frozenset({"tomato", "wheat"}))
    assert r.abstained and r.abstained_because == finalize.CROP_NOT_COVERED


def test_question_naming_no_crop_is_not_crop_checked():
    r = run(draft(), named_crops=frozenset(), passages=[make_chunk(PASSAGES[0].content, crops=())])
    assert not r.abstained


def test_crop_question_answered_from_farm_and_weather_needs_no_corpus_source():
    # "Kya aaj mujhe apne gehun ko paani dena chahiye?" -- the cassette case.
    r = run(
        draft(evidence_basis="farm_and_weather_data", citations=[],
              recommendation="Heavy rain is forecast tomorrow; no need to irrigate today."),
        named_crops=frozenset({"wheat"}),
    )
    assert not r.abstained


# --- Blank abstentions (inj-003 bug, agent eval 2026-09-27) ---------------

def test_blank_model_abstention_gets_the_code_message():
    r = run(draft(abstained=True, abstained_because="out_of_corpus", citations=[],
                  evidence_basis="none", recommendation="", model_inference=""))
    assert r.abstained and r.abstained_because == "out_of_corpus"
    assert r.recommendation == finalize.ABSTAIN_MESSAGE
    assert r.model_inference == "Model abstained: out_of_corpus."


def test_blank_dose_abstention_gets_the_dose_message():
    r = run(draft(abstained=True, abstained_because=interim_dose_guard.SAFE_ABSTAIN_REASON,
                  citations=[], recommendation="  ", model_inference=""))
    assert r.recommendation == interim_dose_guard.SAFE_MESSAGE


def test_blank_injection_abstention_gets_the_injection_message():
    r = run(draft(abstained=True, abstained_because=finalize.INJECTION_ATTEMPT,
                  citations=[], recommendation="", model_inference=""))
    assert r.recommendation == finalize.INJECTION_MESSAGE


def test_answer_with_no_text_is_withheld():
    r = run(draft(recommendation=""))
    assert r.abstained and r.abstained_because == finalize.EMPTY_ANSWER
    assert r.recommendation == finalize.ABSTAIN_MESSAGE


def test_response_schema_refuses_a_blank_recommendation():
    import pytest
    from pydantic import ValidationError

    from app.schemas.advisory import AdvisoryResponse

    with pytest.raises(ValidationError):
        AdvisoryResponse(structured_data=FARM, model_inference="x", recommendation=" ",
                         abstained=True, citations_valid=True)


def test_farmer_messages_are_bilingual_and_never_trip_the_dose_guard():
    for message in (finalize.ABSTAIN_MESSAGE, finalize.INJECTION_MESSAGE, interim_dose_guard.SAFE_MESSAGE):
        assert "KVK" in message and "1800-180-1551" in message
        assert any("\u0900" <= ch <= "\u097f" for ch in message)  # has Hindi (Devanagari)
        assert not interim_dose_guard.find_dose_statement(message)

