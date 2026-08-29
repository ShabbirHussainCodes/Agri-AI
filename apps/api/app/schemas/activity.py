from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

ActivityType = Literal["irrigation", "fertiliser", "spray", "sowing", "scouting", "other"]


class ActivityCreate(BaseModel):
    type: ActivityType
    occurred_on: date
    details: dict[str, Any] = {}


class Activity(BaseModel):
    id: UUID
    farm_crop_id: UUID
    type: str
    occurred_on: date
    details: dict[str, Any]
    source: str
    created_at: datetime
