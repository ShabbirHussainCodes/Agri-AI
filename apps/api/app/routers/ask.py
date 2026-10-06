from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agent.loop import run_agent
from app.core.auth import AuthContext, get_current_user
from app.core.config import settings
from app.core.db import get_authed_conn
from app.providers.base import LLMProvider
from app.providers.groq_provider import GroqProvider
from app.schemas.advisory import AdvisoryResponse
from app.schemas.advisory_record import AdvisoryRecord
from app.services import advisories as advisories_service
from app.services import farms as farms_service

router = APIRouter(tags=["agent"])

_provider = GroqProvider(api_key=settings.groq_api_key)

# Bilingual like every farmer-facing message, Hindi first. The cap exists to
# protect a free-tier budget, so the text says "try tomorrow", not "error".
_LIMIT_MESSAGE = {
    "user": (
        "आज के लिए आपके सवालों की सीमा पूरी हो गई है। कल फिर पूछिए, या अपने कृषि विज्ञान केंद्र (KVK) / "
        "किसान कॉल सेंटर (1800-180-1551) से पूछिए।\n\n"
        "You have used today's questions. Please ask again tomorrow, or ask your Krishi Vigyan Kendra (KVK) "
        "or the Kisan Call Centre (1800-180-1551)."
    ),
    "global": (
        "AgriAI आज बहुत ज़्यादा इस्तेमाल हो चुका है और अभी और सवाल नहीं ले पा रहा। कल फिर कोशिश कीजिए, "
        "या कृषि विज्ञान केंद्र (KVK) / किसान कॉल सेंटर (1800-180-1551) से पूछिए।\n\n"
        "AgriAI has reached its limit for today and cannot take more questions. Please try again tomorrow, "
        "or ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551)."
    ),
}


def get_llm_provider() -> LLMProvider:
    """A dependency, not a bare module import, so tests can swap in a
    fake provider via app.dependency_overrides -- same pattern Phase 1
    used for DB access (get_authed_conn)."""
    return _provider


class AskRequest(BaseModel):
    # A bound on what one request can cost: the question goes into a prompt.
    question: str = Field(min_length=1, max_length=1000)
    # The language the farmer reads the app in. Optional: without it the answer follows the question's language.
    language: Literal["hi", "en"] | None = None


@router.post("/farms/{farm_id}/ask", response_model=AdvisoryResponse)
async def ask(
    farm_id: UUID,
    body: AskRequest,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
    llm: LLMProvider = Depends(get_llm_provider),
):
    # Ownership first: a farm that is not the caller's must not cost LLM tokens.
    if await farms_service.get_farm(conn, farm_id) is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "No such farm."}},
        )
    limited = await advisories_service.quota_reached(
        conn,
        per_user=settings.ask_limit_per_user_per_day,
        global_=settings.ask_limit_global_per_day,
    )
    if limited:
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "ask_limit_reached", "scope": limited, "message": _LIMIT_MESSAGE[limited]}},
        )
    response = await run_agent(
        llm,
        conn,
        farm_id,
        body.question,
        model=settings.groq_chat_model,
        language=body.language,
    )
    # Kept so the timeline can show it. A failed run raises above and is not kept
    # (nor counted: it never reaches this line).
    await advisories_service.save_advisory(conn, farm_id, body.question, response)
    return response


@router.get("/farms/{farm_id}/advisories", response_model=list[AdvisoryRecord])
async def list_advisories(
    farm_id: UUID,
    limit: int = 50,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    rows = await advisories_service.list_advisories(conn, farm_id, max(1, min(limit, 100)))
    return [dict(r) for r in rows]
