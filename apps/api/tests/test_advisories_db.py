"""Saved answers, GET /farms/{id} and the cap against the REAL database (ADR-0017).
Needs the local Supabase stack with migration 20261005120000 applied
(`supabase migration up`, never `db reset`) and the e5 model cache, like
test_agent_rag.py. The model is a fake; everything else is real."""
import json

import pytest

from app.core.config import settings
from app.main import app
from app.providers.base import ChatResult, LLMProvider
from app.routers.ask import get_llm_provider

from .conftest import signup_test_user

pytestmark = pytest.mark.asyncio


class PlainProvider(LLMProvider):
    async def chat(self, messages, *, model, tools=None, response_schema=None):
        if response_schema is None:
            return ChatResult(content="no tools needed")
        return ChatResult(content=json.dumps({
            "evidence_basis": "farm_and_weather_data", "citations": [], "model_inference": "From the farm record.",
            "recommendation": "Keep scouting weekly.", "confidence": 0.5, "abstained": False,
            "abstained_because": None, "irrigation_verdict": "not_applicable",
        }))


async def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _farm(client, token, name="Advisory Farm"):
    r = await client.post("/farms", headers=await _auth(token), json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _ask(client, token, farm_id, question="How do I scout for pests?"):
    app.dependency_overrides[get_llm_provider] = lambda: PlainProvider()
    try:
        return await client.post(f"/farms/{farm_id}/ask", headers=await _auth(token), json={"question": question})
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def test_get_farm_returns_my_farm_and_404_for_someone_elses(client):
    owner, other = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    mine = await client.get(f"/farms/{farm_id}", headers=await _auth(owner))
    assert mine.status_code == 200 and mine.json()["name"] == "Advisory Farm"
    theirs = await client.get(f"/farms/{farm_id}", headers=await _auth(other))
    assert theirs.status_code == 404 and theirs.json()["error"]["code"] == "not_found"


async def test_an_answer_is_saved_and_listed_newest_first_and_only_for_its_owner(client):
    owner, other = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    for q in ("first question", "second question"):
        r = await _ask(client, owner, farm_id, q)
        assert r.status_code == 200, r.text

    listed = await client.get(f"/farms/{farm_id}/advisories", headers=await _auth(owner))
    assert listed.status_code == 200
    items = listed.json()
    assert [i["question"] for i in items] == ["second question", "first question"]
    assert items[0]["response"]["recommendation"] == "Keep scouting weekly."
    assert items[0]["abstained"] is False

    assert (await client.get(f"/farms/{farm_id}/advisories", headers=await _auth(other))).json() == []


async def test_asking_on_someone_elses_farm_is_404_and_saves_nothing(client):
    owner, other = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    r = await _ask(client, other, farm_id)
    assert r.status_code == 404
    assert (await client.get(f"/farms/{farm_id}/advisories", headers=await _auth(owner))).json() == []


async def test_the_per_user_cap_counts_saved_answers_and_returns_429(client, monkeypatch):
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    monkeypatch.setattr(settings, "ask_limit_per_user_per_day", 2)
    assert (await _ask(client, token, farm_id)).status_code == 200
    assert (await _ask(client, token, farm_id)).status_code == 200
    third = await _ask(client, token, farm_id)
    assert third.status_code == 429 and third.json()["error"]["scope"] == "user"
    # another farmer is not affected by this one's cap
    other = await signup_test_user()
    other_farm = await _farm(client, other, "Other")
    assert (await _ask(client, other, other_farm)).status_code == 200


async def test_the_global_cap_uses_the_security_definer_count(client, monkeypatch):
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    await _ask(client, token, farm_id)  # at least one answer exists in the last 24 h
    monkeypatch.setattr(settings, "ask_limit_global_per_day", 1)
    blocked = await _ask(client, token, farm_id)
    assert blocked.status_code == 429 and blocked.json()["error"]["scope"] == "global"
