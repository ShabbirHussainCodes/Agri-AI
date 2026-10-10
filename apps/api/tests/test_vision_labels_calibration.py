"""The label map and the calibration file (app/vision/labels.py, calibration.py): data integrity and
fail-closed behaviour. The shipped files are read as they are."""
import json

import pytest

from app.vision import calibration as cal
from app.vision import labels

from ._vision_fixtures import make_calibration


def test_the_shipped_label_map_is_the_38_classes_in_the_models_order():
    lm = labels.load_label_map()
    assert len(lm.labels) == 38
    assert lm.by_index(29).label == "Tomato___Early_blight" and lm.by_index(37).label == "Tomato___healthy"
    assert lm.by_index(20).label == "Potato___Early_blight"


def test_every_label_has_both_names_and_the_hindi_is_marked_unreviewed():
    for lab in labels.load_label_map().labels:
        assert lab.name_en.strip() and lab.name_hi.strip()
        assert lab.name_hi_status == "unreviewed", lab.label  # flipped only by a Hindi reader (CLAUDE.md section 6)


def test_agriai_knows_only_some_of_the_models_crops():
    lm = labels.load_label_map()
    known = {lab.crop for lab in lm.labels if lab.crop_known_to_agriai}
    assert known == {"tomato", "potato", "maize", "soybean", "citrus"}
    assert not any(lab.crop_known_to_agriai for lab in lm.labels if lab.crop in {"apple", "grape", "peach"})


def test_the_label_lookup_pests_are_only_the_ones_the_table_names():
    pests = {lab.pest_for_label_lookup for lab in labels.load_label_map().labels if lab.pest_for_label_lookup}
    assert pests == {"early blight", "late blight"}


def test_a_label_map_with_a_gap_or_a_duplicate_is_refused(tmp_path):
    data = json.loads(labels.DEFAULT_PATH.read_text(encoding="utf-8"))
    broken = {**data, "labels": [lab for lab in data["labels"] if lab["index"] != 5]}
    p = tmp_path / "gap.json"
    p.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(labels.LabelMapError):
        labels.load_label_map(p)
    dup = {**data, "labels": [*data["labels"][:-1], {**data["labels"][-1], "label": data["labels"][0]["label"]}]}
    p2 = tmp_path / "dup.json"
    p2.write_text(json.dumps(dup), encoding="utf-8")
    with pytest.raises(labels.LabelMapError):
        labels.load_label_map(p2)
    with pytest.raises(labels.LabelMapError):
        labels.load_label_map(tmp_path / "missing.json")


def test_bands_are_looked_up_by_calibrated_probability():
    c = make_calibration()
    assert c.band_for(0.99).name == "high" and c.band_for(0.9).name == "high"
    assert c.band_for(0.89).name == "medium" and c.band_for(0.7).name == "medium"
    assert c.band_for(0.69).name == "low" and c.band_for(0.0).name == "low"


def test_a_calibration_with_misordered_bands_is_refused():
    base = make_calibration().model_dump()
    base["bands"] = list(reversed(base["bands"]))
    with pytest.raises(ValueError):
        cal.Calibration.model_validate(base)


def test_feature_cosine_without_centroids_is_refused():
    base = make_calibration().model_dump()
    base["ood"] = {"score": "feature_cosine", "threshold": 0.5, "centroids": None}
    with pytest.raises(ValueError):
        cal.Calibration.model_validate(base)


def test_crop_enablement_is_per_crop_and_missing_means_off():
    c = make_calibration(enabled_crops=("tomato",))
    assert c.crop_enabled("tomato") and not c.crop_enabled("potato") and not c.crop_enabled("wheat")


def test_a_missing_or_malformed_file_raises_instead_of_looking_uncalibrated(tmp_path):
    with pytest.raises(cal.CalibrationError):
        cal.load_calibration(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text('{"version": "x"}', encoding="utf-8")
    with pytest.raises(cal.CalibrationError):
        cal.load_calibration(bad)


def test_the_shipped_calibration_file_is_valid_whatever_its_status():
    """Until the evaluation has run, the shipped file says `uncalibrated` and no photo is ever diagnosed.
    Once it says `calibrated` it must be internally consistent and name the model's hash."""
    c = cal.load_calibration()
    assert c.status in ("calibrated", "uncalibrated")
    if c.status == "calibrated":
        assert len(c.model["sha256"]) == 64 and c.report
        assert set(c.crops) <= {lab.crop for lab in labels.load_label_map().labels}


def test_the_label_map_is_the_models_own_class_order():
    """The classifier's output index i must mean the label map's label i. The manifest records the model's own id2label
    (written when the pinned file was fetched), so a re-exported model with another order fails here, not in a field."""
    from app.vision import fetch_model

    manifest = fetch_model.read_manifest()
    lm = labels.load_label_map()
    assert len(manifest["id2label"]) == len(lm.labels)
    for lab in lm.labels:
        assert manifest["id2label"][str(lab.index)] == lab.label
