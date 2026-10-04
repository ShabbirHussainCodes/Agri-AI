"""Water-balance math (ADR-0015). Pure tests: no database, no network, no LLM.

Every expected number in the golden cases below was worked out BY HAND from
the formulas in app/agronomy/water_balance.py (shown next to each case), not
copied from the code's output. The crop and soil are SYNTHETIC round numbers,
so these tests prove the arithmetic and the conventions, not agronomy:

    soil:  theta_fc 0.30, theta_wp 0.10, root depth 0.5 m
           TAW = 1000 * (0.30 - 0.10) * 0.5 = 100 mm
    crop:  p = 0.5  ->  RAW = 0.5 * 100 = 50 mm
    FLAT:  Kc = 1.0 in every stage (so ETc = ET0 while the soil is not stressed)
    CURVE: Kc 0.4 -> 1.2 -> 0.6, stages of 10 / 20 / 30 / 10 days
"""
import random
from datetime import date, timedelta

import pytest

from app.agronomy import water_balance as wb
from app.agronomy.crop_water import CropParams, SoilParams, StageDays
from app.agronomy.water_balance import DayWeather, Irrigation, assess_irrigation, kc_and_stage, step

STAGES = StageDays(initial=10, development=20, mid=30, late=10)  # 70 days in all
FLAT = CropParams(name="Flat", kc_ini=1.0, kc_mid=1.0, kc_end=1.0, stage_days=STAGES, root_depth_m=0.5, p=0.5)
CURVE = CropParams(name="Curve", kc_ini=0.4, kc_mid=1.2, kc_end=0.6, stage_days=STAGES, root_depth_m=0.5, p=0.5)
SOIL = SoilParams(texture="loamy", theta_fc=0.30, theta_wp=0.10)
TAW, RAW = 100.0, 50.0

SOWING = date(2026, 10, 1)


def days(start: date, n: int, et0=5.0, rain=0.0) -> list[DayWeather]:
    return [DayWeather(date=start + timedelta(days=i), et0_mm=et0, rain_mm=rain) for i in range(n)]


def run(today: date, *, crop=FLAT, observed=None, forecast=None, irrigations=(), sowing=SOWING, **kw):
    """Observed defaults to dry days (ET0 5 mm) from sowing to yesterday; the
    forecast to 7 dry days (ET0 5 mm) from today."""
    if observed is None:
        observed = days(sowing, (today - sowing).days)
    if forecast is None:
        forecast = days(today, 7)
    return assess_irrigation(
        today=today, sowing_date=sowing, crop=crop, soil=SOIL,
        observed=observed, forecast=forecast, irrigations=list(irrigations), **kw,
    )


# ---------------------------------------------------------------- one day

def test_taw_and_raw():
    assert wb.taw_mm(SOIL, FLAT) == pytest.approx(TAW)
    assert FLAT.p * wb.taw_mm(SOIL, FLAT) == pytest.approx(RAW)


def test_step_unstressed_day():
    # Dr 30 <= RAW 50 so Ks = 1; ETc = 1*1*5 = 5; Dr = 30 + 5 = 35
    s = step(30.0, taw=TAW, raw=RAW, kc=1.0, et0=5.0, rain=0.0, irrigation_mm=0.0)
    assert (s.ks, s.etc, s.depletion) == (1.0, 5.0, 35.0)


def test_step_stressed_day():
    # Dr 60 > RAW: Ks = (100-60)/(100-50) = 0.8; ETc = 0.8*1*5 = 4; Dr = 64
    s = step(60.0, taw=TAW, raw=RAW, kc=1.0, et0=5.0, rain=0.0, irrigation_mm=0.0)
    assert s.ks == pytest.approx(0.8)
    assert s.etc == pytest.approx(4.0)
    assert s.depletion == pytest.approx(64.0)


def test_step_exactly_at_raw_is_still_unstressed():
    # Ks switches on only ABOVE RAW: Dr 50 -> Ks 1, ETc 5, Dr 55
    s = step(50.0, taw=TAW, raw=RAW, kc=1.0, et0=5.0, rain=0.0, irrigation_mm=0.0)
    assert (s.ks, s.depletion) == (1.0, 55.0)


def test_step_empty_root_zone_stays_empty():
    # Dr = TAW -> Ks = 0 -> no ET is supplied, depletion cannot grow
    s = step(100.0, taw=TAW, raw=RAW, kc=1.0, et0=5.0, rain=0.0, irrigation_mm=0.0)
    assert (s.ks, s.etc, s.depletion) == (0.0, 0.0, 100.0)


def test_step_rain_reduces_depletion():
    # 30 - 12 + 5 = 23
    assert step(30.0, taw=TAW, raw=RAW, kc=1.0, et0=5.0, rain=12.0, irrigation_mm=0.0).depletion == 23.0


def test_step_excess_water_is_deep_percolation():
    # 3 - 20 + 5 = -12 -> depletion floors at 0, 12 mm drains away
    s = step(3.0, taw=TAW, raw=RAW, kc=1.0, et0=5.0, rain=20.0, irrigation_mm=0.0)
    assert (s.depletion, s.deep_percolation) == (0.0, 12.0)


def test_step_irrigation_with_depth():
    # 40 - 25 + 5 = 20
    s = step(40.0, taw=TAW, raw=RAW, kc=1.0, et0=5.0, rain=0.0, irrigation_mm=25.0)
    assert s.depletion == 20.0 and s.irrigation_applied == 25.0


def test_step_irrigation_without_depth_refills_then_the_day_dries_it():
    # refill applies exactly the previous depletion: 47 - 47 + 5 = 5
    s = step(47.0, taw=TAW, raw=RAW, kc=1.0, et0=5.0, rain=0.0, irrigation_mm=None)
    assert s.depletion == 5.0 and s.irrigation_applied == 47.0


# ------------------------------------------------------------- Kc curve

@pytest.mark.parametrize(
    "d, kc, stage",
    [
        (0, 0.4, "initial"),
        (9, 0.4, "initial"),
        (10, 0.4, "development"),  # the line starts at Kc_ini: no jump
        (20, 0.8, "development"),  # halfway: 0.4 + (10/20) * 0.8
        (29, 1.16, "development"),  # 0.4 + (19/20) * 0.8
        (30, 1.2, "mid"),
        (59, 1.2, "mid"),
        (60, 1.2, "late"),  # the line starts at Kc_mid
        (65, 0.9, "late"),  # 1.2 + (5/10) * (0.6 - 1.2)
        (69, 0.66, "late"),  # 1.2 + (9/10) * (-0.6)
    ],
)
def test_kc_curve(d, kc, stage):
    got = kc_and_stage(CURVE, d)
    assert got is not None
    assert got[0] == pytest.approx(kc)
    assert got[1] == stage


@pytest.mark.parametrize("d", [-1, 70, 500])
def test_kc_is_undefined_outside_the_season(d):
    assert kc_and_stage(CURVE, d) is None


# ------------------------------------------------------- end to end, verdict

def test_dry_spell_reaches_raw_and_says_irrigate_now():
    # 10 dry days at 5 mm: Dr = 5, 10, ... 50. Today is day 10, Dr = 50 >= RAW 50.
    r = run(SOWING + timedelta(days=10))
    assert r.verdict == "irrigate_now" and r.reason is None
    assert (r.depletion_mm, r.raw_mm, r.taw_mm) == (50.0, 50.0, 100.0)
    assert r.days_to_raw is None
    assert (r.anchor_date, r.anchor_kind) == (SOWING, "sowing")
    assert r.days_since_sowing == 10 and r.stage == "development" and r.kc_today == 1.0


def test_one_day_earlier_it_will_reach_raw_by_the_end_of_today():
    # 9 dry days: Dr = 45 < 50 -> wait. Forecast day 0 (today): 45 + 5 = 50 -> days_to_raw 0.
    r = run(SOWING + timedelta(days=9))
    assert r.verdict == "wait"
    assert r.depletion_mm == 45.0
    assert r.days_to_raw == 0


def test_two_days_earlier():
    # 8 dry days: Dr = 40. Forecast: day 0 -> 45, day 1 -> 50. days_to_raw = 1.
    r = run(SOWING + timedelta(days=8))
    assert (r.verdict, r.depletion_mm, r.days_to_raw) == ("wait", 40.0, 1)


def test_big_rain_resets_the_bucket():
    # Days 1-5: Dr 5..25. Day 6: 25 - 40 + 5 = -10 -> 0 (10 mm drains).
    # Days 7-9: 5, 10, 15. Today is day 9, Dr = 15.
    observed = days(SOWING, 5) + days(SOWING + timedelta(days=5), 1, rain=40.0) + days(SOWING + timedelta(days=6), 3)
    r = run(SOWING + timedelta(days=9), observed=observed)
    assert (r.verdict, r.depletion_mm) == ("wait", 15.0)
    # Forecast: 20, 25, 30, 35, 40, 45, 50 -> reaches RAW on forecast day 6.
    assert r.days_to_raw == 6


def test_logged_irrigation_with_depth_is_applied_on_its_day():
    # Dr by day: 5, 10, 15, 20, then day 5: 20 - 10 + 5 = 15, 20, 25. Today is day 7: Dr = 25.
    observed = days(SOWING, 7)
    r = run(SOWING + timedelta(days=7), observed=observed,
            irrigations=[Irrigation(date=SOWING + timedelta(days=4), depth_mm=10.0)])
    assert (r.depletion_mm, r.anchor_kind) == (25.0, "sowing")
    assert r.last_irrigation_on == SOWING + timedelta(days=4)


def test_irrigation_without_depth_becomes_the_anchor():
    # Refill on day 4: that day 0 -> 0 + 5 = 5; then 10, 15. Today is day 7: Dr = 15.
    refill = SOWING + timedelta(days=4)
    r = run(SOWING + timedelta(days=7), irrigations=[Irrigation(date=refill)])
    assert (r.depletion_mm, r.anchor_date, r.anchor_kind) == (15.0, refill, "logged_irrigation")


def test_missing_weather_before_the_anchor_does_not_matter_but_after_it_does():
    today = SOWING + timedelta(days=7)
    refill = SOWING + timedelta(days=4)
    all_days = days(SOWING, 7)
    gap_before = [d for d in all_days if d.date != SOWING + timedelta(days=1)]
    gap_after = [d for d in all_days if d.date != SOWING + timedelta(days=5)]
    ok = run(today, observed=gap_before, irrigations=[Irrigation(date=refill)])
    assert ok.verdict == "wait" and ok.depletion_mm == 15.0
    bad = run(today, observed=gap_after, irrigations=[Irrigation(date=refill)])
    assert (bad.verdict, bad.reason) == ("cannot_assess", wb.WEATHER_GAP)


def test_irrigation_logged_today_without_depth_fills_the_soil_now():
    # 9 dry days would give Dr 45, but a full irrigation today makes it 0.
    today = SOWING + timedelta(days=9)
    r = run(today, irrigations=[Irrigation(date=today)])
    assert (r.verdict, r.depletion_mm) == ("wait", 0.0)
    # Forecast 5, 10, ... 35 never reaches 50 within 7 days.
    assert r.days_to_raw is None
    assert (r.anchor_date, r.anchor_kind) == (today, "logged_irrigation")


def test_irrigation_logged_today_needs_no_weather_history():
    today = SOWING + timedelta(days=30)
    r = run(today, observed=[], irrigations=[Irrigation(date=today)])
    assert (r.verdict, r.depletion_mm) == ("wait", 0.0)


def test_irrigation_logged_today_with_depth_reduces_todays_start():
    # Dr 45 - 20 = 25
    today = SOWING + timedelta(days=9)
    r = run(today, irrigations=[Irrigation(date=today, depth_mm=20.0)])
    assert r.depletion_mm == 25.0


def test_irrigation_before_sowing_is_ignored():
    r = run(SOWING + timedelta(days=7), irrigations=[Irrigation(date=SOWING - timedelta(days=6))])
    assert (r.anchor_date, r.anchor_kind) == (SOWING, "sowing")


def test_forecast_rain_is_shown_but_not_credited():
    today = SOWING + timedelta(days=9)  # Dr 45
    forecast = days(today, 7, rain=30.0)
    r = run(today, forecast=forecast)
    assert r.days_to_raw == 0  # same as with no forecast rain
    assert r.forecast_rain_mm == [30.0] * 7


def test_forecast_horizon_stops_at_the_end_of_the_season():
    # Season is days 0..69. From day 66 only 4 forecast days (66-69) have a Kc.
    today = SOWING + timedelta(days=66)
    r = run(today, observed=days(SOWING, 66, et0=1.0))  # wet-ish: Dr 66, wait
    assert len(r.forecast_et0_mm) == 4


def test_missing_forecast_does_not_change_the_verdict():
    today = SOWING + timedelta(days=9)
    r = run(today, forecast=[])
    assert (r.verdict, r.depletion_mm) == ("wait", 45.0)
    assert r.forecast_et0_mm == [] and r.days_to_raw is None


def test_forecast_stops_at_the_first_unusable_day():
    today = SOWING + timedelta(days=9)
    fc = days(today, 7)
    fc[2] = DayWeather(date=fc[2].date, et0_mm=None, rain_mm=0.0)
    r = run(today, forecast=fc)
    assert len(r.forecast_et0_mm) == 2


def test_stage_and_kc_are_reported_for_today():
    # Day 25 of CURVE: development, Kc = 0.4 + (15/20) * 0.8 = 1.0
    r = run(SOWING + timedelta(days=25), crop=CURVE, observed=days(SOWING, 25, et0=1.0))
    assert (r.stage, r.kc_today) == ("development", 1.0)


def test_verdict_is_decided_on_the_rounded_numbers_the_farmer_sees():
    # One day of ET0 49.96 -> Dr 49.96 shows as 50.0, the same as RAW 50.0.
    r = run(SOWING + timedelta(days=1), observed=[DayWeather(date=SOWING, et0_mm=49.96, rain_mm=0.0)])
    assert (r.depletion_mm, r.raw_mm) == (50.0, 50.0)
    assert r.verdict == "irrigate_now"


def test_result_carries_the_fixed_assumptions_and_table_version():
    r = run(SOWING + timedelta(days=3), table_version="crop-water-test")
    assert r.assumptions == list(wb.ASSUMPTIONS) and r.table_version == "crop-water-test"


# ------------------------------------------------------------ cannot_assess

def test_not_sown_yet():
    r = run(SOWING - timedelta(days=1), observed=[])
    assert (r.verdict, r.reason) == ("cannot_assess", wb.NOT_SOWN_YET)
    assert r.depletion_mm is None and r.crop == "Flat"


@pytest.mark.parametrize("age, ok", [(69, True), (70, False), (200, False)])
def test_past_the_season_length(age, ok):
    today = SOWING + timedelta(days=age)
    r = run(today, observed=days(SOWING, age, et0=1.0))
    assert (r.verdict != "cannot_assess") is ok
    if not ok:
        assert r.reason == wb.PAST_SEASON_LENGTH


def test_no_observed_weather():
    r = run(SOWING + timedelta(days=5), observed=[])
    assert (r.verdict, r.reason) == ("cannot_assess", wb.NO_WEATHER_DATA)


def test_observed_days_from_today_on_are_not_treated_as_observed():
    # Only a forecast-dated day is supplied as "observed": there is no history.
    today = SOWING + timedelta(days=5)
    r = run(today, observed=days(today, 3))
    assert (r.verdict, r.reason) == ("cannot_assess", wb.NO_WEATHER_DATA)


@pytest.mark.parametrize(
    "bad",
    [
        DayWeather(date=SOWING + timedelta(days=2), et0_mm=None, rain_mm=0.0),
        DayWeather(date=SOWING + timedelta(days=2), et0_mm=5.0, rain_mm=None),
        DayWeather(date=SOWING + timedelta(days=2), et0_mm=-1.0, rain_mm=0.0),
        DayWeather(date=SOWING + timedelta(days=2), et0_mm=5.0, rain_mm=-3.0),
    ],
)
def test_unusable_observed_day_is_a_weather_gap(bad):
    today = SOWING + timedelta(days=5)
    observed = [bad if d.date == bad.date else d for d in days(SOWING, 5)]
    r = run(today, observed=observed)
    assert (r.verdict, r.reason) == ("cannot_assess", wb.WEATHER_GAP)


def test_crop_older_than_the_weather_window_has_no_anchor():
    today = SOWING + timedelta(days=50)
    window = days(SOWING + timedelta(days=31), 19)  # only the last 19 days are known
    r = run(today, observed=window)
    assert (r.verdict, r.reason) == ("cannot_assess", wb.NO_ANCHOR_IN_WINDOW)


def test_a_logged_refill_inside_the_window_rescues_an_old_crop():
    today = SOWING + timedelta(days=50)
    window = days(SOWING + timedelta(days=31), 19)
    inside = SOWING + timedelta(days=40)
    r = run(today, observed=window, irrigations=[Irrigation(date=inside)])
    # Refill on day 40, dry days 40..49 at Kc 1.0: Dr = 5 * 10 = 50 -> irrigate now
    assert (r.verdict, r.depletion_mm, r.anchor_kind) == ("irrigate_now", 50.0, "logged_irrigation")


def test_a_logged_refill_before_the_window_does_not_help():
    today = SOWING + timedelta(days=50)
    window = days(SOWING + timedelta(days=31), 19)
    r = run(today, observed=window, irrigations=[Irrigation(date=SOWING + timedelta(days=20))])
    assert (r.verdict, r.reason) == ("cannot_assess", wb.NO_ANCHOR_IN_WINDOW)


# --------------------------------------------------------------- invariants
# Random but seeded, so a failure is reproducible. Ranges keep every
# kc*et0 well below (TAW - RAW), the regime where more water in can never
# mean more depletion out (a stress-limited ETc could otherwise reverse it
# for absurd inputs, which no real day produces).

def _random_step_args(rng: random.Random) -> dict:
    taw = rng.uniform(60, 200)
    return dict(
        taw=taw,
        raw=rng.uniform(0.3, 0.6) * taw,
        kc=rng.uniform(0.2, 1.3),
        et0=rng.uniform(0, 10),
        rain=0.0 if rng.random() < 0.6 else rng.uniform(0, 80),
    )


def test_step_invariants_over_random_days():
    rng = random.Random(20261004)
    for _ in range(1000):
        a = _random_step_args(rng)
        prev = rng.uniform(0, a["taw"])
        irr = rng.choice([0.0, None, rng.uniform(0, 60)])
        s = step(prev, irrigation_mm=irr, **a)
        assert 0.0 <= s.depletion <= a["taw"]
        assert 0.0 <= s.ks <= 1.0
        assert s.etc >= 0 and s.deep_percolation >= 0 and s.unmet_demand >= 0
        # Mass balance: nothing is created or lost. Water that did not fit
        # (deep percolation) and demand that could not be met (unmet) are the
        # two places the clamp sends the difference.
        assert prev - a["rain"] - s.irrigation_applied + s.etc + s.deep_percolation - s.unmet_demand \
            == pytest.approx(s.depletion, abs=1e-9)
        # Monotone: more rain never raises depletion, more ET never lowers it.
        wetter = step(prev, irrigation_mm=irr, **{**a, "rain": a["rain"] + 3.0})
        drier = step(prev, irrigation_mm=irr, **{**a, "et0": a["et0"] + 3.0})
        assert wetter.depletion <= s.depletion + 1e-9
        assert drier.depletion >= s.depletion - 1e-9
        if irr is not None:
            more = step(prev, irrigation_mm=irr + 3.0, **a)
            assert more.depletion <= s.depletion + 1e-9


def test_assess_invariants_over_random_seasons():
    rng = random.Random(7)
    for _ in range(150):
        n = rng.randint(3, 60)
        today = SOWING + timedelta(days=n)
        observed = [
            DayWeather(
                date=SOWING + timedelta(days=i),
                et0_mm=rng.uniform(0, 9),
                rain_mm=0.0 if rng.random() < 0.7 else rng.uniform(0, 70),
            )
            for i in range(n)
        ]
        forecast = [DayWeather(date=today + timedelta(days=i), et0_mm=rng.uniform(0, 9), rain_mm=rng.uniform(0, 20)) for i in range(7)]
        irrigations = [Irrigation(date=SOWING + timedelta(days=rng.randrange(n)), depth_mm=rng.uniform(5, 40)) for _ in range(rng.randint(0, 3))]
        r = assess_irrigation(today=today, sowing_date=SOWING, crop=CURVE, soil=SOIL,
                              observed=observed, forecast=forecast, irrigations=irrigations)
        assert r.verdict in ("irrigate_now", "wait")
        assert 0.0 <= r.depletion_mm <= r.taw_mm
        assert (r.verdict == "irrigate_now") == (r.depletion_mm >= r.raw_mm)
        if r.verdict == "irrigate_now":
            assert r.days_to_raw is None
        elif r.days_to_raw is not None:
            assert 0 <= r.days_to_raw < len(r.forecast_et0_mm)

        # More rain on any observed day never raises depletion; more ET never lowers it
        # (tolerance covers the 1-decimal rounding of the reported value).
        k = rng.randrange(n)
        wetter = [d.model_copy(update={"rain_mm": d.rain_mm + 10.0}) if i == k else d for i, d in enumerate(observed)]
        drier = [d.model_copy(update={"et0_mm": d.et0_mm + 2.0}) if i == k else d for i, d in enumerate(observed)]
        common = dict(today=today, sowing_date=SOWING, crop=CURVE, soil=SOIL, forecast=forecast, irrigations=irrigations)
        assert assess_irrigation(observed=wetter, **common).depletion_mm <= r.depletion_mm + 0.051
        assert assess_irrigation(observed=drier, **common).depletion_mm >= r.depletion_mm - 0.051
