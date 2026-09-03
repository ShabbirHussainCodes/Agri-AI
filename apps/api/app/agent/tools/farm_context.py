"""get_farm_context: deterministic lookup of a farm's own record
(profiles/farms/farm_crops/activities -- the same Phase-1 tables and
RLS). No LLM involved: days-since-sowing is date math, not something to
ask a model for (docs/ai/agent-design.md "Deterministic vs LLM" table).

Called directly by agent/loop.py's run_agent() before Turn A begins --
NOT exposed to the model as a tool. Every farm-specific question needs
this, so there is no real decision for the model to make about whether
to fetch it (agent-design.md: "Do not give the agent unnecessary
permissions"). It used to be an LLM-optional tool; that was a design
gap (see loop.py's module docstring for the bug it caused), not a
deliberate choice.
"""
import json
from datetime import date
from uuid import UUID

import asyncpg
from pydantic import BaseModel, ConfigDict


class ActivitySummary(BaseModel):
    """`details` is a JSON string, not a nested object: Groq's strict
    schema mode requires every object field to list fixed `properties`
    (verified against console.groq.com/docs/structured-outputs,
    2026-09-03) -- it does not support an open, arbitrary-key dict like
    activities.details actually is (irrigation vs fertiliser vs spray
    each have different fields). This field is read-only evidence shown
    to the model, never written back, so a JSON string is sufficient and
    keeps the schema valid without inventing a fixed shape that doesn't
    exist yet."""
    model_config = ConfigDict(extra="forbid")

    type: str
    occurred_on: date
    details: str


class FarmContextData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    farm_name: str
    crop_name: str | None = None
    variety: str | None = None
    sowing_date: date | None = None
    days_since_sowing: int | None = None
    area_ha: float | None = None
    recent_activities: list[ActivitySummary] = []


async def get_farm_context(conn: asyncpg.Connection, farm_id: UUID) -> FarmContextData:
    """`conn` is the RLS-scoped connection from get_authed_conn, so this
    can only ever read a farm the caller owns -- same guarantee as every
    Phase-1 endpoint, not a new access path."""
    farm_row = await conn.fetchrow(
        "select name, area_ha from public.farms where id = $1",
        farm_id,
    )
    if farm_row is None:
        return FarmContextData(farm_name="(unknown farm)")

    crop_row = await conn.fetchrow(
        """
        select c.name_en, fc.variety, fc.sowing_date
        from public.farm_crops fc
        join public.crops c on c.id = fc.crop_id
        where fc.farm_id = $1 and fc.status = 'active'
        order by fc.sowing_date desc
        limit 1
        """,
        farm_id,
    )

    days_since_sowing = None
    if crop_row and crop_row["sowing_date"]:
        days_since_sowing = (date.today() - crop_row["sowing_date"]).days

    activity_rows = await conn.fetch(
        """
        select a.type, a.occurred_on, a.details
        from public.activities a
        join public.farm_crops fc on fc.id = a.farm_crop_id
        where fc.farm_id = $1
        order by a.occurred_on desc, a.created_at desc
        limit 5
        """,
        farm_id,
    )

    return FarmContextData(
        farm_name=farm_row["name"],
        crop_name=crop_row["name_en"] if crop_row else None,
        variety=crop_row["variety"] if crop_row else None,
        sowing_date=crop_row["sowing_date"] if crop_row else None,
        days_since_sowing=days_since_sowing,
        area_ha=float(farm_row["area_ha"]) if farm_row["area_ha"] is not None else None,
        recent_activities=[
            ActivitySummary(type=r["type"], occurred_on=r["occurred_on"], details=json.dumps(r["details"], default=str))
            for r in activity_rows
        ],
    )
