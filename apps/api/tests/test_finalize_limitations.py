"""The `limitations` note (finalize.no_document_note): a crop-specific answer that rests on no document
says so, in code's words. Pure tests: no database, no network, no LLM."""
from datetime import date

from app.agent import finalize
from app.agent.tools.farm_context import FarmContextData
from app.agent.tools.weather import WeatherData
from app.agronomy.water_balance import WaterBalanceResult
from app.retrieval.citations import Citation
from app.safety.agrochemical_lookup import LabelEntry
from app.schemas.advisory import AdvisoryResponse, DraftAdvisory

from ._chunks import make_chunk

FARM = FarmContextData(farm_name="Test Khet", crop_name="Wheat", sowing_date=date(2026, 8, 30), days_since_sowing=36)
WEATHER = WeatherData(current_temp_c=30.0, current_rain_mm=0.0, forecast_dates=["2026-10-06"], forecast_rain_mm=[0.0])
LABEL = LabelEntry(
    row_id="synthetic-1", molecule="synthetic-molecule", formulation="Synthetic 10% SC", crop="Wheat", pest="aphid",
    dose_formulation=100.0, dose_formulation_unit="ml", waiting_period_days=7, label_date=date(2026, 1, 1),
    source_ref="synthetic test row", table_version="synthetic", text="synthetic card",
)


def draft(**kw) -> DraftAdvisory:
    base = dict(
        evidence_basis="farm_and_weather_data", citations=[],
        model_inference="Farm record shows the wheat was sown on 2026-08-30.",
        recommendation="Your wheat was sown on 30 Aug, so no new sowing is needed now.",
        confidence=0.8, abstained=False, abstained_because=None,
    )
    base.update(kw)
    return DraftAdvisory(**base)


def run(d, *, named=frozenset({"wheat"}), passages=(), live=None, wb=None, labels=None):
    return finalize.finalize_advisory(
        d, farm_data=FARM, live_data=live, passages=list(passages), named_crops=named,
        water_balance=wb, question_text="when should wheat be sown?", agrochemical_label=labels,
    )


def test_the_live_case_gets_the_note():
    # The first live run: crop named, answered from the farm record, 0 sources.
    r = run(draft())
    assert not r.abstained and r.retrieved_evidence == []
    assert r.limitations == finalize.no_document_note(has_weather=False)
    hi, en = r.limitations.split("\n\n")
    assert "जाँचे हुए दस्तावेज़" in hi and "No verified document was used" in en
    assert "1800-180-1551" in hi and "1800-180-1551" in en


def test_the_note_says_weather_when_weather_was_fetched():
    r = run(draft(), live=WEATHER)
    assert r.limitations == finalize.no_document_note(has_weather=True)


def test_no_note_when_a_verified_label_card_carries_the_answer():
    r = run(draft(recommendation="The label card below has the details; the pack label is the legal source."),
            labels=[LABEL])
    assert not r.abstained and r.agrochemical_label == [LABEL] and r.limitations == ""


def test_the_note_is_two_paragraphs_so_the_browser_can_pick_a_language():
    assert len(finalize.no_document_note(True).split("\n\n")) == 2
    assert len(finalize.no_document_note(False).split("\n\n")) == 2


def test_the_note_names_weather_only_when_weather_was_used():
    assert "weather" not in finalize.no_document_note(False)
    assert "weather" in finalize.no_document_note(True)
    assert "मौसम" not in finalize.no_document_note(False).split("\n\n")[0]
    assert "मौसम" in finalize.no_document_note(True).split("\n\n")[0]


def test_no_note_when_the_question_names_no_crop():
    assert run(draft(), named=frozenset()).limitations == ""


def test_no_note_on_an_abstention():
    r = run(draft(abstained=True, abstained_because="out_of_corpus"))
    assert r.abstained and r.limitations == ""


def test_no_note_when_the_model_found_nothing():
    r = run(draft(evidence_basis="none"))
    assert r.abstained and r.limitations == ""


def test_no_note_when_a_document_backs_the_answer():
    chunk = make_chunk("Wheat sown in November gave the best yield in the trial.", crops=("wheat",))
    r = run(
        draft(
            evidence_basis="retrieved_passages",
            citations=[Citation(passage=1, quote="sown in November gave the best yield")],
        ),
        passages=[chunk],
    )
    assert not r.abstained and r.retrieved_evidence and r.limitations == ""


def test_no_note_on_a_computed_irrigation_answer():
    wb = WaterBalanceResult(
        verdict="wait", as_of=date(2026, 10, 10), crop="Wheat", soil_texture="loamy", table_version="t",
        days_since_sowing=9, stage="initial", kc_today=1.0, depletion_mm=45.0, raw_mm=50.0, taw_mm=100.0,
        days_to_raw=0, forecast_et0_mm=[5.0] * 7, forecast_rain_mm=[0.0] * 7,
        anchor_date=date(2026, 10, 1), anchor_kind="sowing",
    )
    r = run(
        draft(
            model_inference="Computed: 45 mm short, limit 50 mm.",
            recommendation="Not yet: the soil is short of 45 mm, the limit is 50 mm.",
            irrigation_verdict="wait",
        ),
        wb=wb,
    )
    assert not r.abstained and r.water_balance == wb and r.limitations == ""


def test_the_interim_dose_guard_clears_the_note_with_the_answer():
    r = run(draft(recommendation="Spray 2 ml per litre of water on the wheat."))
    assert r.abstained and r.limitations == ""


def test_an_advisory_saved_before_the_field_existed_still_parses():
    r = run(draft())
    old = r.model_dump(mode="json")
    old.pop("limitations")
    assert AdvisoryResponse.model_validate(old).limitations == ""
