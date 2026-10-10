"""README.md P8 and P9: the TEST-set report, written to evals/results/vision-<date>.md.

Reads the cached classifier output (vrun.py), the calibration (vcalibrate.py) and the quality thresholds (vquality.py).
`compute` is pure and is unit-tested on synthetic data; `render` turns its dict into the committed markdown. The
test photos are read here for the first time.

    python ../../evals/vision/vreport.py
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
import vmetrics as M  # noqa: E402
import vquality  # noqa: E402
from vcalibrate import MIN_PROBABILITY, SCORE_NAMES, all_scores, class_centroids, effective  # noqa: E402
from vlabels import APPROXIMATE, ID_CALIBRATION, ID_TEST, OOD_NAMES, OOD_TEST  # noqa: E402

RESULTS = ROOT / "evals" / "results"


def ci(values: np.ndarray) -> tuple[float, float, float]:
    lo, hi = M.bootstrap_ci(values)
    return float(values.mean()), lo, hi


def compute(cache: vcache.Cache, label_map: dict, calibration: dict, thresholds, *, centroid_set: str = ID_CALIBRATION, near_duplicate_cosine: float = 0.98) -> dict:
    """Test-set numbers. `centroids` for the feature_cosine score are rebuilt from the CALIBRATION photos (the same way
    vcalibrate built them); if the chosen score is not feature_cosine they are not used."""
    labels = label_map["labels"]
    class_index = {lab["label"]: lab["index"] for lab in labels}
    crop_of = {lab["index"]: lab["crop"] for lab in labels}
    T = calibration["temperature"]
    chosen, tau = calibration["ood"]["score"], calibration["ood"]["threshold"]

    train = cache.mask(centroid_set)
    centroids = class_centroids(cache.features[train], cache.labels(train, class_index), len(labels))

    test = cache.mask(ID_TEST)
    y = cache.labels(test, class_index)
    probs = M.softmax_rows(cache.logits[test], T)
    pred = probs.argmax(axis=1)
    correct = (pred == y).astype(float)
    conf = probs.max(axis=1)
    sources = cache.source[test]
    approx = np.array([s in APPROXIMATE for s in sources])
    crops = np.array([crop_of[int(c)] for c in y])

    raw_probs = M.softmax_rows(cache.logits[test], 1.0)
    out = {
        "n_test": int(test.sum()), "duplicates_removed": cache.test_duplicates_removed, "temperature": T,
        "top1": ci(correct), "top3": ci((np.argsort(-probs, axis=1)[:, :3] == y[:, None]).any(axis=1).astype(float)),
        "top1_macro": M.macro_by_class(correct, y),
        "top1_without_approximate": ci(correct[~approx]) if (~approx).any() else None,
        "ece_before": M.expected_calibration_error(raw_probs.max(axis=1), (raw_probs.argmax(axis=1) == y).astype(float)),
        "ece_after": M.expected_calibration_error(conf, correct),
        "by_crop": {},
        "latency_ms": {"p50": float(np.percentile(cache.latency_ms[cache.ok], 50)), "p95": float(np.percentile(cache.latency_ms[cache.ok], 95))},
    }
    for crop in sorted(set(crops)):
        m = crops == crop
        out["by_crop"][crop] = {"n": int(m.sum()), "top1": float(correct[m].mean()), "top3": float((np.argsort(-probs[m], axis=1)[:, :3] == y[m][:, None]).any(axis=1).mean())}

    # Near-duplicate sensitivity (README A2): a test photo whose features are >= 0.98 cosine to ANY PlantDoc train photo.
    from vcalibrate import unit_rows

    train_all = np.isin(cache.set, ["plantdoc_train", "plantdoc_headtrain", "plantdoc_dropped"]) & cache.ok
    nearest = (unit_rows(cache.features[test]) @ unit_rows(cache.features[train_all]).T).max(axis=1)
    near = nearest >= near_duplicate_cosine
    out["near_duplicates"] = {"flagged": int(near.sum()), "top1_without": float(correct[~near].mean()) if (~near).any() else None,
                              "top1_flagged": float(correct[near].mean()) if near.any() else None}

    scores = all_scores(cache.logits[test], cache.features[test], T, centroids)
    eff = effective(scores[chosen], conf)
    cov, sel = M.coverage_and_selective_accuracy(eff, correct, tau)
    out["operating_point"] = {"score": chosen, "threshold": tau, "coverage": cov, "selective_accuracy": sel,
                              "accepted_n": int((eff >= tau).sum())}
    enabled = {c for c, d in calibration["crops"].items() if d["enabled"]}
    in_enabled = np.array([c in enabled for c in crops])
    acc_enabled = (eff >= tau) & in_enabled
    out["enabled_crops"] = {"crops": sorted(enabled), "accepted_n": int(acc_enabled.sum()),
                            "selective_accuracy": float(correct[acc_enabled].mean()) if acc_enabled.any() else None,
                            "share_of_test_photos_of_these_crops": float(acc_enabled.sum() / in_enabled.sum()) if in_enabled.any() else None}
    out["accepted_by_crop"] = {c: {"accepted": int(((eff >= tau) & (crops == c)).sum()), "of": int((crops == c).sum()),
                                   "accuracy": float(correct[(eff >= tau) & (crops == c)].mean()) if ((eff >= tau) & (crops == c)).any() else None}
                               for c in sorted(set(crops))}

    out["auroc"] = {}
    out["false_accept"] = {}
    for name in OOD_TEST:
        m = cache.mask(name)
        o_scores = all_scores(cache.logits[m], cache.features[m], T, centroids)
        o_conf = M.softmax_rows(cache.logits[m], T).max(axis=1)
        out["false_accept"][name] = {"n": int(m.sum()), "rate": M.false_accept_rate(effective(o_scores[chosen], o_conf), tau)}
        for s in SCORE_NAMES:
            out["auroc"].setdefault(s, {})[name] = M.auroc(effective(scores[s], conf), effective(o_scores[s], o_conf))

    floors = [b["min_probability"] for b in calibration["bands"]]
    out["bands"] = [{"name": b["name"], "calibration_accuracy": b["observed_accuracy"], "calibration_n": b["n"], **r}
                    for b, r in zip(calibration["bands"], M.reliability(conf[eff >= tau], correct[eff >= tau], floors))]
    out["quality_gate"] = vquality.gate_numbers(cache, thresholds)
    return out


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def with_ci(t: tuple[float, float, float]) -> str:
    return f"{pct(t[0])} (95% interval {pct(t[1])} to {pct(t[2])})"


def render(r: dict, calibration: dict, today: str, baseline: tuple[dict, dict] | None = None) -> str:
    op, ec = r["operating_point"], r["enabled_crops"]
    lines = [
        f"# Photo-check evaluation, {today}", "",
        "Protocol: `evals/vision/README.md` (written before any photo was classified). System under test: "
        f"`{calibration['model']['repo']}` (int8 ONNX, sha256 `{calibration['model']['sha256'][:12]}`) with the code in `apps/api/app/vision/`. "
        "Test photos are PlantDoc `test` (CC-BY-4.0, web-scraped field photos), rice and bean leaves, and objects; none were used to choose anything.", "",
        "## Headline: cross-domain accuracy (field photos, no abstention)", "",
        f"- Photos: **{r['n_test']}** PlantDoc test photos ({r['duplicates_removed']} exact duplicates of training photos removed).",
        f"- **Top-1 accuracy: {with_ci(r['top1'])}**; top-3 accuracy: {with_ci(r['top3'])}; macro-by-class top-1: {pct(r['top1_macro'])}.",
        f"- Without the two approximate class mappings: top-1 {with_ci(r['top1_without_approximate']) if r['top1_without_approximate'] else 'n/a'}.",
        "- The model card's own number (98.9% on PlantVillage leaves) was **not** reproduced here and is not a result of this project.",
        f"- Calibration error (15 bins): {pct(r['ece_before'])} before the fitted temperature ({r['temperature']:.2f}), {pct(r['ece_after'])} after.",
        f"- Near-duplicate check: {r['near_duplicates']['flagged']} test photos are within cosine 0.98 of some training photo; top-1 without them {pct(r['near_duplicates']['top1_without'])}, on them {pct(r['near_duplicates']['top1_flagged'])}.",
        f"- Classifier latency on this machine (CPU, one photo): p50 {r['latency_ms']['p50']:.0f} ms, p95 {r['latency_ms']['p95']:.0f} ms.", "",
        "### By crop", "", "| crop | test photos | top-1 | top-3 |", "|---|---:|---:|---:|",
        *[f"| {c} | {v['n']} | {pct(v['top1'])} | {pct(v['top3'])} |" for c, v in r["by_crop"].items()], "",
        "## What the system does with those photos (the operating point)", "",
        f"Chosen out-of-distribution score: **{op['score']}**, threshold {op['threshold']:.4f} (from calibration). "
        f"A photo must also reach calibrated probability {MIN_PROBABILITY}.", "",
        f"- Accepted by the classifier stage: **{op['accepted_n']} of {r['n_test']}** ({pct(op['coverage'])}); accuracy of those: **{pct(op['selective_accuracy'])}**.",
        f"- Crops enabled for diagnosis by the pre-registered rule: **{', '.join(ec['crops']) or 'none'}**.",
        f"- For photos of those crops: {ec['accepted_n']} accepted, accuracy {pct(ec['selective_accuracy'])}, share of their test photos accepted {pct(ec['share_of_test_photos_of_these_crops'])}.", "",
        "| crop | accepted | of | accuracy of accepted |", "|---|---:|---:|---:|",
        *[f"| {c} | {v['accepted']} | {v['of']} | {pct(v['accuracy'])} |" for c, v in r["accepted_by_crop"].items()], "",
        "### Confidence bands, on the test photos that were accepted", "",
        "| band | accuracy seen on calibration (n) | accuracy on test (n) |", "|---|---|---|",
        *[f"| {b['name']} | {pct(b['calibration_accuracy'])} ({b['calibration_n']}) | {pct(b['accuracy'])} ({b['n']}) |" for b in r["bands"]], "",
        "## Out-of-distribution: photos the classifier has no class for", "",
        "| set | photos | accepted by the classifier stage (false accept) |", "|---|---:|---:|",
        *[f"| {OOD_NAMES[n]} | {v['n']} | {pct(v['rate'])} |" for n, v in r["false_accept"].items()], "",
        "AUROC, in-distribution PlantDoc test against each set (1.0 = perfectly separated):", "",
        "| score | " + " | ".join(OOD_NAMES[n] for n in OOD_TEST) + " |", "|---|" + "---:|" * len(OOD_TEST),
        *[f"| {s}{' (chosen)' if s == op['score'] else ''} | " + " | ".join(f"{r['auroc'][s][n]:.3f}" for n in OOD_TEST) + " |" for s in SCORE_NAMES], "",
    ]
    if baseline is not None:
        b, bcal = baseline
        bop = b["operating_point"]
        lines += [
            "## Candidate 1: the model's own published head, on the same test photos", "",
            f"Calibrated by the same protocol (`{bcal['ood']['score']}`, threshold {bcal['ood']['threshold']:.4f}, temperature {bcal['temperature']:.2f}); "
            f"crops enabled by P7: **{', '.join(b['enabled_crops']['crops']) or 'none'}**.", "",
            "| | candidate 1 (published head) | this candidate (field head) |", "|---|---|---|",
            f"| top-1 accuracy, no abstention | {with_ci(b['top1'])} | {with_ci(r['top1'])} |",
            f"| top-3 accuracy | {with_ci(b['top3'])} | {with_ci(r['top3'])} |",
            f"| calibration error after temperature | {pct(b['ece_after'])} | {pct(r['ece_after'])} |",
            f"| accepted by the classifier stage | {pct(bop['coverage'])} ({bop['accepted_n']}) at {pct(bop['selective_accuracy'])} accuracy | {pct(op['coverage'])} ({op['accepted_n']}) at {pct(op['selective_accuracy'])} accuracy |",
            *[f"| false accept, {OOD_NAMES[n]} | {pct(b['false_accept'][n]['rate'])} | {pct(r['false_accept'][n]['rate'])} |" for n in OOD_TEST],
            f"| best AUROC (mean over the three OOD sets) | {max(np.mean(list(b['auroc'][s_].values())) for s_ in SCORE_NAMES):.3f} | {max(np.mean(list(r['auroc'][s_].values())) for s_ in SCORE_NAMES):.3f} |", "",
        ]
    q = r["quality_gate"]
    lines += [
        "## Quality gate", "",
        f"Thresholds `{q['thresholds']['version']}` (derived from PlantDoc train percentiles).", "",
        f"- Real field photos rejected: train {pct(q['train']['rejected'])}, **test {pct(q['test']['rejected'])}**.",
        "- Synthetic degradations of PlantDoc test photos stopped: " + ", ".join(f"{k} {pct(v['rejected'])}" for k, v in q["degraded"].items()) + ".",
        "- Other photos stopped by the gate: " + ", ".join(f"{OOD_NAMES[n]} {pct(v['rejected'])}" for n, v in q["ood_test"].items()) + ".", "",
        "## Limits of this measurement", "",
        "- PlantDoc is web-scraped and curated; it is not photos taken by Indian smallholders on low-end phones. Its class sizes are small (about 8 to 12 test photos per class), so per-class numbers are rough and the intervals above are wide.",
        "- The classifier has no class for wheat, rice, cotton, millets or pulses. Photos of rice leaves show what happens with a crop it does not know; they say nothing about whether a wheat or rice model would work.",
        "- Agreement between the classifier and the vision model (`vpipeline.py`) is not accuracy and is reported separately.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    from app.safety.crop_scope import KNOWN_CROPS  # noqa: F401  (import check only)
    from app.vision import head as head_mod
    from app.vision.quality import load_thresholds

    import vhead

    label_map = json.loads((ROOT / "data" / "vision" / "label-map-v1.json").read_text(encoding="utf-8"))
    calibration = json.loads((ROOT / "data" / "vision" / "calibration-v1.json").read_text(encoding="utf-8"))
    cache = vcache.load(HERE / "_runs" / "features.npz")
    if cache.model_sha256 != calibration["model"]["sha256"]:
        sys.exit("the cached output and the calibration are for different model files; rerun vrun.py and vcalibrate.py")
    thresholds = load_thresholds()
    baseline = None
    shipped_cache, centroid_set = cache, ID_CALIBRATION
    if calibration["model"].get("head_sha256"):
        # Candidate 3 is the shipped one; candidate 1 (calibrated earlier, kept in _runs) is the baseline.
        cand1 = HERE / "_runs" / "calibration-candidate1.json"
        if cand1.exists():
            c1 = json.loads(cand1.read_text(encoding="utf-8"))
            baseline = (compute(cache, label_map, c1, thresholds), c1)
        head = head_mod.load_head(ROOT / "data" / "vision" / "head-v1.json")
        split = json.loads((HERE / "_runs" / "head-split.json").read_text(encoding="utf-8"))
        shipped_cache = vhead.derive_cache(cache, split, head.logits_batch(cache.features))
        centroid_set = vhead.HEAD_TRAIN
    result = compute(shipped_cache, label_map, calibration, thresholds, centroid_set=centroid_set)
    RESULTS.mkdir(exist_ok=True)
    today = date.today().isoformat()
    path = RESULTS / f"vision-{today}.md"
    path.write_text(render(result, calibration, today, baseline), encoding="utf-8")
    (HERE / "_runs" / "report-details.json").write_text(json.dumps({"shipped": result, "baseline": baseline[0] if baseline else None}, indent=1, default=float), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
