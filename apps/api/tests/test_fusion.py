"""Pure unit tests for Reciprocal Rank Fusion (app/retrieval/fusion.py).
No database, no model, no network -- these run anywhere, in milliseconds."""
import pytest

from app.retrieval.fusion import reciprocal_rank_fusion


def test_single_list_keeps_order_and_uses_1_over_k_plus_rank():
    fused = reciprocal_rank_fusion({"dense": ["a", "b", "c"]}, k=50)
    assert [f.key for f in fused] == ["a", "b", "c"]
    assert fused[0].score == pytest.approx(1 / 51)
    assert fused[2].score == pytest.approx(1 / 53)


def test_agreement_between_legs_beats_a_single_leg_top_hit():
    # "b" is only #2 in dense, but BOTH legs found it -- that is the whole
    # point of hybrid retrieval, and RRF should put it first.
    fused = reciprocal_rank_fusion({"dense": ["a", "b", "c"], "lexical": ["b", "d"]}, k=50)
    assert [f.key for f in fused] == ["b", "a", "d", "c"]
    assert fused[0].score == pytest.approx(1 / 52 + 1 / 51)


def test_ranks_per_leg_are_recorded_for_evaluation():
    fused = {f.key: f for f in reciprocal_rank_fusion({"dense": ["a", "b"], "lexical": ["b"]})}
    assert fused["b"].ranks == {"dense": 2, "lexical": 1}
    assert fused["a"].ranks == {"dense": 1}


def test_duplicate_inside_one_leg_is_counted_once_at_its_best_rank():
    fused = reciprocal_rank_fusion({"dense": ["a", "a", "b"]}, k=50)
    by_key = {f.key: f for f in fused}
    assert by_key["a"].score == pytest.approx(1 / 51)
    assert by_key["a"].ranks == {"dense": 1}
    # "b" keeps its real position (3), duplicates do not shift later items up
    assert by_key["b"].ranks == {"dense": 3}


def test_ties_are_broken_deterministically():
    first = reciprocal_rank_fusion({"x": ["q"], "y": ["p"]})
    second = reciprocal_rank_fusion({"y": ["p"], "x": ["q"]})
    assert [f.key for f in first] == [f.key for f in second] == ["p", "q"]


def test_empty_input_gives_empty_output():
    assert reciprocal_rank_fusion({"dense": [], "lexical": []}) == []


@pytest.mark.parametrize("bad_k", [0, -1])
def test_non_positive_k_is_rejected(bad_k):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({"dense": ["a"]}, k=bad_k)
