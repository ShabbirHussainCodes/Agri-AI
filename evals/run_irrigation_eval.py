"""Phase 5 irrigation eval (ADR-0015): the agent loop, the irrigation tool, the
water-balance engine, finalize and the guards, on frozen scenarios.

NO DATABASE and NO NETWORK are needed, and by default NO MODEL either:

    cd apps/api
    python ../../evals/run_irrigation_eval.py            # dry run: a scripted stand-in for the model.
                                                         # Costs no Groq quota. Checks the harness only.
    python ../../evals/run_irrigation_eval.py --live --limit 3   # the real model, 3 scenarios (costs quota)
    python ../../evals/run_irrigation_eval.py --live             # all scenarios

`--live` is the only thing that spends Groq tokens, so it must be asked for.
Get the estimated cost agreed first (the 3-scenario smoke run measures it).
Only a full `--live` run writes evals/results/irrigation-<date>.md; a dry run or
a partial run never produces a "result", so a harness check cannot be mistaken
for a baseline.

What is frozen and what is real is explained in evals/irrigation_eval_world.py.
The scoring rules (safety zero-tolerance, quality as baseline) are in
evals/irrigation_eval_scoring.py.
"""
import argparse
import asyncio
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "evals"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

import irrigation_eval_scoring as scoring  # noqa: E402
import irrigation_eval_world as world  # noqa: E402
from app.agent import loop  # noqa: E402
from app.agent.tools import irrigation  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.errors import AgentError  # noqa: E402
from app.providers.base import LLMProvider  # noqa: E402
from app.retrieval.hybrid import RetrievalResult  # noqa: E402

_state: dict = {"capture": None, "usage": None}
_original_finalize = loop.finalize_advisory


@contextmanager
def _patched(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


def _finalize_and_capture(draft, **kwargs):
    _state["capture"] = draft.model_dump(mode="json")
    return _original_finalize(draft, **kwargs)


class _CountingProvider(LLMProvider):
    """Delegates to the real provider and adds up reported token usage."""

    def __init__(self, inner: LLMProvider):
        self.inner = inner

    async def chat(self, messages, **kwargs):
        result = await self.inner.chat(messages, **kwargs)
        u = _state["usage"]
        if u is not None:
            u["calls"] += 1
            if result.usage is None:
                u["unreported_calls"] += 1
            else:
                u["prompt_tokens"] += result.usage.prompt_tokens
                u["completion_tokens"] += result.usage.completion_tokens
                u["total_tokens"] += result.usage.total_tokens
        return result


def _fresh_usage() -> dict:
    return {"calls": 0, "unreported_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


async def run_scenario(scenario: dict, provider: LLMProvider, model: str):
    """One scenario through the real loop in the frozen world. Returns
    (response_dict | None, draft_dict | None, error | None)."""
    real_status = irrigation.get_irrigation_status

    async def status_in_frozen_world(conn, farm_id, **kw):
        return await real_status(conn, farm_id, fetch=world.make_fetch(scenario), now=world.FROZEN_NOW, **kw)

    async def farm_record(conn, farm_id):
        return world.farm_context_for(scenario)

    async def no_passages(conn, embedder, question, **kw):
        return RetrievalResult(query=question, tier="unfiltered", accepted=True, top_dense_similarity=None, chunks=[])

    _state["capture"] = None
    with (
        _patched(settings, "crop_water_table", world.FIXTURE_TABLE),
        _patched(irrigation, "get_irrigation_status", status_in_frozen_world),
        _patched(loop.farm_context, "get_farm_context", farm_record),
        _patched(loop, "retrieve", no_passages),
        _patched(loop, "finalize_advisory", _finalize_and_capture),
    ):
        try:
            response = await loop.run_agent(
                provider, world.FakeConn(scenario), "eval-farm", scenario["question"],
                model=model, embedder=object(),
            )
        except AgentError as exc:
            return None, None, f"AgentError: {exc}"
    return response.model_dump(mode="json"), _state["capture"], None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use the real Groq model (spends quota)")
    ap.add_argument("--limit", type=int, help="only the first N scenarios (smoke test)")
    ap.add_argument("--only", help="comma-separated scenario ids")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between scenarios (live)")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--backoff", type=float, default=20.0)
    args = ap.parse_args()

    scenarios = world.load_scenarios()
    if args.only:
        wanted = set(args.only.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]
    if args.limit:
        scenarios = scenarios[: args.limit]

    mode = "live" if args.live else "dry-run"
    if args.live:
        from app.providers.groq_provider import GroqProvider
        inner: LLMProvider = GroqProvider(api_key=settings.groq_api_key)
        model = settings.groq_chat_model
    else:
        inner, model = world.DryRunProvider(), "dry-run"
    provider = _CountingProvider(inner)

    runs = REPO_ROOT / "evals" / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_path = runs / f"{stamp}-irrigation-{mode}.jsonl"
    print(f"{len(scenarios)} scenarios, mode {mode} -> {run_path}")

    records = []
    with run_path.open("a", encoding="utf-8") as out:
        for i, sc in enumerate(scenarios, 1):
            response = draft = error = None
            first_error = None
            for attempt in range(args.max_retries + 1 if args.live else 1):
                _state["usage"] = _fresh_usage()
                response, draft, error = await run_scenario(sc, provider, model)
                if error is None:
                    break
                first_error = first_error or error
                if args.live and attempt < args.max_retries:
                    wait = args.backoff * (2 ** attempt)
                    print(f"    {sc['id']}: {error[:120]} -- retrying in {wait:.0f}s")
                    await asyncio.sleep(wait)
            usage = {**_state["usage"], "first_error": first_error}
            row = scoring.score_row(sc, response, draft, error)
            rec = {"scenario": sc, "response": response, "draft": draft, "row": row, "usage": usage}
            records.append(rec)
            out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            out.flush()
            status = "ERROR" if error else ("abstain" if response["abstained"] else "answer")
            flag = "" if error else ("ok" if row["outcome_correct"] else "WRONG")
            tokens = f"{usage['total_tokens']} tok" if usage["calls"] and args.live else ""
            print(f"[{i}/{len(scenarios)}] {sc['id']:<8} {status:<8} {flag:<5} {tokens}")
            if args.live:
                await asyncio.sleep(args.delay)

    summary = scoring.summarise([r["row"] for r in records])
    md = scoring.to_markdown(summary, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), model, mode)
    totals = sorted(r["usage"]["total_tokens"] for r in records if r["usage"]["calls"] and not r["usage"]["unreported_calls"])
    if args.live and totals:
        retried = [r["scenario"]["id"] for r in records if r["usage"]["first_error"]]
        md += (
            f"\n## Tokens (Groq-reported)\n\n"
            f"- Per scenario, all calls: mean **{sum(totals) / len(totals):.0f}**, median {totals[len(totals) // 2]}, "
            f"min {totals[0]}, max {totals[-1]} (n={len(totals)}).\n"
            f"- Scenarios that failed on the first attempt: {len(retried)} / {len(records)}"
            + (f" ({', '.join(retried)})" if retried else "")
            + "\n- Retrieval returned nothing in this harness; a tomato question in production would add its passages.\n"
        )
    if args.live and not args.limit and not args.only:
        results = REPO_ROOT / "evals" / "results"
        results.mkdir(exist_ok=True)
        (results / f"irrigation-{datetime.now(timezone.utc):%Y-%m-%d}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if summary["safety_pass"] and not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
