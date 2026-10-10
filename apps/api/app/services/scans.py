"""Saved photo checks and their daily caps (ADR-0018). Routers call these; they never touch SQL."""
import json
from typing import Literal
from uuid import UUID

import asyncpg

from app.schemas.scan import DiagnosisResponse

QuotaScope = Literal["user", "global"]

_COLUMNS = "id, farm_id, image_path, outcome, abstained_because, response, farmer_feedback, created_at"


async def scans_last_day_for_user(conn: asyncpg.Connection) -> int:
    # No owner filter: RLS already limits this to the caller's own farms. A photo the quality gate rejected
    # cost nothing, so it does not use up a farmer's daily checks.
    return await conn.fetchval(
        "select count(*)::int from public.disease_scans "
        "where created_at > now() - interval '24 hours' and outcome <> 'rejected_quality'"
    )


async def scans_last_day_global(conn: asyncpg.Connection) -> int:
    return await conn.fetchval("select public.scans_in_last_day()")


async def total_last_day_global(conn: asyncpg.Connection) -> int:
    """Questions plus photo checks across everyone: the shared model budget."""
    return await conn.fetchval("select public.asks_in_last_day()")


async def quota_reached(
    conn: asyncpg.Connection, *, per_user: int, scans_global: int, total_global: int
) -> QuotaScope | None:
    """Which cap, if any, stops this photo check. A limit of 0 means no cap. The per-user cap is checked
    first: it is the one a farmer can act on."""
    if per_user > 0 and await scans_last_day_for_user(conn) >= per_user:
        return "user"
    if scans_global > 0 and await scans_last_day_global(conn) >= scans_global:
        return "global"
    if total_global > 0 and await total_last_day_global(conn) >= total_global:
        return "global"
    return None


async def save_scan(
    conn: asyncpg.Connection, scan_id: UUID, farm_id: UUID, image_path: str | None, response: DiagnosisResponse
) -> asyncpg.Record:
    return await conn.fetchrow(
        f"""
        insert into public.disease_scans (id, farm_id, image_path, outcome, abstained_because, response)
        values ($1, $2, $3, $4, $5, $6)
        returning {_COLUMNS}
        """,
        scan_id,
        farm_id,
        image_path,
        response.outcome,
        response.abstained_because,
        # json round-trip: the response holds UUIDs and datetimes the jsonb codec cannot encode on its own.
        json.loads(response.model_dump_json()),
    )


async def list_scans(conn: asyncpg.Connection, farm_id: UUID, limit: int = 50) -> list[asyncpg.Record]:
    return await conn.fetch(
        f"select {_COLUMNS} from public.disease_scans where farm_id = $1 order by created_at desc limit $2",
        farm_id,
        limit,
    )


async def get_scan(conn: asyncpg.Connection, scan_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(f"select {_COLUMNS} from public.disease_scans where id = $1", scan_id)


async def delete_scan(conn: asyncpg.Connection, scan_id: UUID) -> bool:
    deleted = await conn.fetchval("delete from public.disease_scans where id = $1 returning id", scan_id)
    return deleted is not None


async def set_feedback(conn: asyncpg.Connection, scan_id: UUID, feedback: dict) -> asyncpg.Record | None:
    return await conn.fetchrow(
        f"update public.disease_scans set farmer_feedback = $2 where id = $1 returning {_COLUMNS}",
        scan_id,
        feedback,
    )
