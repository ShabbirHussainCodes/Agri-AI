"""POST /farms/{id}/ask around the agent (ADR-0017): ownership, the daily cap,
saving, and CORS. No database, no network, no model: the connection is a fake,
the agent is replaced by a fixed answer, auth is overridden. (The real database
leg lives in test_ask.py and test_farm_update.py.)"""
from datetime import date, datetime, timezone
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport

from app.agent.tools.farm_context import FarmContextData
from app.core.auth import AuthContext, get_current_user
from app.core.config import settings
from app.core.db import get_authed_conn
from app.main import app
from app.routers import ask as ask_router
from app.routers.ask import get_llm_provider
from app.schemas.advisory import AdvisoryResponse
from app.services import advisories as svc

pytestmark = pytest.mark.asyncio

FARM_ID = uuid4()


def answer(abstained=False) -> AdvisoryResponse:
    return AdvisoryResponse(
        structured_data=FarmContextData(farm_name="F", sowing_date=date(2026, 10, 1)),
        model_inference="x", recommendation="y", abstained=abstained, citations_valid=True,
    )


class FakeConn:
    def __init__(self, owns_farm=True, user_count=0, global_count=0):
        self.owns_farm, self.user_count, self.global_count = owns_farm, user_count, global_count
        self.saved = []

    async def fetchrow(self, sql, *args):
        if "from public.farms" in sql:
            return {"id": FARM_ID} if self.owns_farm else None
        if "insert into public.advisories" in sql:
            self.saved.append(args)
            return {"id": uuid4(), "farm_id": args[0], "question": args[1], "response": args[2],
                    "abstained": args[3], "created_at": datetime.now(timezone.utc)}
        raise AssertionError(sql)

    async def fetchval(self, sql, *args):
        return self.global_count if "asks_in_last_day" in sql else self.user_count

    async def fetch(self, sql, *args):
        return []


@pytest.fixture
def wired(monkeypatch):
    calls = {"agent": 0}

    async def fake_run_agent(*a, **kw):
        calls["agent"] += 1
        return answer()

    monkeypatch.setattr(ask_router, "run_agent", fake_run_agent)
    monkeypatch.setattr(settings, "ask_limit_per_user_per_day", 10)
    monkeypatch.setattr(settings, "ask_limit_global_per_day", 35)
    app.dependency_overrides[get_current_user] = lambda: AuthContext("u1", {"sub": "u1"})
    app.dependency_overrides[get_llm_provider] = lambda: object()
    yield calls
    app.dependency_overrides.clear()


def use(conn):
    app.dependency_overrides[get_authed_conn] = lambda: conn


async def post(question="Should I water?", headers=None):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(f"/farms/{FARM_ID}/ask", json={"question": question}, headers=headers or {})


async def test_an_answer_is_returned_and_saved(wired):
    conn = FakeConn()
    use(conn)
    r = await post()
    assert r.status_code == 200 and r.json()["recommendation"] == "y"
    [(farm_id, question, stored, abstained)] = conn.saved
    assert (farm_id, question, abstained) == (FARM_ID, "Should I water?", False)
    assert stored["recommendation"] == "y" and stored["structured_data"]["sowing_date"] == "2026-10-01"  # json-safe


async def test_a_farm_that_is_not_the_callers_costs_no_tokens_and_is_a_404(wired):
    use(FakeConn(owns_farm=False))
    r = await post()
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert wired["agent"] == 0


@pytest.mark.parametrize(
    "conn, scope",
    [(FakeConn(user_count=10), "user"), (FakeConn(user_count=99), "user"), (FakeConn(global_count=35), "global")],
)
async def test_a_cap_stops_the_request_before_the_agent_runs(wired, conn, scope):
    use(conn)
    r = await post()
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["code"] == "ask_limit_reached" and err["scope"] == scope
    assert "KVK" in err["message"] and "1800-180-1551" in err["message"]  # bilingual, points to a human
    assert wired["agent"] == 0 and conn.saved == []


async def test_below_the_caps_it_runs(wired):
    use(FakeConn(user_count=9, global_count=34))
    assert (await post()).status_code == 200


async def test_zero_means_no_cap(wired, monkeypatch):
    monkeypatch.setattr(settings, "ask_limit_per_user_per_day", 0)
    monkeypatch.setattr(settings, "ask_limit_global_per_day", 0)
    use(FakeConn(user_count=500, global_count=500))
    assert (await post()).status_code == 200


async def test_the_user_cap_is_checked_before_the_global_one(wired):
    use(FakeConn(user_count=10, global_count=35))
    assert (await post()).json()["error"]["scope"] == "user"


@pytest.mark.parametrize("question", ["", "x" * 1001])
async def test_a_question_must_be_between_1_and_1000_characters(wired, question):
    use(FakeConn())
    assert (await post(question)).status_code == 422


async def test_quota_service_directly():
    assert await svc.quota_reached(FakeConn(user_count=3), per_user=3, global_=0) == "user"
    assert await svc.quota_reached(FakeConn(global_count=3), per_user=0, global_=3) == "global"
    assert await svc.quota_reached(FakeConn(user_count=2, global_count=2), per_user=3, global_=3) is None


# ---------------------------------------------------------------------- CORS

async def preflight(origin):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.options(
            f"/farms/{FARM_ID}/ask",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                     "Access-Control-Request-Headers": "authorization,content-type"},
        )


async def test_the_web_origin_may_call_the_api_and_others_may_not():
    ok = await preflight(settings.web_base_url)
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == settings.web_base_url
    assert "access-control-allow-credentials" not in ok.headers  # the JWT is a header, never a cookie
    bad = await preflight("https://evil.example")
    assert "access-control-allow-origin" not in bad.headers


async def test_the_ui_language_reaches_the_agent_and_defaults_to_nothing(wired, monkeypatch):
    seen = []

    async def spy(*a, **kw):
        seen.append(kw.get("language", "MISSING"))
        return answer()

    monkeypatch.setattr(ask_router, "run_agent", spy)
    use(FakeConn())
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for body in ({"question": "q"}, {"question": "q", "language": "hi"}, {"question": "q", "language": "en"}):
            assert (await c.post(f"/farms/{FARM_ID}/ask", json=body)).status_code == 200
    assert seen == [None, "hi", "en"]


async def test_an_unsupported_language_is_a_422_and_costs_no_tokens(wired):
    use(FakeConn())
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(f"/farms/{FARM_ID}/ask", json={"question": "q", "language": "fr"})
    assert r.status_code == 422 and wired["agent"] == 0
