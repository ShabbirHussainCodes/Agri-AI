"""PATCH /farms/{id} and the soil_texture field (ADR-0015).

Two kinds of test in one file:
  * schema and SQL-building tests: pure, no database (they still import the
    app, so they need the usual AGRIAI_* environment, as every other test does);
  * endpoint tests (marked `db`): need the local Supabase stack with migration
    20261004120000 applied (`supabase migration up`, never `db reset`), same as
    tests/test_rls.py.
"""
import pytest
from pydantic import ValidationError

from app.schemas.farm import Farm, FarmCreate, FarmUpdate
from app.services import farms as farms_service

from .conftest import signup_test_user

# ------------------------------------------------------------------ schema


@pytest.mark.parametrize(
    "body",
    [
        {},  # nothing to change
        {"name": None},  # name cannot be cleared
        {"name": ""},
        {"lat": 91},
        {"lon": -181},
        {"soil_texture": "rocky"},
        {"profile_id": "x"},  # unknown field
    ],
)
def test_bad_update_bodies_are_rejected(body):
    with pytest.raises(ValidationError):
        FarmUpdate(**body)


def test_an_explicit_null_clears_a_nullable_field_but_is_still_a_change():
    u = FarmUpdate(soil_texture=None)
    assert u.model_dump(exclude_unset=True) == {"soil_texture": None}


@pytest.mark.parametrize("texture", ["sandy", "loamy", "clayey", None])
def test_create_accepts_the_three_soil_classes_and_none(texture):
    assert FarmCreate(name="F", soil_texture=texture).soil_texture == texture


def test_create_rejects_an_impossible_coordinate_and_an_unknown_soil():
    with pytest.raises(ValidationError):
        FarmCreate(name="F", lat=120.0)
    with pytest.raises(ValidationError):
        FarmCreate(name="F", soil_texture="loam")  # the stored word is "loamy"


def test_farm_response_defaults_soil_to_none():
    assert Farm.model_fields["soil_texture"].default is None


# ------------------------------------------------------------ SQL building

class RecordingConn:
    def __init__(self):
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append((" ".join(sql.split()), args))
        return {"id": args[0]}


@pytest.mark.asyncio
async def test_update_sets_only_the_fields_sent_with_bound_parameters():
    conn = RecordingConn()
    await farms_service.update_farm(conn, "farm-1", FarmUpdate(soil_texture="clayey", lat=26.85, district=None))
    [(sql, args)] = conn.calls
    # Columns come out in the model's field order, whatever order the client sent them in.
    assert sql == "update public.farms set lat = $2, district = $3, soil_texture = $4 where id = $1 returning *"
    assert args == ("farm-1", 26.85, None, "clayey")


# --------------------------------------------------------------- endpoints


async def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_patch_sets_soil_and_location_on_an_existing_farm(client):
    token = await signup_test_user()
    created = await client.post("/farms", headers=await _auth(token), json={"name": "Patch Farm"})
    assert created.status_code == 201, created.text
    assert created.json()["soil_texture"] is None
    farm_id = created.json()["id"]

    resp = await client.patch(
        f"/farms/{farm_id}", headers=await _auth(token),
        json={"soil_texture": "loamy", "lat": 26.85, "lon": 80.95},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["soil_texture"], body["lat"], body["lon"], body["name"]) == ("loamy", 26.85, 80.95, "Patch Farm")

    cleared = await client.patch(f"/farms/{farm_id}", headers=await _auth(token), json={"soil_texture": None})
    assert cleared.status_code == 200 and cleared.json()["soil_texture"] is None


@pytest.mark.asyncio
async def test_patch_rejects_bad_bodies_with_422(client):
    token = await signup_test_user()
    created = await client.post("/farms", headers=await _auth(token), json={"name": "Patch Farm"})
    farm_id = created.json()["id"]
    for body in ({}, {"soil_texture": "rocky"}, {"lat": 500}):
        resp = await client.patch(f"/farms/{farm_id}", headers=await _auth(token), json=body)
        assert resp.status_code == 422, (body, resp.text)


@pytest.mark.asyncio
async def test_a_farmer_cannot_patch_another_farmers_farm(client):
    owner, other = await signup_test_user(), await signup_test_user()
    created = await client.post("/farms", headers=await _auth(owner), json={"name": "Mine"})
    farm_id = created.json()["id"]

    resp = await client.patch(f"/farms/{farm_id}", headers=await _auth(other), json={"name": "Stolen"})
    assert resp.status_code == 404  # same answer as "no such farm": RLS hides it
    assert resp.json()["error"]["code"] == "not_found"

    mine = await client.get("/farms", headers=await _auth(owner))
    assert [f["name"] for f in mine.json()] == ["Mine"]
