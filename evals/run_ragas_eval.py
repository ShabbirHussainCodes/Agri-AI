"""Phase 4 step 6b -- LLM-judged Ragas metrics over the step-6a run.

Reads the *-ragas-input.jsonl written by run_agent_eval.py (no agent calls,
no database) and scores it with Ragas 0.4.3's metric collection API
(verified against the ragas 0.4.3 wheel source, 2026-09-26):

  ContextPrecisionWithReference(user_input, reference, retrieved_contexts)
      Were the passages we retrieved relevant, and were the relevant ones
      ranked first? -> "is retrieval bad?"
  ContextRecall(user_input, retrieved_contexts, reference)
      Does what we retrieved contain everything the reference answer needs?
  Faithfulness(user_input, response, retrieved_contexts)
      Is every claim in our answer supported by the passages?  This is the
      metric that catches a REAL-but-irrelevant quote, which the code-side
      citation check cannot (ADR-0013). -> "is the prompt/model bad?"
  AnswerRelevancy(user_input, response)
      Does the answer actually address the question?

Which rows get which metric:
  - context metrics: every question that EXPECTS an answer and has a
    reference answer -- retrieval quality should be measured whether or not
    the system then chose to answer.
  - answer metrics: only rows the system actually ANSWERED. An abstention has
    no claims to be faithful to; its quality is the deterministic abstention
    accuracy in agent-<date>.md.

JUDGE CHOICE (decided with Shabbir, 2026-09-26): `openai/gpt-oss-20b`, NOT
the 120b model that writes the answers. Two reasons:
  1. Budget. Groq's free tier gives gpt-oss-120b 200,000 tokens/day, which
     the agent eval alone nearly exhausts (~4.5-5k tokens per question). The
     429 message names the limit per model, so 20b has its own budget.
  2. Bias. A judge grading its own model's answers tends to favour its own
     phrasing; a different model reduces (does not remove) that.
Cost of the choice: 20b is a weaker judge. The caveat is written into the
results file. Treat scores as a baseline to compare later runs against, not
as absolute truth.

Runs in its own venv (evals/requirements-ragas.txt), from the repo root:
    python evals/run_ragas_eval.py evals/_runs/<stamp>-ragas-input.jsonl --limit 2
    python evals/run_ragas_eval.py evals/_runs/<stamp>-ragas-input.jsonl
"""
import os

# Must be set before ragas is imported: Ragas sends usage analytics unless
# told not to. Nothing about farmers' questions needs to leave this laptop
# except the judge calls themselves.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_JUDGE = "openai/gpt-oss-20b"  # see JUDGE CHOICE in the module docstring


def _groq_key() -> str:
    """AGRIAI_GROQ_API_KEY from the environment, else from apps/api/.env
    (the same file the API reads). Never printed, never written anywhere."""
    key = os.environ.get("AGRIAI_GROQ_API_KEY")
    if key:
        return key
    env_file = REPO_ROOT / "apps" / "api" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("AGRIAI_GROQ_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("AGRIAI_GROQ_API_KEY not set and not found in apps/api/.env")


def _e5_embeddings():
    """Ragas embedding adapter around AgriAI's own e5 query embedder. Answer
    relevancy compares the question with questions generated back from the
    answer -- query-vs-query, so the 'query:' side of e5 is the right one."""
    from ragas.embeddings.base import BaseRagasEmbedding

    from app.retrieval.embedder import QueryEmbedder

    model = QueryEmbedder(REPO_ROOT / "ingest" / "_cache" / "models")

    class E5Embeddings(BaseRagasEmbedding):
        def embed_text(self, text: str, **kwargs):
            return model.embed_query(text).tolist()

        async def aembed_text(self, text: str, **kwargs):
            return model.embed_query(text).tolist()

    return E5Embeddings()


async def _score(metric, **kwargs):
    try:
        return float((await metric.ascore(**kwargs)).value), None
    except Exception as exc:  # noqa: BLE001 -- recorded per row, never dropped silently
        return None, f"{type(exc).__name__}: {str(exc)[:200]}"


def _mean(values):
    vals = [v for v in values if v is not None]
    return (statistics.mean(vals), len(vals)) if vals else (None, 0)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="evals/_runs/<stamp>-ragas-input.jsonl")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE)
    ap.add_argument("--limit", type=int, help="first N eligible rows only (smoke test)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between rows")
    args = ap.parse_args()

    from openai import AsyncOpenAI
    from ragas.cache import DiskCacheBackend
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithReference,
        ContextRecall,
        Faithfulness,
    )

    # Groq's OpenAI-compatible endpoint + provider="openai": Ragas then uses
    # instructor.from_openai in JSON mode. (Its provider="groq" path calls
    # client.messages.create, which is the Anthropic SDK's method name, not
    # the Groq SDK's -- so the OpenAI-compatible route is the reliable one.)
    # max_retries: the OpenAI SDK retries 429s with exponential backoff.
    client = AsyncOpenAI(base_url=GROQ_OPENAI_BASE_URL, api_key=_groq_key(), max_retries=8)
    # Disk cache: a re-run (e.g. after a rate-limit stop) re-uses every judge
    # call already made instead of spending the quota again.
    cache = DiskCacheBackend(cache_dir=str(REPO_ROOT / "evals" / "_runs" / "ragas-cache"))
    llm = llm_factory(args.judge_model, provider="openai", client=client, cache=cache, temperature=0)

    metrics = {
        "context_precision": ContextPrecisionWithReference(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=_e5_embeddings()),
    }

    rows = [json.loads(l) for l in args.input.read_text(encoding="utf-8").splitlines() if l.strip()]
    eligible = [r for r in rows if r["expected_behaviour"] == "answer" and r.get("reference") and r["retrieved_contexts"]]
    if args.limit:
        eligible = eligible[: args.limit]
    print(f"{len(eligible)} rows to judge with {args.judge_model}")

    results = []
    # Set when the judge's DAILY token quota runs out. Every later call would
    # fail the same way (seen on 2026-09-27: 18 of 31 rows came back ERR), so
    # stop instead of recording a pile of meaningless errors. Successful judge
    # calls are in the disk cache, so the next run resumes almost for free.
    daily_quota_hit = False
    for i, r in enumerate(eligible, 1):
        out = {"id": r["id"], "bucket": r["bucket"], "answered": not r["abstained"], "scores": {}, "errors": {}}
        jobs = {
            "context_precision": dict(user_input=r["user_input"], reference=r["reference"], retrieved_contexts=r["retrieved_contexts"]),
            "context_recall": dict(user_input=r["user_input"], retrieved_contexts=r["retrieved_contexts"], reference=r["reference"]),
        }
        if not r["abstained"]:
            jobs["faithfulness"] = dict(user_input=r["user_input"], response=r["response"], retrieved_contexts=r["retrieved_contexts"])
            jobs["answer_relevancy"] = dict(user_input=r["user_input"], response=r["response"])
        for name, kwargs in jobs.items():
            score, err = await _score(metrics[name], **kwargs)
            out["scores"][name] = score
            if err:
                out["errors"][name] = err
                if "tokens per day" in err or "(TPD)" in err:
                    daily_quota_hit = True
                    break
        results.append(out)
        shown = " ".join(f"{k}={v:.2f}" if v is not None else f"{k}=ERR" for k, v in out["scores"].items())
        print(f"[{i}/{len(eligible)}] {r['id']:<12} {shown}")
        if daily_quota_hit:
            print(
                f"\nSTOPPED at row {i}/{len(eligible)}: {args.judge_model}'s daily token quota is used up. "
                "Re-run the same command after it refills -- cached judge calls are reused."
            )
            break
        await asyncio.sleep(args.delay)

    summary = {}
    for name in metrics:
        mean, n = _mean(x["scores"].get(name) for x in results)
        errors = sum(1 for x in results if name in x["errors"])
        summary[name] = {"mean": mean, "n": n, "errors": errors}

    now = datetime.now(timezone.utc)
    runs = REPO_ROOT / "evals" / "_runs"
    (runs / f"{now:%Y%m%dT%H%M%SZ}-ragas.json").write_text(json.dumps({"summary": summary, "rows": results}, indent=2))

    lines = [
        f"# Ragas baseline — {now:%Y-%m-%d %H:%M UTC}",
        "",
        f"Judge: `{args.judge_model}` via Groq, Ragas 0.4.3. Input: `{args.input.name}` "
        f"({len(eligible)} answer-expected questions with a reference answer). "
        "Context metrics cover every one of them; answer metrics cover only those the system actually answered.",
        "",
        "> **Judge caveat:** the judge is an LLM (by default `gpt-oss-20b`, a smaller model than the `gpt-oss-120b` "
        "that wrote the answers — chosen for Groq free-tier budget and to avoid self-grading). Scores are a baseline "
        "for comparing later runs, not an absolute quality measure.",
        "",
        "| metric | mean | n scored | judge errors |",
        "|---|---:|---:|---:|",
    ]
    for name, s in summary.items():
        mean = "–" if s["mean"] is None else f"{s['mean']:.2f}"
        lines.append(f"| {name} | {mean} | {s['n']} | {s['errors']} |")
    lines.append("")
    md = "\n".join(lines)
    complete = not daily_quota_hit and len(results) == len(eligible)
    if not complete:
        # A baseline built from part of the eval set would be misleading next
        # to the full-set agent results, so no results/ file is written.
        md = "PARTIAL RUN -- not written to evals/results/.\n\n" + md
    if not args.limit and complete:
        (REPO_ROOT / "evals" / "results" / f"ragas-{now:%Y-%m-%d}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
