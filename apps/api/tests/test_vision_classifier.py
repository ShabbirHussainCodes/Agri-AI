"""The classifier wrapper (app/vision/classifier.py) with a fake backend: no model file needed."""
import hashlib

import numpy as np
import pytest
from PIL import Image

from app.vision import classifier as C

from ._images import leaf_like
from ._vision_fixtures import (
    LABELS,
    TOMATO_EARLY,
    TOMATO_LATE,
    FakeBackend,
    logits_for,
    make_calibration,
)


def test_preprocess_shape_dtype_and_range():
    batch = C.preprocess(leaf_like(640, 480))
    assert batch.shape == (1, 3, 224, 224) and batch.dtype == np.float32
    assert batch.flags["C_CONTIGUOUS"]
    assert -2.2 < batch.min() and batch.max() < 2.7  # ImageNet-normalised


def test_preprocess_is_resize_shorter_side_to_256_then_centre_crop_224():
    # A 512x256 image whose left half is black and right half white: after resize (shorter side 256 -> no
    # change in height; 512 wide stays 512) the centre crop of width 224 sits across the middle, half and half.
    img = np.zeros((256, 512, 3), dtype=np.uint8)
    img[:, 256:] = 255
    batch = C.preprocess(img)
    black, white = (0 - C.MEAN) / C.STD, (1 - C.MEAN) / C.STD
    left, right = batch[0, :, 112, 10], batch[0, :, 112, 213]
    assert np.allclose(left, black, atol=1e-4) and np.allclose(right, white, atol=1e-4)


def test_preprocess_uses_the_models_own_mean_and_std():
    flat = np.full((300, 300, 3), 128, dtype=np.uint8)
    batch = C.preprocess(flat)
    expected = (128 / 255 - C.MEAN) / C.STD
    assert np.allclose(batch[0, :, 100, 100], expected, atol=1e-4)


def test_preprocess_handles_a_small_photo_by_scaling_up_the_shorter_side():
    assert C.preprocess(leaf_like(100, 60)).shape == (1, 3, 224, 224)


def test_softmax_sums_to_one_and_temperature_flattens_it():
    z = np.array([4.0, 1.0, 0.0])
    p1, p3 = C.softmax(z, 1.0), C.softmax(z, 3.0)
    assert p1.sum() == pytest.approx(1.0) and p3.sum() == pytest.approx(1.0)
    assert p3.max() < p1.max()


def test_ood_scores_by_hand():
    z = np.array([2.0, 0.0, 0.0], dtype=np.float32)
    s = C.ood_scores(z, None, 1.0, None)
    e = np.exp(2) + 2
    assert s["max_logit"] == pytest.approx(2.0)
    assert s["msp"] == pytest.approx(np.exp(2) / e)
    assert s["energy"] == pytest.approx(np.log(e))
    assert "feature_cosine" not in s


def test_feature_cosine_is_the_best_matching_centroid():
    centroids = np.array([[1.0, 0.0], [0.0, 1.0]])
    s = C.ood_scores(np.zeros(2, dtype=np.float32), np.array([3.0, 4.0], dtype=np.float32), 1.0, centroids)
    assert s["feature_cosine"] == pytest.approx(0.8)  # 4/5 against the second centroid


def test_top3_is_ordered_and_uses_the_calibrated_temperature():
    z = logits_for(TOMATO_EARLY, top=6.0, second=TOMATO_LATE, second_value=4.0)
    sharp = C.Classifier(FakeBackend(z), LABELS, make_calibration(temperature=1.0)).predict(leaf_like())
    flat = C.Classifier(FakeBackend(z), LABELS, make_calibration(temperature=4.0)).predict(leaf_like())
    assert [r.index for r in sharp.top][:2] == [TOMATO_EARLY, TOMATO_LATE] and len(sharp.top) == 3
    assert sharp.top[0].probability > flat.top[0].probability  # a higher temperature is less confident
    assert sharp.top[0].probability >= sharp.top[1].probability >= sharp.top[2].probability


def test_in_distribution_is_the_calibrated_threshold_on_the_chosen_score():
    z = logits_for(TOMATO_EARLY, top=8.0)
    inside = C.Classifier(FakeBackend(z), LABELS, make_calibration(ood_score="max_logit", ood_threshold=7.9)).predict(leaf_like())
    outside = C.Classifier(FakeBackend(z), LABELS, make_calibration(ood_score="max_logit", ood_threshold=8.1)).predict(leaf_like())
    assert inside.in_distribution and inside.ood_score == pytest.approx(8.0)
    assert not outside.in_distribution


def test_a_score_exactly_at_the_threshold_is_in_distribution():
    z = logits_for(TOMATO_EARLY, top=8.0)
    at = C.Classifier(FakeBackend(z), LABELS, make_calibration(ood_score="max_logit", ood_threshold=8.0)).predict(leaf_like())
    assert at.in_distribution  # the threshold is inclusive, the same convention as the calibration that chose it


def test_the_wrong_number_of_classes_is_a_mismatch():
    with pytest.raises(C.ModelMismatch):
        C.Classifier(FakeBackend(np.zeros(10)), LABELS, make_calibration()).predict(leaf_like())


def test_a_score_the_backend_cannot_compute_is_a_mismatch():
    cal = make_calibration()
    cal = cal.model_copy(update={"ood": cal.ood.model_copy(update={"score": "feature_cosine", "centroids": [[1.0, 0.0]]})})
    with pytest.raises(C.ModelMismatch):
        C.Classifier(FakeBackend(logits_for(TOMATO_EARLY)), LABELS, cal).predict(leaf_like())  # no features given


def test_the_model_file_must_be_the_one_the_calibration_was_measured_for(tmp_path):
    path = tmp_path / "m.onnx"
    path.write_bytes(b"not a model")
    with pytest.raises(C.ModelMismatch):
        C.load_classifier(path, LABELS, make_calibration(sha256="f" * 64))
    with pytest.raises(C.ModelMismatch):
        C.load_classifier(path, LABELS, make_calibration(sha256=""))
    assert C.file_sha256(path) == hashlib.sha256(b"not a model").hexdigest()


def test_the_backend_receives_the_preprocessed_batch():
    backend = FakeBackend(logits_for(TOMATO_EARLY))
    C.Classifier(backend, LABELS, make_calibration()).predict(leaf_like())
    assert backend.batches[0].shape == (1, 3, 224, 224)
