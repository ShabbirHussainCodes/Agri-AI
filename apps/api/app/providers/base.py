"""LLMProvider: the abstraction every agent call goes through.

Nothing in app/agent/ ever imports groq directly -- it only depends on
this interface. Swapping providers (adding the Mistral fallback from
ADR-0004 later) means writing one new class here, not touching the loop.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    """Normalised result of one provider call, regardless of vendor.

    Exactly one of `content` / `tool_calls` is meaningful at a time: the
    model either asked to call tools, or it gave a final answer.
    """

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(ABC):
    """One chat call. Pass `tools` for Turn A (model may ask for data);
    pass `response_schema` for Turn B (model is forced into that shape,
    no tool calls). See docs/ai/agent-design.md for the two-turn loop.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> ChatResult: ...
