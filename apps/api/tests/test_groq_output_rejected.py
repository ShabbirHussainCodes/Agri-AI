"""GroqProvider turns "the model's output was unusable" into ProviderOutputInvalid and leaves every
other failure alone (so the loop retries exactly the first kind). No network: the SDK client is a fake."""
from types import SimpleNamespace

import httpx
import pytest
from groq import BadRequestError, RateLimitError

from app.providers.base import ProviderOutputInvalid
from app.providers.groq_provider import GroqProvider, _rejected_code

pytestmark = pytest.mark.asyncio


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.groq.test/chat"))


def bad_request(body, message="Error code: 400") -> BadRequestError:
    return BadRequestError(message, response=_response(400), body=body)


def provider_raising(exc: Exception) -> GroqProvider:
    async def create(**_kw):
        raise exc

    p = GroqProvider.__new__(GroqProvider)
    p._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return p


def provider_returning(message) -> GroqProvider:
    async def create(**_kw):
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)

    p = GroqProvider.__new__(GroqProvider)
    p._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return p


@pytest.mark.parametrize("code", ["json_validate_failed", "tool_use_failed"])
@pytest.mark.parametrize("wrap", [True, False])
async def test_a_rejected_model_output_becomes_provider_output_invalid(code, wrap):
    inner = {"message": "Failed to generate JSON", "type": "invalid_request_error", "code": code,
             "failed_generation": "{FARM DATA THE MODEL WROTE"}
    exc = bad_request({"error": inner} if wrap else inner)
    with pytest.raises(ProviderOutputInvalid) as caught:
        await provider_raising(exc).chat([{"role": "user", "content": "x"}], model="m")
    assert str(caught.value) == code
    assert "FARM DATA" not in str(caught.value)  # the model's text is never carried along


async def test_the_code_is_found_in_the_message_when_the_body_is_missing():
    exc = bad_request(None, message="Error code: 400 - {'error': {'code': 'json_validate_failed'}}")
    assert _rejected_code(exc) == "json_validate_failed"


async def test_a_bad_request_for_another_reason_is_not_swallowed():
    exc = bad_request({"error": {"code": "context_length_exceeded", "message": "too long"}})
    with pytest.raises(BadRequestError):
        await provider_raising(exc).chat([{"role": "user", "content": "x"}], model="m")


async def test_a_rate_limit_is_not_a_rejected_output():
    exc = RateLimitError("Error code: 429", response=_response(429), body={"error": {"code": "rate_limit_exceeded"}})
    with pytest.raises(RateLimitError):
        await provider_raising(exc).chat([{"role": "user", "content": "x"}], model="m")


def tool_call(arguments):
    return SimpleNamespace(id="c1", function=SimpleNamespace(name="get_weather", arguments=arguments))


@pytest.mark.parametrize("arguments", ['{"a": ', "not json", "[1, 2]", None])
async def test_malformed_tool_arguments_are_a_rejected_output(arguments):
    p = provider_returning(SimpleNamespace(tool_calls=[tool_call(arguments)], content=None))
    with pytest.raises(ProviderOutputInvalid):
        await p.chat([{"role": "user", "content": "x"}], model="m")


async def test_well_formed_tool_arguments_still_work():
    p = provider_returning(SimpleNamespace(tool_calls=[tool_call("{}")], content=None))
    result = await p.chat([{"role": "user", "content": "x"}], model="m")
    assert [(c.name, c.arguments) for c in result.tool_calls] == [("get_weather", {})]
