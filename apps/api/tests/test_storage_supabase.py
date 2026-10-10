"""The private `crop-photos` bucket against the REAL local Supabase Storage API (ADR-0008, ADR-0018).
Proves row-level security on storage.objects is the gatekeeper: another farmer's token cannot write, read
or delete a photo under my farm's folder. Needs the local stack and migration 20261010120000."""
import uuid

import httpx
import pytest

from app.providers.storage import StorageError, SupabaseStorage

from ._images import encode, leaf_like
from .conftest import SUPABASE_PUBLISHABLE_KEY, signup_test_user

pytestmark = pytest.mark.asyncio

LOCAL_URL = "http://127.0.0.1:54321"


def storage() -> SupabaseStorage:
    return SupabaseStorage(LOCAL_URL, SUPABASE_PUBLISHABLE_KEY, "crop-photos")


async def _farm(client, token) -> str:
    r = await client.post("/farms", headers={"Authorization": f"Bearer {token}"}, json={"name": "Photo Farm"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _fetch(url: str) -> httpx.Response:
    async with httpx.AsyncClient() as c:
        return await c.get(url)


async def test_the_owner_can_store_sign_read_and_delete_a_photo(client):
    owner = await signup_test_user()
    farm_id = await _farm(client, owner)
    key, data = f"{farm_id}/{uuid.uuid4()}.jpg", encode(leaf_like(300, 200), "JPEG")
    s = storage()
    await s.put(key, data, content_type="image/jpeg", token=owner)
    url = await s.signed_url(key, token=owner, expires_in=60)
    got = await _fetch(url)
    assert got.status_code == 200 and got.content == data
    await s.delete(key, token=owner)
    assert (await _fetch(url)).status_code in (400, 404)


async def test_another_farmer_cannot_write_sign_or_delete_in_my_farms_folder(client):
    owner, intruder = await signup_test_user(), await signup_test_user()
    farm_id = await _farm(client, owner)
    key, data = f"{farm_id}/{uuid.uuid4()}.jpg", encode(leaf_like(200, 200), "JPEG")
    s = storage()
    with pytest.raises(StorageError):
        await s.put(key, data, content_type="image/jpeg", token=intruder)

    await s.put(key, data, content_type="image/jpeg", token=owner)
    with pytest.raises(StorageError):
        await s.signed_url(key, token=intruder)
    with pytest.raises(StorageError):  # "Access denied" from row-level security; the object stays
        await s.delete(key, token=intruder)
    assert (await _fetch(await s.signed_url(key, token=owner))).status_code == 200
    await s.delete(key, token=owner)


async def test_a_path_outside_any_of_my_farms_is_refused_even_for_a_logged_in_user(client):
    owner = await signup_test_user()
    await _farm(client, owner)
    s = storage()
    for key in (f"{uuid.uuid4()}/x.jpg", "loose.jpg"):
        with pytest.raises(StorageError):
            await s.put(key, b"\xff\xd8\xff" + b"0" * 100, content_type="image/jpeg", token=owner)


async def test_the_bucket_accepts_only_small_jpeg(client):
    owner = await signup_test_user()
    farm_id = await _farm(client, owner)
    s = storage()
    with pytest.raises(StorageError):
        await s.put(f"{farm_id}/a.png", encode(leaf_like(100, 100), "PNG"), content_type="image/png", token=owner)
    with pytest.raises(StorageError):
        await s.put(f"{farm_id}/big.jpg", b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024 + 10), content_type="image/jpeg", token=owner)


async def test_an_anonymous_caller_cannot_read_the_private_bucket(client):
    owner = await signup_test_user()
    farm_id = await _farm(client, owner)
    key = f"{farm_id}/{uuid.uuid4()}.jpg"
    s = storage()
    await s.put(key, encode(leaf_like(100, 100), "JPEG"), content_type="image/jpeg", token=owner)
    anonymous = await _fetch(f"{LOCAL_URL}/storage/v1/object/crop-photos/{key}")
    public = await _fetch(f"{LOCAL_URL}/storage/v1/object/public/crop-photos/{key}")
    assert anonymous.status_code in (400, 401, 403, 404) and public.status_code in (400, 404)
    await s.delete(key, token=owner)
