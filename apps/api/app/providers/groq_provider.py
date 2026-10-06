"""Groq implementation of LLMProvider (ADR-0004).

Verified against the current Groq Python SDK (AsyncGroq, groq>=1.7) and
Groq's own docs (console.groq.com/docs/tool-use,
console.groq.com/docs/structured-outputs) on 2026-08-30 -- both tool
calling and structured outputs use the same request shape as OpenAI's
API, which Groq's SDK mirrors.
"""
import json
from typing import Any

from groq import AsyncGroq, BadRequestError

from app.providers.base import ChatResult, LLMProvider, ProviderOutputInvalid, TokenUsage, ToolCall

# Groq 400 error codes that mean "the model wrote something unusable", as opposed to "your request is wrong".
# json_validate_failed was measured (20b failed 3 of 15 questions, 2026-09-30); tool_use_failed is the same
# kind of failure on Turn A and is named here from Groq's error vocabulary, not from a measured failure.
_OUTPUT_REJECTED = ("json_validate_failed", "tool_use_failed")


def _rejected_code(exc: BadRequestError) -> str | None:
    """The reason code if this 400 is a rejected model output, else None. Reads the SDK's `code`, then the
    body (with or without the {"error": ...} wrapper), then the message text, because the SDK's exact
    shape for this is not something to rely on from memory."""
    candidates: list[object] = [getattr(exc, "code", None)]
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        candidates += [body.get("code"), inner.get("code") if isinstance(inner, dict) else None]
    for c in candidates:
        if isinstance(c, str) and c in _OUTPUT_REJECTED:
            return c
    text = str(exc)
    return next((code for code in _OUTPUT_REJECTED if code in text), None)


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
    # `default` is dropped: every property is required here, so a default can
    # never apply, and strict mode may not accept the keyword (Phase 5 added the
    # first field with a default, DraftAdvisory.irrigation_verdict).
    schema.pop("default", None)
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

        try:
            completion = await self._client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            code = _rejected_code(exc)
            if code is None:
                raise
            raise ProviderOutputInvalid(code) from exc
        message = completion.choices[0].message
        usage = _usage(completion)

        if message.tool_calls:
            return ChatResult(
                usage=usage,
                tool_calls=[
                    ToolCall(id=tc.id, name=tc.function.name, arguments=_tool_arguments(tc))
                    for tc in message.tool_calls
                ]
            )
        return ChatResult(content=message.content, usage=usage)


def _tool_arguments(tool_call: Any) -> dict[str, Any]:
    """A tool call whose arguments are not valid JSON is a bad model output, not a server fault."""
    try:
        arguments = json.loads(tool_call.function.arguments)
    except (TypeError, ValueError) as exc:
        raise ProviderOutputInvalid("tool_arguments_not_json") from exc
    if not isinstance(arguments, dict):
        raise ProviderOutputInvalid("tool_arguments_not_an_object")
    return arguments


def _usage(completion: Any) -> TokenUsage | None:
    """Groq's response is OpenAI-compatible and normally carries `usage`;
    read it defensively so a response without it records None instead of
    failing the farmer's request over bookkeeping."""
    u = getattr(completion, "usage", None)
    try:
        return TokenUsage(
            prompt_tokens=int(u.prompt_tokens),
            completion_tokens=int(u.completion_tokens),
            total_tokens=int(u.total_tokens),
        )
    except (AttributeError, TypeError, ValueError):
        return None
