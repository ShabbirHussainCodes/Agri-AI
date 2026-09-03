from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agent.loop import run_agent
from app.core.auth import AuthContext, get_current_user
from app.core.config import settings
from app.core.db import get_authed_conn
from app.providers.base import LLMProvider
from app.providers.groq_provider import GroqProvider
from app.schemas.advisory import AdvisoryResponse

router = APIRouter(tags=["agent"])

_provider = GroqProvider(api_key=settings.groq_api_key)


def get_llm_provider() -> LLMProvider:
    """A dependency, not a bare module import, so tests can swap in a
    fake provider via app.dependency_overrides -- same pattern Phase 1
    used for DB access (get_authed_conn)."""
    return _provider


class AskRequest(BaseModel):
    question: str


@router.post("/farms/{farm_id}/ask", response_model=AdvisoryResponse)
async def ask(
    farm_id: UUID,
    body: AskRequest,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
    llm: LLMProvider = Depends(get_llm_provider),
):
    return await run_agent(
        llm,
        conn,
        farm_id,
        body.question,
        model=settings.groq_chat_model,
    )
