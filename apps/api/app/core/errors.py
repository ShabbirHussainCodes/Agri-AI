"""Typed exceptions -> a consistent JSON error envelope
(docs/backend/backend-architecture.md, docs/api/api-contracts.md
Conventions). Each exception type gets its own handler here, registered
in main.py -- new error cases grow this file, not scattered
try/excepts in routers."""
import logging

import asyncpg
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("agriai.errors")


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


class AgentError(Exception):
    """Raised by app/agent/loop.py when the agent pipeline (LLM provider
    call, or the final schema validation) fails. Covers provider errors,
    malformed generations, and anything else that would otherwise
    surface as a bare, undiagnosable 500 -- the farmer must see an
    honest error, never a fabricated answer
    (docs/backend/backend-architecture.md: "AI provider failures ... the
    endpoint returns an honest error, never a fabricated answer")."""


async def agent_error_handler(request: Request, exc: AgentError):
    logger.exception("Agent error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": "agent_unavailable",
                "message": "Could not get an answer right now. Please try again in a moment.",
            }
        },
    )
