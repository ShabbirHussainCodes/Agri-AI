"""Checks the model's irrigation answer against what code computed (ADR-0015).

Runs inside finalize_advisory, AFTER the model, in code, so no model output can
contradict the water balance on its way to the farmer (CLAUDE.md rule 2).

The model writes the explanation and one word, `irrigation_verdict`. This
module decides whether that wording may be shown:

  no water balance exists
      claim irrigate_now / wait          -> IRRIGATION_VERDICT_UNSUPPORTED
      claim anything else                -> fine (nothing to contradict)
  water balance is cannot_assess         -> not this module's business: the
      caller shows the code-authored message and the model's text is dropped
  water balance has a verdict
      the model's verdict differs        -> IRRIGATION_VERDICT_MISMATCH
      a number in the text is not in the
      evidence (number_grounding.py)     -> UNGROUNDED_NUMBER

Pure functions; tests/test_irrigation_guard.py.
"""
from collections.abc import Sequence

from app.agronomy.water_balance import WaterBalanceResult
from app.safety import number_grounding

IRRIGATION_VERDICT_UNSUPPORTED = "irrigation_verdict_unsupported"
IRRIGATION_VERDICT_MISMATCH = "irrigation_verdict_mismatch"
UNGROUNDED_NUMBER = "ungrounded_number"

_CLAIMS_A_COMPUTATION = ("irrigate_now", "wait")


def check_irrigation_answer(
    *,
    claimed_verdict: str,
    water_balance: WaterBalanceResult | None,
    texts: Sequence[str],
    evidence: Sequence[str],
) -> str | None:
    """A reason code if the answer may not be shown as written, else None.
    `texts`: what the farmer would read (recommendation, reasoning).
    `evidence`: everything the model was allowed to take numbers from."""
    if water_balance is None:
        return IRRIGATION_VERDICT_UNSUPPORTED if claimed_verdict in _CLAIMS_A_COMPUTATION else None
    if water_balance.verdict == "cannot_assess":
        return None
    if claimed_verdict != water_balance.verdict:
        return IRRIGATION_VERDICT_MISMATCH
    if number_grounding.ungrounded_numbers(texts, evidence):
        return UNGROUNDED_NUMBER
    return None
