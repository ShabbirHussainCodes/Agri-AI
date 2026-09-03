# ADR-0009: Separate Supabase project; BillingMars isolation

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
Shabbir already runs a separate project, **BillingMars**, on the same Supabase account (org `BillingMars`, project `billingmars-db`, `ap-northeast-1`). AgriAI must not touch it.

## Decision
AgriAI uses its **own** Supabase project `agriai-db` in region `ap-south-1` (Mumbai), with its own database, pgvector setup, auth configuration, storage configuration, and API keys. AgriAI environment variables are namespaced `AGRIAI_*`. The BillingMars project/database is never read, modified, migrated, or shared with AgriAI. (Verified by listing only; nothing was modified.)

## Why
Hard data-isolation requirement, and Mumbai region for Indian-user latency (BillingMars is in Tokyo). Namespacing prevents credential confusion.

## Consequences
- **Positive:** complete isolation; correct region; no credential mixups.
- **Trade-off (resolved 2026-08-29):** the free plan's "Limit of 2 active projects" is confirmed **per account, across all orgs** (verified against the live Supabase account) — a new org does not grant extra slots. `agriai-db` + `billingmars-db` now use both free slots; a third project will need pausing, upgrading, or deleting one of them.

## Links
`docs/deployment/deployment.md`, `docs/security/security-model.md`.
