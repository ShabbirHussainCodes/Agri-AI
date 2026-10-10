from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ScanRecord(BaseModel):
    """A saved photo check. `response` is the DiagnosisResponse exactly as the farmer received it, kept
    as a plain object on purpose: that contract grows, and an old row must never fail to load."""

    id: UUID
    farm_id: UUID
    image_path: str | None
    outcome: str
    abstained_because: str | None
    response: dict[str, Any]
    farmer_feedback: dict[str, Any] | None = None
    created_at: datetime


class ScanFeedback(BaseModel):
    """The farmer's own verdict on a photo check. `confirmed_label` is a class of the label map (checked in
    the router) when the farmer says the real problem was a different one."""

    agrees: bool
    confirmed_label: str | None = Field(default=None, max_length=120)
