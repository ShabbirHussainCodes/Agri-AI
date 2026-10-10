"""README.md A2: trains the candidate-3 head (a linear layer on the frozen backbone's features) on PlantDoc-train photos.

`split_photos`, `fit_softmax`, `choose_l2` and `train_head` are pure numpy and unit-tested on synthetic data
(evals/tests/test_vision_head.py). The test split is never read here. The result is data:
data/vision/head-v1.json (read at run time by apps/api/app/vision/head.py).

    python ../../evals/vision/vhead.py            # from apps/api
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
from vlabels import ID_CALIBRATION  # noqa: E402

OUT = ROOT / "data" / "vision" / "head-v1.json"
SPLIT_FILE = HERE / "_runs" / "head-split.json"
SEED = 7
HEAD_TRAIN_FRACTION = 0.70
MIN_HEAD_TRAIN_PER_CLASS = 20
L2_GRID = (1e-4, 1e-3, 1e-2, 1e-1, 1.0)
FOLDS = 5
HEAD_TRAIN, CALIBRATION, DROPPED = "plantdoc_headtrain", ID_CALIBRATION, "plantdoc_dropped"


def split_photos(labels: np.ndarray, seed: int = SEED) -> np.ndarray:
    """Per class, a seeded shuffle: 70 % head-train, 30 % calibration. A class with fewer than MIN_HEAD_TRAIN_PER_CLASS
    head-train photos is dropped entirely (its photos get DROPPED). Returns an array of set names, one per photo."""
    rng = np.random.default_rng(seed)
    out = np.empty(len(labels), dtype=object)
    for c in np.unique(labels):
        idx = np.flatnonzero(labels == c)
        rng.shuffle(idx)
        n_train = int(round(HEAD_TRAIN_FRACTION * len(idx)))
        if n_train < MIN_HEAD_TRAIN_PER_CLASS:
            out[idx] = DROPPED
        else:
            out[idx[:n_train]] = HEAD_TRAIN
            out[idx[n_train:]] = CALIBRATION
    return out


def fit_softmax(x: np.ndarray, y: np.ndarray, n_classes: int, l2: float, *, iters: int = 400, lr: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Multinomial logistic regression, full-batch Adam, L2 on the weights only. x is already standardised."""
    n, d = x.shape
    w, b = np.zeros((n_classes, d)), np.zeros(n_classes)
    onehot = np.eye(n_classes)[y]
    m = [np.zeros_like(w), np.zeros_like(b)]
    v = [np.zeros_like(w), np.zeros_like(b)]
    for t in range(1, iters + 1):
        p = M.softmax_rows(x @ w.T + b)
        gw = (p - onehot).T @ x / n + l2 * w
        gb = (p - onehot).mean(axis=0)
        for i, (param, g) in enumerate(((w, gw), (b, gb))):
            m[i] = 0.9 * m[i] + 0.1 * g
            v[i] = 0.999 * v[i] + 0.001 * g * g
            param -= lr * (m[i] / (1 - 0.9**t)) / (np.sqrt(v[i] / (1 - 0.999**t)) + 1e-8)
    return w, b


def standardise(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu, sigma = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
    return (x - mu) / sigma, mu, sigma


def choose_l2(x: np.ndarray, y: np.ndarray, n_classes: int, grid=L2_GRID, folds: int = FOLDS, seed: int = SEED) -> tuple[float, dict]:
    """5-fold cross-validated log-loss on head-train (README A2). Returns the best l2 and every score."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    parts = np.array_split(order, folds)
    scores = {}
    for l2 in grid:
        losses = []
        for k in range(folds):
            val = parts[k]
            tr = np.concatenate([parts[j] for j in range(folds) if j != k])
            xs, mu, sigma = standardise(x[tr])
            w, b = fit_softmax(xs, y[tr], n_classes, l2)
            p = M.softmax_rows(((x[val] - mu) / sigma) @ w.T + b)
            losses.append(float(-np.log(np.clip(p[np.arange(len(val)), y[val]], 1e-12, None)).mean()))
        scores[l2] = float(np.mean(losses))
    return min(scores, key=scores.get), scores


def train_head(features: np.ndarray, labels: np.ndarray, n_label_space: int) -> dict:
    """features: head-train photos only. labels: indexes in the label-map space. Returns the head's file body (without
    provenance fields): folded weights for the classes that have photos."""
    classes = np.unique(labels)
    remap = {int(c): i for i, c in enumerate(classes)}
    y = np.array([remap[int(c)] for c in labels])
    l2, scores = choose_l2(features, y, len(classes))
    xs, mu, sigma = standardise(features)
    w, b = fit_softmax(xs, y, len(classes), l2)
    w_folded = w / sigma
    b_folded = b - w_folded @ mu
    return {
        "n_classes": n_label_space, "classes": [int(c) for c in classes], "l2": l2, "cv_logloss": scores,
        "weight": w_folded.round(6).tolist(), "bias": b_folded.round(6).tolist(),
    }


def derive_cache(cache: vcache.Cache, split: dict[str, str], logits: np.ndarray) -> vcache.Cache:
    """The same cached photos, with the head's logits and the PlantDoc-train photos renamed by their split."""
    sets = np.array([split.get(str(k), s) if s == ID_CALIBRATION else s for k, s in zip(cache.key, cache.set)])
    return vcache.Cache(**{**cache.__dict__, "set": sets, "logits": logits})


def main() -> None:
    from app.vision.head import LinearHead, LinearHeadFile

    label_map = json.loads((ROOT / "data" / "vision" / "label-map-v1.json").read_text(encoding="utf-8"))
    class_index = {lab["label"]: lab["index"] for lab in label_map["labels"]}
    cache = vcache.load(HERE / "_runs" / "features.npz")
    mask = cache.mask(ID_CALIBRATION)
    keys, feats = cache.key[mask], cache.features[mask]
    labels = cache.labels(mask, class_index)
    names = split_photos(labels)
    split = {str(k): str(n) for k, n in zip(keys, names)}
    SPLIT_FILE.write_text(json.dumps(split), encoding="utf-8")
    train = names == HEAD_TRAIN
    body = train_head(feats[train], labels[train], len(class_index))
    head_file = {
        "version": "head-v1", "backbone_sha256": cache.model_sha256, **body,
        "n_head_train": int(train.sum()),
        "trained_on": f"PlantDoc train photos (CC-BY-4.0), {int(train.sum())} head-train photos of {len(body['classes'])} classes; "
                      f"the other 30 % are the calibration split; the test split was not read",
        "split_seed": SEED, "generated_by": "evals/vision/vhead.py", "date": date.today().isoformat(),
    }
    cv = head_file.pop("cv_logloss")
    LinearHeadFile.model_validate(head_file)  # fail here, not at run time
    OUT.write_text(json.dumps(head_file) + "\n", encoding="utf-8")
    head = LinearHead(LinearHeadFile.model_validate(head_file))
    pred = head.logits_batch(feats).argmax(axis=1)
    cal = names == CALIBRATION
    print("l2", body["l2"], "cv log-loss", {k: round(v, 3) for k, v in cv.items()})
    print("head-train photos", int(train.sum()), "calibration photos", int(cal.sum()), "dropped", int((names == DROPPED).sum()))
    print("head-train accuracy", round(float((pred[train] == labels[train]).mean()), 3), "| calibration accuracy", round(float((pred[cal] == labels[cal]).mean()), 3))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
