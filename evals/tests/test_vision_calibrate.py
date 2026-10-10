"""vcalibrate.calibrate on SYNTHETIC cached output: the algorithm is verified before any real photo exists."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "evals" / "vision"))

import vcache  # noqa: E402
import vcalibrate as V  # noqa: E402

N_CLASSES, DIM = 6, 16
LABEL_MAP = {
    "labels": [
        {"index": i, "label": f"{crop}___{cond}", "crop": crop}
        for i, (crop, cond) in enumerate([("tomato", "a"), ("tomato", "b"), ("tomato", "healthy"), ("potato", "a"), ("potato", "healthy"), ("apple", "scab")])
    ],
    "known_crops": ["tomato", "potato"],
}
CLASS_NAMES = [lab["label"] for lab in LABEL_MAP["labels"]]
RNG = np.random.default_rng(0)
PROTOTYPES = RNG.normal(0, 1, (N_CLASSES, DIM))


def id_photo(c: int, noise: float, strength: float = 6.0):
    feat = PROTOTYPES[c] + RNG.normal(0, noise, DIM)
    logits = RNG.normal(0, 0.5, N_CLASSES)
    logits[c] += strength
    return logits, feat


def ood_photo():
    return RNG.normal(0, 0.7, N_CLASSES), RNG.normal(0, 1.5, DIM)  # flat logits, features far from every prototype


def make_cache(*, wrong_tomato: float = 0.0, n_per_class: int = 60, n_ood: int = 120, potato_per_class: int | None = None) -> vcache.Cache:
    rows = {"set": [], "cls": [], "logits": [], "features": []}
    for c in range(N_CLASSES):
        count = potato_per_class if (potato_per_class is not None and 3 <= c <= 4) else n_per_class
        for _ in range(count):
            truth = c
            # tomato photos are sometimes misclassified as the neighbouring tomato class (a weak crop)
            shown = (c + 1) % 3 if (c < 3 and RNG.random() < wrong_tomato) else c
            logits, feat = id_photo(shown, 0.3)
            rows["set"].append("plantdoc_train"); rows["cls"].append(CLASS_NAMES[truth])
            rows["logits"].append(logits); rows["features"].append(feat)
    for name in V.OOD_CALIBRATION:
        for _ in range(n_ood):
            logits, feat = ood_photo()
            rows["set"].append(name); rows["cls"].append(""); rows["logits"].append(logits); rows["features"].append(feat)
    n = len(rows["set"])
    return vcache.Cache(
        key=np.array([f"k{i}" for i in range(n)]), set=np.array(rows["set"]), cls=np.array(rows["cls"]), source=np.array([""] * n),
        ok=np.ones(n, bool), logits=np.array(rows["logits"], np.float32), features=np.array(rows["features"], np.float32),
        quality=np.zeros((n, 7)), latency_ms=np.zeros(n), model_sha256="ab" * 32, test_duplicates_removed=0, degraded={},
    )


META = {"repo": "r", "revision": "rev", "file": "f.onnx", "sha256": "ab" * 32}


def run(cache):
    return V.calibrate(cache, LABEL_MAP, model_meta=META, today="2026-10-10")


def test_a_clean_problem_calibrates_enables_the_known_crops_and_not_the_unknown_one():
    cal, details = run(make_cache())
    assert cal["status"] == "calibrated" and details["target_met"]
    assert details["selective_accuracy"] >= 0.80 and details["coverage"] > 0.9
    assert cal["crops"]["tomato"]["enabled"] and cal["crops"]["potato"]["enabled"]
    assert not cal["crops"]["apple"]["enabled"] and "not a crop AgriAI has" in cal["crops"]["apple"]["reason"]
    assert all(f < 0.1 for f in details["false_accept"].values())


def test_every_candidate_score_is_scored_and_one_is_chosen_by_mean_auroc():
    _, details = run(make_cache())
    assert set(details["mean_auroc"]) == {"msp", "max_logit", "energy", "feature_cosine"}
    assert details["chosen_score"] == max(details["mean_auroc"], key=details["mean_auroc"].get)
    assert all(v > 0.9 for v in details["mean_auroc"].values())


def test_the_output_is_a_valid_runtime_calibration():
    from app.vision.calibration import Calibration

    cal, _ = run(make_cache())
    parsed = Calibration.model_validate(cal)
    assert parsed.status == "calibrated" and [b.name for b in parsed.bands] == ["high", "medium", "low"]
    assert parsed.band_for(0.95).name == "high" and parsed.crop_enabled("tomato")


def test_centroids_are_shipped_only_when_the_chosen_score_needs_them(monkeypatch):
    cal, details = run(make_cache())
    assert (cal["ood"]["centroids"] is not None) == (details["chosen_score"] == "feature_cosine")
    forced_cache = make_cache()
    monkeypatch.setattr(V, "SCORE_NAMES", ("feature_cosine",))
    cal2, details2 = V.calibrate(forced_cache, LABEL_MAP, model_meta=META, today="2026-10-10")
    assert details2["chosen_score"] == "feature_cosine" and len(cal2["ood"]["centroids"]) == N_CLASSES


def test_a_crop_with_too_few_accepted_photos_is_disabled_with_the_count_in_the_reason():
    cache = make_cache(n_per_class=10)  # 20 potato photos only
    cal, _ = run(cache)
    assert not cal["crops"]["potato"]["enabled"] and "need 25" in cal["crops"]["potato"]["reason"]


def test_a_crop_below_the_accuracy_bar_is_disabled_even_when_the_overall_target_is_met():
    # Plenty of easy potato photos keep the overall selective accuracy above 0.80, so tomato (65 % right) is
    # accepted in volume and fails the per-crop bar on its own.
    cal, details = run(make_cache(wrong_tomato=0.35, potato_per_class=300))
    assert details["target_met"]
    assert not cal["crops"]["tomato"]["enabled"] and "below 0.80" in cal["crops"]["tomato"]["reason"]
    assert cal["crops"]["potato"]["enabled"]


def test_a_crop_that_cannot_be_trusted_is_never_enabled_whatever_the_reason():
    cal, _ = run(make_cache(wrong_tomato=0.6))
    assert not cal["crops"]["tomato"]["enabled"]


def test_overconfident_logits_get_a_temperature_above_one():
    cache = make_cache(wrong_tomato=0.3)
    cal, _ = run(cache)
    assert cal["temperature"] > 1.0


def test_bands_report_what_was_observed_and_how_many():
    cal, details = run(make_cache())
    bands = {b["name"]: b for b in cal["bands"]}
    assert bands["high"]["n"] + bands["medium"]["n"] + bands["low"]["n"] == int(round(details["coverage"] * details["n_id_calibration"]))
    assert bands["high"]["observed_accuracy"] >= 0.9


def test_test_sets_are_never_read_and_an_empty_calibration_set_is_an_error():
    cache = make_cache()
    renamed = vcache.Cache(**{**cache.__dict__, "set": np.where(cache.set == "rice_cal", "rice_test", cache.set)})
    with pytest.raises(ValueError, match="rice_cal"):
        V.calibrate(renamed, LABEL_MAP, model_meta=META, today="2026-10-10")
    no_id = vcache.Cache(**{**cache.__dict__, "set": np.where(cache.set == "plantdoc_train", "plantdoc_test", cache.set)})
    with pytest.raises(ValueError, match="plantdoc_train"):
        V.calibrate(no_id, LABEL_MAP, model_meta=META, today="2026-10-10")
