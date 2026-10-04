"""The crop/soil reference table is fail-closed (ADR-0012, ADR-0015).

Pure tests: no database, no network, no LLM. They use a SYNTHETIC verified
row ("Testcrop", round numbers) to prove the mechanism. They say nothing
about real agronomy, and the shipped table's real values are checked by a
human against FAO-56 (data/crop_water/README.md), not by these tests.
"""
import json

import pytest
from pydantic import ValidationError

from app.agronomy import crop_water
from app.agronomy.crop_water import (
    CROP_NOT_SUPPORTED,
    CROP_UNVERIFIED,
    SOIL_MISSING,
    SOIL_UNVERIFIED,
    CropTableError,
    CropWaterTable,
    find_crop,
    find_soil,
    load_table,
)

GOOD_CROP = {
    "name_en": "Testcrop",
    "status": "verified",
    "verified_by": "Test Reviewer",
    "verified_on": "2026-10-04",
    "kc_ini": 0.4,
    "kc_mid": 1.2,
    "kc_end": 0.6,
    "stage_days": {"initial": 10, "development": 20, "mid": 30, "late": 10},
    "stage_length_basis": "synthetic test values",
    "root_depth_m": 0.5,
    "p": 0.5,
    "sources": {"kc": "test", "stage_days": "test", "root_depth_m": "test", "p": "test"},
}
GOOD_SOIL = {
    "texture": "loamy",
    "status": "verified",
    "verified_by": "Test Reviewer",
    "verified_on": "2026-10-04",
    "fao56_class": "synthetic",
    "theta_fc": 0.30,
    "theta_wp": 0.10,
    "sources": {"theta": "test"},
}
UNVERIFIED_SOIL = {"texture": "sandy", "status": "unverified"}


def _table(crops=None, soils=None) -> CropWaterTable:
    return CropWaterTable.model_validate({
        "table_version": "test",
        "method": "test",
        "primary_source": "test",
        "crops": [GOOD_CROP] if crops is None else crops,
        "soils": [GOOD_SOIL, UNVERIFIED_SOIL] if soils is None else soils,
    })


def test_shipped_table_loads_and_is_fail_closed():
    table = load_table()
    assert {c.name_en for c in table.crops} >= {"Wheat", "Tomato", "Maize"}
    assert {s.texture for s in table.soils} == {"sandy", "loamy", "clayey"}
    for row in table.crops:
        params, reason = find_crop(table, row.name_en)
        # A row is usable if and only if a human verified it.
        assert (params is not None) == (row.status == "verified")
        assert reason == (None if params else CROP_UNVERIFIED)
    for row in table.soils:
        params, reason = find_soil(table, row.texture)
        assert (params is not None) == (row.status == "verified")
        assert reason == (None if params else SOIL_UNVERIFIED)


def test_verified_row_is_found_case_insensitively_and_typed():
    table = _table()
    params, reason = find_crop(table, "  testCROP ")
    assert reason is None and params is not None
    assert params.name == "Testcrop"
    assert params.stage_days.total == 70
    soil, reason = find_soil(table, "loamy")
    assert reason is None and soil is not None and soil.theta_fc == 0.30


@pytest.mark.parametrize("name", ["Rice (Paddy)", "", None, "sugarcane"])
def test_unknown_crop_is_not_supported(name):
    assert find_crop(_table(), name) == (None, CROP_NOT_SUPPORTED)


def test_unverified_and_missing_soil_give_distinct_reasons():
    table = _table()
    assert find_soil(table, "sandy") == (None, SOIL_UNVERIFIED)
    assert find_soil(table, "clayey") == (None, SOIL_MISSING)  # not in this table
    assert find_soil(table, None) == (None, SOIL_MISSING)


@pytest.mark.parametrize(
    "change",
    [
        {"kc_end": None},  # missing value
        {"stage_days": None},
        {"verified_by": None},
        {"verified_by": "  "},
        {"verified_on": None},
        {"sources": {"kc": "x", "stage_days": "x", "root_depth_m": "x"}},  # no source for p
        {"stage_length_basis": ""},
        {"p": 1.2},  # out of range
        {"p": 0.0},
        {"kc_mid": 0.3},  # peak below kc_ini: ADR-0012 sanity check
        {"kc_end": 1.5},  # end above the mid-season peak
        {"kc_ini": 2.5, "kc_mid": 2.6},  # implausible coefficient
        {"root_depth_m": 0},
        {"stage_days": {"initial": 0, "development": 20, "mid": 30, "late": 10}},
    ],
)
def test_bad_verified_crop_row_does_not_load(change):
    with pytest.raises(ValidationError):
        _table(crops=[{**GOOD_CROP, **change}])


@pytest.mark.parametrize(
    "change",
    [
        {"theta_fc": None},
        {"theta_fc": 0.10, "theta_wp": 0.30},  # field capacity below wilting point
        {"theta_fc": 0.20, "theta_wp": 0.20},
        {"theta_fc": 0.9},
        {"sources": {}},
        {"verified_by": ""},
    ],
)
def test_bad_verified_soil_row_does_not_load(change):
    with pytest.raises(ValidationError):
        _table(soils=[{**GOOD_SOIL, **change}])


def test_unverified_row_may_be_blank():
    table = _table(crops=[{"name_en": "Blank", "status": "unverified"}])
    assert find_crop(table, "blank") == (None, CROP_UNVERIFIED)


def test_duplicate_rows_are_rejected():
    with pytest.raises(ValidationError):
        _table(crops=[GOOD_CROP, {**GOOD_CROP, "name_en": "TESTCROP"}])
    with pytest.raises(ValidationError):
        _table(soils=[GOOD_SOIL, GOOD_SOIL])


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        _table(crops=[{**GOOD_CROP, "kc_mid_adjusted": 1.1}])


def test_load_table_wraps_every_failure_in_crop_table_error(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises(CropTableError):
        load_table(missing)
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    with pytest.raises(CropTableError):
        load_table(bad_json)
    bad_row = tmp_path / "bad_row.json"
    bad_row.write_text(json.dumps({
        "table_version": "t", "method": "t", "primary_source": "t",
        "crops": [{**GOOD_CROP, "p": 5}], "soils": [],
    }), encoding="utf-8")
    with pytest.raises(CropTableError):
        load_table(bad_row)


def test_get_table_is_cached_per_path(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({
        "table_version": "t", "method": "t", "primary_source": "t",
        "crops": [GOOD_CROP], "soils": [GOOD_SOIL],
    }), encoding="utf-8")
    crop_water._cached_table.cache_clear()
    assert crop_water.get_table(path) is crop_water.get_table(path)
