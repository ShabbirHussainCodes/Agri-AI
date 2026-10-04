"""Typed clients for external data APIs (docs/backend/backend-architecture.md).
Each one has an explicit timeout and turns every failure into its own error
type, so a caller can say "unavailable" instead of crashing."""
