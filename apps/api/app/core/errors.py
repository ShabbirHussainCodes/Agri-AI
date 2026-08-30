"""Turn a Postgres RLS rejection into a clean 403 instead of a raw 500.
Minimal for Phase 1 — a fuller typed-exception envelope (per
docs/backend/backend-architecture.md) can grow here as more error cases
show up."""
import logging

import asyncpg
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("agriai.db_errors")


async def postgres_error_handler(request: Request, exc: asyncpg.PostgresError):
    # The client only ever sees a clean, generic message (never DB
    # internals) -- but we still need the real error somewhere, or every
    # failure becomes undiagnosable. This is that "somewhere": full
    # exception + traceback to the server's own console/logs.
    logger.exception("Postgres error on %s %s", request.method, request.url.path)

    if "row-level security" in str(exc).lower():
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "forbidden", "message": "You don't have access to that resource."}},
        )
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "database_error", "message": "Something went wrong."}},
    )
