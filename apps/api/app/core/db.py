"""Database connection pool.

One asyncpg pool, created once when the app starts (see lifespan in
main.py) and reused for every request — opening a fresh connection per
request would be slow and would exhaust Postgres's connection limit.
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from fastapi import FastAPI

from app.core.config import settings

pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global pool
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    try:
        yield
    finally:
        await pool.close()


async def get_pool() -> asyncpg.Pool:
    assert pool is not None, "DB pool not initialised — is the app running via its lifespan?"
    return pool
