"""days_since_sowing counts on the farm's calendar (app/core/clock.py), not the server's."""
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.agent.tools import farm_context


class FakeConn:
    """Just enough of asyncpg.Connection for get_farm_context."""

    def __init__(self, sowing: date):
        self.sowing = sowing

    async def fetchrow(self, sql, *args):
        if "from public.farms" in sql:
            return {"name": "Test Khet", "area_ha": None}
        return {"name_en": "Wheat", "variety": None, "sowing_date": self.sowing}

    async def fetch(self, sql, *args):
        return []


@pytest.mark.asyncio
async def test_default_today_is_the_farm_calendar_not_date_today(monkeypatch):
    # The server (UTC) still says 4 Oct; the farm's calendar says 5 Oct: 36 days, not 35.
    real = farm_context.farm_today
    monkeypatch.setattr(
        farm_context, "farm_today",
        lambda: real(datetime(2026, 10, 4, 20, 24, 51, tzinfo=timezone.utc), offset_minutes=330),
    )
    ctx = await farm_context.get_farm_context(FakeConn(date(2026, 8, 30)), uuid4())
    assert ctx.days_since_sowing == 36


@pytest.mark.asyncio
async def test_an_explicit_today_wins():
    ctx = await farm_context.get_farm_context(FakeConn(date(2026, 8, 30)), uuid4(), today=date(2026, 10, 4))
    assert ctx.days_since_sowing == 35


@pytest.mark.asyncio
async def test_sowing_day_itself_is_day_zero():
    ctx = await farm_context.get_farm_context(FakeConn(date(2026, 10, 5)), uuid4(), today=date(2026, 10, 5))
    assert ctx.days_since_sowing == 0
