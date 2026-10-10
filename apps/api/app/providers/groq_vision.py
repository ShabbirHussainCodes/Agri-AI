"""Groq implementation of VisionProvider (ADR-0004, ADR-0018).

Model `qwen/qwen3.8-27b`. The model named in ADR-0004, `qwen/qwen3.6-27b`, is no longer in Groq's model
list (checked 2026-10-10 with models.list); the vision docs name `qwen/qwen3.8-27b` as the vision model:
text and images in, JSON object mode supported, at most 3 images and 20 MB per request, each image
counted as 2,048 input tokens, status Preview.

The photo is sent as a base64 data URL in the standard chat-completions shape. JSON object mode is used
(the output is validated by app/vision/vlm.py, not trusted); a 400 whose code says the model's output was
rejected becomes ProviderOutputInvalid so the caller can retry once.
"""
import base64
from typing import Any

from groq import AsyncGroq, BadRequestError

from app.providers.base import ProviderOutputInvalid, TokenUsage, VisionProvider, VisionResult
from app.providers.groq_provider import _rejected_code, _usage

# A closed-vocabulary answer plus one short sentence needs far fewer tokens than this; the cap is a
# bound on cost, not a target.
MAX_COMPLETION_TOKENS = 600


class GroqVisionProvider(VisionProvider):
    def __init__(self, api_key: str, *, extra_params: dict[str, Any] | None = None):
        self._client = AsyncGroq(api_key=api_key)
        # Request parameters that depend on the model (for example a reasoning setting), kept out of code.
        self._extra = dict(extra_params or {})

    async def describe(self, image_jpeg: bytes, *, prompt: str, model: str) -> VisionResult:
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")
        try:
            completion = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                **self._extra,
            )
        except BadRequestError as exc:
            code = _rejected_code(exc)
            if code is None:
                raise
            raise ProviderOutputInvalid(code) from exc
        usage: TokenUsage | None = _usage(completion)
        return VisionResult(content=completion.choices[0].message.content, usage=usage)
