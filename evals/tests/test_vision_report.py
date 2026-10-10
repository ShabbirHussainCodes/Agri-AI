"""vreport.compute/render and vquality on SYNTHETIC cached output (no photos, no model)."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "evals" / "vision"))
sys.path.insert(0, str(ROOT / "evals" / "tests"))

import vcache  # noqa: E402
import vquality  # noqa: E402
import vreport  # noqa: E402
from app.vision import quality  # noqa: E402
from test_vision_calibrate import LABEL_MAP, META, N_CLASSES, make_cache  # noqa: E402
import vcalibrate  # noqa: E402


def with_quality(cache: vcache.Cache) -> vcache.Cache:
    rng = np.random.default_rng(2)
    n = len(cache.set)
    q = np.column_stack([np.full(n, 640), np.full(n, 480), rng.uniform(80, 400, n), rng.uniform(70, 160, n),
                         rng.uniform(0, 0.1, n), rng.uniform(0, 0.1, n), rng.uniform(0.2, 0.7, n)])
    degraded = {"blur6": np.column_stack([np.full(50, 640), np.full(50, 480), rng.uniform(1, 10, 50), np.full(50, 110), np.zeros(50), np.zeros(50), np.full(50, 0.4)])}
    return vcache.Cache(**{**cache.__dict__, "quality": q, "degraded": degraded})


def test_test_set_report_on_synthetic_data_is_consistent():
    cal_cache = make_cache()
    cal, _ = vcalibrate.calibrate(cal_cache, LABEL_MAP, model_meta=META, today="2026-10-10")
    # a test cache built the same way, with the *_cal sets renamed to *_test and plantdoc_train photos added as plantdoc_test
    base = make_cache()
    sets = np.array([s.replace("_cal", "_test") if s.endswith("_cal") else s for s in base.set])
    sets_test = np.where(base.set == "plantdoc_train", "plantdoc_test", sets)
    both = vcache.Cache(**{
        **base.__dict__,
        "set": np.concatenate([base.set, sets_test]), "cls": np.concatenate([base.cls, base.cls]),
        "source": np.concatenate([base.source, base.source]), "key": np.concatenate([base.key, base.key]),
        "ok": np.concatenate([base.ok, base.ok]), "logits": np.concatenate([base.logits, base.logits]),
        "features": np.concatenate([base.features, base.features]), "quality": np.zeros((2 * len(base.set), 7)),
        "latency_ms": np.full(2 * len(base.set), 50.0),
    })
    both = with_quality(both)
    t = quality.QualityThresholds(version="synthetic")
    r = vreport.compute(both, LABEL_MAP, cal, t)
    assert r["n_test"] == N_CLASSES * 60
    assert r["top1"][0] > 0.9 and r["top3"][0] >= r["top1"][0] and r["top1"][1] <= r["top1"][0] <= r["top1"][2]
    assert r["ece_after"] <= r["ece_before"] + 0.05
    assert r["operating_point"]["selective_accuracy"] >= 0.9 and r["operating_point"]["coverage"] > 0.9
    assert all(v["rate"] < 0.1 for v in r["false_accept"].values())
    assert set(r["auroc"]) == {"msp", "max_logit", "energy", "feature_cosine"}
    assert set(r["enabled_crops"]["crops"]) == {"tomato", "potato"}
    assert r["quality_gate"]["degraded"]["blur6"]["rejected"] >= 0.0
    text = vreport.render(r, cal, "2026-10-10")
    for needle in ("Headline: cross-domain accuracy", "By crop", "Out-of-distribution", "Quality gate", "Limits of this measurement", "was **not** reproduced"):
        assert needle in text


def test_quality_thresholds_reject_about_the_budgeted_share_of_real_photos_and_catch_blur():
    rng = np.random.default_rng(4)
    n = 2000
    rows = np.column_stack([np.full(n, 640), np.full(n, 480), rng.lognormal(5.0, 0.6, n), rng.normal(110, 25, n),
                            rng.beta(1, 30, n), rng.beta(1, 30, n), rng.beta(5, 5, n)])
    t = vquality.derive_thresholds(rows, "synthetic")
    report = vquality.gate_report(rows, t)
    assert 0.02 <= report["rejected"] <= 0.07, "a union of a 2% blur budget and four 1% budgets"
    assert 0.015 <= report["by_check"][quality.TOO_BLURRY] <= 0.025
    blurry = rows.copy(); blurry[:, 2] = 3.0
    assert vquality.gate_report(blurry, t)["by_check"][quality.TOO_BLURRY] == 1.0
    assert t.min_side_px == 224 and t.version == "synthetic"
