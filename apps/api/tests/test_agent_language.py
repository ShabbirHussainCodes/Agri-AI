"""The UI-language hint for /ask: opt-in, and the default prompt is exactly what the baselines measured.
Same fakes as test_agent_irrigation.py (no database, network or model)."""
import json

import pytest

from app.agent import loop
from app.routers.ask import AskRequest

from .test_agent_irrigation import ScriptedModel, wired  # noqa: F401  (wired is a fixture)
from .test_agent_irrigation import FakeConn



async def run(model, language=None, question="Should I water my wheat today?"):
    return await loop.run_agent(model, FakeConn("loamy"), "farm-1", question, model="fake", embedder=object(), language=language)


def turn_b_system(model) -> str:
    return model.calls[-1]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_without_a_language_turn_b_is_exactly_the_baseline_prompt(wired):
    model = ScriptedModel("match", calls_tool=False)
    await run(model)
    assert turn_b_system(model) == loop.TURN_B_SYSTEM_PROMPT  # nothing was added: the Phase 4 numbers still apply


@pytest.mark.parametrize("language, must_have", [("hi", ["Hindi (Devanagari", "digits 0-9"]), ("en", ["in English"])])
@pytest.mark.asyncio
async def test_a_language_adds_one_rule_at_the_end(wired, language, must_have):
    model = ScriptedModel("match", calls_tool=False)
    await run(model, language)
    prompt = turn_b_system(model)
    assert prompt == loop.TURN_B_SYSTEM_PROMPT + loop.TURN_B_LANGUAGE_RULES[language]
    assert all(s in prompt for s in must_have)
    assert "overrides the language rule above" in prompt
    assert "never translate or change a quote" in prompt  # quotes are validated verbatim against the passage


@pytest.mark.asyncio
async def test_the_language_rule_is_added_after_the_irrigation_rule(wired):
    model = ScriptedModel("match")  # calls the irrigation tool
    await run(model, "hi")
    prompt = turn_b_system(model)
    assert loop.TURN_B_IRRIGATION_RULE in prompt
    assert prompt.endswith(loop.TURN_B_LANGUAGE_RULES["hi"])


@pytest.mark.asyncio
async def test_turn_a_never_gets_the_language_rule(wired):
    model = ScriptedModel("match")
    await run(model, "hi")
    turn_a = model.calls[0]["messages"][0]["content"]
    assert turn_a == loop.TURN_A_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_an_unsupported_language_is_refused_before_any_model_call(wired):
    model = ScriptedModel("match")
    with pytest.raises(ValueError):
        await run(model, "fr")
    assert model.calls == []


@pytest.mark.asyncio
async def test_the_answer_still_goes_through_finalize_in_hindi(wired):
    # A model that follows the rule writes Hindi with ASCII digits; the code-side checks still apply to it.
    class HindiModel(ScriptedModel):
        def _answer(self, messages):
            a = super()._answer(messages)
            a["recommendation"] = "अभी रुकिए: मिट्टी में 45.0 मिमी की कमी है, सीमा 50.0 मिमी है।"
            return a

    r = await run(HindiModel("match"), "hi")
    assert not r.abstained and "रुकिए" in r.recommendation


def test_the_request_accepts_hi_en_or_nothing_and_nothing_else():
    assert AskRequest(question="x").language is None
    assert AskRequest(question="x", language="hi").language == "hi"
    assert AskRequest(question="x", language="en").language == "en"
    with pytest.raises(ValueError):
        AskRequest(question="x", language="fr")
