"""Phase 4 step 3 -- retrieval-only evaluation (no LLM, no judge, no cost).

Answers one question before any prompt work: "does the right passage come
back?" Every eval question with a `gold_source` {handle, page} is run through
app.retrieval.hybrid.retrieve() and we record where the gold page lands under
three modes:

  dense    -- the e5 leg on its own
  lexical  -- the full-text leg on its own
  hybrid   -- both, fused with RRF (what /ask actually uses)

HOW ONE RUN GIVES ALL THREE: top_k is set larger than the two legs combined,
so the fused list contains every chunk either leg returned, each carrying its
own dense_rank / lexical_rank. The gold chunk's rank inside a single leg is
therefore exact, not estimated.

It also records top_dense_similarity for EVERY question, split by
expected_behaviour. That distribution is the input to step 5 (calibrating the
abstention floor): the floor should sit where "answer" questions and
"out_of_corpus" questions separate -- if they separate at all.

Metrics, per mode and per bucket:
  recall@5, recall@20 -- share of questions whose gold page is in the top k
  MRR                 -- mean of 1/rank (0 when missed); rewards rank 1 most

Run from the repo root, with the local Supabase stack up and the Phase 3
corpus ingested:
    cd apps/api && python ../../evals/run_retrieval_eval.py
Writes: evals/_runs/<timestamp>-retrieval.json (gitignored, full detail)
        evals/results/retrieval-<date>.md          (committed summary)
"""
import asyncio
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

MODES = ("dense", "lexical", "hybrid")
LEG_LIMIT = 40
# > 2 * LEG_LIMIT, so no chunk returned by either leg is cut from the fused list.
EVAL_TOP_K = 2 * LEG_LIMIT + 1


def load_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _gold_ranks(chunks, handle: str, page: int) -> dict[str, int | None]:
    gold = [c for c in chunks if c.handle == handle and c.page_no == page]
    dense = [c.dense_rank for c in gold if c.dense_rank is not None]
    lexical = [c.lexical_rank for c in gold if c.lexical_rank is not None]
    hybrid = next((i for i, c in enumerate(chunks, start=1) if c.handle == handle and c.page_no == page), None)
    return {
        "dense": min(dense) if dense else None,
        "lexical": min(lexical) if lexical else None,
        "hybrid": hybrid,
    }


async def evaluate(conn, embedder, questions: list[dict]) -> dict:
    """The measurable core, separated from I/O so it can be tested with a
    fake embedder and a throwaway database."""
    from app.retrieval.hybrid import retrieve

    rows = []
    for q in questions:
        # min_similarity=-1.0: accept the unfiltered tier unconditionally.
        # This run MEASURES similarity; it must not be gated by a threshold
        # that has not been calibrated yet.
        result = await retrieve(
            conn, embedder, q["question"], min_similarity=-1.0,
            top_k=EVAL_TOP_K, leg_limit=LEG_LIMIT,
        )
        gold = q.get("gold_source")
        rows.append({
            "id": q["id"],
            "bucket": q["bucket"],
            "language": q["language"],
            "expected_behaviour": q["expected_behaviour"],
            "abstain_reason": q.get("abstain_reason"),
            "gold": gold,
            "ranks": _gold_ranks(result.chunks, gold["handle"], gold["page"]) if gold else None,
            "top_dense_similarity": result.top_dense_similarity,
        })
    return {"rows": rows, "summary": summarise(rows)}


def _metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "recall@5": sum(1 for r in ranks if r is not None and r <= 5) / n,
        "recall@20": sum(1 for r in ranks if r is not None and r <= 20) / n,
        "mrr": sum(1 / r for r in ranks if r is not None) / n,
    }


def summarise(rows: list[dict]) -> dict:
    with_gold = [r for r in rows if r["ranks"] is not None]
    overall = {m: _metrics([r["ranks"][m] for r in with_gold]) for m in MODES}
    by_bucket = {}
    buckets = defaultdict(list)
    for r in with_gold:
        buckets[r["bucket"]].append(r)
    for b, rs in sorted(buckets.items()):
        by_bucket[b] = {m: _metrics([r["ranks"][m] for r in rs]) for m in MODES}

    sims = defaultdict(list)
    for r in rows:
        if r["top_dense_similarity"] is None:
            continue
        key = r["expected_behaviour"] if r["expected_behaviour"] == "answer" else f"abstain:{r['abstain_reason']}"
        sims[key].append(r["top_dense_similarity"])
    similarity = {
        k: {"n": len(v), "min": min(v), "median": statistics.median(v), "max": max(v)}
        for k, v in sorted(sims.items())
    }
    return {"overall": overall, "by_bucket": by_bucket, "top_dense_similarity": similarity}


def to_markdown(summary: dict, run_at: str) -> str:
    def fmt(m):
        if m.get("n", 0) == 0:
            return "–"
        return f"{m['recall@5']:.2f} / {m['recall@20']:.2f} / {m['mrr']:.2f}"

    lines = [
        f"# Retrieval baseline — {run_at}",
        "",
        "Retrieval-only (no LLM). Cells are **recall@5 / recall@20 / MRR** for the gold page.",
        "Produced by `evals/run_retrieval_eval.py`; full per-question detail is in `evals/_runs/`.",
        "",
        "| scope | n | dense | lexical | hybrid (RRF k=50) |",
        "|---|---:|---|---|---|",
    ]
    o = summary["overall"]
    lines.append(f"| **all with gold** | {o['hybrid']['n']} | {fmt(o['dense'])} | {fmt(o['lexical'])} | {fmt(o['hybrid'])} |")
    for b, m in summary["by_bucket"].items():
        lines.append(f"| {b} | {m['hybrid']['n']} | {fmt(m['dense'])} | {fmt(m['lexical'])} | {fmt(m['hybrid'])} |")
    lines += [
        "",
        "## Top dense similarity by expected behaviour (input to the abstention floor)",
        "",
        "| group | n | min | median | max |",
        "|---|---:|---:|---:|---:|",
    ]
    for k, s in summary["top_dense_similarity"].items():
        lines.append(f"| {k} | {s['n']} | {s['min']:.3f} | {s['median']:.3f} | {s['max']:.3f} |")
    lines.append("")
    return "\n".join(lines)


async def main() -> int:
    import asyncpg

    from app.core.config import settings
    from app.retrieval.embedder import get_query_embedder

    questions = load_questions(REPO_ROOT / "evals" / "questions.jsonl")
    embedder = get_query_embedder()

    conn = await asyncpg.connect(settings.database_url)
    try:
        async with conn.transaction():
            # Same role /ask uses, so the eval measures the real access path.
            await conn.execute("set local role authenticated")
            report = await evaluate(conn, embedder, questions)
    finally:
        await conn.close()

    now = datetime.now(timezone.utc)
    runs = REPO_ROOT / "evals" / "_runs"
    results = REPO_ROOT / "evals" / "results"
    runs.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    (runs / f"{now:%Y%m%dT%H%M%SZ}-retrieval.json").write_text(json.dumps(report, indent=2, default=str))
    md = to_markdown(report["summary"], now.strftime("%Y-%m-%d %H:%M UTC"))
    (results / f"retrieval-{now:%Y-%m-%d}.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
