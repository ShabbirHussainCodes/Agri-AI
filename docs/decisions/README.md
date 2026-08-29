# Architecture Decision Records (ADRs)

Each ADR records one significant decision: its context, the options considered, what was chosen, why, and the consequences. ADRs are immutable once `Accepted` — to change a decision, write a new ADR that supersedes the old one (and link both ways). Trivial decisions do not get an ADR.

Format: `docs/decisions/ADR-000-template.md`.

| ADR | Title | Status |
|---|---|---|
| [0001](ADR-0001-backend-python-fastapi.md) | Python + FastAPI backend, Next.js frontend | Accepted |
| [0002](ADR-0002-agent-hand-rolled-loop.md) | Hand-rolled tool-calling loop first | Accepted |
| [0003](ADR-0003-rag-pgvector-supabase.md) | RAG on pgvector inside Supabase | Accepted |
| [0004](ADR-0004-vision-provider-and-llm-routing.md) | Vision = Groq qwen; chat = gpt-oss; Gemini free tier rejected | Accepted |
| [0005](ADR-0005-deterministic-agrochemical-safety.md) | Deterministic agrochemical safety layer | Accepted |
| [0006](ADR-0006-evidence-typed-response.md) | Evidence-typed response model | Accepted |
| [0007](ADR-0007-multilingual-retrieval.md) | Multilingual retrieval without query translation; evaluation-first | Accepted |
| [0008](ADR-0008-storage-supabase-behind-interface.md) | Supabase Storage behind a StorageProvider interface | Accepted |
| [0009](ADR-0009-supabase-project-isolation.md) | Separate Supabase project; BillingMars isolation | Accepted |
| [0010](ADR-0010-language-scope-hindi-english.md) | MVP language scope: Hindi + English only | Accepted |
