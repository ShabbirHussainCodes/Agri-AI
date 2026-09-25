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


def run(d: DraftAdvisory):
    return finalize.finalize_advisory(d, farm_data=FARM, live_data=None, passages=PASSAGES)


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
