"""Token usage is read from the provider response defensively: a response
without usage must record None, never crash a farmer's request."""
from types import SimpleNamespace

from app.providers.base import TokenUsage
from app.providers.groq_provider import _usage


def test_reported_usage_is_copied():
    completion = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3900, completion_tokens=250, total_tokens=4150))
    assert _usage(completion) == TokenUsage(prompt_tokens=3900, completion_tokens=250, total_tokens=4150)


def test_missing_or_partial_usage_is_none():
    assert _usage(SimpleNamespace()) is None
    assert _usage(SimpleNamespace(usage=None)) is None
    assert _usage(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=None, completion_tokens=1, total_tokens=1))) is None
