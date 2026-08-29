"""Proves Row-Level Security actually enforces per-farmer isolation —
not just that policies exist, but that a second farmer genuinely cannot
read or write a first farmer's data. This is the most important test in
Phase 1: see docs/security/security-model.md and ADR-0009/CLAUDE.md §4.
"""
import pytest

from .conftest import signup_test_user

pytestmark = pytest.mark.asyncio


async def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_farmer_cannot_see_another_farmers_farms(client):
    token1 = await signup_test_user()
    token2 = await signup_test_user()

    create = await client.post(
        "/farms", headers=await _auth(token1), json={"name": "Farmer 1's Farm"}
    )
    assert create.status_code == 201
    farm_id = create.json()["id"]

    # Owner sees it.
    mine = await client.get("/farms", headers=await _auth(token1))
    assert any(f["id"] == farm_id for f in mine.json())

    # A different, unrelated farmer does not — even though they're a
    # legitimate authenticated user, just not this row's owner.
    others = await client.get("/farms", headers=await _auth(token2))
    assert all(f["id"] != farm_id for f in others.json())


async def test_farmer_cannot_read_another_farmers_timeline(client):
    token1 = await signup_test_user()
    token2 = await signup_test_user()

    create = await client.post(
        "/farms", headers=await _auth(token1), json={"name": "Farmer 1's Farm"}
    )
    farm_id = create.json()["id"]

    timeline = await client.get(f"/farms/{farm_id}/timeline", headers=await _auth(token2))
    assert timeline.status_code == 200
    assert timeline.json() == []


async def test_farmer_cannot_write_into_another_farmers_farm(client):
    token1 = await signup_test_user()
    token2 = await signup_test_user()

    create = await client.post(
        "/farms", headers=await _auth(token1), json={"name": "Farmer 1's Farm"}
    )
    farm_id = create.json()["id"]

    crops = await client.get("/crops", headers=await _auth(token2))
    crop_id = crops.json()[0]["id"]

    blocked = await client.post(
        f"/farms/{farm_id}/crops",
        headers=await _auth(token2),
        json={"crop_id": crop_id, "sowing_date": "2026-06-15"},
    )
    assert blocked.status_code == 403
