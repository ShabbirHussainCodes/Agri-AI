"""Shared test fixtures.

These are integration tests, not pure unit tests: they need the local
Supabase stack running (`supabase start`) because RLS can only be proven
against a real Postgres with real policies — there is nothing meaningful
to mock here. See docs/testing/testing-strategy.md.
"""
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from app.main import app

SUPABASE_AUTH_URL = "http://127.0.0.1:54321/auth/v1"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_ACJWlzQHlZjBrEguHvfOxg_3BJgxAaH"


@pytest_asyncio.fixture
async def client():
    # ASGITransport talks directly to the app's ASGI callable and does NOT
    # run FastAPI's lifespan (the startup/shutdown hooks that create and
    # close app.core.db.pool). We have to enter that lifespan context
    # ourselves, or every DB-dependent request fails with
    # "DB pool not initialised". app.router.lifespan_context(app) is the
    # same async context manager FastAPI/Starlette use internally when a
    # real server boots the app -- no extra dependency needed.
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def signup_test_user() -> str:
    """Creates a fresh farmer via the real local Supabase Auth API and
    returns their access token. A random email each time keeps tests
    re-runnable without 'already registered' collisions."""
    email = f"test-{uuid.uuid4().hex[:12]}@test.local"
    async with httpx.AsyncClient() as c:
        resp = await c.post(
            f"{SUPABASE_AUTH_URL}/signup",
            headers={"apikey": SUPABASE_PUBLISHABLE_KEY},
            json={"email": email, "password": "testpass123"},
        )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    assert token, f"Signup did not return an access_token: {resp.json()}"
    return token
