# ADR-0002: Hand-rolled tool-calling loop first

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
The agent needs tool calling over a small set of read/write tools for a single advisory agent, built by a solo learner who wants to actually understand the mechanics.

## Options considered
- **Hand-rolled loop** — ~80 lines; highest learning value; no vendor lock-in; you understand exactly what happens.
- **LangGraph** — powerful but a high-concept graph/state model; overkill at first; pulls toward LangSmith.
- **CrewAI / multi-agent** — wrong shape for one advisory agent; hides the mechanics; extra token cost per turn.
- **Pydantic AI** — clean, typed, first-class Groq provider; the natural *later* migration.

## Decision
Hand-roll the tool loop for v1. Adopt Pydantic AI later only if a real need appears (durable retries, human-in-the-loop approval, richer eval harness). No LangGraph/CrewAI on day one.

## Why
Anthropic's own guidance is to start with the API directly. It is the highest learning-value artifact in the project, and every extra agent turn costs a real slice of the free-tier token budget, so a lean loop is also cheaper. Migration to Pydantic AI is a string-swap, not a rewrite, since it supports Groq and the same fallback ladder.

## Consequences
- **Positive:** deep understanding; minimal dependencies; cheap.
- **Trade-off:** we build memory/retry/HITL ourselves if/when needed.
- **Follow-up:** record the Pydantic AI migration in a new ADR when triggered.

## Links
`docs/ai/agent-design.md`.
