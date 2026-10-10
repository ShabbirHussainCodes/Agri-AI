"""README.md P9: derive the quality gate's thresholds from REAL field photos, then measure the gate.

`derive_thresholds` sets each limit at a percentile of the PlantDoc-train measurements, so a stated small share of
real field photos is rejected by each check (blur 2 %, the rest 1 % each; the size floor is fixed at 224 px
because the classifier crops 224). `gate_report` applies thresholds to any set of cached measurements.
Writes data/vision/quality-thresholds-v1.json. The test set and the degraded copies are only measured, never used
to choose anything.

    python ../../evals/vision/vquality.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(HERE))

import vcache  # noqa: E402
from vlabels import ID_CALIBRATION, ID_TEST, OOD_TEST  # noqa: E402

from app.vision import quality  # noqa: E402

OUT = ROOT / "data" / "vision" / "quality-thresholds-v1.json"
BLUR_BUDGET, OTHER_BUDGET = 2.0, 1.0  # percent of real field photos each check may reject
MIN_SIDE = 224


def derive_thresholds(rows: np.ndarray, version: str) -> quality.QualityThresholds:
    c = lambda name: vcache.col(rows, name)  # noqa: E731
    return quality.QualityThresholds(
        version=version,
        min_side_px=MIN_SIDE,
        min_sharpness=float(np.percentile(c("sharpness"), BLUR_BUDGET)),
        min_mean_luma=float(np.percentile(c("mean_luma"), OTHER_BUDGET)),
        max_mean_luma=float(np.percentile(c("mean_luma"), 100 - OTHER_BUDGET)),
        max_dark_fraction=float(np.percentile(c("dark_fraction"), 100 - OTHER_BUDGET)),
        max_bright_fraction=float(np.percentile(c("bright_fraction"), 100 - OTHER_BUDGET)),
        min_vegetation_fraction=float(np.percentile(c("vegetation_fraction"), OTHER_BUDGET)),
    )


def metrics_of(row: np.ndarray) -> quality.QualityMetrics:
    return quality.QualityMetrics(
        width=int(row[0]), height=int(row[1]), sharpness=float(row[2]), mean_luma=float(row[3]),
        dark_fraction=float(row[4]), bright_fraction=float(row[5]), vegetation_fraction=float(row[6]),
    )


def gate_report(rows: np.ndarray, t: quality.QualityThresholds) -> dict:
    """Share of photos rejected overall and by each check (a photo can fail several)."""
    n = len(rows)
    reasons = [quality.reasons_for(metrics_of(r), t) for r in rows]
    by = {k: sum(k in r for r in reasons) / n for k in (quality.TOO_SMALL, quality.TOO_BLURRY, quality.TOO_DARK, quality.TOO_BRIGHT, quality.NO_VEGETATION)}
    return {"n": n, "rejected": sum(bool(r) for r in reasons) / n, "by_check": by}


def gate_numbers(cache: vcache.Cache, t: quality.QualityThresholds) -> dict:
    out = {"thresholds": t.__dict__, "train": gate_report(cache.quality[cache.mask(ID_CALIBRATION)], t),
           "test": gate_report(cache.quality[cache.mask(ID_TEST)], t), "ood_test": {}, "degraded": {}}
    for name in OOD_TEST:
        out["ood_test"][name] = gate_report(cache.quality[cache.mask(name)], t)
    for kind, rows in cache.degraded.items():
        out["degraded"][kind] = gate_report(rows, t)
    return out


def main() -> None:
    cache = vcache.load(HERE / "_runs" / "features.npz")
    train = cache.quality[cache.mask(ID_CALIBRATION)]
    t = derive_thresholds(train, version=f"quality-v1-{date.today().isoformat()}")
    OUT.write_text(json.dumps({
        "version": t.version,
        "thresholds": {k: v for k, v in t.__dict__.items() if k != "version"},
        "derived_from": f"percentiles of {len(train)} PlantDoc train photos (CC-BY-4.0): blur {BLUR_BUDGET}%, others {OTHER_BUDGET}% each; min side fixed at {MIN_SIDE}px",
        "generated_by": "evals/vision/vquality.py",
        "date": date.today().isoformat(),
    }, indent=1) + "\n", encoding="utf-8")
    numbers = gate_numbers(cache, t)
    (HERE / "_runs" / "quality-details.json").write_text(json.dumps(numbers, indent=1), encoding="utf-8")
    print(json.dumps({"train_rejected": numbers["train"]["rejected"], "test_rejected": numbers["test"]["rejected"],
                      "degraded": {k: round(v["rejected"], 3) for k, v in numbers["degraded"].items()}}, indent=1))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
