from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AdvisoryRecord(BaseModel):
    """A saved answer. `response` is the AdvisoryResponse exactly as it was when
    the farmer received it, kept as a plain object on purpose: that contract
    grows, and an old row must never fail to load because of a newer schema."""

    id: UUID
    farm_id: UUID
    question: str
    response: dict[str, Any]
    abstained: bool
    created_at: datetime
