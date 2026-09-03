"""Groq implementation of LLMProvider (ADR-0004).

Verified against the current Groq Python SDK (AsyncGroq, groq>=1.7) and
Groq's own docs (console.groq.com/docs/tool-use,
console.groq.com/docs/structured-outputs) on 2026-08-30 -- both tool
calling and structured outputs use the same request shape as OpenAI's
API, which Groq's SDK mirrors.
"""
import json
from typing import Any

from groq import AsyncGroq

from app.providers.base import ChatResult, LLMProvider, ToolCall


def _make_strict(schema: dict[str, Any]) -> dict[str, Any]:
    """Post-process a Pydantic-generated JSON schema to satisfy Groq/OpenAI
    strict-mode structured-output rules: every object needs
    `additionalProperties: false`, and every property must be listed in
    `required` (an Optional Python field becomes a string|null union in
    the schema instead of being left out -- strict mode disallows a
    *missing key*, not a null value). Applied recursively, including
    through `$defs` (where Pydantic puts nested model schemas, e.g.
    FarmContextData/WeatherData inside AdvisoryResponse) and `anyOf`
    (where it puts unions like `str | None`).

    NOTE: this is the one part of Phase 2 verified by reasoning about the
    spec rather than a working example straight from Groq's docs -- the
    first real cassette recording (next step after this) is what actually
    proves it against the live API, not this function in isolation.
    """
    if schema.get("type") == "object" or "properties" in schema:
        props = schema.get("properties", {})
        schema["additionalProperties"] = False
        schema["required"] = list(props.keys())
        for value in props.values():
            _make_strict(value)
    if "items" in schema:
        _make_strict(schema["items"])
    for key in ("anyOf", "oneOf", "allOf"):
        for value in schema.get(key, []):
            _make_strict(value)
    for value in schema.get("$defs", {}).values():
        _make_strict(value)
    return schema


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str):
        self._client = AsyncGroq(api_key=api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> ChatResult:
        kwargs: dict[str, Any] = {"model": model, "messages": messages}

        if tools:
            kwargs["tools"] = tools

        if response_schema:
            schema_name = response_schema.get("title", "response")
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": _make_strict(response_schema),
                },
            }

        completion = await self._client.chat.completions.create(**kwargs)
        message = completion.choices[0].message

        if message.tool_calls:
            return ChatResult(
                tool_calls=[
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                    for tc in message.tool_calls
                ]
            )
        return ChatResult(content=message.content)
