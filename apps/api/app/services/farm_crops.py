import asyncpg
from uuid import UUID

from app.schemas.farm_crop import FarmCropCreate


async def create_farm_crop(conn: asyncpg.Connection, farm_id: UUID, data: FarmCropCreate) -> asyncpg.Record:
    # No ownership check here: if farm_id isn't the caller's, the RLS
    # INSERT policy's WITH CHECK rejects the row and Postgres raises —
    # that IS the check. See errors.py for how we turn that into a 403.
    return await conn.fetchrow(
        """
        insert into public.farm_crops (farm_id, crop_id, variety, sowing_date, expected_harvest)
        values ($1, $2, $3, $4, $5)
        returning *
        """,
        farm_id, data.crop_id, data.variety, data.sowing_date, data.expected_harvest,
    )


async def list_farm_crops(conn: asyncpg.Connection, farm_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "select * from public.farm_crops where farm_id = $1 order by sowing_date desc",
        farm_id,
    )
