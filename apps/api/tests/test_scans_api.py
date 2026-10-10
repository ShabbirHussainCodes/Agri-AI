"""POST /farms/{id}/scans and friends against the REAL local database (ADR-0018). Needs the local Supabase
stack with migration 20261010120000 applied (`supabase migration up`, never `db reset`). Models are fakes,
storage is an in-memory fake here (the real Storage API has its own test below); everything else is real:
auth, row-level security, the saved rows, the caps."""
import io
import json

import pytest
from PIL import Image

from app.core.config import settings
from app.main import app
from app.providers.base import ChatResult, LLMProvider
from app.providers.storage import StorageError, StorageProvider
from app.routers import scans as scans_router
from app.routers.ask import get_llm_provider
from app.vision import decision as D
from app.vision import imaging, messages, quality

from . import test_vision_diagnose as vd
from ._images import blurred, encode, jpeg_with_exif, leaf_like
from .conftest import signup_test_user

pytestmark = pytest.mark.asyncio


class MemoryStorage(StorageProvider):
    def __init__(self, fail_put: bool = False):
        self.objects: dict[str, bytes] = {}
        self.tokens: list[str] = []
        self.deleted: list[str] = []
        self.fail_put = fail_put

    async def put(self, key, data, *, content_type, token):
        if self.fail_put:
            raise StorageError("upload failed (500)")
        assert content_type == "image/jpeg"
        self.objects[key] = data
        self.tokens.append(token)

    async def delete(self, key, *, token):
        self.deleted.append(key)
        self.objects.pop(key, None)

    async def signed_url(self, key, *, token, expires_in=3600):
        return f"http://storage.test/{key}"


@pytest.fixture
def setup(monkeypatch, tmp_path):
    """Fake models/classifier/retrieval/storage wired into the real router."""
    table = tmp_path / "agrochem.json"
    table.write_text(json.dumps({"table_version": "synthetic-v1", "primary_source": "t", "rows": [vd.ROW]}), encoding="utf-8")

    async def nothing(conn, embedder, question, **kw):
        from app.retrieval.hybrid import RetrievalResult
        return RetrievalResult(query=question, tier="unfiltered", accepted=True, top_dense_similarity=None, chunks=[])

    monkeypatch.setattr(vd.dg, "retrieve", nothing)
    monkeypatch.setattr(vd.dg, "get_query_embedder", lambda: object())
    state = {"deps": vd.make_deps(agrochem_table=table), "storage": MemoryStorage()}
    monkeypatch.setattr(scans_router.runtime, "build_deps", lambda llm, vision: state["deps"])
    app.dependency_overrides[scans_router.get_storage_provider] = lambda: state["storage"]
    app.dependency_overrides[get_llm_provider] = lambda: state["deps"].llm
    monkeypatch.setattr(settings, "scan_limit_per_user_per_day", 0)
    monkeypatch.setattr(settings, "scan_limit_global_per_day", 0)
    yield state
    app.dependency_overrides.pop(scans_router.get_storage_provider, None)
    app.dependency_overrides.pop(get_llm_provider, None)


async def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _farm(client, token):
    r = await client.post("/farms", headers=await _auth(token), json={"name": "Scan Farm"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload(data: bytes, name="leaf.jpg", mime="image/jpeg"):
    return {"image": (name, data, mime)}


async def _scan(client, token, farm_id, data=None, **form):
    return await client.post(
        f"/farms/{farm_id}/scans", headers=await _auth(token),
        files=_upload(data if data is not None else encode(leaf_like(640, 480), "JPEG")), data=form,
    )


async def test_a_photo_is_diagnosed_saved_stored_and_listed_for_its_owner_only(client, setup):
    owner, other = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    r = await _scan(client, owner, farm_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "diagnosis" and body["candidates"][0]["label"] == "Tomato___Early_blight"
    assert body["scan_id"] and body["created_at"] and body["image_path"] == f"{farm_id}/{body['scan_id']}.jpg"
    assert body["advisory"]["agrochemical_label"][0]["molecule"] == "testmolecule"

    store = setup["storage"]
    assert list(store.objects) == [body["image_path"]] and store.tokens == [owner]  # stored as the caller, with their own token

    listed = await client.get(f"/farms/{farm_id}/scans", headers=await _auth(owner))
    assert [row["id"] for row in listed.json()] == [body["scan_id"]]
    assert listed.json()[0]["outcome"] == "diagnosis" and listed.json()[0]["response"]["candidates"]
    assert (await client.get(f"/farms/{farm_id}/scans", headers=await _auth(other))).json() == []  # RLS


async def test_what_is_stored_has_no_exif_even_if_the_upload_had_gps(client, setup):
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    original = jpeg_with_exif(leaf_like(640, 480), orientation=1, gps=True)
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)
    r = await _scan(client, token, farm_id, original)
    assert r.status_code == 200
    stored = next(iter(setup["storage"].objects.values()))
    assert dict(Image.open(io.BytesIO(stored)).getexif()) == {} and b"SecretPhone" not in stored


async def test_someone_elses_farm_is_a_404_and_costs_no_model_call(client, setup):
    owner, intruder = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    r = await _scan(client, intruder, farm_id)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert setup["deps"].vision.calls == [] and setup["storage"].objects == {}


@pytest.mark.parametrize("data,status,code", [
    (b"", 400, imaging.REASON_EMPTY),
    (b"%PDF-1.4 not an image", 415, imaging.REASON_UNSUPPORTED),
    (b"\xff\xd8\xff\xe0" + b"junk" * 50, 422, imaging.REASON_UNREADABLE),
])
async def test_bad_uploads_get_a_bilingual_error_envelope_and_nothing_runs(client, setup, data, status, code):
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    r = await _scan(client, token, farm_id, data)
    assert r.status_code == status
    err = r.json()["error"]
    assert err["code"] == code and err["message"] == messages.UPLOAD_ERRORS[code][1] and "\n\n" in err["message"]
    assert setup["deps"].vision.calls == [] and setup["storage"].objects == {}


async def test_an_oversized_upload_is_refused(client, setup, monkeypatch):
    monkeypatch.setattr(imaging, "MAX_UPLOAD_BYTES", 5000)
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    r = await _scan(client, token, farm_id, encode(leaf_like(800, 600), "PNG"))
    assert r.status_code == 413 and r.json()["error"]["code"] == imaging.REASON_TOO_LARGE


async def test_an_unknown_language_is_a_422(client, setup):
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    assert (await _scan(client, token, farm_id, language="fr")).status_code == 422


async def test_language_hi_reaches_the_answer_model(client, setup):
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    assert (await _scan(client, token, farm_id, language="hi")).status_code == 200
    assert "Hindi (Devanagari" in setup["deps"].llm.calls[0]["messages"][0]["content"]


async def test_a_rejected_photo_is_neither_saved_stored_nor_counted(client, setup, monkeypatch):
    monkeypatch.setattr(settings, "scan_limit_per_user_per_day", 1)
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    for _ in range(3):  # three blurry retakes do not use up the farmer's one daily check
        r = await _scan(client, token, farm_id, encode(blurred(leaf_like(640, 480), 9), "JPEG"))
        assert r.status_code == 200 and r.json()["outcome"] == "rejected_quality"
        assert r.json()["scan_id"] is None and r.json()["message"] == messages.QUALITY_TIPS[quality.TOO_BLURRY]
    assert (await client.get(f"/farms/{farm_id}/scans", headers=await _auth(token))).json() == []
    assert setup["storage"].objects == {}
    assert (await _scan(client, token, farm_id)).status_code == 200  # the one real check is still available


async def test_an_abstained_photo_is_saved_and_counts(client, setup, monkeypatch):
    monkeypatch.setattr(settings, "scan_limit_per_user_per_day", 1)
    setup["deps"].vision.answer = {**vd.GOOD_VLM, "crop": "wheat"}
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    r = await _scan(client, token, farm_id)
    assert r.json()["outcome"] == "abstained" and r.json()["abstained_because"] == D.MODEL_DISAGREEMENT
    assert r.json()["scan_id"] and r.json()["image_path"]  # kept: it is the record of what the farmer was told
    again = await _scan(client, token, farm_id)
    assert again.status_code == 429


async def test_the_per_user_scan_cap_is_a_bilingual_429_before_any_model_call(client, setup, monkeypatch):
    monkeypatch.setattr(settings, "scan_limit_per_user_per_day", 1)
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    assert (await _scan(client, token, farm_id)).status_code == 200
    calls_before = len(setup["deps"].vision.calls)
    r = await _scan(client, token, farm_id)
    err = r.json()["error"]
    assert r.status_code == 429 and err["code"] == "scan_limit_reached" and err["scope"] == "user"
    assert err["message"] == messages.SCAN_LIMIT_MESSAGE["user"]
    assert len(setup["deps"].vision.calls) == calls_before


async def test_a_photo_check_uses_the_same_global_budget_as_a_question(client, setup, monkeypatch):
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    assert (await _scan(client, token, farm_id)).status_code == 200
    # One check was made. With a global total of 1, both a second check and a question are refused.
    monkeypatch.setattr(settings, "ask_limit_global_per_day", 1)
    again = await _scan(client, token, farm_id)
    assert again.status_code == 429 and again.json()["error"]["scope"] == "global"
    ask = await client.post(f"/farms/{farm_id}/ask", headers=await _auth(token), json={"question": "How do I scout?"})
    assert ask.status_code == 429 and ask.json()["error"]["scope"] == "global"


async def test_a_storage_failure_does_not_lose_the_diagnosis(client, setup):
    setup["storage"] = MemoryStorage(fail_put=True)
    app.dependency_overrides[scans_router.get_storage_provider] = lambda: setup["storage"]
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    r = await _scan(client, token, farm_id)
    assert r.status_code == 200 and r.json()["outcome"] == "diagnosis" and r.json()["image_path"] is None
    assert (await client.get(f"/farms/{farm_id}/scans", headers=await _auth(token))).json()[0]["image_path"] is None


async def test_no_storage_configured_still_diagnoses(client, setup):
    app.dependency_overrides[scans_router.get_storage_provider] = lambda: None
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    r = await _scan(client, token, farm_id)
    assert r.status_code == 200 and r.json()["image_path"] is None


async def test_feedback_is_stored_for_the_owner_and_validated(client, setup):
    owner, other = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    scan_id = (await _scan(client, owner, farm_id)).json()["scan_id"]
    ok = await client.post(f"/scans/{scan_id}/feedback", headers=await _auth(owner), json={"agrees": False, "confirmed_label": "Tomato___Late_blight"})
    assert ok.status_code == 200 and ok.json()["farmer_feedback"] == {"agrees": False, "confirmed_label": "Tomato___Late_blight"}
    bad = await client.post(f"/scans/{scan_id}/feedback", headers=await _auth(owner), json={"agrees": False, "confirmed_label": "Dragon___fruit"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unknown_label"
    theirs = await client.post(f"/scans/{scan_id}/feedback", headers=await _auth(other), json={"agrees": True})
    assert theirs.status_code == 404


async def test_the_farmer_can_delete_a_check_and_its_photo_and_nobody_else_can(client, setup):
    owner, other = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    body = (await _scan(client, owner, farm_id)).json()
    assert (await client.delete(f"/scans/{body['scan_id']}", headers=await _auth(other))).status_code == 404
    assert setup["storage"].objects  # untouched
    gone = await client.delete(f"/scans/{body['scan_id']}", headers=await _auth(owner))
    assert gone.status_code == 204
    assert setup["storage"].deleted == [body["image_path"]] and setup["storage"].objects == {}
    assert (await client.get(f"/farms/{farm_id}/scans", headers=await _auth(owner))).json() == []


async def test_an_uncalibrated_deployment_refuses_every_photo_honestly(client, setup):
    setup["deps"] = vd.make_deps(classifier=False)
    token = await signup_test_user()
    farm_id = await _farm(client, token)
    r = await _scan(client, token, farm_id)
    assert r.status_code == 200 and r.json()["abstained_because"] == D.VISION_NOT_CALIBRATED
    assert setup["deps"].vision.calls == []


async def test_disease_scans_cannot_be_forged_for_someone_elses_farm_at_the_database(client, setup):
    """Row-level security, not application code, stops it: insert directly as the intruder."""
    import asyncpg
    owner, intruder = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    from app.core.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE authenticated")
            import jwt
            sub = jwt.decode(intruder, options={"verify_signature": False})["sub"]
            await conn.execute("select set_config('request.jwt.claims', $1, true)", json.dumps({"sub": sub, "role": "authenticated"}))
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "insert into public.disease_scans (farm_id, outcome, response) values ($1, 'abstained', '{}'::jsonb)",
                    __import__("uuid").UUID(farm_id),
                )


async def test_the_daily_count_ignores_a_rejected_photo_even_if_one_were_stored(client, setup):
    """Defence in depth: the router never saves a rejected photo, and the count would not use one up if it did."""
    import uuid
    from app.core.db import get_pool
    from app.services import scans as scans_service
    from app.schemas.scan import DiagnosisResponse

    token = await signup_test_user()
    farm_id = await _farm(client, token)
    rejected = vd.dg._refusal(D.decide_quality(vd.quality.QualityReport(False, (quality.TOO_BLURRY,), vd.quality.QualityMetrics(10, 10, 0, 0, 0, 0, 0), "t")), vd.dg._quality_info(
        vd.quality.QualityReport(False, (quality.TOO_BLURRY,), vd.quality.QualityMetrics(10, 10, 0, 0, 0, 0, 0), "t")), vd.dg.ModelVersions(classifier="c", calibration="k", label_map="l"))
    assert isinstance(rejected, DiagnosisResponse) and rejected.outcome == "rejected_quality"
    import jwt
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE authenticated")
            await conn.execute("select set_config('request.jwt.claims', $1, true)", json.dumps({"sub": sub, "role": "authenticated"}))
            before = (await scans_service.scans_last_day_global(conn), await scans_service.total_last_day_global(conn))
            await scans_service.save_scan(conn, uuid.uuid4(), uuid.UUID(farm_id), None, rejected)
            assert await scans_service.scans_last_day_for_user(conn) == 0
            assert (await scans_service.scans_last_day_global(conn), await scans_service.total_last_day_global(conn)) == before
