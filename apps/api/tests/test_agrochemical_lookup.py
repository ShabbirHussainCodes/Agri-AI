"""The verified label table and card (app/safety/agrochemical_lookup.py, ADR-0016).
Pure tests. All rows are SYNTHETIC ("testmolecule", round numbers): they exercise
the mechanism and say nothing about any real pesticide."""
import json

import pytest
from pydantic import ValidationError

from app.safety import agrochemical_lookup as al
from app.safety import chemical_guard as cg

VERIFIED = {"status": "verified", "verified_by": "Test Reviewer", "verified_on": "2026-10-04"}
ROW = {
    "id": "tomato-blight-001", "molecule": "testmolecule", "molecule_aliases": ["testcide"],
    "formulation": "Testmolecule 50% WP", "crop": "tomato", "pest": "early blight", "pest_aliases": ["अगेती झुलसा"],
    "dose_ai_g_per_ha": 375.0, "dose_formulation": 750.0, "dose_formulation_unit": "g", "dilution_l_per_ha": 500.0,
    "waiting_period_days": 7, "label_date": "2024-03-31", "source_ref": "synthetic test document, p. 1", **VERIFIED,
}
EMPTY_DENYLIST = cg.Denylist.model_validate({"list_version": "t", "scope": "central", "primary_source": "t", "entries": []})


def table(*rows) -> al.AgrochemTable:
    return al.AgrochemTable.model_validate({"table_version": "synthetic-v1", "primary_source": "test", "rows": list(rows)})


def test_the_shipped_table_loads_and_returns_only_its_verified_rows():
    shipped = al.load_table()
    for row in shipped.rows:
        found, _ = al.lookup(shipped, EMPTY_DENYLIST, crop=row.crop, pest=row.pest, molecule=row.molecule)
        assert (row in found) == (row.status == "verified"), row.id
        for alias in row.pest_aliases:  # every alias reaches the same row
            assert (row in al.lookup(shipped, EMPTY_DENYLIST, crop=row.crop, pest=alias)[0]) == (row.status == "verified"), (row.id, alias)


def test_no_shipped_row_names_a_molecule_on_the_shipped_denylist():
    from app.safety import chemical_guard

    denylist = chemical_guard.load_denylist()
    for row in al.load_table().rows:
        assert not chemical_guard.find_banned([row.molecule, *row.molecule_aliases, row.formulation or ""], denylist), row.id


@pytest.mark.parametrize(
    "change",
    [
        {"waiting_period_days": None},  # a dose without its waiting period is never shown
        {"dose_formulation": None},
        {"dose_formulation_unit": None},
        {"formulation": " "},
        {"label_date": None},
        {"source_ref": ""},
        {"verified_by": None},
        {"verified_on": None},
        {"pest": " "},
        {"crop": "unicorn"},  # not a canonical crop key
        {"molecule": "Testmolecule"},  # not lower case
        {"waiting_period_days": -1},
        {"waiting_period_days": 400},
        {"dose_formulation": 0},
        {"dose_formulation_unit": "kg"},
        {"dilution_l_per_ha": -5},
        {"surprise": 1},
    ],
)
def test_a_bad_verified_row_does_not_load(change):
    with pytest.raises(ValidationError):
        table({**ROW, **change})


def test_an_unverified_row_may_be_incomplete_but_is_never_returned():
    t = table({"id": "u1", "molecule": "testmolecule", "crop": "tomato", "pest": "early blight", "status": "unverified"})
    assert al.lookup(t, EMPTY_DENYLIST, crop="tomato", pest="early blight") == ([], al.NO_VERIFIED_ENTRY)


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValidationError):
        table(ROW, ROW)


def test_lookup_matches_crop_pest_aliases_and_molecule_case_insensitively():
    t = table(ROW)
    for kwargs in (
        dict(crop="tomato", pest="Early  Blight"),
        dict(crop="tomato", pest="अगेती झुलसा"),
        dict(crop="tomato", pest="early blight", molecule="TestCide"),
    ):
        rows, reason = al.lookup(t, EMPTY_DENYLIST, **kwargs)
        assert reason is None and [r.id for r in rows] == ["tomato-blight-001"]


@pytest.mark.parametrize(
    "kwargs",
    [dict(crop="wheat", pest="early blight"), dict(crop="tomato", pest="late blight"),
     dict(crop="tomato", pest="early blight", molecule="othermolecule")],
)
def test_lookup_does_not_stretch_to_other_crops_pests_or_molecules(kwargs):
    assert al.lookup(table(ROW), EMPTY_DENYLIST, **kwargs) == ([], al.NO_VERIFIED_ENTRY)


def test_a_banned_molecule_is_never_returned_even_if_a_verified_row_exists():
    banned = cg.Denylist.model_validate({
        "list_version": "t", "scope": "central", "primary_source": "t",
        "entries": [{"molecule": "testmolecule", "aliases": [], "category": "unclassified", "status": "unverified"}],
    })
    assert al.lookup(table(ROW), banned, crop="tomato", pest="early blight") == ([], al.NO_VERIFIED_ENTRY)
    alias_listed = cg.Denylist.model_validate({
        "list_version": "t", "scope": "central", "primary_source": "t",
        "entries": [{"molecule": "other", "aliases": ["testcide"], "category": "unclassified", "status": "unverified"}],
    })
    assert al.lookup(table(ROW), alias_listed, crop="tomato", pest="early blight")[0] == []


def test_the_label_card_is_copied_from_the_row_and_says_what_it_is():
    entry = al.entry_from_row(table(ROW).rows[0], "synthetic-v1")
    assert (entry.dose_formulation, entry.dose_formulation_unit, entry.waiting_period_days) == (750.0, "g", 7)
    assert entry.table_version == "synthetic-v1" and entry.source_ref.startswith("synthetic test document")
    for fragment in ("750 g per hectare", "500 litres of water per hectare", "Waiting period: 7 days",
                     "label on the product pack", "प्रतीक्षा अवधि: 7 दिन", "750 ग्राम प्रति हेक्टेयर", "2024-03-31"):
        assert fragment in entry.text, fragment


def test_a_card_without_the_optional_values_leaves_them_out():
    bare = {k: v for k, v in ROW.items() if k not in ("dose_ai_g_per_ha", "dilution_l_per_ha")}
    entry = al.entry_from_row(table(bare).rows[0], "v")
    assert "active ingredient" not in entry.text and "litres of water" not in entry.text


def test_load_wraps_every_failure(tmp_path):
    with pytest.raises(al.AgrochemTableError):
        al.load_table(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(al.AgrochemTableError):
        al.load_table(bad)
    row_bad = tmp_path / "row.json"
    row_bad.write_text(json.dumps({"table_version": "t", "primary_source": "t", "rows": [{**ROW, "waiting_period_days": None}]}), encoding="utf-8")
    with pytest.raises(al.AgrochemTableError):
        al.load_table(row_bad)
