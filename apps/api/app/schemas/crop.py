from uuid import UUID
from pydantic import BaseModel

class Crop(BaseModel):
    id: UUID
    name_en: str
    name_hi: str
    default_duration_days: int | None
