"""Open-Meteo client for the irrigation water balance (ADR-0015).

Free, no API key, data under CC BY 4.0 (docs/integrations/external-integrations.md);
the free API is for non-commercial use, so a commercial product needs a paid plan.
Parameter names and limits (`et0_fao_evapotranspiration`, `past_days` 0-92,
`forecast_days` up to 16) were taken from search results on 2026-10-04 because
open-meteo.com was unreachable from the build environment. The response SHAPE
(`utc_offset_seconds`, `daily.time`, `daily.<variable>`) was checked against the
real response recorded in tests/cassettes/test_ask. The first live call is the
proof of the variable names: a wrong one makes Open-Meteo answer HTTP 400, which
this client reports as OpenMeteoError, never as data.

Privacy (CLAUDE.md section 5): farm location is personal data. Coordinates are
rounded to 2 decimals (about 1 km) before they leave the server. Open-Meteo
snaps a request to its own model grid anyway (the recorded response for
26.85/80.95 came back as 26.819/80.930), so nothing is lost.
"""
from datetime import date

import httpx
from pydantic import BaseModel, ConfigDict

from app.agronomy.water_balance import DayWeather

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
# precipitation_sum, not rain_sum: any water that reaches the soil counts.
DAILY_VARIABLES = "et0_fao_evapotranspiration,precipitation_sum"
PAST_DAYS = 92  # the most the forecast endpoint serves
FORECAST_DAYS = 7
TIMEOUT_SECONDS = 10.0

# CC BY 4.0 requires attribution where the data is shown.
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"


class OpenMeteoError(Exception):
    """Any failure to get a usable daily series: network, HTTP status,
    malformed body. The message is for logs; the farmer is told the weather
    is unavailable."""


class DailySeries(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Offset of the farm's local time from UTC, from the response. "Today"
    # for the water balance is the local date, not the server's.
    utc_offset_seconds: int
    days: list[DayWeather]


def _round_coordinate(value: float) -> float:
    return round(value, 2)


def parse_daily(payload: dict) -> DailySeries:
    """Pure: the response body -> DailySeries. Raises OpenMeteoError on any
    shape problem so a half-understood body is never treated as weather."""
    try:
        offset = int(payload["utc_offset_seconds"])
        daily = payload["daily"]
        times = daily["time"]
        et0 = daily["et0_fao_evapotranspiration"]
        rain = daily["precipitation_sum"]
        if not (len(times) == len(et0) == len(rain)):
            raise ValueError("daily arrays differ in length")
        days = [
            DayWeather(date=date.fromisoformat(t), et0_mm=e, rain_mm=r)
            for t, e, r in zip(times, et0, rain)
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise OpenMeteoError(f"unexpected Open-Meteo response: {exc}") from exc
    return DailySeries(utc_offset_seconds=offset, days=days)


async def fetch_daily(
    lat: float,
    lon: float,
    *,
    past_days: int = PAST_DAYS,
    forecast_days: int = FORECAST_DAYS,
    client: httpx.AsyncClient | None = None,
) -> DailySeries:
    params = {
        "latitude": _round_coordinate(lat),
        "longitude": _round_coordinate(lon),
        "daily": DAILY_VARIABLES,
        "timezone": "auto",
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    try:
        if client is not None:
            resp = await client.get(OPEN_METEO_URL, params=params)
        else:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as own:
                resp = await own.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:  # ValueError: body is not JSON
        raise OpenMeteoError(f"Open-Meteo request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenMeteoError("unexpected Open-Meteo response: not an object")
    return parse_daily(payload)
