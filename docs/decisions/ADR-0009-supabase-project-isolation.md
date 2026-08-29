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
- **Trade-off / open item:** the free plan's "Limit of 2 active projects" — BillingMars uses one slot, and it's undocumented whether the limit is per-org or per-account. **Check the dashboard before creating `agriai-db`;** if per-org, use a new free org so BillingMars' slot is untouched.

## Links
`docs/deployment/deployment.md`, `docs/security/security-model.md`.
