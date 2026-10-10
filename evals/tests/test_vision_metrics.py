"""Pure tests for evals/vision/vmetrics.py. Run from the repo root with the API venv:  pytest evals/tests"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals" / "vision"))

import vmetrics as m  # noqa: E402


def test_softmax_rows_sum_to_one_and_temperature_flattens():
    z = np.array([[4.0, 1.0, 0.0], [0.0, 0.0, 0.0]])
    assert np.allclose(m.softmax_rows(z).sum(axis=1), 1.0)
    assert m.softmax_rows(z, 4.0)[0].max() < m.softmax_rows(z, 1.0)[0].max()
    assert np.allclose(m.softmax_rows(z)[1], 1 / 3)


def test_fit_temperature_recovers_overconfidence():
    rng = np.random.default_rng(0)
    n, k = 4000, 5
    labels = rng.integers(0, k, n)
    logits = rng.normal(0, 1, (n, k))
    logits[np.arange(n), labels] += 1.0           # a weak signal ...
    logits *= 4.0                                  # ... multiplied into an over-confident model
    assert m.fit_temperature(logits, labels) > 2.0
    sharp = np.zeros((300, k)); lab = rng.integers(0, k, 300); sharp[np.arange(300), lab] = 1.0
    assert m.fit_temperature(sharp, lab) <= 1.0    # an already under-confident model is not "cooled" further


def test_top_k_and_macro_accuracy_by_hand():
    probs = np.array([[0.6, 0.3, 0.1], [0.2, 0.5, 0.3], [0.1, 0.2, 0.7], [0.5, 0.4, 0.1]])
    labels = np.array([0, 2, 2, 1])
    assert m.top_k_accuracy(probs, labels, 1) == pytest.approx(0.5)      # rows 0 and 2
    assert m.top_k_accuracy(probs, labels, 2) == pytest.approx(1.0)      # row 1: 2 is second; row 3: 1 is second
    correct = np.array([1, 0, 1, 0])
    assert m.macro_by_class(correct, labels) == pytest.approx((1.0 + 0.5 + 0.0) / 3)  # classes 0, 2 (1 and 0), 1


def test_ece_is_zero_for_a_calibrated_model_and_gap_for_a_miscalibrated_one():
    conf = np.full(1000, 0.8)
    rng = np.random.default_rng(1)
    assert m.expected_calibration_error(conf, (rng.random(1000) < 0.8).astype(float)) < 0.03
    assert m.expected_calibration_error(np.full(100, 0.9), np.full(100, 0.5)) == pytest.approx(0.4)
    assert m.expected_calibration_error(np.array([1.0]), np.array([1.0])) == pytest.approx(0.0)  # confidence == 1 lands in the last bin


def test_auroc_perfect_inverse_tied_and_by_hand():
    assert m.auroc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert m.auroc(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == 0.0
    assert m.auroc(np.array([1.0, 1.0]), np.array([1.0, 1.0])) == 0.5
    assert m.auroc(np.array([1.0, 3.0]), np.array([2.0])) == pytest.approx(0.5)  # 3>2 counts, 1<2 does not
    rng = np.random.default_rng(3)
    a, b = rng.normal(1, 1, 400), rng.normal(0, 1, 400)
    brute = np.mean([(x > y) + 0.5 * (x == y) for x in a for y in b])
    assert m.auroc(a, b) == pytest.approx(brute)


def test_coverage_selective_accuracy_and_false_accept():
    scores = np.array([0.9, 0.8, 0.5, 0.2])
    correct = np.array([1, 1, 0, 0])
    assert m.coverage_and_selective_accuracy(scores, correct, 0.7) == (0.5, 1.0)
    assert m.coverage_and_selective_accuracy(scores, correct, 0.1) == (1.0, 0.5)
    assert m.coverage_and_selective_accuracy(scores, correct, 1.0) == (0.0, None)
    assert m.false_accept_rate(np.array([0.3, 0.6, 0.9, 0.1]), 0.5) == 0.5
    assert m.false_accept_rate(np.array([0.5]), 0.5) == 1.0          # the threshold itself is accepted (>=)


def test_choose_threshold_takes_the_largest_coverage_that_meets_both_limits():
    id_scores = np.array([0.95, 0.9, 0.85, 0.8, 0.6, 0.5])
    id_correct = np.array([1, 1, 1, 1, 0, 0])
    ood = np.array([0.7, 0.4, 0.3, 0.2, 0.2, 0.1, 0.1, 0.05, 0.05, 0.0])
    t, met = m.choose_threshold(id_scores, id_correct, ood)
    assert met and t == 0.6                       # 5 accepted, 4 right = 0.80 exactly; 1 of 10 OOD (0.7) = 0.10 exactly: both limits are inclusive
    ood_worse = np.array([0.7, 0.7, 0.3, 0.2, 0.2, 0.1, 0.1, 0.05, 0.05, 0.0])
    t_strict, met_strict = m.choose_threshold(id_scores, id_correct, ood_worse)
    assert met_strict and t_strict == 0.8         # 0.6 now lets 2 of 10 OOD in, so only the four correct ones are taken
    t2, met2 = m.choose_threshold(id_scores, id_correct, np.array([0.99] * 10))
    assert not met2                               # every OOD photo scores above every ID photo: no threshold can be safe
    t3, met3 = m.choose_threshold(id_scores, np.array([1, 0, 0, 0, 0, 0]), ood)
    assert met3 and t3 == 0.95                    # only accepting the single top photo reaches 0.80, and that is enough
    t4, met4 = m.choose_threshold(id_scores, np.zeros(6), ood)
    assert not met4                               # nothing is ever right: the target cannot be met at any threshold
    assert 0.0 <= t4 <= 0.95


def test_bootstrap_interval_brackets_the_mean_and_is_seeded():
    vals = (np.random.default_rng(5).random(300) < 0.6).astype(float)
    lo, hi = m.bootstrap_ci(vals)
    assert lo < vals.mean() < hi and hi - lo < 0.15
    assert m.bootstrap_ci(vals) == (lo, hi)


def test_reliability_bands():
    conf = np.array([0.95, 0.92, 0.85, 0.75, 0.6, 0.55, 0.4])
    correct = np.array([1, 1, 1, 0, 1, 0, 0])
    rel = m.reliability(conf, correct, [0.9, 0.7, 0.5])
    assert [r["n"] for r in rel] == [2, 2, 2] and [r["accuracy"] for r in rel] == [1.0, 0.5, 0.5]
