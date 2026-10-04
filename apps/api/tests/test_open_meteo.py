"""Open-Meteo client (app/integrations/open_meteo.py). No network: the HTTP
leg is httpx.MockTransport. The response shape below (utc_offset_seconds,
daily.time, daily.<variable>) matches the real response recorded in
tests/cassettes/test_ask; the variable names are NOT proven here (ADR-0015),
only that the client sends them and refuses anything it does not understand."""
from datetime import date

import httpx
import pytest

from app.integrations import open_meteo
from app.integrations.open_meteo import OpenMeteoError, fetch_daily, parse_daily

BODY = {
    "latitude": 26.81898,
    "longitude": 80.93023,
    "utc_offset_seconds": 19800,
    "timezone": "Asia/Kolkata",
    "daily_units": {"time": "iso8601", "et0_fao_evapotranspiration": "mm", "precipitation_sum": "mm"},
    "daily": {
        "time": ["2026-10-08", "2026-10-09", "2026-10-10"],
        "et0_fao_evapotranspiration": [4.1, None, 5.0],
        "precipitation_sum": [0.0, 12.5, 0.3],
    },
}


def test_parse_daily_maps_dates_values_and_keeps_missing_values_missing():
    s = parse_daily(BODY)
    assert s.utc_offset_seconds == 19800
    assert [d.date for d in s.days] == [date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 10)]
    assert s.days[0].et0_mm == 4.1 and s.days[0].rain_mm == 0.0
    assert s.days[1].et0_mm is None  # a gap stays a gap: the engine refuses to guess it
    assert s.days[1].rain_mm == 12.5


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.pop("utc_offset_seconds"),
        lambda b: b.pop("daily"),
        lambda b: b["daily"].pop("et0_fao_evapotranspiration"),
        lambda b: b["daily"].pop("precipitation_sum"),
        lambda b: b["daily"].update(precipitation_sum=[0.0]),  # lengths differ
        lambda b: b["daily"].update(time=["not-a-date", "2026-10-09", "2026-10-10"]),
        lambda b: b.update(utc_offset_seconds="soon"),
        lambda b: b["daily"].update(et0_fao_evapotranspiration=["x", 1, 2]),
    ],
)
def test_a_malformed_body_is_an_error_never_weather(mutate):
    import copy
    body = copy.deepcopy(BODY)
    mutate(body)
    with pytest.raises(OpenMeteoError):
        parse_daily(body)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_the_request_asks_for_the_right_things_and_rounds_the_coordinates():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        seen["host"] = request.url.host
        return httpx.Response(200, json=BODY)

    async with _client(handler) as client:
        series = await fetch_daily(26.818987, 80.930234, client=client)
    assert seen["host"] == "api.open-meteo.com"
    assert seen["latitude"] == "26.82" and seen["longitude"] == "80.93"  # ~1 km, not the farm gate
    assert seen["daily"] == "et0_fao_evapotranspiration,precipitation_sum"
    assert seen["timezone"] == "auto"
    assert seen["past_days"] == "92" and seen["forecast_days"] == "7"
    assert len(series.days) == 3


@pytest.mark.asyncio
async def test_http_error_becomes_open_meteo_error():
    def handler(request):
        return httpx.Response(400, json={"error": True, "reason": "Cannot initialize WeatherVariable from invalid String value"})

    async with _client(handler) as client:
        with pytest.raises(OpenMeteoError):
            await fetch_daily(26.85, 80.95, client=client)


@pytest.mark.asyncio
async def test_non_json_body_becomes_open_meteo_error():
    async with _client(lambda r: httpx.Response(200, text="<html>gateway</html>")) as client:
        with pytest.raises(OpenMeteoError):
            await fetch_daily(26.85, 80.95, client=client)


@pytest.mark.asyncio
async def test_a_json_body_that_is_not_an_object_becomes_open_meteo_error():
    async with _client(lambda r: httpx.Response(200, json=[1, 2, 3])) as client:
        with pytest.raises(OpenMeteoError):
            await fetch_daily(26.85, 80.95, client=client)


@pytest.mark.asyncio
async def test_a_timeout_becomes_open_meteo_error():
    def handler(request):
        raise httpx.ConnectTimeout("too slow", request=request)

    async with _client(handler) as client:
        with pytest.raises(OpenMeteoError):
            await fetch_daily(26.85, 80.95, client=client)


def test_attribution_names_the_source_and_licence():
    assert "Open-Meteo.com" in open_meteo.ATTRIBUTION and "CC BY 4.0" in open_meteo.ATTRIBUTION
