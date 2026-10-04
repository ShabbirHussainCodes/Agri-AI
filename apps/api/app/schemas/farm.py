"""Pydantic models = the API contract (see docs/api/api-contracts.md).
The same class shape is used for both the request body and the response,
kept separate here because a farmer never sends `id`/`created_at`."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agronomy.crop_water import SoilTexture


class FarmCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Range-checked: an impossible coordinate would only fail later, inside a
    # weather request, far from where the mistake was made.
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    district: str | None = None
    state: str | None = None
    area_ha: float | None = None
    # ADR-0015: sandy (retili) | loamy (domat) | clayey (chikni/kali).
    soil_texture: SoilTexture | None = None


class FarmUpdate(BaseModel):
    """PATCH body: only the fields sent are changed (`exclude_unset`), and an
    explicit null clears a nullable field. Needed because a farm created
    without a location or soil type could otherwise never gain one, and the
    irrigation water balance (ADR-0015) needs both."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    district: str | None = None
    state: str | None = None
    area_ha: float | None = None
    soil_texture: SoilTexture | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> "FarmUpdate":
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be cleared")
        return self


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
    soil_texture: SoilTexture | None = None
    created_at: datetime
