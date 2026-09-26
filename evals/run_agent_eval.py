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
from app.main import app  # noqa: E402
from tests.conftest import signup_test_user  # noqa: E402

_state: dict = {"inject": None, "capture": None}
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


def _finalize_and_capture(draft, *, farm_data, live_data, passages):
    _state["capture"] = {
        "draft": draft.model_dump(mode="json"),
        "passages": [p.model_dump(mode="json") for p in passages],
    }
    return _original_finalize(draft, farm_data=farm_data, live_data=live_data, passages=passages)


loop.retrieve = _retrieve_with_injection
loop.finalize_advisory = _finalize_and_capture


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
    for attempt in range(max_retries + 1):
        _state["capture"] = None
        resp = await client.post(f"/farms/{farm_id}/ask", headers=headers, json={"question": question["question"]})
        if resp.status_code == 200:
            cap = _state["capture"] or {}
            return resp.json(), cap.get("draft"), cap.get("passages", []), None
        error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        if attempt < max_retries:
            wait = backoff * (2 ** attempt)
            print(f"    {question['id']}: {error} -- retrying in {wait:.0f}s")
            await asyncio.sleep(wait)
    return None, None, [], error


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
                    response, draft, passages, error = await _ask(
                        client, headers, farm_id, q, max_retries=args.max_retries, backoff=args.backoff
                    )
                    row = scoring.score_row(q, response, draft, passages, error)
                    rec = {"question": q, "response": response, "draft": draft, "passages": passages, "row": row}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                    done[q["id"]] = rec
                    status = "ERROR" if error else ("abstain" if response["abstained"] else "answer")
                    ok = "" if error else ("ok" if row["behaviour_correct"] else "WRONG")
                    print(f"[{i}/{len(questions)}] {q['id']:<12} {status:<8} {ok}")
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
    results = REPO_ROOT / "evals" / "results"
    results.mkdir(exist_ok=True)
    if not args.limit and not args.only:
        (results / f"agent-{datetime.now(timezone.utc):%Y-%m-%d}.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"Ragas input: {ragas_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
