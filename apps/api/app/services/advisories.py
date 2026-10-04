"""Saved answers and the daily ask cap (ADR-0017). Routers call these; they
never touch SQL directly."""
import json
from typing import Literal
from uuid import UUID

import asyncpg

from app.schemas.advisory import AdvisoryResponse

QuotaScope = Literal["user", "global"]


async def asks_last_day_for_user(conn: asyncpg.Connection) -> int:
    # No WHERE on the owner: RLS already restricts this to the caller's own farms.
    return await conn.fetchval(
        "select count(*)::int from public.advisories where created_at > now() - interval '24 hours'"
    )


async def asks_last_day_global(conn: asyncpg.Connection) -> int:
    return await conn.fetchval("select public.asks_in_last_day()")


async def quota_reached(conn: asyncpg.Connection, *, per_user: int, global_: int) -> QuotaScope | None:
    """Which cap, if any, stops this request. A limit of 0 means no cap. The
    per-user cap is checked first: it is the one a farmer can act on."""
    if per_user > 0 and await asks_last_day_for_user(conn) >= per_user:
        return "user"
    if global_ > 0 and await asks_last_day_global(conn) >= global_:
        return "global"
    return None


async def save_advisory(
    conn: asyncpg.Connection, farm_id: UUID, question: str, response: AdvisoryResponse
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        insert into public.advisories (farm_id, question, response, abstained)
        values ($1, $2, $3, $4)
        returning id, farm_id, question, response, abstained, created_at
        """,
        farm_id,
        question,
        # json round-trip: the response holds dates and UUIDs, which the jsonb
        # codec's json.dumps cannot encode on its own.
        json.loads(response.model_dump_json()),
        response.abstained,
    )


async def list_advisories(conn: asyncpg.Connection, farm_id: UUID, limit: int = 50) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        select id, farm_id, question, response, abstained, created_at
        from public.advisories where farm_id = $1
        order by created_at desc limit $2
        """,
        farm_id,
        limit,
    )
