# ADR-0001: Python + FastAPI backend, Next.js frontend

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
AgriAI needs document ingestion, RAG evaluation, computer vision, and structured-output validation, on free tiers, built by a solo developer on a Data-Scientist learning path. The earlier AgriAI v1 was Next.js + Prisma (TypeScript).

## Options considered
- **Python + FastAPI backend, Next.js frontend** — Docling, Ragas, Pydantic, PyTorch/ONNX all native; one Pydantic model doubles as LLM schema + API contract.
- **TypeScript-only (Next.js full-stack)** — one language, fastest to ship, Vercel-native; but document parsing (Docling), RAG evals (Ragas), and CV are Python-only, needing a Python sidecar later anyway.

## Decision
Python 3.12 + FastAPI as the AI backend; Next.js (App Router) PWA as frontend only.

## Why
The three capabilities AgriAI actually depends on — ingestion, evals, vision — are Python-shaped, and the project's stated goal is learning modern AI engineering, not fastest ship. One Pydantic model serving as LLM schema + FastAPI response + OpenAPI contract is genuine architectural leverage. Aligns with the Data-Scientist career path.

## Consequences
- **Positive:** best ecosystem fit; contract-first; strong learning value.
- **Trade-off:** two languages / two deploy targets (Vercel + a Python host) instead of one.
- **Follow-up:** keep the frontend free of business logic so the split stays clean.

## Links
`docs/backend/backend-architecture.md`, `docs/frontend/frontend-architecture.md`.
