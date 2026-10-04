"""The irrigation guard and the code-authored irrigation messages (ADR-0015).
Pure tests: no database, no network, no LLM."""
from datetime import date

import pytest

from app.agent.tools import irrigation as irrigation_tool
from app.agronomy import crop_water, messages, water_balance
from app.agronomy.water_balance import WaterBalanceResult
from app.safety import interim_dose_guard
from app.safety.irrigation_guard import (
    IRRIGATION_VERDICT_MISMATCH,
    IRRIGATION_VERDICT_UNSUPPORTED,
    UNGROUNDED_NUMBER,
    check_irrigation_answer,
)


def computed(verdict="wait", depletion=45.0, raw=50.0, days_to_raw=0, forecast=7) -> WaterBalanceResult:
    return WaterBalanceResult(
        verdict=verdict, as_of=date(2026, 10, 10), crop="Wheat", soil_texture="loamy",
        table_version="test", days_since_sowing=9, stage="initial", kc_today=1.0,
        depletion_mm=depletion, raw_mm=raw, taw_mm=100.0, days_to_raw=days_to_raw,
        forecast_et0_mm=[5.0] * forecast, forecast_rain_mm=[0.0] * forecast,
        anchor_date=date(2026, 10, 1), anchor_kind="sowing",
    )


EVIDENCE = [computed().model_dump_json()]


def check(claimed, wb, text="The soil is short of 45 mm; the limit is 50 mm."):
    return check_irrigation_answer(claimed_verdict=claimed, water_balance=wb, texts=[text], evidence=EVIDENCE)


# ------------------------------------------------------------------- guard

def test_matching_verdict_and_grounded_numbers_pass():
    assert check("wait", computed("wait")) is None


def test_a_different_verdict_is_a_mismatch():
    assert check("irrigate_now", computed("wait")) == IRRIGATION_VERDICT_MISMATCH
    assert check("wait", computed("irrigate_now")) == IRRIGATION_VERDICT_MISMATCH


def test_not_applicable_does_not_dodge_the_check_when_a_result_exists():
    assert check("not_applicable", computed("wait")) == IRRIGATION_VERDICT_MISMATCH


def test_an_invented_number_is_flagged_even_when_the_verdict_matches():
    assert check("wait", computed("wait"), text="Give 35 mm to be safe.") == UNGROUNDED_NUMBER


@pytest.mark.parametrize("claimed", ["irrigate_now", "wait"])
def test_a_verdict_with_no_computation_is_unsupported(claimed):
    assert check(claimed, None) == IRRIGATION_VERDICT_UNSUPPORTED


@pytest.mark.parametrize("claimed", ["not_applicable", "cannot_assess"])
def test_no_computation_and_no_verdict_claim_is_fine(claimed):
    assert check(claimed, None) is None


def test_cannot_assess_is_left_to_the_caller():
    wb = WaterBalanceResult.cannot("soil_texture_missing", as_of=date(2026, 10, 10))
    assert check("irrigate_now", wb) is None  # finalize shows the code message instead


# ---------------------------------------------------------------- messages

ALL_REASONS = [
    water_balance.NOT_SOWN_YET, water_balance.PAST_SEASON_LENGTH, water_balance.NO_WEATHER_DATA,
    water_balance.NO_ANCHOR_IN_WINDOW, water_balance.WEATHER_GAP,
    crop_water.CROP_NOT_SUPPORTED, crop_water.CROP_UNVERIFIED, crop_water.SOIL_MISSING, crop_water.SOIL_UNVERIFIED,
    irrigation_tool.NO_LOCATION, irrigation_tool.NO_ACTIVE_CROP,
    irrigation_tool.QUESTION_CROP_DIFFERS, irrigation_tool.WEATHER_UNAVAILABLE,
    messages.IRRIGATION_UNAVAILABLE,
]


def test_the_message_module_and_the_tool_agree_on_reason_codes():
    assert messages.NO_LOCATION == irrigation_tool.NO_LOCATION
    assert messages.NO_ACTIVE_CROP == irrigation_tool.NO_ACTIVE_CROP
    assert messages.QUESTION_CROP_DIFFERS == irrigation_tool.QUESTION_CROP_DIFFERS
    assert messages.WEATHER_UNAVAILABLE == irrigation_tool.WEATHER_UNAVAILABLE


@pytest.mark.parametrize("reason", ALL_REASONS)
def test_every_reason_the_system_can_emit_has_its_own_message(reason):
    assert reason in messages.KNOWN_REASONS
    text = messages.irrigation_message(WaterBalanceResult.cannot(reason, as_of=date(2026, 10, 10)))
    assert text != messages.irrigation_message(WaterBalanceResult.cannot("something_new", as_of=date(2026, 10, 10)))
    assert "1800-180-1551" in text
    assert any("ऀ" <= ch <= "ॿ" for ch in text)  # Hindi present
    assert interim_dose_guard.find_dose_statement(text) is None


def test_an_unknown_reason_still_gets_a_bilingual_message():
    text = messages.irrigation_message(WaterBalanceResult.cannot("something_new", as_of=date(2026, 10, 10)))
    assert "could not be calculated" in text and "1800-180-1551" in text


@pytest.mark.parametrize(
    "wb",
    [
        computed("irrigate_now", depletion=50.0, raw=50.0, days_to_raw=None),
        computed("irrigate_now", depletion=63.7, raw=50.0, days_to_raw=None),
        computed("wait", days_to_raw=0),
        computed("wait", days_to_raw=1),
        computed("wait", days_to_raw=4),
        computed("wait", days_to_raw=None),
        computed("wait", days_to_raw=None, forecast=0),
    ],
)
def test_computed_messages_carry_the_numbers_and_never_look_like_a_dose(wb):
    text = messages.irrigation_message(wb)
    assert messages._fmt(wb.depletion_mm) in text and messages._fmt(wb.raw_mm) in text
    assert "mm" in text and "मिमी" in text
    assert interim_dose_guard.find_dose_statement(text) is None


def test_message_wording_follows_the_verdict():
    now = messages.irrigation_message(computed("irrigate_now", days_to_raw=None))
    assert "time to irrigate" in now
    today = messages.irrigation_message(computed("wait", days_to_raw=0))
    assert "by the end of today" in today
    one = messages.irrigation_message(computed("wait", days_to_raw=1))
    assert "about 1 day." in one
    several = messages.irrigation_message(computed("wait", days_to_raw=4))
    assert "about 4 days." in several
    never = messages.irrigation_message(computed("wait", days_to_raw=None))
    assert "not expected to reach the limit in the next 7 days" in never


def test_number_formatting():
    assert messages._fmt(50.0) == "50" and messages._fmt(45.3) == "45.3" and messages._fmt(0.0) == "0"
