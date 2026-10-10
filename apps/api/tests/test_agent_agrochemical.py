"""The agent loop with the label lookup wired in (ADR-0016), with no database,
network or real model. Same fakes as test_agent_irrigation.py. The label table is
SYNTHETIC. What it proves: the model is offered the tool only for chemical
questions, never sees a number, the dose reaches the farmer only as a label card,
and every misbehaviour (a dose in prose, a banned molecule, a broken file) is
stopped by code."""
import json
import re

import pytest

from app.agent import loop
from app.agent.tools import agrochemical
from app.agent.tools.farm_context import FarmContextData
from app.core.errors import AgentError
from app.providers.base import ChatResult, LLMProvider, ToolCall
from app.retrieval.hybrid import RetrievalResult
from app.safety import chemical_guard, interim_dose_guard

from .test_agrochemical_lookup import ROW

pytestmark = pytest.mark.asyncio

TABLE = {"table_version": "synthetic-v1", "primary_source": "synthetic", "rows": [ROW]}


class Model(LLMProvider):
    def __init__(self, mode="card", args=None, calls_tool=True, basis="farm_and_weather_data"):
        self.mode, self.calls_tool, self.basis = mode, calls_tool, basis
        self.args = args or {"crop": "tomato", "pest": "early blight"}
        self.calls = []

    async def chat(self, messages, *, model, tools=None, response_schema=None):
        self.calls.append({"messages": messages, "tools": tools})
        if response_schema is None:
            if self.calls_tool and not any(m.get("role") == "tool" for m in messages):
                return ChatResult(tool_calls=[ToolCall(id="c1", name="lookup_agrochemical", arguments=self.args)])
            return ChatResult(content="enough")
        text = {
            "card": "The system shows a label card below. The label on the product pack is the legal source.",
            "writes_dose": "Mix 750 g per hectare in 500 litres of water.",
            "sneaky": "The product goes on at seven hundred and fifty: 750 over the plot.",
            "banned": "Use endosulfan on the tomatoes.",
        }.get(self.mode, "")
        abstain = self.mode == "abstain"
        return ChatResult(content=json.dumps({
            "evidence_basis": "none" if abstain else self.basis, "citations": [],
            "model_inference": "", "recommendation": "" if abstain else text, "confidence": 0.5,
            "abstained": abstain, "abstained_because": "no_verified_dose_source" if abstain else None,
            "irrigation_verdict": "not_applicable",
        }))


@pytest.fixture
def world(monkeypatch, tmp_path):
    table = tmp_path / "synthetic-agrochem.json"
    table.write_text(json.dumps(TABLE), encoding="utf-8")
    monkeypatch.setattr(loop.settings, "agrochem_table", table)

    async def farm(conn, farm_id):
        return FarmContextData(farm_name="Chem Farm", crop_name="Tomato")

    async def nothing(conn, embedder, question, **kw):
        return RetrievalResult(query=question, tier="unfiltered", accepted=True, top_dense_similarity=None, chunks=[])

    monkeypatch.setattr(loop.farm_context, "get_farm_context", farm)
    monkeypatch.setattr(loop, "retrieve", nothing)
    return tmp_path


async def ask(model, question="What should I spray for early blight on my tomato?"):
    return await loop.run_agent(model, object(), "farm-1", question, model="fake", embedder=object())


def names(call):
    return {t["function"]["name"] for t in call["tools"]}


async def test_a_chemical_question_gets_the_tool_and_the_dose_arrives_only_as_a_card(world):
    model = Model("card")
    r = await ask(model)
    assert "lookup_agrochemical" in names(model.calls[0])
    assert not r.abstained and "label card" in r.recommendation
    assert interim_dose_guard.find_dose_statement(r.recommendation) is None
    [card] = r.agrochemical_label
    assert (card.dose_formulation, card.dose_formulation_unit, card.waiting_period_days) == (750.0, "g", 7)
    assert "Waiting period: 7 days" in card.text
    # the prose has no number; the numbers live in the structured card
    assert not re.search(r"\d", r.recommendation)


async def test_the_model_never_sees_a_number_from_the_table(world):
    model = Model("card")
    await ask(model)
    tool_msgs = [m["content"] for c in model.calls for m in c["messages"] if m.get("role") == "tool"]
    assert tool_msgs and all(not re.search(r"\d", t) for t in tool_msgs)
    seen = json.dumps(model.calls)
    assert "750" not in seen and "375" not in seen and "WP" not in seen


async def test_turn_b_gets_the_label_rule_only_when_a_card_was_found(world):
    found = Model("card")
    await ask(found)
    assert loop.TURN_B_LABEL_RULE in found.calls[-1]["messages"][0]["content"]
    missing = Model("abstain", args={"crop": "tomato", "pest": "late blight"})
    await ask(missing)
    assert loop.TURN_B_LABEL_RULE not in missing.calls[-1]["messages"][0]["content"]


async def test_a_non_chemical_question_is_not_offered_the_tool(world):
    model = Model("card", calls_tool=False)
    await ask(model, question="When should I water my tomato?")
    assert "lookup_agrochemical" not in names(model.calls[0])
    assert model.calls[-1]["messages"][0]["content"] == loop.TURN_B_SYSTEM_PROMPT


async def test_no_verified_entry_means_no_card_and_the_existing_dose_abstention(world):
    r = await ask(Model("abstain", args={"crop": "tomato", "pest": "late blight"}))
    assert r.abstained and r.abstained_because == "no_verified_dose_source" and r.agrochemical_label == []
    assert r.recommendation == interim_dose_guard.SAFE_MESSAGE


@pytest.mark.parametrize("mode", ["writes_dose", "sneaky"])
async def test_a_dose_the_model_writes_anyway_is_blocked_and_the_card_is_not_shown(world, mode):
    r = await ask(Model(mode))
    assert r.abstained and r.abstained_because == interim_dose_guard.SAFE_ABSTAIN_REASON
    assert r.agrochemical_label == []
    assert "750" not in r.recommendation


async def test_a_banned_molecule_named_by_the_farmer_gets_the_code_message_and_no_card(world):
    r = await ask(Model("card"), question="Can I spray endosulfan for early blight on tomato?")
    assert r.abstained and r.abstained_because == "banned_molecule" and r.agrochemical_label == []


async def test_a_banned_molecule_in_the_models_text_is_replaced(world):
    r = await ask(Model("banned"))
    assert r.abstained_because == "banned_molecule" and r.agrochemical_label == []
    assert r.recommendation == chemical_guard.banned_message(chemical_guard.find_banned(["endosulfan"], chemical_guard.load_denylist()))
    assert "Use endosulfan" not in r.recommendation


async def test_asking_the_tool_for_a_banned_molecule_finds_nothing(world):
    model = Model("card", args={"crop": "tomato", "pest": "early blight", "molecule": "endosulfan"})
    r = await ask(model)
    tool_msg = next(m["content"] for m in model.calls[-1]["messages"] if m.get("role") == "tool")
    assert "molecule_not_permitted" in tool_msg and r.agrochemical_label == []


async def test_a_broken_table_hides_its_path_from_the_model_and_shows_no_card(world, monkeypatch):
    bad = world / "secret-dir" / "bad.json"
    bad.parent.mkdir()
    bad.write_text("{", encoding="utf-8")
    monkeypatch.setattr(loop.settings, "agrochem_table", bad)
    model = Model("abstain")
    r = await ask(model)
    tool_msgs = [m["content"] for c in model.calls for m in c["messages"] if m.get("role") == "tool"]
    assert tool_msgs and all("secret-dir" not in t for t in tool_msgs)
    assert r.agrochemical_label == [] and r.abstained


async def test_an_unreadable_denylist_stops_the_request_before_any_model_call(world, monkeypatch, tmp_path):
    bad = tmp_path / "bad-denylist.json"
    bad.write_text("{", encoding="utf-8")
    monkeypatch.setattr(chemical_guard, "DEFAULT_DENYLIST_PATH", bad)
    chemical_guard._cached.cache_clear()
    model = Model("card")
    try:
        with pytest.raises(AgentError):
            await ask(model)
        assert model.calls == []  # no quota spent
    finally:
        chemical_guard._cached.cache_clear()


def test_gating_vocabulary():
    deny = chemical_guard.load_denylist()
    yes = ["What should I spray?", "tomato me kaun si dawai daalein", "कीटनाशक का छिड़काव कब करें", "dose of mancozeb?",
           "Is endosulfan good?", "which fungicide for blight"]
    no = ["When should I water my tomato?", "How deep should I sow wheat?", "What is the weather tomorrow?"]
    assert all(agrochemical.question_is_chemical(q, deny) for q in yes)
    assert not any(agrochemical.question_is_chemical(q, deny) for q in no)


@pytest.mark.parametrize(
    "args, reason",
    [
        ({"crop": "tomato"}, "invalid_arguments"),
        ({"crop": "", "pest": "x"}, "invalid_arguments"),
        ({"crop": "tomato", "pest": "x" * 200}, "invalid_arguments"),
        ({"crop": "tomato", "pest": "blight", "molecule": 5}, "invalid_arguments"),
        ({"crop": "unicorn", "pest": "blight"}, "crop_not_recognised"),
        ({"crop": "wheat and tomato", "pest": "blight"}, "crop_not_recognised"),
    ],
)
def test_tool_arguments_are_validated(args, reason):
    from app.safety import agrochemical_lookup as al
    out = agrochemical.run_lookup(args, table=al.AgrochemTable.model_validate(TABLE), denylist=chemical_guard.load_denylist())
    assert out.payload["reason"] == reason and out.entries == []


async def test_a_card_answer_with_evidence_basis_none_is_still_an_answer(world):
    # Live, 2026-10-10: the real model answered from a card with evidence_basis "none"
    # (no schema value fits a label card) and finalize withheld it as insufficient_evidence.
    r = await ask(Model("card", basis="none"))
    assert not r.abstained and r.abstained_because is None
    [card] = r.agrochemical_label
    assert card.waiting_period_days == 7 and "label card" in r.recommendation


async def test_evidence_basis_none_without_a_card_still_abstains(world):
    # The relaxation is only for a card: no verified row found means nothing to stand on.
    r = await ask(Model("card", args={"crop": "tomato", "pest": "late blight"}, basis="none"))
    assert r.abstained and r.abstained_because == "insufficient_evidence" and r.agrochemical_label == []


@pytest.mark.parametrize("mode", ["writes_dose", "sneaky", "banned"])
async def test_a_card_with_basis_none_does_not_let_a_dose_or_a_banned_molecule_through(world, mode):
    r = await ask(Model(mode, basis="none"))
    assert r.abstained and r.agrochemical_label == []
    assert "750" not in r.recommendation
