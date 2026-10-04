"""get_irrigation_status (app/agent/tools/irrigation.py) without a database
and without a network: a fake connection returns the farm rows, a fake
fetcher returns the weather, a clock is passed in.

The reference table used here is SYNTHETIC (round numbers, written to a temp
file, flat Kc of 1.0). It proves the plumbing and every cannot_assess reason,
not agronomy. The shipped table is not used, so these tests keep passing
when a human later verifies its rows."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.agent.tools import irrigation
from app.agent.tools.irrigation import _depth_mm, get_irrigation_status, to_tool_payload
from app.agronomy.water_balance import DayWeather, WaterBalanceResult
from app.integrations.open_meteo import ATTRIBUTION, DailySeries, OpenMeteoError

pytestmark = pytest.mark.asyncio

SOWING = date(2026, 10, 1)
NOW = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)  # 11:30 IST on 10 Oct

VERIFIED = {"verified_by": "Test Reviewer", "verified_on": "2026-10-04"}
TABLE = {
    "table_version": "synthetic-test",
    "method": "test", "primary_source": "test",
    "crops": [
        {"name_en": "Wheat", "status": "verified", **VERIFIED,
         "kc_ini": 1.0, "kc_mid": 1.0, "kc_end": 1.0,
         "stage_days": {"initial": 10, "development": 20, "mid": 30, "late": 10},
         "stage_length_basis": "synthetic", "root_depth_m": 0.5, "p": 0.5,
         "sources": {"kc": "t", "stage_days": "t", "root_depth_m": "t", "p": "t"}},
        {"name_en": "Maize", "status": "unverified"},
    ],
    "soils": [
        {"texture": "loamy", "status": "verified", **VERIFIED, "fao56_class": "synthetic",
         "theta_fc": 0.30, "theta_wp": 0.10, "sources": {"theta": "t"}},
        {"texture": "sandy", "status": "unverified"},
    ],
}


@pytest.fixture
def table_path(tmp_path):
    path = tmp_path / "synthetic-crop-water.json"
    path.write_text(json.dumps(TABLE), encoding="utf-8")
    return path


class FakeConn:
    """Answers the three queries the tool makes, by what the SQL mentions."""

    def __init__(self, farm=None, crop=None, events=()):
        self.farm, self.crop, self.events = farm, crop, list(events)

    async def fetchrow(self, sql, *args):
        if "public.farms" in sql:
            return self.farm
        if "public.farm_crops" in sql:
            return self.crop
        raise AssertionError(f"unexpected query: {sql}")

    async def fetch(self, sql, *args):
        assert "public.activities" in sql and "type = 'irrigation'" in sql
        return self.events


def farm(**kw):
    return {"lat": 26.85, "lon": 80.95, "soil_texture": "loamy", **kw}


def crop(name="Wheat", sowing=SOWING):
    return {"id": "crop-1", "name_en": name, "sowing_date": sowing}


def weather(today=date(2026, 10, 10), observed_days=9, offset=19800):
    start = today - timedelta(days=observed_days)
    days = [DayWeather(date=start + timedelta(days=i), et0_mm=5.0, rain_mm=0.0) for i in range(observed_days + 7)]
    return DailySeries(utc_offset_seconds=offset, days=days)


class Fetcher:
    def __init__(self, series=None, error=None):
        self.series, self.error, self.calls = series, error, []

    async def __call__(self, lat, lon, **kw):
        self.calls.append((lat, lon))
        if self.error:
            raise self.error
        return self.series


async def run(conn, table_path, fetcher=None, **kw):
    return await get_irrigation_status(
        conn, "farm-1", table_path=table_path, fetch=fetcher or Fetcher(weather()), now=NOW, **kw
    )


async def test_happy_path_computes_and_attributes_the_weather(table_path):
    fetcher = Fetcher(weather())
    r = await run(FakeConn(farm(), crop()), table_path, fetcher)
    # 9 dry days at ET0 5, Kc 1: depletion 45, limit 50 -> wait, limit reached by end of today
    assert (r.verdict, r.depletion_mm, r.raw_mm, r.taw_mm, r.days_to_raw) == ("wait", 45.0, 50.0, 100.0, 0)
    assert r.crop == "Wheat" and r.soil_texture == "loamy" and r.table_version == "synthetic-test"
    assert r.data_source == ATTRIBUTION
    assert fetcher.calls == [(26.85, 80.95)]  # the client does the rounding, not the tool


async def test_today_is_the_farms_local_date_not_the_servers(table_path):
    # 20:00 UTC on 9 Oct is already 01:30 IST on 10 Oct.
    late = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
    r = await get_irrigation_status(
        FakeConn(farm(), crop()), "farm-1", table_path=table_path,
        fetch=Fetcher(weather()), now=late,
    )
    assert r.as_of == date(2026, 10, 10) and r.days_since_sowing == 9


@pytest.mark.parametrize("conn", [FakeConn(None, crop()), FakeConn(farm(lat=None), crop()), FakeConn(farm(lon=None), crop())])
async def test_no_location(conn, table_path):
    r = await run(conn, table_path)
    assert (r.verdict, r.reason) == ("cannot_assess", irrigation.NO_LOCATION)


async def test_no_active_crop(table_path):
    r = await run(FakeConn(farm(), None), table_path)
    assert (r.verdict, r.reason) == ("cannot_assess", irrigation.NO_ACTIVE_CROP)


@pytest.mark.parametrize(
    "conn, reason",
    [
        (FakeConn(farm(soil_texture=None), crop()), "soil_texture_missing"),
        (FakeConn(farm(soil_texture="sandy"), crop()), "soil_reference_unverified"),
        (FakeConn(farm(soil_texture="clayey"), crop()), "soil_texture_missing"),  # not in the table
        (FakeConn(farm(), crop("Maize")), "crop_reference_unverified"),
        (FakeConn(farm(), crop("Rice (Paddy)")), "crop_not_supported"),
    ],
)
async def test_reference_data_reasons(conn, reason, table_path):
    fetcher = Fetcher(weather())
    r = await run(conn, table_path, fetcher)
    assert (r.verdict, r.reason) == ("cannot_assess", reason)
    assert r.table_version == "synthetic-test"
    assert fetcher.calls == []  # no weather is fetched for an answer that cannot be given


async def test_a_question_about_another_crop_is_never_answered_with_this_crops_balance(table_path):
    r = await run(FakeConn(farm(), crop("Wheat")), table_path, named_crops=frozenset({"tomato"}))
    assert (r.verdict, r.reason) == ("cannot_assess", irrigation.QUESTION_CROP_DIFFERS)


@pytest.mark.parametrize("named", [frozenset(), frozenset({"wheat"}), frozenset({"wheat", "tomato"})])
async def test_a_question_naming_the_farms_crop_or_no_crop_is_answered(named, table_path):
    r = await run(FakeConn(farm(), crop("Wheat")), table_path, named_crops=named)
    assert r.verdict == "wait"


async def test_weather_unavailable(table_path):
    r = await run(FakeConn(farm(), crop()), table_path, Fetcher(error=OpenMeteoError("down")))
    assert (r.verdict, r.reason) == ("cannot_assess", irrigation.WEATHER_UNAVAILABLE)


async def test_an_irrigation_with_no_depth_is_a_refill_and_with_a_depth_is_that_amount(table_path):
    refill = {"occurred_on": date(2026, 10, 6), "details": {}}
    r = await run(FakeConn(farm(), crop(), [refill]), table_path)
    # refill on day 5 (6 Oct): that day 5, then 10, 15, 20 on 7-9 Oct -> 20 at the start of 10 Oct
    assert (r.depletion_mm, r.anchor_kind, r.last_irrigation_on) == (20.0, "logged_irrigation", date(2026, 10, 6))

    with_depth = {"occurred_on": date(2026, 10, 6), "details": {"depth_mm": 10}}
    r = await run(FakeConn(farm(), crop(), [with_depth]), table_path)
    # 5 per dry day for 9 days = 45, minus 10 applied on 6 Oct = 35
    assert (r.depletion_mm, r.anchor_kind) == (35.0, "sowing")


@pytest.mark.parametrize(
    "details, expected",
    [
        ({"depth_mm": 20}, 20.0),
        ({"depth_mm": 12.5}, 12.5),
        ({"depth_mm": 0}, 0.0),
        ({}, None),
        ({"depth_mm": "20"}, None),  # a string is not an amount
        ({"depth_mm": True}, None),  # True must not read as 1 mm
        ({"depth_mm": -5}, None),
        ({"depth_mm": 5000}, None),
        ("not a dict", None),
        (None, None),
    ],
)
async def test_depth_parsing(details, expected):
    assert _depth_mm(details) == expected


async def test_a_broken_table_is_raised_not_hidden(tmp_path):
    from app.agronomy.crop_water import CropTableError
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    with pytest.raises(CropTableError):
        await get_irrigation_status(FakeConn(farm(), crop()), "f", table_path=bad, fetch=Fetcher(weather()), now=NOW)


# ------------------------------------------------------------ tool payload

async def test_payload_drops_empty_fields_keeps_days_to_raw_and_round_trips(table_path):
    # Sown 9 Oct, one dry day observed: depletion 5 mm, and the 7 forecast days
    # only reach 40 mm, so it is a "wait" with nothing inside the horizon.
    r = await run(FakeConn(farm(), crop(sowing=date(2026, 10, 9))), table_path, Fetcher(weather(observed_days=1)))
    assert r.verdict == "wait" and r.depletion_mm == 5.0
    payload = to_tool_payload(r)
    assert payload["verdict"] == "wait" and "days_to_raw" in payload and payload["days_to_raw"] is None
    assert "reason" not in payload and "last_irrigation_on" not in payload
    assert WaterBalanceResult.model_validate(payload) == r


async def test_payload_of_a_cannot_assess_result_is_small():
    payload = to_tool_payload(WaterBalanceResult.cannot("no_location", as_of=date(2026, 10, 10)))
    assert payload == {"verdict": "cannot_assess", "reason": "no_location", "as_of": "2026-10-10"}
