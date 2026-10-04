"""Replay a captured agent-eval run through the CURRENT code-side rules --
no LLM call, no Groq quota, no database.

run_agent_eval.py records, for every question, the model's DraftAdvisory and
the exact passages it saw. finalize_advisory() is a pure function, so a rule
added to it later (ADR-0014's crop check, for example) can be measured
against the same drafts the baseline was scored on.

What a replay can and cannot tell you:
  * CAN: what the new finalize rules do to the recorded drafts.
  * CANNOT: what the model would have written if it had seen a different
    passage block. Crop scoping (ADR-0014) changes the passage block itself,
    so every question whose block would change is LISTED, not guessed -- run
    exactly those live with run_agent_eval.py --only <ids>.

Coverage metadata (`doc_crops_covered`) is taken from ingest/sources.yaml by
document handle, because runs captured before ADR-0014 do not carry it.

    python evals/replay_finalize.py evals/_runs/<stamp>-agent.jsonl

Phase 6 (ADR-0016): the replay passes the question text too, because the banned-
molecule guard and the chemical-context number rule read it. Run it on the captured
Phase 4 run and compare behaviour accuracy with the recorded 53/55: that is the
no-quota check that the stricter dose guard did not turn harmless answers into
abstentions.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.agent.finalize import finalize_advisory  # noqa: E402
from app.agent.tools.farm_context import FarmContextData  # noqa: E402
from app.retrieval.hybrid import RetrievedChunk  # noqa: E402
from app.safety import crop_scope  # noqa: E402
from app.schemas.advisory import DraftAdvisory  # noqa: E402


def load_coverage() -> dict[str, list[str]]:
    register = yaml.safe_load((REPO_ROOT / "ingest" / "sources.yaml").read_text(encoding="utf-8"))
    return {
        item["handle"]: list(item.get("crops_covered") or [])
        for source in register["sources"]
        for item in (source.get("approved_items") or [])
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path, help="evals/_runs/<stamp>-agent.jsonl")
    args = ap.parse_args()

    coverage = load_coverage()
    rows = [json.loads(l) for l in args.run.read_text(encoding="utf-8").splitlines() if l.strip()]
    # Score against the CURRENT eval set, not the copy frozen inside the run: an
    # expectation can change after a run (tab-004, 2026-10-05), and both columns
    # must be judged by the same rule or the comparison is meaningless.
    current = {
        q["id"]: q
        for q in (json.loads(l) for l in (REPO_ROOT / "evals" / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())
    }
    re_expected = []

    changed, scoped_ids, table = [], [], []
    old_ok = new_ok = n = 0
    old_blank = new_blank = 0
    for rec in rows:
        q, draft, resp = rec["question"], rec.get("draft"), rec.get("response")
        if resp is None:
            continue
        n += 1
        expected = current.get(q["id"], q)["expected_behaviour"]
        if expected != q["expected_behaviour"]:
            re_expected.append(q["id"])
        expect_abstain = expected == "abstain"
        old_abstained = bool(resp["abstained"])
        named = crop_scope.crops_named_in(q["question"])

        old_blank += not (resp.get("recommendation") or "").strip()
        new_recommendation = resp.get("recommendation") or ""
        if draft is None:
            # The run recorded no draft (e.g. the request failed before Turn B);
            # nothing to replay, keep the recorded outcome.
            new_abstained, new_reason = old_abstained, resp.get("abstained_because")
        else:
            passages = [
                RetrievedChunk.model_validate({**p, "doc_crops_covered": coverage.get(p.get("handle"), [])})
                for p in rec.get("passages") or []
            ]
            if len(crop_scope.scope_passages(passages, named)) != len(passages):
                scoped_ids.append(q["id"])
            new = finalize_advisory(
                DraftAdvisory.model_validate(draft),
                farm_data=FarmContextData.model_validate(resp["structured_data"]),
                live_data=None,
                passages=passages,
                named_crops=named,
                question_text=q["question"],  # Phase 6: the banned-molecule and chemical-context rules read it
            )
            new_abstained, new_reason = new.abstained, new.abstained_because
            new_recommendation = new.recommendation
        new_blank += not new_recommendation.strip()

        old_ok += old_abstained == expect_abstain
        new_ok += new_abstained == expect_abstain
        if new_abstained != old_abstained:
            changed.append(q["id"])
        table.append((q["id"], expected, sorted(named), old_abstained, new_abstained, new_reason))

    print(f"# Finalize replay -- {args.run.name}\n")
    print(f"Questions replayed: {n}")
    print(f"Behaviour accuracy: recorded {old_ok}/{n} ({old_ok / n:.0%}) -> replayed {new_ok}/{n} ({new_ok / n:.0%})")
    print(f"Blank recommendation shown to the farmer: recorded {old_blank} -> replayed {new_blank}")
    print(f"Expectation changed since the run was recorded (scored by today's): {', '.join(re_expected) or 'none'}")
    print(f"Outcome changed by the new rules: {', '.join(changed) or 'none'}")
    print(f"Passage block would change under crop scoping (verify live with --only): "
          f"{','.join(scoped_ids) or 'none'}\n")
    print("| id | expected | crops named | abstained (recorded) | abstained (replayed) | replayed reason |")
    print("|---|---|---|---|---|---|")
    for row in table:
        if row[2] or row[3] != row[4]:
            print("| " + " | ".join(str(x) for x in row) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
