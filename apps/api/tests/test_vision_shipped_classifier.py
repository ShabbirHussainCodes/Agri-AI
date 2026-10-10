"""The files that ship (data/vision/*) agree with each other, and the real classifier loads and refuses mismatches.

The first group needs no model file. The second runs only where the 24 MB ONNX file has been fetched
(`python -m app.vision.fetch_model`), like the embedder tests."""
import json
import shutil

import numpy as np
import pytest

from app.vision import calibration as cal_mod
from app.vision import classifier as C
from app.vision import fetch_model, head as head_mod, labels, runtime

from ._images import leaf_like

HAS_MODEL = runtime.model_path().exists()


def test_the_shipped_calibration_names_the_pinned_model_and_the_shipped_head():
    cal = cal_mod.load_calibration()
    manifest = fetch_model.read_manifest()
    assert cal.model["repo"] == manifest["repo"] and cal.model["sha256"] == manifest["sha256"]
    if cal.model.get("head_sha256"):
        assert head_mod.file_sha256(head_mod.DEFAULT_PATH) == cal.model["head_sha256"]
        head = head_mod.load_head()
        assert head.meta.backbone_sha256 == manifest["sha256"]
        assert head.n_classes == len(labels.load_label_map().labels)


def test_every_class_the_head_can_name_belongs_to_the_label_map():
    head = head_mod.load_head()
    assert all(0 <= c < len(labels.load_label_map().labels) for c in head.meta.classes)
    assert len(head.meta.classes) >= 20


def test_a_crop_is_enabled_only_with_measured_support_written_beside_it():
    cal = cal_mod.load_calibration()
    for crop, decision in cal.crops.items():
        if decision.enabled:
            assert decision.n_calibration >= 25 and (decision.selective_accuracy or 0) >= 0.80, crop
            assert "accepted calibration photos" in decision.reason


@pytest.mark.skipif(not HAS_MODEL, reason="the classifier file has not been fetched")
def test_the_real_classifier_loads_and_gives_a_top3_for_a_synthetic_photo():
    lm, cal, clf = runtime._load_classifier_parts()
    assert clf is not None and cal.status == "calibrated"
    pred = clf.predict(leaf_like(640, 480))
    assert len(pred.top) == 3 and abs(sum(r.probability for r in pred.top)) <= 1.0 + 1e-9
    assert all(0 <= r.index < len(lm.labels) for r in pred.top)
    assert set(pred.scores) >= {"msp", "max_logit", "energy"}


@pytest.mark.skipif(not HAS_MODEL, reason="the classifier file has not been fetched")
def test_a_tampered_head_is_refused(tmp_path):
    lm, cal = labels.load_label_map(), cal_mod.load_calibration()
    if not cal.model.get("head_sha256"):
        pytest.skip("shipped calibration uses the backbone's own head")
    body = json.loads(head_mod.DEFAULT_PATH.read_text(encoding="utf-8"))
    body["bias"][0] += 1.0
    tampered = tmp_path / "head.json"
    tampered.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(C.ModelMismatch, match="head file"):
        C.load_classifier(runtime.model_path(), lm, cal, head_path=tampered)


@pytest.mark.skipif(not HAS_MODEL, reason="the classifier file has not been fetched")
def test_a_head_trained_on_another_backbone_is_refused_even_if_its_hash_was_listed(tmp_path):
    lm, cal = labels.load_label_map(), cal_mod.load_calibration()
    if not cal.model.get("head_sha256"):
        pytest.skip("shipped calibration uses the backbone's own head")
    body = json.loads(head_mod.DEFAULT_PATH.read_text(encoding="utf-8"))
    body["backbone_sha256"] = "0" * 64
    other = tmp_path / "head.json"
    other.write_text(json.dumps(body), encoding="utf-8")
    cal2 = cal.model_copy(update={"model": {**cal.model, "head_sha256": head_mod.file_sha256(other)}})
    with pytest.raises(C.ModelMismatch, match="different backbone"):
        C.load_classifier(runtime.model_path(), lm, cal2, head_path=other)
