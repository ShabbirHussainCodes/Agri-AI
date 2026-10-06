"""get_irrigation_status: the computed answer to "should I water now?"
(ADR-0015). A thin glue layer: it READS the farm record, the irrigation log
and Open-Meteo, then hands everything to the pure engine in
app/agronomy/water_balance.py. No arithmetic and no agronomy lives here.

Like get_weather it takes no parameters: farm_id is bound server-side, so
the model cannot ask for a balance at another farm. Unlike get_weather its
result is typed (`WaterBalanceResult`) and ends up in the farmer's response
as `water_balance`, written by code, never by the model.

Every way this can fail to produce a verdict returns a `cannot_assess`
result with a reason code (never a guess, never an exception the farmer
would see): no location, no active crop, a crop or soil the reference table
does not cover or has not verified, an unreachable weather service.
"""
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg

from app.agronomy import crop_water
from app.agronomy.water_balance import Irrigation, WaterBalanceResult, assess_irrigation
from app.core.clock import farm_today
from app.integrations import open_meteo
from app.safety import crop_scope

NO_LOCATION = "no_location"
NO_ACTIVE_CROP = "no_active_crop"
QUESTION_CROP_DIFFERS = "question_crop_differs"
WEATHER_UNAVAILABLE = "weather_unavailable"

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "get_irrigation_status",
        "description": (
            "Get the computed irrigation status of this farm's active crop: whether "
            "irrigation is due now, how many mm of water the soil is short of, and how "
            "soon that reaches the limit. Calculated by code from the weather, the farm "
            "record and the irrigation log. Use it for any question about whether or "
            "when to water or irrigate."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}

FetchDaily = Callable[..., Awaitable[open_meteo.DailySeries]]


def _depth_mm(details: Any) -> float | None:
    """`details.depth_mm` if it is a sane number, else None (= amount not
    logged, so the engine assumes a full refill, as for an irrigation logged
    without an amount). bool is excluded: True would otherwise read as 1."""
    if not isinstance(details, dict):
        return None
    value = details.get("depth_mm")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if 0 <= value <= 1000 else None


async def get_irrigation_status(
    conn: asyncpg.Connection,
    farm_id: UUID,
    *,
    named_crops: frozenset[str] = frozenset(),
    table_path=None,
    fetch: FetchDaily = open_meteo.fetch_daily,
    now: datetime | None = None,
) -> WaterBalanceResult:
    """`named_crops`: crops the farmer's question names (crop_scope). `now`
    and `fetch` exist so tests need neither a clock nor a network."""
    now = now or datetime.now(timezone.utc)
    # Until the weather response says what the farm's local date is, the
    # farm calendar date at the configured offset (app/core/clock.py) stands in
    # for `as_of` on the early-exit results below.
    utc_today = farm_today(now)

    farm = await conn.fetchrow(
        "select lat, lon, soil_texture from public.farms where id = $1", farm_id
    )
    if farm is None or farm["lat"] is None or farm["lon"] is None:
        return WaterBalanceResult.cannot(NO_LOCATION, as_of=utc_today)

    crop_row = await conn.fetchrow(
        """
        select fc.id, c.name_en, fc.sowing_date
        from public.farm_crops fc
        join public.crops c on c.id = fc.crop_id
        where fc.farm_id = $1 and fc.status = 'active'
        order by fc.sowing_date desc
        limit 1
        """,
        farm_id,
    )
    if crop_row is None:
        return WaterBalanceResult.cannot(NO_ACTIVE_CROP, as_of=utc_today)
    crop_name: str = crop_row["name_en"]
    soil_texture: str | None = farm["soil_texture"]

    def cannot(reason: str, table_version: str | None = None) -> WaterBalanceResult:
        return WaterBalanceResult.cannot(
            reason,
            as_of=utc_today,
            crop=crop_name,
            soil_texture=soil_texture,
            table_version=table_version,
        )

    # A question about another crop must never be answered with this crop's
    # balance. The farm's crop is matched with the same lexicon as the question.
    if named_crops and not (named_crops & crop_scope.crops_named_in(crop_name)):
        return cannot(QUESTION_CROP_DIFFERS)

    table = crop_water.get_table(table_path)
    crop_params, reason = crop_water.find_crop(table, crop_name)
    if crop_params is None:
        return cannot(reason or crop_water.CROP_NOT_SUPPORTED, table.table_version)
    soil_params, reason = crop_water.find_soil(table, soil_texture)
    if soil_params is None:
        return cannot(reason or crop_water.SOIL_MISSING, table.table_version)

    event_rows = await conn.fetch(
        """
        select occurred_on, details from public.activities
        where farm_crop_id = $1 and type = 'irrigation' and occurred_on >= $2
        order by occurred_on
        """,
        crop_row["id"],
        crop_row["sowing_date"],
    )
    irrigations = [
        Irrigation(date=r["occurred_on"], depth_mm=_depth_mm(r["details"])) for r in event_rows
    ]

    try:
        series = await fetch(farm["lat"], farm["lon"])
    except open_meteo.OpenMeteoError:
        return cannot(WEATHER_UNAVAILABLE, table.table_version)

    today = (now + timedelta(seconds=series.utc_offset_seconds)).date()
    result = assess_irrigation(
        today=today,
        sowing_date=crop_row["sowing_date"],
        crop=crop_params,
        soil=soil_params,
        observed=[d for d in series.days if d.date < today],
        forecast=[d for d in series.days if d.date >= today],
        irrigations=irrigations,
        table_version=table.table_version,
    )
    return result.model_copy(update={"data_source": open_meteo.ATTRIBUTION})


def to_tool_payload(result: WaterBalanceResult) -> dict[str, Any]:
    """What the model reads: the same fields, minus empty ones, to spare
    tokens. `days_to_raw` stays even when null: null there means "not within
    the forecast", which is information, not absence."""
    data = result.model_dump(mode="json")
    keep_null = {"days_to_raw"} if result.verdict == "wait" else set()
    return {
        k: v
        for k, v in data.items()
        if (v is not None or k in keep_null) and v != []
    }
