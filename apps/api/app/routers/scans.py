"""Crop-photo diagnosis endpoints (ADR-0018). Thin on purpose: validate, call the pipeline, save."""
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.core.auth import AuthContext, get_current_user
from app.core.config import settings
from app.core.db import get_authed_conn
from app.core.errors import AgentError
from app.providers.base import LLMProvider, VisionProvider
from app.providers.groq_vision import GroqVisionProvider
from app.providers.storage import StorageError, StorageProvider, SupabaseStorage
from app.routers.ask import get_llm_provider
from app.safety import chemical_guard
from app.schemas.scan import DiagnosisResponse
from app.schemas.scan_record import ScanFeedback, ScanRecord
from app.services import farms as farms_service
from app.services import scans as scans_service
from app.vision import imaging, messages, runtime
from app.vision.diagnose import diagnose

logger = logging.getLogger("agriai.vision")

router = APIRouter(tags=["scans"])

_vision_provider = GroqVisionProvider(api_key=settings.groq_api_key, extra_params=settings.groq_vision_extra_params)

# Multipart overhead on top of the photo itself; a request announcing more than this is refused before its
# body is read into memory.
_MULTIPART_SLACK = 256 * 1024


def get_vision_provider() -> VisionProvider:
    """A dependency, not a bare import, so tests can swap in a fake (same pattern as get_llm_provider)."""
    return _vision_provider


def get_storage_provider() -> StorageProvider | None:
    """None when no Supabase URL is configured: photos are analysed but not kept."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        return None
    return SupabaseStorage(settings.supabase_url, settings.supabase_anon_key, settings.crop_photos_bucket)


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


@router.post("/farms/{farm_id}/scans", response_model=DiagnosisResponse)
async def create_scan(
    farm_id: UUID,
    request: Request,
    image: UploadFile = File(...),
    language: str | None = Form(default=None),
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
    llm: LLMProvider = Depends(get_llm_provider),
    vision: VisionProvider = Depends(get_vision_provider),
    storage: StorageProvider | None = Depends(get_storage_provider),
):
    if language not in (None, "hi", "en"):
        return _error(422, "invalid_language", "language must be 'hi' or 'en'.")
    # Ownership first: a farm that is not the caller's must not cost model calls.
    if await farms_service.get_farm(conn, farm_id) is None:
        return _error(404, "not_found", "No such farm.")
    limited = await scans_service.quota_reached(
        conn,
        per_user=settings.scan_limit_per_user_per_day,
        scans_global=settings.scan_limit_global_per_day,
        total_global=settings.ask_limit_global_per_day,
    )
    if limited:
        return _error(429, "scan_limit_reached", messages.SCAN_LIMIT_MESSAGE[limited], scope=limited)

    announced = request.headers.get("content-length")
    if announced and announced.isdigit() and int(announced) > imaging.MAX_UPLOAD_BYTES + _MULTIPART_SLACK:
        status, message = messages.UPLOAD_ERRORS[imaging.REASON_TOO_LARGE]
        return _error(status, imaging.REASON_TOO_LARGE, message)
    data = await image.read(imaging.MAX_UPLOAD_BYTES + 1)
    try:
        prepared = imaging.prepare_image(data)
    except imaging.ImageRejected as rejected:
        status, message = messages.UPLOAD_ERRORS[rejected.code]
        return _error(status, rejected.code, message)

    try:
        deps = runtime.build_deps(llm, vision)
    except chemical_guard.DenylistError as exc:
        raise AgentError(f"Safety data unavailable: {exc}") from exc

    result = await diagnose(conn, farm_id, prepared, deps, language=language)
    response = result.response

    # A photo the quality gate refused is neither kept nor counted: nothing was analysed.
    if response.outcome == "rejected_quality":
        return response

    scan_id = uuid4()
    image_path: str | None = None
    if storage is not None:
        key = f"{farm_id}/{scan_id}.jpg"
        try:
            await storage.put(key, prepared.jpeg, content_type="image/jpeg", token=user.token)
            image_path = key
        except StorageError as exc:
            logger.warning("photo not stored: %s", exc)
    record = await scans_service.save_scan(conn, scan_id, farm_id, image_path, response)
    return response.model_copy(update={"scan_id": record["id"], "image_path": image_path, "created_at": record["created_at"]})


@router.get("/farms/{farm_id}/scans", response_model=list[ScanRecord])
async def list_scans(
    farm_id: UUID,
    limit: int = 50,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    rows = await scans_service.list_scans(conn, farm_id, max(1, min(limit, 100)))
    return [dict(r) for r in rows]


@router.post("/scans/{scan_id}/feedback", response_model=ScanRecord)
async def scan_feedback(
    scan_id: UUID,
    body: ScanFeedback,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
):
    label_names = {lab.label for lab in runtime.label_map().labels}
    if body.confirmed_label is not None and body.confirmed_label not in label_names:
        return _error(422, "unknown_label", "confirmed_label is not one of the classifier's labels.")
    row = await scans_service.set_feedback(
        conn, scan_id, {"agrees": body.agrees, "confirmed_label": body.confirmed_label}
    )
    if row is None:
        return _error(404, "not_found", "No such photo check.")
    return dict(row)


@router.delete("/scans/{scan_id}", status_code=204)
async def delete_scan(
    scan_id: UUID,
    user: AuthContext = Depends(get_current_user),
    conn=Depends(get_authed_conn),
    storage: StorageProvider | None = Depends(get_storage_provider),
):
    """The farmer removes a photo check and its photo. Row first (so nothing points at a deleted photo),
    then the object; a failure to delete the object is logged, not shown: the row is already gone."""
    row = await scans_service.get_scan(conn, scan_id)
    if row is None:
        return _error(404, "not_found", "No such photo check.")
    await scans_service.delete_scan(conn, scan_id)
    if storage is not None and row["image_path"]:
        try:
            await storage.delete(row["image_path"], token=user.token)
        except StorageError as exc:
            logger.warning("photo object not deleted: %s", exc)
    return None
