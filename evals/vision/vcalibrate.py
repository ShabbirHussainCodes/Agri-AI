"""README.md P2 to P7: from the cached classifier output on the CALIBRATION sets to data/vision/calibration-v1.json.

Pure function `calibrate` (tested on synthetic data in evals/tests/test_vision_calibrate.py) plus a thin main.
The test sets are never read here.

    python ../../evals/vision/vcalibrate.py [--model-revision <hf commit>]
"""
import argparse
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
import vmetrics as M  # noqa: E402
from vlabels import ID_CALIBRATION, OOD_CALIBRATION, OOD_NAMES  # noqa: E402

OUT = ROOT / "data" / "vision" / "calibration-v1.json"
DETAILS = HERE / "_runs" / "calibration-details.json"

MIN_PROBABILITY = 0.5            # P5
BAND_FLOORS = [("high", 0.90), ("medium", 0.70)]  # P6; "low" is everything above min_probability
MIN_ACCEPTED_FOR_CROP = 25       # P7(b)
MIN_CROP_ACCURACY = 0.80         # P7(c)
SCORE_NAMES = ("msp", "max_logit", "energy", "feature_cosine")


def unit_rows(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x.astype(np.float64), axis=1, keepdims=True)
    return x / np.where(n == 0, 1.0, n)


def class_centroids(features: np.ndarray, labels: np.ndarray, n_classes: int) -> np.ndarray:
    """Mean unit feature vector per class, re-normalised; a class with no calibration photo gets a zero row
    (it can never be the best match)."""
    out = np.zeros((n_classes, features.shape[1]), dtype=np.float64)
    units = unit_rows(features)
    for c in range(n_classes):
        if (labels == c).any():
            mean = units[labels == c].mean(axis=0)
            out[c] = mean / np.linalg.norm(mean)
    return out


def all_scores(logits: np.ndarray, features: np.ndarray, temperature: float, centroids: np.ndarray) -> dict[str, np.ndarray]:
    probs = M.softmax_rows(logits, temperature)
    z = logits.astype(np.float64)
    zmax = z.max(axis=1)
    return {
        "msp": probs.max(axis=1),
        "max_logit": zmax,
        "energy": zmax + np.log(np.exp(z - zmax[:, None]).sum(axis=1)),
        "feature_cosine": (unit_rows(features) @ centroids.T).max(axis=1),
    }


def effective(score: np.ndarray, top_probability: np.ndarray) -> np.ndarray:
    """A photo is accepted only if BOTH the OOD score passes and the calibrated top-1 probability is at least
    MIN_PROBABILITY (the runtime does the same, app/vision/decision.py), so a photo below it is scored -inf."""
    return np.where(top_probability >= MIN_PROBABILITY, score, -np.inf)


def calibrate(
    cache: vcache.Cache, label_map: dict, *, model_meta: dict, today: str, report_path: str = "",
    centroid_set: str = ID_CALIBRATION, calibrated_on: str | None = None,
) -> tuple[dict, dict]:
    labels = label_map["labels"]
    class_index = {lab["label"]: lab["index"] for lab in labels}
    crop_of = {lab["index"]: lab["crop"] for lab in labels}
    known = set(label_map["known_crops"])
    n_classes = len(labels)

    for required in (ID_CALIBRATION, *OOD_CALIBRATION):
        if not cache.mask(required).any():
            raise ValueError(f"no calibration photos in set {required!r}: nothing to calibrate on")
    id_mask = cache.mask(ID_CALIBRATION)
    y = cache.labels(id_mask, class_index)
    id_logits, id_features = cache.logits[id_mask], cache.features[id_mask]

    temperature = M.fit_temperature(id_logits, y)
    cm = cache.mask(centroid_set)
    centroids = class_centroids(cache.features[cm], cache.labels(cm, class_index), n_classes)
    id_scores = all_scores(id_logits, id_features, temperature, centroids)
    id_probs = M.softmax_rows(id_logits, temperature)
    id_top_p = id_probs.max(axis=1)
    id_correct = (id_probs.argmax(axis=1) == y).astype(np.float64)

    ood = {}
    for name in OOD_CALIBRATION:
        m = cache.mask(name)
        probs = M.softmax_rows(cache.logits[m], temperature)
        ood[name] = (all_scores(cache.logits[m], cache.features[m], temperature, centroids), probs.max(axis=1))

    auroc = {s: {n: M.auroc(effective(id_scores[s], id_top_p), effective(ood[n][0][s], ood[n][1])) for n in OOD_CALIBRATION} for s in SCORE_NAMES}
    mean_auroc = {s: float(np.mean(list(auroc[s].values()))) for s in SCORE_NAMES}
    chosen = max(SCORE_NAMES, key=lambda s: mean_auroc[s])

    id_eff = effective(id_scores[chosen], id_top_p)
    ood_pooled = np.concatenate([effective(ood[n][0][chosen], ood[n][1]) for n in OOD_CALIBRATION])
    tau, target_met = M.choose_threshold(id_eff, id_correct, ood_pooled)
    accepted = id_eff >= tau
    coverage, selective = M.coverage_and_selective_accuracy(id_eff, id_correct, tau)

    bands = []
    upper = 1.0 + 1e-9
    for name, floor in [*BAND_FLOORS, ("low", MIN_PROBABILITY)]:
        mask = accepted & (id_top_p >= floor) & (id_top_p < upper)
        bands.append({"name": name, "min_probability": floor, "observed_accuracy": float(id_correct[mask].mean()) if mask.any() else 0.0, "n": int(mask.sum())})
        upper = floor

    crops = {}
    pred = id_probs.argmax(axis=1)
    for crop in sorted({lab["crop"] for lab in labels}):
        of_crop = np.array([crop_of[int(c)] == crop for c in y])
        sel = accepted & of_crop
        n_acc, acc = int(sel.sum()), (float(id_correct[sel].mean()) if sel.any() else None)
        if crop not in known:
            enabled, reason = False, "not a crop AgriAI has (app/safety/crop_scope.py)"
        elif n_acc < MIN_ACCEPTED_FOR_CROP:
            enabled, reason = False, f"only {n_acc} calibration photos accepted (need {MIN_ACCEPTED_FOR_CROP}); {int(of_crop.sum())} available"
        elif acc < MIN_CROP_ACCURACY:
            enabled, reason = False, f"accepted-photo accuracy {acc:.2f} below {MIN_CROP_ACCURACY:.2f}"
        else:
            enabled, reason = True, f"{n_acc} accepted calibration photos, accuracy {acc:.2f}"
        crops[crop] = {"enabled": enabled, "n_calibration": n_acc, "selective_accuracy": None if acc is None else round(acc, 4), "reason": reason}

    far = {n: float(M.false_accept_rate(effective(ood[n][0][chosen], ood[n][1]), tau)) for n in OOD_CALIBRATION}
    calibration = {
        "version": "calibration-v1",
        "status": "calibrated",
        "model": model_meta,
        "temperature": round(temperature, 4),
        "ood": {
            "score": chosen,
            "threshold": float(tau),
            "centroids": [[round(float(v), 6) for v in row] for row in centroids] if chosen == "feature_cosine" else None,
        },
        "min_probability": MIN_PROBABILITY,
        "bands": [{**b, "observed_accuracy": round(b["observed_accuracy"], 4)} for b in bands],
        "crops": crops,
        "calibrated_on": calibrated_on or (
            f"PlantDoc train photos (CC-BY-4.0; web-scraped field photos): {int(id_mask.sum())} photos for accuracy and "
            f"confidence, with rice, bean and object photos as out-of-distribution examples. Not Indian smallholder photos."
        ),
        "generated_by": "evals/vision/vcalibrate.py",
        "date": today,
        "report": report_path,
    }
    details = {
        "n_id_calibration": int(id_mask.sum()), "temperature": temperature, "auroc": auroc, "mean_auroc": mean_auroc,
        "chosen_score": chosen, "threshold": float(tau), "target_met": bool(target_met),
        "coverage": coverage, "selective_accuracy": selective,
        "top1_accuracy_all": float((pred == y).mean()), "false_accept": {OOD_NAMES[n] + f" [{n}]": v for n, v in far.items()},
        "n_ood": {n: int(cache.mask(n).sum()) for n in OOD_CALIBRATION},
    }
    return calibration, details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-revision", default="unknown")
    parser.add_argument("--report", default="")
    parser.add_argument("--head", action="store_true", help="candidate 3: the field-trained head (vhead.py) instead of the published one")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    from app.safety.crop_scope import KNOWN_CROPS

    label_map = json.loads((ROOT / "data" / "vision" / "label-map-v1.json").read_text(encoding="utf-8"))
    label_map["known_crops"] = sorted(KNOWN_CROPS)
    cache = vcache.load(HERE / "_runs" / "features.npz")
    meta = {
        "repo": label_map["model"], "revision": args.model_revision,
        "file": "onnx/model_with_features_quantized.onnx", "sha256": cache.model_sha256,
    }
    centroid_set, calibrated_on = ID_CALIBRATION, None
    if args.head:
        import vhead
        from app.vision import head as head_mod

        head_path = ROOT / "data" / "vision" / "head-v1.json"
        head = head_mod.load_head(head_path)
        if head.meta.backbone_sha256 != cache.model_sha256:
            sys.exit("the head was trained on a different backbone file than the cached features")
        split = json.loads((HERE / "_runs" / "head-split.json").read_text(encoding="utf-8"))
        cache = vhead.derive_cache(cache, split, head.logits_batch(cache.features))
        meta = {**meta, "head": "head-v1.json", "head_sha256": head_mod.file_sha256(head_path)}
        centroid_set = vhead.HEAD_TRAIN
        n_cal, n_train = int(cache.mask(ID_CALIBRATION).sum()), int(cache.mask(centroid_set).sum())
        calibrated_on = (
            f"PlantDoc train photos (CC-BY-4.0; web-scraped photos): a linear head trained on {n_train} of them, and "
            f"{n_cal} others held out for accuracy and confidence, with rice, bean and object photos as out-of-distribution "
            f"examples. Not Indian smallholder photos."
        )
    calibration, details = calibrate(
        cache, label_map, model_meta=meta, today=date.today().isoformat(), report_path=args.report,
        centroid_set=centroid_set, calibrated_on=calibrated_on,
    )
    Path(args.out).write_text(json.dumps(calibration, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    DETAILS.write_text(json.dumps(details, indent=1), encoding="utf-8")
    print(json.dumps({k: details[k] for k in ("n_id_calibration", "top1_accuracy_all", "temperature", "chosen_score", "threshold", "target_met", "coverage", "selective_accuracy")}, indent=1))
    print("mean AUROC", {k: round(v, 3) for k, v in details["mean_auroc"].items()}, "false accept", {k: round(v, 3) for k, v in details["false_accept"].items()})
    print({c: (v["enabled"], v["n_calibration"]) for c, v in calibration["crops"].items() if c in ("tomato", "potato", "maize", "soybean")})
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
