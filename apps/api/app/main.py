from fastapi import FastAPI

from app.core.config import settings
from app.core.db import get_pool, lifespan

app = FastAPI(title="AgriAI API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Liveness check — no database involved."""
    return {"status": "ok", "env": settings.env}


@app.get("/health/db")
async def health_db():
    """Readiness check — proves the app can actually reach Postgres and
    read real data (the crops seeded by migration 0004)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        crop_count = await conn.fetchval("select count(*) from crops")
    return {"status": "ok", "crops_seeded": crop_count}
