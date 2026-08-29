# ADR-0008: Supabase Storage behind a StorageProvider interface

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
Crop-disease photos need object storage on a free tier, with per-farmer access control and privacy.

## Options considered
- **Supabase Storage** — 1 GB free, egress shared with API responses (5 GB), but access control is the same `auth.uid()` RLS policy as the rest of the farm data; one SDK, one auth model, one vendor/DPA.
- **Cloudflare R2** — 10 GB, zero egress, but a separate account/credentials, a self-built signed-URL layer, an extra trust boundary, and an unverified card requirement.

## Decision
Supabase Storage for the MVP, behind a `StorageProvider` interface. Migrate to R2 only if actual constraints justify it (trigger: storage > 800 MB or egress > 4 GB).

## Why
At this scale (≈1,000–2,000 compressed photos in 1 GB, with client-side resize) R2's headroom isn't needed yet, and R2's cost is complexity and a second trust boundary for farmer photos. RLS integration is decisive: photo access uses the same policy as farm data — exactly where student projects otherwise leak. The interface keeps the migration cheap.

## Consequences
- **Positive:** simplest, RLS-aligned, one vendor for DB+auth+storage.
- **Trade-offs:** shared egress budget; must watch usage and honour the migration trigger.

## Links
`docs/security/security-model.md`, `docs/deployment/deployment.md`.
