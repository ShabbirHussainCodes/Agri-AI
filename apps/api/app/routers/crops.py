from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.db import get_authed_conn
from app.schemas.crop import Crop

router = APIRouter(prefix="/crops", tags=["crops"])


@router.get("", response_model=list[Crop])
async def list_crops(user=Depends(get_current_user), conn=Depends(get_authed_conn)):
    rows = await conn.fetch("select id, name_en, name_hi, default_duration_days from public.crops order by name_en")
    return [dict(r) for r in rows]
