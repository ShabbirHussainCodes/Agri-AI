"""Pydantic models = the API contract (see docs/api/api-contracts.md).
The same class shape is used for both the request body and the response,
kept separate here because a farmer never sends `id`/`created_at`."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FarmCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lat: float | None = None
    lon: float | None = None
    district: str | None = None
    state: str | None = None
    area_ha: float | None = None


class Farm(BaseModel):
    id: UUID
    profile_id: UUID
    name: str
    lat: float | None
    lon: float | None
    district: str | None
    state: str | None
    agro_climatic_zone: str | None
    area_ha: float | None
    created_at: datetime
