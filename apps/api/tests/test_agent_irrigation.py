"""The whole agent loop with the irrigation tool wired in (ADR-0015), with no
database, no network and no real model:

  real: run_agent, the tool dispatch, get_irrigation_status, the water-balance
        engine, finalize_advisory, the guards
  fake: the model (a scripted provider), the farm rows (a fake connection),
        the weather (a fake fetcher), the clock, retrieval (returns nothing)
        and get_farm_context (a fixed record)

The reference table is SYNTHETIC (round numbers in a temp file): this proves
the wiring, not agronomy. test_agent_rag.py covers the same loop against the
real database and corpus.
"""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.agent import loop
from app.agent.tools import irrigation
from app.agent.tools.farm_context import FarmContextData
from app.agronomy.messages import irrigation_message
from app.integrations.open_meteo import DailySeries
from app.agronomy.water_balance import DayWeather
from app.providers.base import ChatResult, LLMProvider, ToolCall
from app.retrieval.hybrid import RetrievalResult

pytestmark = pytest.mark.asyncio

SOWING = date(2026, 10, 1)
NOW = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)
VERIFIED = {"verified_by": "Test Reviewer", "verified_on": "2026-10-04"}
TABLE = {
    "table_version": "synthetic-test", "method": "test", "primary_source": "test",
    "crops": [{
        "name_en": "Wheat", "status": "verified", **VERIFIED,
        "kc_ini": 1.0, "kc_mid": 1.0, "kc_end": 1.0,
        "stage_days": {"initial": 10, "development": 20, "mid": 30, "late": 10},
        "stage_length_basis": "synthetic", "root_depth_m": 0.5, "p": 0.5,
        "sources": {"kc": "t", "stage_days": "t", "root_depth_m": "t", "p": "t"},
    }],
    "soils": [{
        "texture": "loamy", "status": "verified", **VERIFIED, "fao56_class": "synthetic",
        "theta_fc": 0.30, "theta_wp": 0.10, "sources": {"theta": "t"},
    }],
}


class FakeConn:
    def __init__(self, soil="loamy"):
        self.soil = soil

    async def fetchrow(self, sql, *args):
        if "public.farms" in sql:
            return {"lat": 26.85, "lon": 80.95, "soil_texture": self.soil}
        return {"id": "crop-1", "name_en": "Wheat", "sowing_date": SOWING}

    async def fetch(self, sql, *args):
        return []


def dry_weather(_lat, _lon, **_kw):
    # Nine dry observed days at 5 mm, then a dry week: depletion 45 mm today, limit 50 mm.
    async def go():
        days = [DayWeather(date=SOWING + timedelta(days=i), et0_mm=5.0, rain_mm=0.0) for i in range(16)]
        return DailySeries(utc_offset_seconds=19800, days=days)
    return go()


class ScriptedModel(LLMProvider):
    """Turn A: optionally asks for the irrigation tool. Turn B: writes an answer
    from what the tool actually returned, in the way `mode` says."""

    def __init__(self, mode="match", calls_tool=True):
        self.mode, self.calls_tool, self.calls = mode, calls_tool, []

    async def chat(self, messages, *, model, tools=None, response_schema=None):
        self.calls.append({"messages": messages, "tools": tools, "schema": response_schema})
        if response_schema is None:
            has_tool_result = any(m.get("role") == "tool" for m in messages)
            if self.calls_tool and not has_tool_result:
                return ChatResult(tool_calls=[ToolCall(id="c1", name="get_irrigation_status", arguments={})])
            return ChatResult(content="enough")
        return ChatResult(content=json.dumps(self._answer(messages)))

    def _answer(self, messages):
        tool_msgs = [json.loads(m["content"]) for m in messages if m.get("role") == "tool"]
        wb = tool_msgs[0] if tool_msgs else {}
        verdict = wb.get("verdict", "wait")
        d, r = wb.get("depletion_mm"), wb.get("raw_mm")
        text = f"Short of {d} mm; the limit is {r} mm."
        claimed = verdict
        if self.mode == "wrong_verdict":
            claimed = "irrigate_now" if verdict == "wait" else "wait"
        if self.mode == "invented_number":
            text += " Give 35 mm."
        if self.mode == "claims_without_tool":
            claimed, text = "wait", "Wait, no irrigation yet."
        return {
            "evidence_basis": "farm_and_weather_data", "citations": [],
            "model_inference": "Based on the computed irrigation status.",
            "recommendation": text, "confidence": 0.7,
            "abstained": False, "abstained_because": None, "irrigation_verdict": claimed,
        }


@pytest.fixture
def wired(monkeypatch, tmp_path):
    table = tmp_path / "synthetic.json"
    table.write_text(json.dumps(TABLE), encoding="utf-8")
    monkeypatch.setattr(loop.settings, "crop_water_table", table)

    async def fake_farm_context(conn, farm_id):
        return FarmContextData(farm_name="Loop Farm", crop_name="Wheat", sowing_date=SOWING, days_since_sowing=9)

    async def no_passages(conn, embedder, question, **kw):
        return RetrievalResult(query=question, tier="unfiltered", accepted=True, top_dense_similarity=None, chunks=[])

    real = irrigation.get_irrigation_status

    async def with_fake_world(conn, farm_id, **kw):
        return await real(conn, farm_id, fetch=dry_weather, now=NOW, **kw)

    monkeypatch.setattr(loop.farm_context, "get_farm_context", fake_farm_context)
    monkeypatch.setattr(loop, "retrieve", no_passages)
    monkeypatch.setattr(irrigation, "get_irrigation_status", with_fake_world)


async def ask(model, question="Should I water my wheat today?", soil="loamy"):
    return await loop.run_agent(model, FakeConn(soil), "farm-1", question, model="fake", embedder=object())


async def test_the_model_is_offered_the_tool_and_a_matching_answer_is_shown(wired):
    model = ScriptedModel("match")
    r = await ask(model)
    assert {t["function"]["name"] for t in model.calls[0]["tools"]} == {"get_weather", "get_irrigation_status"}
    assert r.water_balance is not None and r.water_balance.verdict == "wait"
    assert (r.water_balance.depletion_mm, r.water_balance.raw_mm) == (45.0, 50.0)
    assert not r.abstained and r.recommendation == "Short of 45.0 mm; the limit is 50.0 mm."
    assert r.live_data is None  # get_weather was not called


async def test_turn_b_sees_the_computed_result_and_the_rule_about_it(wired):
    model = ScriptedModel("match")
    await ask(model)
    turn_b = model.calls[-1]["messages"]
    tool_msg = next(m for m in turn_b if m.get("role") == "tool")
    assert json.loads(tool_msg["content"])["verdict"] == "wait"
    assert "irrigation_verdict" in turn_b[0]["content"] and "mm only" in turn_b[0]["content"]
    assert "irrigation_verdict" in json.dumps(model.calls[-1]["schema"])
    assert "cannot_assess" in turn_b[0]["content"]


async def test_the_irrigation_rule_is_only_in_turn_b_when_the_tool_ran(wired):
    # Token budget: ~170 tokens that a non-irrigation question must not pay.
    ran = ScriptedModel("match")
    await ask(ran)
    assert loop.TURN_B_IRRIGATION_RULE in ran.calls[-1]["messages"][0]["content"]
    skipped = ScriptedModel("claims_without_tool", calls_tool=False)
    await ask(skipped)
    assert loop.TURN_B_IRRIGATION_RULE not in skipped.calls[-1]["messages"][0]["content"]
    assert skipped.calls[-1]["messages"][0]["content"] == loop.TURN_B_SYSTEM_PROMPT


async def test_a_wrong_verdict_is_replaced_by_the_computed_answer(wired):
    r = await ask(ScriptedModel("wrong_verdict"))
    assert not r.abstained
    assert r.recommendation == irrigation_message(r.water_balance)
    assert "irrigation_verdict_mismatch" in r.model_inference


async def test_an_invented_number_is_replaced_by_the_computed_answer(wired):
    r = await ask(ScriptedModel("invented_number"))
    assert r.recommendation == irrigation_message(r.water_balance)
    assert "35" not in r.recommendation and "ungrounded_number" in r.model_inference


async def test_cannot_assess_is_an_abstention_with_the_specific_reason(wired):
    r = await ask(ScriptedModel("match"), soil=None)
    assert r.abstained and r.abstained_because == "soil_texture_missing"
    assert r.water_balance.verdict == "cannot_assess"
    assert r.recommendation == irrigation_message(r.water_balance)


async def test_a_question_about_another_crop_is_not_answered_with_this_crops_balance(wired):
    r = await ask(ScriptedModel("match"), question="Should I water my tomato today?")
    assert r.abstained and r.abstained_because == "question_crop_differs"


async def test_a_verdict_claimed_without_calling_the_tool_is_withheld(wired):
    r = await ask(ScriptedModel("claims_without_tool", calls_tool=False))
    assert r.water_balance is None
    assert r.abstained and r.abstained_because == "irrigation_verdict_unsupported"


async def test_a_broken_table_hides_the_file_path_from_the_model(wired, monkeypatch, tmp_path):
    bad = tmp_path / "secret-location" / "bad.json"
    bad.parent.mkdir()
    bad.write_text("{nope", encoding="utf-8")
    monkeypatch.setattr(loop.settings, "crop_water_table", bad)
    model = ScriptedModel("claims_without_tool")
    r = await ask(model)
    tool_msgs = [m["content"] for call in model.calls for m in call["messages"] if m.get("role") == "tool"]
    assert tool_msgs and all("secret-location" not in c and "bad.json" not in c for c in tool_msgs)
    # Code knows nothing was computed, so it says so instead of letting the model improvise.
    assert r.water_balance.verdict == "cannot_assess" and r.water_balance.reason == "irrigation_unavailable"
    assert r.abstained and r.abstained_because == "irrigation_unavailable"
    assert r.recommendation == irrigation_message(r.water_balance)
