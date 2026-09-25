"""Reciprocal Rank Fusion (RRF) -- a pure function, no DB and no model.

WHAT: combine several ranked lists into one ranking.
HOW:  every list contributes 1 / (k + rank) for each item it contains
      (rank starts at 1). An item's fused score is the sum over lists.
WHY RANKS AND NOT SCORES: the dense leg produces cosine similarity (0..1,
      bunched together) and the lexical leg produces ts_rank_cd (unbounded,
      depends on document length). Adding those raw numbers would let one
      scale drown the other, and "fixing" that needs per-corpus calibration.
      Ranks have no units, so RRF needs no calibration at all.
WHY k: k damps the top of each list, so one leg's #1 cannot outvote an item
      both legs agree on. k=50 is rag-design.md section 1's choice; the
      eval baseline is what tells us whether to revisit it, not intuition.

Kept separate from hybrid.py so the maths is unit-testable with plain lists
(tests/test_fusion.py) and records each leg's rank for evaluation.
"""
from dataclasses import dataclass, field
from typing import Hashable, Mapping, Sequence

DEFAULT_RRF_K = 50


@dataclass(frozen=True)
class FusedItem:
    key: Hashable
    score: float
    # Leg name -> 1-based rank in that leg; a leg that missed the item is absent.
    # The eval uses this to answer "did dense or lexical find the gold chunk?".
    ranks: dict[str, int] = field(default_factory=dict)


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[Hashable]],
    *,
    k: int = DEFAULT_RRF_K,
) -> list[FusedItem]:
    """Fuse named ranked lists (best first) into one list, best first.

    Duplicates inside one list keep only their best (first) rank, so a leg
    cannot vote twice for the same chunk.

    Ties are broken deterministically -- first by the best rank the item got
    in any leg, then by the key's string form -- so the same inputs always
    give the same order (a flaky order would make eval runs incomparable).
    """
    if k <= 0:
        raise ValueError("k must be positive")

    scores: dict[Hashable, float] = {}
    ranks: dict[Hashable, dict[str, int]] = {}

    for leg, items in ranked_lists.items():
        seen: set[Hashable] = set()
        for position, key in enumerate(items, start=1):
            if key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + position)
            ranks.setdefault(key, {})[leg] = position

    return sorted(
        (FusedItem(key=key, score=scores[key], ranks=ranks[key]) for key in scores),
        key=lambda item: (-item.score, min(item.ranks.values()), str(item.key)),
    )
