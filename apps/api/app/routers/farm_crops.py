from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import AuthContext, get_current_user
from app.core.db import get_authed_conn
from app.schemas.activity import Activity, ActivityCreate
from app.schemas.farm_crop import FarmCrop, FarmCropCreate
from app.services import activities as activities_service
from app.services import farm_crops as farm_crops_service

router = APIRouter(tags=["farm_crops"])


@router.post("/farms/{farm_id}/crops", response_model=FarmCrop, status_code=201)
async def create_farm_crop(
    farm_id: UUID,
    data: FarmCropCreate,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    row = await farm_crops_service.create_farm_crop(conn, farm_id, data)
    return dict(row)


@router.get("/farms/{farm_id}/crops", response_model=list[FarmCrop])
async def list_farm_crops(
    farm_id: UUID,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    rows = await farm_crops_service.list_farm_crops(conn, farm_id)
    return [dict(r) for r in rows]


@router.post("/farm-crops/{farm_crop_id}/activities", response_model=Activity, status_code=201)
async def create_activity(
    farm_crop_id: UUID,
    data: ActivityCreate,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    row = await activities_service.create_activity(conn, farm_crop_id, data)
    return dict(row)


@router.get("/farms/{farm_id}/timeline", response_model=list[Activity])
async def farm_timeline(
    farm_id: UUID,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    rows = await activities_service.farm_timeline(conn, farm_id)
    return [dict(r) for r in rows]
