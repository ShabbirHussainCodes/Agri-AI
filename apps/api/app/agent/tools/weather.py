"""get_weather: minimal live weather via Open-Meteo -- free, no API key
(verified against open-meteo.com/en/docs on 2026-08-30).

Deliberately a SUBSET of the full tool spec in docs/ai/agent-design.md
(which also wants soil moisture at 5 depths, soil temperature, and
ET0) -- that full version is Phase 5's job. Phase 2 only needs current
+ 3-day rain, per the Phase 2 planning discussion (Decision A2): enough
to demonstrate the tool-calling loop against genuinely live data without
front-loading Phase 5's scope.
"""
from typing import Any
from uuid import UUID

import asyncpg
import httpx
from pydantic import BaseModel, ConfigDict

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherUnavailable(Exception):
    """Raised when the farm has no stored location (lat/lon) yet."""


class WeatherData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_temp_c: float | None = None
    current_rain_mm: float | None = None
    forecast_dates: list[str] = []
    forecast_rain_mm: list[float] = []


# No parameters -- like get_farm_context, farm_id is server-bound from the
# URL path. The model cannot ask for weather at an arbitrary location,
# only at the farm it is already scoped to; the farm's own lat/lon
# (Phase 1's farms table) is looked up here, not supplied by the model.
TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Get current temperature and rain, plus a 3-day rain "
            "forecast, at this farm's own location. Use this for "
            "irrigation-timing or spray-timing questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}


async def get_weather(conn: asyncpg.Connection, farm_id: UUID) -> WeatherData:
    row = await conn.fetchrow("select lat, lon from public.farms where id = $1", farm_id)
    if row is None or row["lat"] is None or row["lon"] is None:
        raise WeatherUnavailable("This farm has no location (lat/lon) set yet.")

    params = {
        "latitude": row["lat"],
        "longitude": row["lon"],
        "current": "temperature_2m,rain",
        "daily": "rain_sum",
        "timezone": "auto",
        "forecast_days": 3,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    current = data.get("current", {})
    daily = data.get("daily", {})

    return WeatherData(
        current_temp_c=current.get("temperature_2m"),
        current_rain_mm=current.get("rain"),
        forecast_dates=daily.get("time", []),
        forecast_rain_mm=daily.get("rain_sum", []),
    )
