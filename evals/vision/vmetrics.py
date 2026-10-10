"""Pure metric functions for the photo-check evaluation (README.md P2 to P8). numpy only, no I/O.

Conventions: probabilities are float arrays (n, classes); labels are int arrays (n,); scores are float arrays
(n,) where HIGHER = MORE LIKE A SUPPORTED LEAF, matching app/vision/classifier.py.
"""
import numpy as np


def softmax_rows(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = logits.astype(np.float64) / temperature
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def nll(logits: np.ndarray, labels: np.ndarray, temperature: float) -> float:
    p = softmax_rows(logits, temperature)
    return float(-np.log(np.clip(p[np.arange(len(labels)), labels], 1e-12, None)).mean())


def fit_temperature(logits: np.ndarray, labels: np.ndarray, lo: float = 0.5, hi: float = 5.0, step: float = 0.05) -> float:
    """README P2: grid search of the negative log-likelihood."""
    grid = np.round(np.arange(lo, hi + step / 2, step), 4)
    return float(min(grid, key=lambda t: nll(logits, labels, float(t))))


def top_k_accuracy(probs: np.ndarray, labels: np.ndarray, k: int) -> float:
    top = np.argsort(-probs, axis=1)[:, :k]
    return float((top == labels[:, None]).any(axis=1).mean())


def macro_by_class(correct: np.ndarray, labels: np.ndarray) -> float:
    """Mean over classes of the per-class accuracy (classes with no photo are skipped)."""
    per = [correct[labels == c].mean() for c in np.unique(labels)]
    return float(np.mean(per))


def expected_calibration_error(confidence: np.ndarray, correct: np.ndarray, bins: int = 15) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece, n = 0.0, len(confidence)
    for i in range(bins):
        hi = edges[i + 1]
        mask = (confidence >= edges[i]) & ((confidence < hi) if i < bins - 1 else (confidence <= hi))
        if mask.any():
            ece += mask.sum() / n * abs(correct[mask].mean() - confidence[mask].mean())
    return float(ece)


def auroc(id_scores: np.ndarray, ood_scores: np.ndarray) -> float:
    """Probability that a random in-distribution photo scores higher than a random OOD one (ties count half).
    Rank-based, O(n log n)."""
    scores = np.concatenate([id_scores, ood_scores])
    order = scores.argsort(kind="mergesort")
    ranks = np.empty(len(scores), dtype=np.float64)
    sorted_scores = scores[order]
    i = 0
    while i < len(scores):
        j = i
        while j + 1 < len(scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    n_id, n_ood = len(id_scores), len(ood_scores)
    return float((ranks[:n_id].sum() - n_id * (n_id + 1) / 2.0) / (n_id * n_ood))


def accept(scores: np.ndarray, threshold: float) -> np.ndarray:
    return scores >= threshold


def coverage_and_selective_accuracy(scores: np.ndarray, correct: np.ndarray, threshold: float) -> tuple[float, float | None]:
    accepted = accept(scores, threshold)
    if not accepted.any():
        return 0.0, None
    return float(accepted.mean()), float(correct[accepted].mean())


def false_accept_rate(ood_scores: np.ndarray, threshold: float) -> float:
    return float(accept(ood_scores, threshold).mean())


def choose_threshold(
    id_scores: np.ndarray, id_correct: np.ndarray, ood_scores: np.ndarray,
    *, min_selective_accuracy: float = 0.80, max_false_accept: float = 0.10,
) -> tuple[float, bool]:
    """README P4. Returns (threshold, target_met). Candidates are the distinct ID scores. Among thresholds that
    satisfy both limits take the one with the largest coverage; if none does, take the best selective accuracy
    among those with false-accept <= max_false_accept (or, failing that, the lowest false-accept)."""
    candidates = np.unique(id_scores[np.isfinite(id_scores)])  # -inf = "never accepted", not a threshold
    best_ok: tuple[float, float] | None = None  # (coverage, threshold)
    rows = []
    for t in candidates:
        cov, sel = coverage_and_selective_accuracy(id_scores, id_correct, float(t))
        far = false_accept_rate(ood_scores, float(t))
        rows.append((float(t), cov, sel if sel is not None else 0.0, far))
        if sel is not None and sel >= min_selective_accuracy and far <= max_false_accept:
            if best_ok is None or cov > best_ok[0]:
                best_ok = (cov, float(t))
    if best_ok is not None:
        return best_ok[1], True
    within = [r for r in rows if r[3] <= max_false_accept and r[1] > 0]
    if within:
        return max(within, key=lambda r: (r[2], r[1]))[0], False
    return min(rows, key=lambda r: (r[3], -r[1]))[0], False


def bootstrap_ci(values: np.ndarray, *, resamples: int = 1000, seed: int = 7, alpha: float = 0.05) -> tuple[float, float]:
    """README P8: percentile interval of the mean of per-photo 0/1 (or any) values."""
    rng = np.random.default_rng(seed)
    n = len(values)
    means = np.array([values[rng.integers(0, n, n)].mean() for _ in range(resamples)])
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def reliability(confidence: np.ndarray, correct: np.ndarray, floors: list[float]) -> list[dict]:
    """Accuracy observed in each band defined by descending probability floors, e.g. [0.9, 0.7, 0.5]: band i is
    [floors[i], floors[i-1]); the first is [floors[0], 1]. Photos below the last floor are not in any band."""
    out = []
    for i, floor in enumerate(floors):
        upper = floors[i - 1] if i else 1.0 + 1e-9
        mask = (confidence >= floor) & (confidence < upper)
        out.append({"floor": floor, "n": int(mask.sum()), "accuracy": float(correct[mask].mean()) if mask.any() else None})
    return out
