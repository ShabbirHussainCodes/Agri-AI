from fastapi import APIRouter, Depends

from app.core.auth import AuthContext, get_current_user
from app.core.db import get_authed_conn
from app.schemas.farm import Farm, FarmCreate
from app.services import farms as farms_service

router = APIRouter(prefix="/farms", tags=["farms"])


@router.post("", response_model=Farm, status_code=201)
async def create_farm(
    data: FarmCreate,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    row = await farms_service.create_farm(conn, user, data)
    return dict(row)


@router.get("", response_model=list[Farm])
async def list_farms(
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    rows = await farms_service.list_farms(conn)
    return [dict(r) for r in rows]
