# ingest/

Corpus ingestion. **Runs on the developer laptop, not in production** (Docling needs ~6 GB RAM and this is a one-time offline job).

Pipeline: parse (Docling, with an OCR bake-off for scanned Hindi) → contextualise (v2 contextual-retrieval prefixes) → chunk → embed (local ONNX) → upsert into Postgres.

- `sources.yaml` — the corpus licence register (url, licence, permission status). Keep it honest; it answers "where did your corpus come from and are you allowed to use it?"
- Raw downloaded PDFs go in `_downloads/` (gitignored) — never committed.

See `docs/rag/rag-design.md` §7–8.
