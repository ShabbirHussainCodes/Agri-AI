from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.auth import AuthContext, get_current_user
from app.core.db import get_authed_conn
from app.schemas.farm import Farm, FarmCreate, FarmUpdate
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


@router.get("/{farm_id}", response_model=Farm)
async def get_farm(
    farm_id: UUID,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    row = await farms_service.get_farm(conn, farm_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "No such farm."}},
        )
    return dict(row)


@router.patch("/{farm_id}", response_model=Farm)
async def update_farm(
    farm_id: UUID,
    data: FarmUpdate,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    row = await farms_service.update_farm(conn, farm_id, data)
    if row is None:
        # Same answer for "no such farm" and "someone else's farm": RLS hides
        # the row, and telling them apart would leak that it exists.
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "No such farm."}},
        )
    return dict(row)
