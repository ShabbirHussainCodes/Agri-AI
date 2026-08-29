from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class FarmCropCreate(BaseModel):
    crop_id: UUID
    variety: str | None = None
    sowing_date: date
    expected_harvest: date | None = None


class FarmCrop(BaseModel):
    id: UUID
    farm_id: UUID
    crop_id: UUID
    variety: str | None
    sowing_date: date
    expected_harvest: date | None
    status: str
    created_at: datetime
