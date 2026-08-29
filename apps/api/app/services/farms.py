"""Farm business logic. Routers call these — they never touch SQL
directly (see docs/backend/backend-architecture.md's "routers are thin"
rule)."""
import asyncpg

from app.core.auth import AuthContext
from app.schemas.farm import FarmCreate
from app.services.profiles import ensure_profile


async def create_farm(conn: asyncpg.Connection, user: AuthContext, data: FarmCreate) -> asyncpg.Record:
    await ensure_profile(conn, user)
    return await conn.fetchrow(
        """
        insert into public.farms (profile_id, name, lat, lon, district, state, area_ha)
        values ($1, $2, $3, $4, $5, $6, $7)
        returning *
        """,
        user.user_id,
        data.name,
        data.lat,
        data.lon,
        data.district,
        data.state,
        data.area_ha,
    )


async def list_farms(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    # No WHERE profile_id = ... here on purpose — RLS already restricts
    # this to the caller's own rows. Adding a redundant filter would just
    # hide a bug in the policy instead of catching it.
    return await conn.fetch("select * from public.farms order by created_at desc")
