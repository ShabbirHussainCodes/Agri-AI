"""run_agent when the model's output is unusable: one retry, then an honest abstention written by code.
Same fakes as test_agent_irrigation.py (no database, network or real model)."""
import json

import pytest

from app.agent import finalize, loop
from app.core.errors import AgentError
from app.safety import interim_dose_guard
from app.providers.base import ChatResult, ProviderOutputInvalid

from .test_agent_irrigation import ScriptedModel, ask, wired  # noqa: F401  (wired is a fixture)

pytestmark = pytest.mark.asyncio


class Flaky(ScriptedModel):
    """The scripted model, except that chosen calls fail first. `turn_a` / `turn_b` are lists of
    behaviours consumed one per call: "ok", "reject" (provider rejects the output), "empty",
    "not_json", "wrong_shape", "boom" (a non-output failure), or a dict (its JSON is the answer)."""

    def __init__(self, turn_a=(), turn_b=(), calls_tool=True):
        super().__init__("match", calls_tool=calls_tool)
        self.turn_a, self.turn_b = list(turn_a), list(turn_b)
        self.a_calls = self.b_calls = 0

    async def chat(self, messages, *, model, tools=None, response_schema=None):
        queue, is_b = (self.turn_b, True) if response_schema is not None else (self.turn_a, False)
        self.b_calls += is_b
        self.a_calls += not is_b
        step = queue.pop(0) if queue else "ok"
        if step == "reject":
            raise ProviderOutputInvalid("json_validate_failed")
        if step == "boom":
            raise RuntimeError("provider is down")
        if step == "empty":
            return ChatResult(content=None)
        if step == "not_json":
            return ChatResult(content="{not json")
        if step == "wrong_shape":
            return ChatResult(content=json.dumps({"recommendation": "hi"}))
        if isinstance(step, dict):
            return ChatResult(content=json.dumps(step))
        return await super().chat(messages, model=model, tools=tools, response_schema=response_schema)


def answer(**kw):
    base = {"evidence_basis": "farm_and_weather_data", "citations": [], "model_inference": "Based on the status.",
            "recommendation": "Short of 45.0 mm; the limit is 50.0 mm.", "confidence": 0.7,
            "abstained": False, "abstained_because": None, "irrigation_verdict": "wait"}
    return {**base, **kw}


async def test_one_rejected_answer_is_retried_and_the_second_is_shown(wired):
    model = Flaky(turn_b=["reject"])
    r = await ask(model)
    assert model.b_calls == 2 and not r.abstained
    assert r.recommendation == "Short of 45.0 mm; the limit is 50.0 mm."


@pytest.mark.parametrize("bad", ["empty", "not_json", "wrong_shape"])
async def test_an_empty_or_malformed_answer_is_retried_too(wired, bad):
    model = Flaky(turn_b=[bad])
    r = await ask(model)
    assert model.b_calls == 2 and not r.abstained


@pytest.mark.parametrize("bad", ["reject", "empty", "not_json", "wrong_shape"])
async def test_two_unusable_answers_end_in_an_honest_abstention_not_an_error(wired, bad):
    model = Flaky(turn_b=[bad, bad])
    r = await ask(model)
    assert model.b_calls == 2  # exactly one retry, never a third attempt
    assert r.abstained and r.abstained_because == finalize.GENERATION_FAILED
    assert r.recommendation == finalize.GENERATION_FAILED_MESSAGE
    assert r.retrieved_evidence == [] and r.agrochemical_label == [] and r.limitations == ""
    assert "Answer withheld by code" in r.model_inference


async def test_the_water_balance_code_computed_is_still_shown(wired):
    r = await ask(Flaky(turn_b=["reject", "reject"]))
    assert r.abstained and r.water_balance is not None and r.water_balance.verdict == "wait"
    assert (r.water_balance.depletion_mm, r.water_balance.raw_mm) == (45.0, 50.0)  # code's numbers


async def test_the_message_is_two_paragraphs_with_the_helpline():
    hi, en = finalize.GENERATION_FAILED_MESSAGE.split("\n\n")
    assert "1800-180-1551" in hi and "1800-180-1551" in en and "ask again" in en


async def test_a_rejected_tool_call_is_retried(wired):
    model = Flaky(turn_a=["reject"])
    r = await ask(model)
    assert model.a_calls >= 2 and not r.abstained and r.water_balance is not None


async def test_two_rejected_tool_calls_abstain_without_ever_reaching_turn_b(wired):
    model = Flaky(turn_a=["reject", "reject"])
    r = await ask(model)
    assert r.abstained and r.abstained_because == finalize.GENERATION_FAILED
    assert model.b_calls == 0 and r.water_balance is None


@pytest.mark.parametrize("turn", ["turn_a", "turn_b"])
async def test_a_failure_that_is_not_a_rejected_output_is_not_retried(wired, turn):
    model = Flaky(**{turn: ["boom", "ok"]})
    with pytest.raises(AgentError):
        await ask(model)
    assert (model.a_calls if turn == "turn_a" else model.b_calls) == 1


async def test_the_retried_answer_still_goes_through_every_safety_check(wired):
    # First attempt rejected; the second is a pesticide dose. The retry must not be a way around the guards.
    dose = answer(recommendation="Spray 2 ml per litre of water on the wheat.", irrigation_verdict="not_applicable")
    model = Flaky(turn_b=["reject", dose], calls_tool=False)
    r = await ask(model, question="What should I spray on my wheat?")
    assert model.b_calls == 2 and r.abstained
    assert r.abstained_because == interim_dose_guard.SAFE_ABSTAIN_REASON  # the dose guard, not the retry path
    assert "2 ml" not in r.recommendation
