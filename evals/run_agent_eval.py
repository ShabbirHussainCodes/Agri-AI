"""Phase 4 step 6a -- end-to-end agent eval with the REAL model.

Every eval question goes through the real `POST /farms/{id}/ask` path in
process: auth, RLS, retrieval, Turn A, Turn B (Groq), code-side citation
validation, interim dose guard. Only two things are added, both as wrappers
around functions app.agent.loop already calls -- production code is not
changed for the eval:

  1. retrieve() is wrapped so prompt-injection cases can plant their
     `injected_context` into the top retrieved passage (CLAUDE.md rule 9 says
     corpus text is untrusted; this is how that is tested).
  2. finalize_advisory() is wrapped to record the model's DRAFT and the exact
     passages it saw, so scoring can tell "the model abstained" from "code
     withheld it" from "the dose guard caught it".
  3. The LLM provider is wrapped (via FastAPI's dependency override) to add
     up the tokens each question consumed, as Groq reports them -- so the
     free-tier budget is measured, not estimated. Only the final attempt of
     a retried question is counted.

Passage budget: set AGRIAI_RAG_CONTEXT_CHUNKS to change how many passages
Turn B sees (default 6); the value is printed in the summary.

Scoring is deterministic (evals/agent_eval_scoring.py). LLM-judged Ragas
metrics are step 6b (evals/run_ragas_eval.py), which reads the
`*-ragas-input.jsonl` this script writes.

Rate limits: Groq's free-tier limits are shown only in the console (CLAUDE.md
section 11), so this script does not guess them. It spaces requests by
--delay seconds, retries a failed question with exponential backoff, and
writes every result to disk as it goes, so an interrupted run continues with
--resume instead of starting over and spending the quota twice.

Run from apps/api (the API reads its .env from the working directory), with
the local Supabase stack up:
    cd apps/api
    python ../../evals/run_agent_eval.py --limit 3        # smoke test first
    python ../../evals/run_agent_eval.py                  # all questions
    python ../../evals/run_agent_eval.py --resume ../../evals/_runs/<file>.jsonl
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Order matters: apps/api must win, because both apps/api/tests and
# evals/tests are packages named `tests`, and the signup helper lives in
# apps/api/tests/conftest.py.
sys.path.insert(0, str(REPO_ROOT / "evals"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

import httpx  # noqa: E402

import agent_eval_scoring as scoring  # noqa: E402
from app.agent import loop  # noqa: E402
from app.core.config import settings  # noqa: E402

# ADR-0017: /ask caps and saves answers. An eval is 55 questions in one go: no cap.
settings.ask_limit_per_user_per_day = 0
settings.ask_limit_global_per_day = 0
from app.main import app  # noqa: E402
from app.providers.base import LLMProvider, ProviderOutputInvalid  # noqa: E402
from app.routers.ask import get_llm_provider  # noqa: E402
from tests.conftest import signup_test_user  # noqa: E402

_state: dict = {"inject": None, "capture": None, "usage": None}
_original_retrieve = loop.retrieve
_original_finalize = loop.finalize_advisory


async def _retrieve_with_injection(*args, **kwargs):
    result = await _original_retrieve(*args, **kwargs)
    planted = _state["inject"]
    if planted and result.chunks:
        top = result.chunks[0]
        poisoned = top.model_copy(update={"content": f"{top.content}\n\n{planted}"})
        result = result.model_copy(update={"chunks": [poisoned, *result.chunks[1:]]})
    return result


def _finalize_and_capture(draft, *, passages, **kwargs):
    # **kwargs passes through whatever else finalize_advisory takes (farm_data,
    # live_data, named_crops since ADR-0014), so the eval never drifts from it.
    _state["capture"] = {
        "draft": draft.model_dump(mode="json"),
        "passages": [p.model_dump(mode="json") for p in passages],
    }
    return _original_finalize(draft, passages=passages, **kwargs)


loop.retrieve = _retrieve_with_injection
loop.finalize_advisory = _finalize_and_capture


class _CountingProvider(LLMProvider):
    """Delegates to the real provider and adds up reported token usage."""

    def __init__(self, inner: LLMProvider):
        self.inner = inner

    async def chat(self, messages, **kwargs):
        try:
            result = await self.inner.chat(messages, **kwargs)
        except ProviderOutputInvalid:
            # /ask retries these once (loop.py), so the farmer would not have seen an error;
            # counted here so the provider's real reject rate stays visible in the report.
            if _state["usage"] is not None:
                _state["usage"]["provider_rejects"] += 1
            raise
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
    return {"calls": 0, "unreported_calls": 0, "provider_rejects": 0,
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _token_lines(records: list[dict]) -> list[str]:
    totals = sorted(r["usage"]["total_tokens"] for r in records
                    if r.get("usage") and r["usage"]["calls"] and not r["usage"]["unreported_calls"])
    lines = [f"- Passages shown to Turn B (rag_context_chunks): **{settings.rag_context_chunks}**"]
    tracked = [r for r in records if r.get("usage") and "attempts" in r["usage"]]
    if tracked:
        retried = [r["question"]["id"] for r in tracked if r["usage"]["attempts"] > 1]
        lines.append(f"- Questions that failed over HTTP on the first attempt (a farmer would have seen an error): "
                     f"**{len(retried)} / {len(tracked)}**" + (f" ({', '.join(retried)})" if retried else ""))
        rejected = [r["question"]["id"] for r in tracked if r["usage"].get("provider_rejects")]
        lines.append(f"- Questions where the provider rejected the model's output at least once (/ask retries once, "
                     f"then abstains with `answer_generation_failed`): **{len(rejected)} / {len(tracked)}**"
                     + (f" ({', '.join(rejected)})" if rejected else ""))
    if totals:
        mean = sum(totals) / len(totals)
        median = totals[len(totals) // 2] if len(totals) % 2 else (totals[len(totals) // 2 - 1] + totals[len(totals) // 2]) / 2
        prompt = [r["usage"]["prompt_tokens"] for r in records if r.get("usage") and r["usage"]["calls"]]
        lines.append(f"- Tokens per question, all turns (Groq-reported): mean **{mean:.0f}**, median {median:.0f}, "
                     f"min {totals[0]}, max {totals[-1]} (n={len(totals)}); mean prompt tokens {sum(prompt) / len(prompt):.0f}")
    else:
        lines.append("- Tokens per question: not recorded (run predates usage tracking, or the provider reported none)")
    return lines


def _load_done(path: Path) -> dict[str, dict]:
    done = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if not rec["row"].get("error"):
                    done[rec["question"]["id"]] = rec
    return done


async def _ask(client, headers, farm_id, question: dict, *, max_retries: int, backoff: float):
    _state["inject"] = question.get("injected_context") or None
    error = None
    # Recorded so the provider's first-attempt failure rate is measured:
    # /ask itself does not retry, so every retry here is an error a farmer
    # would have seen.
    first_error = None
    for attempt in range(max_retries + 1):
        _state["capture"] = None
        _state["usage"] = _fresh_usage()
        resp = await client.post(f"/farms/{farm_id}/ask", headers=headers, json={"question": question["question"]})
        if resp.status_code == 200:
            cap = _state["capture"] or {}
            usage = {**_state["usage"], "attempts": attempt + 1, "first_error": first_error}
            return resp.json(), cap.get("draft"), cap.get("passages", []), None, usage
        error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        first_error = first_error or error
        if attempt < max_retries:
            wait = backoff * (2 ** attempt)
            print(f"    {question['id']}: {error} -- retrying in {wait:.0f}s")
            await asyncio.sleep(wait)
    return None, None, [], error, {**_state["usage"], "attempts": max_retries + 1, "first_error": first_error}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    ap.add_argument("--only", help="comma-separated question ids")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between questions")
    ap.add_argument("--max-retries", type=int, default=4)
    ap.add_argument("--backoff", type=float, default=20.0, help="first retry wait; doubles each retry")
    ap.add_argument("--resume", type=Path, help="continue an earlier *-agent.jsonl run")
    args = ap.parse_args()

    questions = [json.loads(l) for l in (REPO_ROOT / "evals" / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    runs = REPO_ROOT / "evals" / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_path = args.resume.resolve() if args.resume else runs / f"{stamp}-agent.jsonl"
    done = _load_done(run_path)
    print(f"{len(questions)} questions, {len(done)} already done -> {run_path}")

    real_provider = get_llm_provider()
    app.dependency_overrides[get_llm_provider] = lambda: _CountingProvider(real_provider)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=None) as client:
            token = await signup_test_user()
            headers = {"Authorization": f"Bearer {token}"}
            # No crop and no location on purpose: the eval questions are about
            # the corpus, not this farm, and without lat/lon get_weather makes
            # no network call.
            farm = await client.post("/farms", headers=headers, json={"name": "Eval Farm"})
            farm.raise_for_status()
            farm_id = farm.json()["id"]

            with run_path.open("a", encoding="utf-8") as out:
                for i, q in enumerate(questions, 1):
                    if q["id"] in done:
                        continue
                    response, draft, passages, error, usage = await _ask(
                        client, headers, farm_id, q, max_retries=args.max_retries, backoff=args.backoff
                    )
                    row = scoring.score_row(q, response, draft, passages, error)
                    rec = {"question": q, "response": response, "draft": draft, "passages": passages,
                           "row": row, "usage": usage, "rag_context_chunks": settings.rag_context_chunks}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                    done[q["id"]] = rec
                    status = "ERROR" if error else ("abstain" if response["abstained"] else "answer")
                    ok = "" if error else ("ok" if row["behaviour_correct"] else "WRONG")
                    tokens = f"{usage['total_tokens']} tok" if usage and usage["calls"] else ""
                    print(f"[{i}/{len(questions)}] {q['id']:<12} {status:<8} {ok:<5} {tokens}")
                    await asyncio.sleep(args.delay)

    # Re-read the whole file so a resumed run summarises everything.
    records = [json.loads(l) for l in run_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    latest = {r["question"]["id"]: r for r in records}  # last attempt per id wins
    summary = scoring.summarise([r["row"] for r in latest.values()])

    ragas_path = run_path.with_name(run_path.name.replace("-agent.jsonl", "-ragas-input.jsonl"))
    with ragas_path.open("w", encoding="utf-8") as f:
        for r in latest.values():
            if r["response"] is None:
                continue
            f.write(json.dumps({
                "id": r["question"]["id"],
                "bucket": r["question"]["bucket"],
                "expected_behaviour": r["question"]["expected_behaviour"],
                "abstained": r["response"]["abstained"],
                "user_input": r["question"]["question"],
                "response": r["response"]["recommendation"],
                "retrieved_contexts": [p["content"] for p in r["passages"]],
                "reference": r["question"].get("reference_answer"),
            }, ensure_ascii=False) + "\n")

    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = scoring.to_markdown(summary, run_at, settings.groq_chat_model)
    md = md.rstrip("\n") + "\n\n" + "\n".join(_token_lines(list(latest.values()))) + "\n"
    results = REPO_ROOT / "evals" / "results"
    results.mkdir(exist_ok=True)
    if not args.limit and not args.only:
        (results / f"agent-{datetime.now(timezone.utc):%Y-%m-%d}.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"Ragas input: {ragas_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
