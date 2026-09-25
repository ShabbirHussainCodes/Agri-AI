"""Integration test: /ask with retrieval wired in, using a FAKE LLM provider.

Real parts: auth, RLS, farm record, the e5 embedder, hybrid retrieval over
the local 113-chunk corpus, citation validation, the dose guard.
Fake part: only the model. The fake quotes the REAL text of whatever passage
[1] retrieval produced, so the validation it exercises is genuine.

Needs the local Supabase stack (`supabase start`) with the Phase 3 corpus.
No GROQ_API_KEY and no cassette needed.
"""
import json
import re

import pytest

from app.providers.base import ChatResult, LLMProvider
from app.retrieval.context import PASSAGE_CLOSE, PASSAGE_OPEN
from app.routers.ask import get_llm_provider
from app.main import app
from app.safety import interim_dose_guard

from .conftest import signup_test_user

pytestmark = pytest.mark.asyncio


def _passage_one(text: str) -> str:
    m = re.search(rf"{re.escape(PASSAGE_OPEN)} \[1\][^\n]*\n(.*?)\n{re.escape(PASSAGE_CLOSE)}", text, re.S)
    assert m, "Turn B did not receive a passage [1]"
    return m.group(1)


class FakeProvider(LLMProvider):
    def __init__(self, mode: str):
        self.mode = mode
        self.calls: list[list[dict]] = []

    async def chat(self, messages, *, model, tools=None, response_schema=None):
        self.calls.append(messages)
        if response_schema is None:
            return ChatResult(content="no tools needed")  # Turn A: ask for nothing
        words = _passage_one(messages[-1]["content"]).split()[:8]
        quote = " ".join(words)
        if self.mode == "fabricated":
            quote = "this sentence does not appear in any passage at all"
        recommendation = "The study describes this; see the cited passage."
        if self.mode == "dose":
            recommendation = "Spray 4 g/L every week."
        return ChatResult(content=json.dumps({
            "evidence_basis": "retrieved_passages",
            "citations": [{"passage": 1, "quote": quote}],
            "model_inference": "Based on passage [1].",
            "recommendation": recommendation,
            "confidence": 0.6,
            "abstained": False,
            "abstained_because": None,
        }))


async def _ask(client, provider: FakeProvider, question: str) -> dict:
    token = await signup_test_user()
    headers = {"Authorization": f"Bearer {token}"}
    farm = await client.post("/farms", headers=headers, json={"name": "RAG Farm", "area_ha": 1.0})
    assert farm.status_code == 201, farm.text
    app.dependency_overrides[get_llm_provider] = lambda: provider
    try:
        resp = await client.post(f"/farms/{farm.json()['id']}/ask", headers=headers, json={"question": question})
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_real_quote_from_real_retrieval_is_answered_with_provenance(client):
    provider = FakeProvider("valid")
    body = await _ask(client, provider, "Which eggplant rootstocks were used in the tomato study?")
    assert body["abstained"] is False, body
    assert body["citations_valid"] is True
    [ev] = body["retrieved_evidence"]
    assert ev["licence"] and ev["url"] and ev["doc_title"]
    # Rule 9: corpus text reached Turn B only, never Turn A.
    assert not any(PASSAGE_OPEN in str(m.get("content")) for m in provider.calls[0])
    assert PASSAGE_OPEN in provider.calls[-1][-1]["content"]


async def test_fabricated_quote_is_withheld(client):
    body = await _ask(client, FakeProvider("fabricated"), "Which eggplant rootstocks were used in the tomato study?")
    assert body["abstained"] is True and body["abstained_because"] == "invalid_citation"
    assert body["citations_valid"] is False
    assert body["retrieved_evidence"] == []


async def test_dose_in_answer_is_blocked_by_interim_guard(client):
    body = await _ask(client, FakeProvider("dose"), "How much Bacillus subtilis should I spray on my tomato crop?")
    assert body["abstained"] is True
    assert body["abstained_because"] == interim_dose_guard.SAFE_ABSTAIN_REASON
    assert body["recommendation"] == interim_dose_guard.SAFE_MESSAGE
