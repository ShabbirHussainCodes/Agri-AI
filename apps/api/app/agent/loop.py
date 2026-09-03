"""The hand-rolled tool-calling loop (ADR-0002, docs/ai/agent-design.md).

Turn A (bounded, up to MAX_TOOL_ROUNDS): model sees the read tools it is
actually allowed a choice about, decides what evidence it needs; we run
the real tools and feed results back. Turn B: model sees only the
gathered evidence under its own, separate system prompt, forced into the
AdvisoryResponse schema -- no tools, no more freedom to ask for data.

This module never imports asyncpg for its own queries -- `conn` is only
ever handed through to a tool (or to get_farm_context directly, below).
It doesn't know or care how a tool gets its data, only that it returns a
typed Pydantic result.

2026-09 bug fix: Turn A and Turn B used to share one SYSTEM_PROMPT that
included the Turn-B-only instruction "set abstained=true ...". In Turn A
(tools available, no schema) the model tried to follow that instruction
anyway and emitted a malformed tool-call-shaped generation (Groq
`failed_generation`, an invalid "abstained=False" function name) -- an
unhandled exception that surfaced as a bare 500 to the caller. Root
cause was two mixed concerns: (1) one prompt serving two turns with
different capabilities, and (2) get_farm_context being an LLM-optional
tool for something every farm-specific question needs deterministically
(agent-design.md "Deterministic vs LLM"). Fixed by splitting the prompt
per turn and calling get_farm_context directly, below, instead of
exposing it as a tool.
"""
import json
from typing import Any
from uuid import UUID

import asyncpg

from app.agent.tools import farm_context, weather
from app.core.errors import AgentError
from app.providers.base import LLMProvider
from app.schemas.advisory import AdvisoryResponse

MAX_TOOL_ROUNDS = 3

# Turn A: evidence gathering only. get_farm_context is NOT offered as a
# tool here -- it is fetched deterministically in run_agent() before this
# prompt is even built, because every farm-specific question needs it
# and there is no real decision for the model to make about whether to
# fetch it. Only get_weather remains genuinely LLM-gated, since whether
# a question needs weather is a real judgement call.
#
# Deliberately says nothing about `abstained` -- that field doesn't
# exist yet at this point in the conversation (no schema is active), and
# telling the model to "set" it here is exactly what caused the bug
# described above.
TURN_A_SYSTEM_PROMPT = """You are AgriAI, a farming advisory assistant for Indian smallholder farmers.

You have already been given this farm's own record in the user message below -- use it, don't ask for it again.

Rules:
- Use ONLY the tools provided to get real data. Never invent crop, weather, or activity data.
- Call get_weather only if the question depends on weather (irrigation, spraying, timing).
- When you have enough evidence (or you've decided no more tools will help), stop calling tools. Do not write a final answer here -- a separate step will ask you for the structured answer."""

# Turn B: answer construction. A fresh, short system message of its
# own -- it does NOT reuse Turn A's prompt, so instructions that only
# make sense once a schema is active (abstention) can't leak into Turn A
# where there is no schema and no legal way to express them.
TURN_B_SYSTEM_PROMPT = """You are AgriAI. Using only the evidence below (this farm's own record, any weather data fetched, and your own reasoning), produce the final structured advisory.

Rules:
- structured_data and live_data must reflect exactly what was provided below -- do not alter or invent values in them.
- model_inference and recommendation must be grounded only in the evidence below. Never state a specific number (temperature, rainfall, dose, date) that isn't present in the evidence.
- If the evidence doesn't give you enough to answer confidently, set abstained=true and explain why in abstained_because -- do not guess.
- Never state a pesticide dose or waiting period -- that capability does not exist yet in this system.
- Keep the recommendation short, concrete, and actionable for a farmer reading on a phone."""

TOOLS = [weather.TOOL_SPEC]


async def _dispatch_tool(
    conn: asyncpg.Connection, farm_id: UUID, name: str
) -> dict[str, Any]:
    """Every branch here is explicit -- an unknown tool name or a tool
    failure becomes evidence the model can see and reason about (e.g.
    abstain), never an unhandled crash (agent-design.md: "explicit error
    handling" is a requirement for every tool)."""
    try:
        if name == "get_weather":
            result = await weather.get_weather(conn, farm_id)
        else:
            return {"error": f"unknown tool: {name}"}
        return result.model_dump(mode="json")
    except weather.WeatherUnavailable as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{name} failed: {exc}"}


async def run_agent(
    provider: LLMProvider,
    conn: asyncpg.Connection,
    farm_id: UUID,
    question: str,
    *,
    model: str,
) -> AdvisoryResponse:
    # Deterministic, not LLM-gated (agent-design.md "Deterministic vs
    # LLM"): every farm-specific question needs this, so there is no
    # real decision for the model to make about whether to fetch it. A
    # DB failure here is a Postgres/RLS error, not an agent error -- it
    # deliberately falls through to the existing postgres_error_handler
    # (main.py), not the AgentError handling below.
    farm_data = await farm_context.get_farm_context(conn, farm_id)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": TURN_A_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Farm record:\n{farm_data.model_dump_json()}\n\n"
                f"Farmer's question: {question}"
            ),
        },
    ]

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            result = await provider.chat(messages, model=model, tools=TOOLS)

            if not result.tool_calls:
                break

            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in result.tool_calls
                    ],
                }
            )
            for tc in result.tool_calls:
                tool_result = await _dispatch_tool(conn, farm_id, tc.name)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(tool_result)}
                )

        # Turn B gets its own system message, not Turn A's -- see
        # TURN_B_SYSTEM_PROMPT above. `messages[1:]` is the user question
        # plus any tool-call rounds, with Turn A's system message dropped.
        turn_b_messages = [
            {"role": "system", "content": TURN_B_SYSTEM_PROMPT},
            *messages[1:],
        ]

        final = await provider.chat(
            turn_b_messages,
            model=model,
            response_schema=AdvisoryResponse.model_json_schema(),
        )

        if final.content is None:
            raise RuntimeError("Model did not return a final structured answer")

        return AdvisoryResponse.model_validate(json.loads(final.content))

    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        # Provider failure, malformed generation, schema-validation
        # failure -- whatever it is, the farmer must see an honest error,
        # never a fabricated answer and never a raw traceback
        # (docs/backend/backend-architecture.md). AgentError's own
        # handler (main.py) turns this into a clean {"error": {...}}
        # envelope instead of a bare 500.
        raise AgentError(f"Agent pipeline failed: {exc}") from exc
