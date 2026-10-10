"""The quality gate (app/vision/quality.py): synthetic photos only."""
import json

import numpy as np
import pytest

from app.vision import quality

from ._images import blurred, flat, gray_wall, leaf_like, scaled


@pytest.fixture(autouse=True)
def _builtin_thresholds(monkeypatch, tmp_path):
    """These tests are about the gate's logic against the built-in defaults, not about the shipped, measured file
    (data/vision/quality-thresholds-v1.json), which has its own consistency test below."""
    monkeypatch.setattr(quality, "DEFAULT_PATH", tmp_path / "none.json")


def test_the_shipped_thresholds_load_and_say_where_they_came_from(monkeypatch):
    monkeypatch.undo()
    t = quality.load_thresholds()
    assert t.version.startswith("quality-v1-") and t.min_side_px == 224
    data = json.loads(quality.DEFAULT_PATH.read_text(encoding="utf-8"))
    assert "PlantDoc" in data["derived_from"] and data["generated_by"] == "evals/vision/vquality.py"


def test_a_sharp_well_exposed_leaf_passes():
    report = quality.assess(leaf_like(640, 480))
    assert report.passed and report.reasons == ()
    assert report.thresholds_version == "builtin-default"


def test_a_blurry_photo_is_too_blurry():
    sharp = quality.measure(leaf_like(640, 480))
    soft = quality.measure(blurred(leaf_like(640, 480), radius=8))
    assert soft.sharpness < sharp.sharpness / 10
    assert quality.TOO_BLURRY in quality.assess(blurred(leaf_like(640, 480), radius=8)).reasons


def test_sharpness_does_not_depend_on_photo_size():
    # The same scene photographed at two resolutions must not fall on different sides of the line.
    small = quality.measure(leaf_like(512, 384, seed=3))
    large = quality.measure(np.kron(leaf_like(512, 384, seed=3), np.ones((2, 2, 1), dtype=np.uint8)))
    assert small.sharpness > 100
    assert large.sharpness == pytest.approx(small.sharpness, rel=0.02)  # analysed at the same 512 px scale


def test_a_dark_photo_is_too_dark():
    report = quality.assess(scaled(leaf_like(640, 480), 0.12))
    assert quality.TOO_DARK in report.reasons and not report.passed


def test_a_washed_out_photo_is_too_bright():
    report = quality.assess(np.clip(leaf_like(640, 480).astype(np.int32) + 170, 0, 255).astype(np.uint8))
    assert quality.TOO_BRIGHT in report.reasons


def test_a_tiny_photo_is_too_small():
    report = quality.assess(leaf_like(160, 120))
    assert quality.TOO_SMALL in report.reasons


def test_a_grey_wall_has_no_vegetation():
    report = quality.assess(gray_wall())
    assert report.reasons == (quality.NO_VEGETATION,)


def test_a_flat_colour_fails_for_sharpness_and_vegetation_both():
    report = quality.assess(flat(640, 480, (128, 128, 128)))
    assert quality.TOO_BLURRY in report.reasons and quality.NO_VEGETATION in report.reasons


def test_a_mostly_brown_diseased_leaf_still_has_enough_green_to_pass():
    img = leaf_like(640, 480)
    brown = img.copy()
    brown[:, : 640 * 3 // 4] = (120, 85, 40)  # three quarters necrotic brown
    brown[:, : 640 * 3 // 4] += np.random.default_rng(0).integers(0, 25, size=(480, 480, 3), dtype=np.uint8)
    report = quality.assess(brown)
    assert quality.NO_VEGETATION not in report.reasons


def test_vegetation_mask_calls_green_and_yellow_green_leaf_and_not_red_blue_or_grey():
    px = np.array([[[40, 160, 50], [150, 170, 40], [200, 40, 40], [40, 60, 200], [128, 128, 128], [0, 0, 0]]], dtype=np.uint8)
    assert quality.vegetation_mask(px).tolist() == [[True, True, False, False, False, False]]


def test_every_failed_check_is_reported_in_a_fixed_order():
    report = quality.assess(flat(100, 100, (5, 5, 5)))
    assert list(report.reasons) == [quality.TOO_SMALL, quality.TOO_BLURRY, quality.TOO_DARK, quality.NO_VEGETATION]


def test_thresholds_load_from_a_file_and_a_malformed_file_is_loud(tmp_path):
    good = tmp_path / "t.json"
    good.write_text(json.dumps({"version": "q-test", "thresholds": {"min_side_px": 300}}), encoding="utf-8")
    assert quality.load_thresholds(good).min_side_px == 300 and quality.load_thresholds(good).version == "q-test"
    assert quality.assess(leaf_like(640, 250), quality.load_thresholds(good)).reasons == (quality.TOO_SMALL,)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        quality.load_thresholds(bad)
    assert quality.load_thresholds(tmp_path / "missing.json").version == "builtin-default"
