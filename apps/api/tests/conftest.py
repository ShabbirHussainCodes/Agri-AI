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


@pytest.fixture(scope="module")
def vcr_config():
    """docs/testing/testing-strategy.md Layer 2: cassettes are committed
    to the repo, so anything sensitive in a recorded request/response
    must be scrubbed BEFORE it's written, not after. Groq's Python SDK
    sends the API key as a standard `Authorization: Bearer <key>` header
    (OpenAI-compatible); `x-api-key` is filtered too in case a future
    provider uses that style instead. Applies to every cassette in this
    test package (pytest-recording looks up this fixture by name)."""
    return {
        "filter_headers": [
            ("authorization", "REDACTED"),
            ("x-api-key", "REDACTED"),
        ],
        # Local Supabase (127.0.0.1:54321) and our own app (called via
        # ASGITransport(base_url="http://test") in the `client` fixture
        # above) must run LIVE on every test run, never be recorded into
        # or replayed from a cassette:
        #  - Supabase: it's already required to be running for every
        #    test in this suite (test_rls.py etc.) -- recording it buys
        #    nothing and would commit a real (if short-lived, local-only)
        #    JWT into the cassette.
        #  - our own app: if this were cassette-replayed too, the test
        #    would stop exercising the current code on every run after
        #    the first recording -- exactly the opposite of what
        #    testing-strategy.md Layer 2 is for ("test our code around
        #    the model"). Only the genuinely external legs (Groq,
        #    Open-Meteo) should ever be frozen into the cassette.
        # (verified: vcrpy docs, "Advanced Features" -- ignore_hosts/
        # ignore_localhost bypass VCR entirely, request hits the real
        # server every time, nothing recorded or replayed.)
        "ignore_localhost": True,
        "ignore_hosts": ["test"],
    }


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
