"""Deterministic safety layer (CLAUDE.md rules 1-2, ADR-0005).

Runs AFTER the LLM, in code, so no model output and no prompt-injected text
can skip it. The full layer (CIB&RC label table, banned-molecule denylist,
dose lookup) is Phase 6. Until then only interim_dose_guard.py lives here.
"""
