import asyncpg
from uuid import UUID

from app.schemas.activity import ActivityCreate


async def create_activity(conn: asyncpg.Connection, farm_crop_id: UUID, data: ActivityCreate) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        insert into public.activities (farm_crop_id, type, occurred_on, details)
        values ($1, $2, $3, $4)
        returning *
        """,
        farm_crop_id, data.type, data.occurred_on, data.details,
    )


async def farm_timeline(conn: asyncpg.Connection, farm_id: UUID) -> list[asyncpg.Record]:
    """Chronological activities across every crop planted on this farm.
    Advisories/disease_scans will join in here too, once those tables
    exist (Phase 2+) — see docs/api/api-contracts.md."""
    return await conn.fetch(
        """
        select a.* from public.activities a
        join public.farm_crops fc on fc.id = a.farm_crop_id
        where fc.farm_id = $1
        order by a.occurred_on desc, a.created_at desc
        """,
        farm_id,
    )
