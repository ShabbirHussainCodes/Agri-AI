"""How finalize_advisory treats irrigation answers (ADR-0015).
Pure tests: no database, no network, no LLM."""
from datetime import date

from app.agent import finalize
from app.agent.tools.farm_context import FarmContextData
from app.agent.tools.weather import WeatherData
from app.agronomy.messages import irrigation_message
from app.agronomy.water_balance import WaterBalanceResult
from app.retrieval.citations import Citation
from app.schemas.advisory import DraftAdvisory

from ._chunks import make_chunk

FARM = FarmContextData(farm_name="Test Farm", crop_name="Wheat", sowing_date=date(2026, 10, 1), days_since_sowing=9)
PASSAGES = [make_chunk("Tomato grafted onto EG 203 rootstock combined with IPDM performed better.")]


def computed(verdict="wait", depletion=45.0, days_to_raw=0) -> WaterBalanceResult:
    return WaterBalanceResult(
        verdict=verdict, as_of=date(2026, 10, 10), crop="Wheat", soil_texture="loamy",
        table_version="test", days_since_sowing=9, stage="initial", kc_today=1.0,
        depletion_mm=depletion, raw_mm=50.0, taw_mm=100.0, days_to_raw=days_to_raw,
        forecast_et0_mm=[5.0] * 7, forecast_rain_mm=[0.0] * 7,
        anchor_date=date(2026, 10, 1), anchor_kind="sowing",
    )


def draft(**overrides) -> DraftAdvisory:
    base = dict(
        evidence_basis="farm_and_weather_data",
        citations=[],
        model_inference="Computed: the soil is short of 45 mm and the limit is 50 mm.",
        recommendation="Not yet: the soil is short of 45 mm, the limit is 50 mm. Check again tomorrow.",
        confidence=0.8,
        abstained=False,
        abstained_because=None,
        irrigation_verdict="wait",
    )
    base.update(overrides)
    return DraftAdvisory(**base)


def run(d, wb, *, question="Should I water my wheat today?", passages=PASSAGES,
        named_crops=frozenset({"wheat"}), live_data=None):
    return finalize.finalize_advisory(
        d, farm_data=FARM, live_data=live_data, passages=passages, named_crops=named_crops,
        water_balance=wb, question_text=question,
    )


def test_a_matching_grounded_answer_is_shown_as_the_model_wrote_it():
    wb = computed("wait")
    r = run(draft(), wb)
    assert not r.abstained and r.abstained_because is None
    assert r.recommendation.startswith("Not yet")
    assert r.water_balance == wb  # copied by code


def test_cannot_assess_abstains_with_the_balances_own_reason_and_a_code_message():
    wb = WaterBalanceResult.cannot("soil_texture_missing", as_of=date(2026, 10, 10), crop="Wheat")
    r = run(draft(irrigation_verdict="cannot_assess", recommendation="Water it, probably 30 mm."), wb)
    assert r.abstained and r.abstained_because == "soil_texture_missing"
    assert r.recommendation == irrigation_message(wb)  # the model's text is never shown
    assert "30 mm" not in r.recommendation
    assert r.water_balance == wb


def test_the_specific_cannot_assess_message_replaces_a_generic_model_abstention():
    wb = WaterBalanceResult.cannot("soil_texture_missing", as_of=date(2026, 10, 10), crop="Wheat")
    for d in (
        draft(abstained=True, abstained_because="out_of_corpus", recommendation="", model_inference=""),
        draft(evidence_basis="none", recommendation="Nothing answers this."),
    ):
        r = run(d, wb)
        assert r.abstained and r.abstained_because == "soil_texture_missing"
        assert r.recommendation == irrigation_message(wb)  # says "add your soil type", not "no verified information"


def test_a_dose_refusal_keeps_its_own_message_over_cannot_assess():
    wb = WaterBalanceResult.cannot("soil_texture_missing", as_of=date(2026, 10, 10), crop="Wheat")
    r = run(draft(abstained=True, abstained_because="no_verified_dose_source", recommendation="", model_inference=""), wb)
    assert r.abstained_because == "no_verified_dose_source"
    assert r.recommendation == finalize.interim_dose_guard.SAFE_MESSAGE


def test_cannot_assess_wins_even_if_the_model_claims_a_verdict():
    wb = WaterBalanceResult.cannot("no_location", as_of=date(2026, 10, 10))
    r = run(draft(irrigation_verdict="irrigate_now"), wb)
    assert r.abstained and r.abstained_because == "no_location"


def test_a_different_verdict_is_replaced_by_the_computed_answer_and_stays_an_answer():
    wb = computed("irrigate_now", depletion=50.0, days_to_raw=None)
    r = run(draft(irrigation_verdict="wait", recommendation="Wait, the soil is short of 50 mm."), wb)
    assert not r.abstained
    assert r.recommendation == irrigation_message(wb)
    assert "irrigation_verdict_mismatch" in r.model_inference
    assert r.retrieved_evidence == [] and r.water_balance == wb


def test_a_number_the_evidence_lacks_replaces_the_text():
    wb = computed("wait")
    r = run(draft(recommendation="Not yet. The soil is short of 45 mm; give 35 mm on Friday."), wb)
    assert not r.abstained
    assert r.recommendation == irrigation_message(wb)
    assert "ungrounded_number" in r.model_inference


def test_the_farmers_own_number_may_be_repeated():
    r = run(draft(recommendation="You irrigated 20 mm on the 5th. Not yet: short of 45 mm, limit 50 mm."),
            computed("wait"), question="I irrigated 20 mm on the 5th. Should I water again?")
    assert not r.abstained and r.recommendation.startswith("You irrigated")


def test_a_number_from_the_weather_tool_is_evidence_too():
    wb = computed("wait")
    weather = WeatherData(current_temp_c=22.5, current_rain_mm=0.7, forecast_dates=["2026-10-10"], forecast_rain_mm=[39.4])
    text = "Not yet: short of 45 mm, limit 50 mm. A forecast of 39.4 mm rain may delay the need."
    assert run(draft(recommendation=text), wb, live_data=weather).recommendation == text
    # The same sentence without that weather result cites a number nobody supplied.
    assert run(draft(recommendation=text), wb).recommendation == irrigation_message(wb)


def test_a_verdict_with_nothing_computed_abstains():
    r = run(draft(irrigation_verdict="irrigate_now", recommendation="Water now."), None)
    assert r.abstained and r.abstained_because == "irrigation_verdict_unsupported"
    assert r.recommendation == finalize.ABSTAIN_MESSAGE
    assert r.water_balance is None


def test_a_non_irrigation_answer_is_untouched_when_nothing_was_computed():
    r = run(draft(irrigation_verdict="not_applicable", recommendation="No rain is forecast."), None)
    assert not r.abstained and r.water_balance is None


def test_an_injection_abstention_keeps_priority_over_cannot_assess():
    wb = WaterBalanceResult.cannot("soil_texture_missing", as_of=date(2026, 10, 10))
    r = run(draft(abstained=True, abstained_because=finalize.INJECTION_ATTEMPT, recommendation="", model_inference=""), wb)
    assert r.abstained and r.abstained_because == finalize.INJECTION_ATTEMPT
    assert r.recommendation == finalize.INJECTION_MESSAGE


def test_an_invalid_citation_keeps_priority_over_a_good_irrigation_answer():
    r = run(draft(evidence_basis="retrieved_passages",
                  citations=[Citation(passage=1, quote="a sentence that is not in the passage at all")]),
            computed("wait"))
    assert r.abstained and r.abstained_because == finalize.INVALID_CITATION


def test_the_interim_dose_guard_still_runs_last():
    wb = computed("wait")
    r = run(draft(recommendation="Not yet (45 mm of 50 mm). Spray 4 g/L tomorrow."), wb)
    # The number 4 is not in the evidence, so code replaces the text first; either way no dose reaches the farmer.
    from app.safety import interim_dose_guard
    assert interim_dose_guard.find_dose_statement(r.recommendation) is None


def test_pre_phase_5_callers_are_unchanged():
    r = finalize.finalize_advisory(
        draft(irrigation_verdict="not_applicable"),
        farm_data=FARM, live_data=None, passages=PASSAGES, named_crops=frozenset(),
    )
    assert not r.abstained and r.water_balance is None
