"""Farm business logic. Routers call these — they never touch SQL
directly (see docs/backend/backend-architecture.md's "routers are thin"
rule)."""
from uuid import UUID

import asyncpg

from app.core.auth import AuthContext
from app.schemas.farm import FarmCreate, FarmUpdate
from app.services.profiles import ensure_profile

# Column names that PATCH may touch. They are interpolated into SQL, so they
# come from this fixed tuple, never from the request: values are always
# bound parameters.
_UPDATABLE = ("name", "lat", "lon", "district", "state", "area_ha", "soil_texture")


async def create_farm(conn: asyncpg.Connection, user: AuthContext, data: FarmCreate) -> asyncpg.Record:
    await ensure_profile(conn, user)
    return await conn.fetchrow(
        """
        insert into public.farms (profile_id, name, lat, lon, district, state, area_ha, soil_texture)
        values ($1, $2, $3, $4, $5, $6, $7, $8)
        returning *
        """,
        user.user_id,
        data.name,
        data.lat,
        data.lon,
        data.district,
        data.state,
        data.area_ha,
        data.soil_texture,
    )


async def update_farm(conn: asyncpg.Connection, farm_id: UUID, data: FarmUpdate) -> asyncpg.Record | None:
    """None when no row was updated: the farm does not exist or is not the
    caller's (RLS hides it, so the two look the same, on purpose)."""
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _UPDATABLE}
    assignments = ", ".join(f"{col} = ${i}" for i, col in enumerate(changes, start=2))
    return await conn.fetchrow(
        f"update public.farms set {assignments} where id = $1 returning *",
        farm_id,
        *changes.values(),
    )


async def get_farm(conn: asyncpg.Connection, farm_id: UUID) -> asyncpg.Record | None:
    """None when the farm does not exist or is not the caller's: RLS hides it, so
    the two look the same, on purpose."""
    return await conn.fetchrow("select * from public.farms where id = $1", farm_id)


async def list_farms(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    # No WHERE profile_id = ... here on purpose — RLS already restricts
    # this to the caller's own rows. Adding a redundant filter would just
    # hide a bug in the policy instead of catching it.
    return await conn.fetch("select * from public.farms order by created_at desc")
