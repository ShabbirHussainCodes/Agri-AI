"""Cassette-backed test for the /ask endpoint's real Groq + Open-Meteo
flow (docs/testing/testing-strategy.md Layer 2; roadmap Phase 2
"Verified by: Cassette-backed tests; one real question answered").

The HTTP calls to Groq (agent loop) and Open-Meteo (get_weather) are
recorded once against the live APIs into tests/cassettes/test_ask/, then
replayed by CI at zero cost and zero flakiness -- no GROQ_API_KEY needed
to replay. Still needs the local Supabase stack running (`supabase
start`) for auth/DB, same as test_rls.py: VCR only replays outbound
HTTP, not Postgres.

Caveat (testing-strategy.md): a cassette freezes model behaviour -- this
proves our code handles a real recorded Groq response correctly (schema
parsing, tool-call dispatch, error paths), not that the model will say
the same thing next time. Assertions below are on contract/shape, never
on the model's exact wording, per the same doc's rule: "assert on
facts, schemas, and tool-call sequences, never exact strings."

To record (first run only, needs a real AGRIAI_GROQ_API_KEY in .env and
the local stack running):
    pytest tests/test_ask.py --record-mode=once

To replay (every run after that, including CI -- no live services
needed for the Groq/weather leg):
    pytest tests/test_ask.py
"""
import pytest

from .conftest import signup_test_user

pytestmark = pytest.mark.asyncio


async def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.vcr()
async def test_ask_returns_grounded_advisory(client):
    token = await signup_test_user()

    create = await client.post(
        "/farms",
        headers=await _auth(token),
        json={"name": "Cassette Test Farm", "lat": 26.85, "lon": 80.95, "area_ha": 1.5},
    )
    assert create.status_code == 201, create.text
    farm_id = create.json()["id"]

    resp = await client.post(
        f"/farms/{farm_id}/ask",
        headers=await _auth(token),
        json={"question": "Kya aaj mujhe apne gehun ko paani dena chahiye?"},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    # Contract checks only (docs/api/api-contracts.md AdvisoryResponse
    # shape) -- never the model's exact wording.
    assert body["structured_data"]["farm_name"] == "Cassette Test Farm"
    assert isinstance(body["abstained"], bool)
    assert isinstance(body["citations_valid"], bool)
    assert body["model_inference"]
    assert body["recommendation"]
    # get_weather was expected to fire for an irrigation-timing
    # question (agent-design.md tool rules) -- if it didn't, live_data
    # being present/absent is itself evidence of a regression in the
    # agent's tool-use behaviour, worth failing loudly on rather than
    # silently accepting either shape.
    assert body["live_data"] is not None
