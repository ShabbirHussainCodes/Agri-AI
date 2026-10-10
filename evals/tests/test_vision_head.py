"""vhead (training the candidate-3 head) and app/vision/head.py on SYNTHETIC features."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "evals" / "vision"))

import vhead as H  # noqa: E402
from app.vision import head as RT  # noqa: E402

RNG = np.random.default_rng(3)
D, K = 24, 4
PROTOS = RNG.normal(0, 2.0, (K, D))


def photos(per_class: int, noise: float = 1.0):
    y = np.repeat(np.arange(K), per_class)
    return PROTOS[y] + RNG.normal(0, noise, (len(y), D)), y


def test_the_split_is_per_class_seeded_and_70_30():
    _, y = photos(100)
    a, b = H.split_photos(y), H.split_photos(y)
    assert (a == b).all()
    for c in range(K):
        assert (a[y == c] == H.HEAD_TRAIN).sum() == 70 and (a[y == c] == H.CALIBRATION).sum() == 30
    assert not (H.split_photos(y, seed=8) == a).all()


def test_a_class_with_too_few_head_train_photos_is_dropped_whole():
    y = np.array([0] * 100 + [1] * 20)  # 20 photos -> 14 head-train < 20
    names = H.split_photos(y)
    assert (names[y == 1] == H.DROPPED).all() and (names[y == 0] == H.HEAD_TRAIN).sum() == 70


def test_the_head_learns_separable_classes_and_generalises():
    x, y = photos(80)
    xt, yt = photos(40)
    body = H.train_head(x, y, 6)
    assert body["classes"] == [0, 1, 2, 3] and body["l2"] in H.L2_GRID
    head = RT.LinearHead(RT.LinearHeadFile(version="t", backbone_sha256="a" * 64, trained_on="synthetic", split_seed=7, generated_by="t", date="d",
                                           n_head_train=len(y), **{k: body[k] for k in ("n_classes", "classes", "weight", "bias", "l2")}))
    pred = head.logits_batch(xt).argmax(axis=1)
    assert (pred == yt).mean() > 0.95


def test_folded_standardisation_gives_the_same_logits_as_standardising_first():
    x, y = photos(60)
    xs, mu, sigma = H.standardise(x)
    w, b = H.fit_softmax(xs, y, K, 1e-2)
    folded_w = w / sigma
    folded_b = b - folded_w @ mu
    assert np.allclose(x @ folded_w.T + folded_b, xs @ w.T + b, atol=1e-8)


def test_l2_is_chosen_by_cross_validation_and_reported():
    x, y = photos(60, noise=3.0)
    best, scores = H.choose_l2(x, y, K)
    assert best == min(scores, key=scores.get) and set(scores) == set(H.L2_GRID)


def test_classes_the_head_does_not_know_can_never_win():
    x, y = photos(60)
    body = H.train_head(x, y, 10)  # a label space of 10, the head knows 4
    head = RT.LinearHead(RT.LinearHeadFile(version="t", backbone_sha256="a" * 64, trained_on="s", split_seed=7, generated_by="t", date="d",
                                           n_head_train=len(y), **{k: body[k] for k in ("n_classes", "classes", "weight", "bias", "l2")}))
    out = head.logits(x[0])
    assert out.shape == (10,) and (out[4:] == RT.UNTRAINED_LOGIT).all() and out[:4].max() > RT.UNTRAINED_LOGIT


def test_a_malformed_head_is_refused(tmp_path):
    for body in ('{"version": "x"}', "not json"):
        p = tmp_path / "h.json"
        p.write_text(body, encoding="utf-8")
        with pytest.raises(RT.HeadError):
            RT.load_head(p)
    with pytest.raises(RT.HeadError):
        RT.load_head(tmp_path / "missing.json")


def test_the_head_backend_replaces_the_backbones_own_logits_and_needs_features():
    class Backbone:
        def __init__(self, features):
            self.features = features

        def run(self, batch):
            return np.full((1, 4), 99.0, np.float32), self.features

    x, y = photos(60)
    body = H.train_head(x, y, 4)
    head = RT.LinearHead(RT.LinearHeadFile(version="t", backbone_sha256="a" * 64, trained_on="s", split_seed=7, generated_by="t", date="d",
                                           n_head_train=len(y), **{k: body[k] for k in ("n_classes", "classes", "weight", "bias", "l2")}))
    logits, feats = RT.HeadBackend(Backbone(x[0].astype(np.float32)[None, :]), head).run(np.zeros((1, 3, 224, 224), np.float32))
    assert logits.shape == (1, 4) and logits.max() < 90
    with pytest.raises(RT.HeadError):
        RT.HeadBackend(Backbone(None), head).run(np.zeros((1, 3, 224, 224), np.float32))
