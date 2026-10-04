"""FAO-56 single-crop-coefficient root-zone water balance (ADR-0015).

Pure functions: no I/O, no clock (`today` is a parameter), no LLM. The model
only explains what this module computes (CLAUDE.md rule 7).

The bucket. `depletion` is how many mm of water are missing from the root
zone: 0 means full (field capacity), TAW means empty (wilting point).

    TAW = 1000 * (theta_fc - theta_wp) * root_depth_m        total available water, mm
    RAW = p * TAW                                            readily available water, mm
    Ks  = 1                              if depletion <= RAW
          (TAW - depletion)/(TAW - RAW)  otherwise           stress factor, 0..1
    ETc = Ks * Kc * ET0
    depletion_today = depletion_yesterday - rain - irrigation + ETc
                      then clamped to [0, TAW]; below 0 the excess is deep percolation

(FAO-56 chapter 8, Eq. 82-85, as read from search results on 2026-10-04: the
primary pages were unreachable from the build environment. The Ks form and
the depletion balance were seen quoted; TAW/RAW are the standard forms. Check
all four against the paper when the crop table is verified.)

Our own conventions, NOT FAO-56 verbatim, so tests pin them down:
  * Day index d = (date - sowing_date).days, so the sowing day is d = 0.
  * Kc is piecewise linear: Kc_ini through the initial stage, a straight line
    to Kc_mid across the development stage, Kc_mid through the mid stage, a
    straight line to Kc_end across the late stage. Past the last day Kc is
    undefined and the engine says so rather than extrapolating.
  * Ks uses the PREVIOUS day's depletion (the day's own ETc is not known yet).
  * Runoff and capillary rise are zero; rain is fully effective. Deep
    percolation is the part of rain + irrigation that does not fit.
  * One constant root depth and one depletion fraction for the whole season.
  * The balance starts from an ANCHOR where the soil is assumed to be full:
    sowing day, or the most recent logged irrigation with no depth.
  * Only observed days (before `today`) change the state. `today` and later
    are forecast: used to project days-to-RAW, with NO forecast rain credited.
  * Displayed numbers are rounded to 1 decimal and the verdict is decided on
    the rounded numbers, so the farmer never sees "50.0 of 50.0" and "wait".

Verdict (rule agreed with the project owner before any run):
  irrigate_now   depletion at the start of today >= RAW
  wait           otherwise; `days_to_raw` = first forecast day (0 = today)
                 whose END reaches RAW, or None if not within the horizon
  cannot_assess  any input missing or not trustworthy; `reason` says which
"""
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict

from app.agronomy.crop_water import CropParams, SoilParams

Verdict = Literal["irrigate_now", "wait", "cannot_assess"]
Stage = Literal["initial", "development", "mid", "late"]
AnchorKind = Literal["sowing", "logged_irrigation"]

# Engine-level reason codes (table-level ones live in crop_water.py).
NOT_SOWN_YET = "not_sown_yet"
PAST_SEASON_LENGTH = "past_season_length"
NO_WEATHER_DATA = "no_weather_data"
NO_ANCHOR_IN_WINDOW = "no_anchor_in_window"
WEATHER_GAP = "weather_gap"

# How many forecast days are projected (and shown). Forecast skill falls with
# lead time and every number shown costs tokens.
DEFAULT_HORIZON_DAYS = 7

# Fixed, code-authored statements of what the number rests on. Shown to the
# model with the result so it can be honest about uncertainty.
ASSUMPTIONS = (
    "The soil is assumed full (field capacity) on the starting date: sowing, or the last irrigation logged without an amount.",
    "All rain is assumed to soak in (no runoff). Forecast rain is not counted.",
    "One root depth and one depletion fraction are used for the whole season.",
    "An irrigation logged without an amount is assumed to refill the root zone completely.",
)


class DayWeather(BaseModel):
    """One calendar day in the farm's local date. None = not available."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: date
    et0_mm: float | None
    rain_mm: float | None


class Irrigation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    date: date
    depth_mm: float | None = None  # None: amount not logged, assume a full refill


class WaterBalanceResult(BaseModel):
    """What the farmer's response carries as `water_balance`: computed by
    code, never written by the model."""

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    reason: str | None = None
    as_of: date
    crop: str | None = None
    soil_texture: str | None = None
    table_version: str | None = None

    days_since_sowing: int | None = None
    stage: Stage | None = None
    kc_today: float | None = None
    depletion_mm: float | None = None
    raw_mm: float | None = None
    taw_mm: float | None = None
    days_to_raw: int | None = None
    forecast_et0_mm: list[float] = []
    forecast_rain_mm: list[float] = []  # context only: NOT credited in the balance
    anchor_date: date | None = None
    anchor_kind: AnchorKind | None = None
    last_irrigation_on: date | None = None
    assumptions: list[str] = []
    data_source: str | None = None  # set by the tool that fetched the weather

    @classmethod
    def cannot(
        cls,
        reason: str,
        *,
        as_of: date,
        crop: str | None = None,
        soil_texture: str | None = None,
        table_version: str | None = None,
    ) -> "WaterBalanceResult":
        return cls(
            verdict="cannot_assess",
            reason=reason,
            as_of=as_of,
            crop=crop,
            soil_texture=soil_texture,
            table_version=table_version,
        )


class DayStep(NamedTuple):
    depletion: float
    etc: float
    ks: float
    deep_percolation: float  # water that did not fit (rain + irrigation beyond depletion)
    unmet_demand: float  # ET that could not be supplied because the root zone is empty
    irrigation_applied: float


def taw_mm(soil: SoilParams, crop: CropParams) -> float:
    return 1000.0 * (soil.theta_fc - soil.theta_wp) * crop.root_depth_m


def kc_and_stage(crop: CropParams, day_index: int) -> tuple[float, Stage] | None:
    """Kc and stage for day `day_index` after sowing, or None past the season."""
    s = crop.stage_days
    if day_index < 0:
        return None
    if day_index < s.initial:
        return crop.kc_ini, "initial"
    end_dev = s.initial + s.development
    if day_index < end_dev:
        frac = (day_index - s.initial) / s.development
        return crop.kc_ini + frac * (crop.kc_mid - crop.kc_ini), "development"
    end_mid = end_dev + s.mid
    if day_index < end_mid:
        return crop.kc_mid, "mid"
    if day_index < s.total:
        frac = (day_index - end_mid) / s.late
        return crop.kc_mid + frac * (crop.kc_end - crop.kc_mid), "late"
    return None


def step(
    depletion_prev: float,
    *,
    taw: float,
    raw: float,
    kc: float,
    et0: float,
    rain: float,
    irrigation_mm: float | None,
) -> DayStep:
    """One day of the bucket. `irrigation_mm=None` means refill completely:
    exactly the previous depletion is applied."""
    ks = 1.0 if depletion_prev <= raw else max(0.0, (taw - depletion_prev) / (taw - raw))
    etc = ks * kc * et0
    irrigation = depletion_prev if irrigation_mm is None else irrigation_mm
    unclamped = depletion_prev - rain - irrigation + etc
    return DayStep(
        depletion=min(max(unclamped, 0.0), taw),
        etc=etc,
        ks=ks,
        deep_percolation=max(-unclamped, 0.0),
        unmet_demand=max(unclamped - taw, 0.0),
        irrigation_applied=irrigation,
    )


def choose_anchor(
    *,
    today: date,
    sowing_date: date,
    window_start: date,
    irrigations: Sequence[Irrigation],
) -> tuple[date, AnchorKind] | None:
    """Where the soil is assumed full. The most recent irrigation logged with
    no amount (after sowing, before today) beats sowing, because it is later.
    Either must lie inside the observed weather window, or the days between
    the anchor and today have no data."""
    refills = [
        e.date for e in irrigations if e.depth_mm is None and sowing_date <= e.date < today
    ]
    if refills and max(refills) >= window_start:
        return max(refills), "logged_irrigation"
    if sowing_date >= window_start:
        return sowing_date, "sowing"
    return None


def _valid(x: float | None) -> bool:
    return x is not None and x >= 0.0


def _irrigation_on(events: Sequence[Irrigation], day: date) -> float | None:
    """Combined irrigation for one calendar day: any refill event wins,
    otherwise the logged depths add up."""
    todays = [e for e in events if e.date == day]
    if any(e.depth_mm is None for e in todays):
        return None
    return sum(e.depth_mm for e in todays if e.depth_mm is not None)


def assess_irrigation(
    *,
    today: date,
    sowing_date: date,
    crop: CropParams,
    soil: SoilParams,
    observed: Sequence[DayWeather],
    forecast: Sequence[DayWeather],
    irrigations: Sequence[Irrigation],
    table_version: str | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> WaterBalanceResult:
    def cannot(reason: str) -> WaterBalanceResult:
        return WaterBalanceResult.cannot(
            reason,
            as_of=today,
            crop=crop.name,
            soil_texture=soil.texture,
            table_version=table_version,
        )

    if sowing_date > today:
        return cannot(NOT_SOWN_YET)
    days_since_sowing = (today - sowing_date).days
    today_kc = kc_and_stage(crop, days_since_sowing)
    if today_kc is None:
        return cannot(PAST_SEASON_LENGTH)
    kc_today, stage = today_kc

    taw = taw_mm(soil, crop)
    raw = crop.p * taw

    past = {d.date: d for d in observed if d.date < today}
    todays_events = [e for e in irrigations if e.date == today]
    refill_today = any(e.depth_mm is None for e in todays_events)

    # An irrigation logged today with no amount makes the soil full right now,
    # whatever the history was, so no history is needed for the verdict.
    anchor_date: date | None = None
    anchor_kind: AnchorKind | None = None
    depletion = 0.0
    if refill_today:
        anchor_date, anchor_kind = today, "logged_irrigation"
    else:
        if not past:
            return cannot(NO_WEATHER_DATA)
        anchor = choose_anchor(
            today=today,
            sowing_date=sowing_date,
            window_start=min(past),
            irrigations=irrigations,
        )
        if anchor is None:
            return cannot(NO_ANCHOR_IN_WINDOW)
        anchor_date, anchor_kind = anchor

        day = anchor_date
        while day < today:
            wx = past.get(day)
            if wx is None or not _valid(wx.et0_mm) or not _valid(wx.rain_mm):
                return cannot(WEATHER_GAP)
            kc_stage = kc_and_stage(crop, (day - sowing_date).days)
            if kc_stage is None:  # unreachable while today is in season; kept as a guard
                return cannot(PAST_SEASON_LENGTH)
            depletion = step(
                depletion,
                taw=taw,
                raw=raw,
                kc=kc_stage[0],
                et0=wx.et0_mm,  # type: ignore[arg-type]
                rain=wx.rain_mm,  # type: ignore[arg-type]
                irrigation_mm=_irrigation_on(irrigations, day),
            ).depletion
            day += timedelta(days=1)

    # Irrigation logged today is applied to the start-of-today state.
    if todays_events:
        applied = _irrigation_on(irrigations, today)
        depletion = 0.0 if applied is None else max(depletion - applied, 0.0)

    depletion_shown = round(depletion, 1)
    raw_shown = round(raw, 1)
    verdict: Verdict = "irrigate_now" if depletion_shown >= raw_shown else "wait"

    # Projection over the forecast, only the contiguous days starting today.
    fc = {d.date: d for d in forecast if d.date >= today}
    et0s: list[float] = []
    rains: list[float] = []
    days_to_raw: int | None = None
    projected = depletion
    for k in range(horizon_days):
        wx = fc.get(today + timedelta(days=k))
        if wx is None or not _valid(wx.et0_mm) or not _valid(wx.rain_mm):
            break
        kc_stage = kc_and_stage(crop, days_since_sowing + k)
        if kc_stage is None:
            break
        et0s.append(round(wx.et0_mm, 1))  # type: ignore[arg-type]
        rains.append(round(wx.rain_mm, 1))  # type: ignore[arg-type]
        if verdict == "wait" and days_to_raw is None:
            projected = step(
                projected,
                taw=taw,
                raw=raw,
                kc=kc_stage[0],
                et0=wx.et0_mm,  # type: ignore[arg-type]
                rain=0.0,  # forecast rain is NOT credited
                irrigation_mm=0.0,
            ).depletion
            if round(projected, 1) >= raw_shown:
                days_to_raw = k

    last_irrigation = max((e.date for e in irrigations if e.date <= today), default=None)
    return WaterBalanceResult(
        verdict=verdict,
        as_of=today,
        crop=crop.name,
        soil_texture=soil.texture,
        table_version=table_version,
        days_since_sowing=days_since_sowing,
        stage=stage,
        kc_today=round(kc_today, 2),
        depletion_mm=depletion_shown,
        raw_mm=raw_shown,
        taw_mm=round(taw, 1),
        days_to_raw=days_to_raw,
        forecast_et0_mm=et0s,
        forecast_rain_mm=rains,
        anchor_date=anchor_date,
        anchor_kind=anchor_kind,
        last_irrigation_on=last_irrigation,
        assumptions=list(ASSUMPTIONS),
    )
