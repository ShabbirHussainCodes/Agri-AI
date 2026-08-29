"""Database connection pool, and a per-request connection that carries the
caller's identity into Postgres so Row-Level Security is the real
gatekeeper (not just application code) — see docs/security/security-model.md
and ADR-0003.
"""
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from fastapi import Depends, FastAPI

from app.core.auth import AuthContext, get_current_user
from app.core.config import settings

pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """asyncpg does not convert Python dict <-> Postgres jsonb on its own —
    without this, jsonb columns come back as raw text and dicts sent in
    must be pre-serialized. Registering this codec once, per connection,
    makes it transparent everywhere else in the app."""
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global pool
    pool = await asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=5, init=_init_connection
    )
    try:
        yield
    finally:
        await pool.close()


async def get_pool() -> asyncpg.Pool:
    assert pool is not None, "DB pool not initialised — is the app running via its lifespan?"
    return pool


async def get_authed_conn(
    user: AuthContext = Depends(get_current_user),
) -> AsyncIterator[asyncpg.Connection]:
    """One connection, for one request, running AS the `authenticated`
    Postgres role with this user's real JWT claims attached.

    Why a transaction: `SET LOCAL` only lasts for the current transaction —
    that's deliberate. It means the role/claims we set here can never leak
    into another request that happens to reuse this pooled connection
    afterwards.
    """
    p = await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE authenticated")
            await conn.execute(
                "SELECT set_config('request.jwt.claims', $1, true)",
                json.dumps(user.claims),
            )
            yield conn
