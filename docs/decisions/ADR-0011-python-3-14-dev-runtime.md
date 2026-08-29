# ADR-0011: Use Python 3.14 (not 3.12) for the AI backend

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Shabbir (+ Claude)
- **Supersedes:** the Python-version clause of ADR-0001 (rest of ADR-0001 is unchanged)

## Context
ADR-0001 locked "Python 3.12" as a modern, stable choice at proposal time — not because any planned dependency requires exactly 3.12. During Phase 1 environment setup, Shabbir's actual dev machine has Python 3.14.6 as `python3`, with no 3.12 installed. Installing 3.12 specifically would need an extra tool (pyenv/Homebrew) with no technical benefit identified.

## Options considered
- **Install Python 3.12 to match ADR-0001 exactly** — extra tooling, extra step, matches the original document literally.
- **Use Python 3.14 (already present) and update the record** — zero extra setup; needs verification that core dependencies install cleanly.

## Decision
Use **Python 3.14** for local development; target "3.12+" generally (no code will rely on a 3.12-only language feature).

## Why
Verified directly: `fastapi`, `asyncpg`, `pydantic-settings`, `pyjwt[crypto]`, `pytest`, `pytest-asyncio`, `httpx`, `uvicorn[standard]` all installed cleanly on Python 3.14 (arm64 Mac) with prebuilt wheels — no source compilation, no errors. Nothing in AgriAI's Phase 1 stack depends on a 3.12-specific feature, so pinning to the machine's actual, working Python avoids unnecessary tooling for zero benefit.

## Consequences
- **Positive:** no pyenv/Homebrew Python management needed; dev environment matches what's actually installed and already verified working.
- **Trade-off / watch-item:** a later phase may add a more specialized ML dependency (e.g. ONNX runtime for embeddings/vision in Phases 2–7) that could lag on 3.14 wheel availability. Re-verify a clean install when each such dependency is first added; if one truly requires an older Python, revisit then rather than pre-emptively downgrading now.
- **Follow-up:** `CLAUDE.md` §3 and ADR-0001 updated to point here.

## Links
`CLAUDE.md` §3 (tech stack), ADR-0001.
