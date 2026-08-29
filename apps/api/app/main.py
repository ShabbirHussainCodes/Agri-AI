from fastapi import Depends, FastAPI

from app.core.auth import AuthContext, get_current_user
from app.core.config import settings
from app.core.db import get_authed_conn, get_pool, lifespan
from app.routers import farms as farms_router

app = FastAPI(title="AgriAI API", version="0.1.0", lifespan=lifespan)
app.include_router(farms_router.router)


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

@app.get("/whoami")
async def whoami(
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    """Proves the full chain: JWT verified -> role/claims set in Postgres
    -> auth.uid() resolves inside the database. jwt_sub and db_auth_uid
    must be equal and non-null for RLS to work at all."""
    db_auth_uid = await conn.fetchval("select auth.uid()")
    return {
        "jwt_sub": user.user_id,
        "db_auth_uid": str(db_auth_uid) if db_auth_uid else None,
        "match": str(db_auth_uid) == user.user_id if db_auth_uid else False,
    }
