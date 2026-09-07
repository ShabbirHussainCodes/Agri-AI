# ingest/

Corpus ingestion. **Runs on the developer laptop, not in production** (Docling needs ~6 GB RAM and this is a one-time offline job).

Pipeline: parse (Docling) → chunk (structure-aware, page + heading provenance) → embed (local ONNX `multilingual-e5-small`) → upsert into Postgres (`public.documents`, `public.chunks`).

## Files

| File | Role |
|---|---|
| `sources.yaml` | The corpus **licence register** — every source, its licence, and the specific `approved_items` a human signed off. The pipeline reads this, so an unregistered PDF cannot be ingested by accident. |
| `config.py` | `AGRIAI_*` settings (same convention as the API). |
| `sources.py` | Loads the register; refuses any licence outside the commercial-safe allow-list. |
| `parse_chunk.py` | Docling parse + `HybridChunker`; extracts `page_no` and `section_path`. |
| `embed.py` | ONNX `multilingual-e5-small`. Owns the `passage:`/`query:` prefixes and mean pooling. |
| `db.py` | Writes to `public.documents` / `public.chunks`. |
| `run.py` | The CLI orchestrator. |
| `probe.py` | One-off check of what the *installed* Docling actually returns, before trusting the metadata mapping. |

Raw downloaded PDFs live in `_downloads/` and the embedder model in `_cache/` — both gitignored, never committed.

## Setup (laptop)

```bash
cd ingest
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip freeze > requirements.lock.txt     # pin the versions that actually resolved
```

`AGRIAI_DATABASE_URL` must point at the database you want to write. Start with the **local** Supabase stack (`supabase start`), not the real `agriai-db` project.

## Running

```bash
# 0. Confirm the installed Docling gives us page numbers + headings.
python probe.py

# 1. Parse and chunk only — writes nothing, prints a per-document summary.
python run.py --dry-run

# 1b. Same, but also write every chunk to _cache/dumps/ so you can actually
#     read what Docling extracted (the only way to check tables).
python run.py --dry-run --dump

# 2. Full run: parse, chunk, embed, upsert.
python run.py

# One document at a time:
python run.py --handle 10568/180614
```

Re-running is idempotent: documents are keyed on their repository handle, and a document's chunks are deleted and re-inserted inside one transaction.

## Notes

- **Ingestion bypasses RLS by design.** It connects directly to Postgres; the corpus tables have a read-only policy for `authenticated` and no write policy at all, so this job is the only writer. Never import `db.py` from the API.
- **Page numbers matter.** `rag-design.md` §6 builds citations from them. `run.py` warns loudly if a document produced none.
- **Chunking deviates from `rag-design.md` §5** (which specifies recursive/fixed chunking with 15% overlap). We use Docling's structure-aware `HybridChunker` instead, because it is what supplies `page_no` and `section_path` — see the module docstring in `parse_chunk.py`. **Pending Shabbir's sign-off.**
- **Embeddings are contextualised, stored text is not.** `chunks.content` holds the raw chunk (that is what gets cited); the vector is built from the same chunk with its heading trail prepended, via Docling's `contextualize()`. Without this, a chunk saying "apply at 15 days after transplanting" has nothing in its vector tying it to tomato — the orphaned-chunk problem in `rag-design.md` §5.
- **Docling OCR stays ON** (`AGRIAI_DOCLING_OCR`), and that was measured, not assumed. An ocr-on/ocr-off A/B on both Phase 3 documents showed OCR is *not* the source of the text corruption — the tomato article's dumps differ by 10 lines out of 119 KB, and every truncation and prose/table interleave appears in both. Meanwhile turning OCR off drops the kitchen-garden manual from 47 chunks to 19 and loses pages 11–13 completely, because its Appendix 1 crop calendar is an **image**, and OCR is the only thing that reads it. Compare runs with `--dump`: dump filenames carry the mode.
- **Known unfixed: reading order on two-column PDFs.** Both documents show dropped end-of-line characters ("Pla height", "b ometric") and, around large tables, body prose spliced into table rows. This comes from the PDF text layer / layout order, not OCR. Affects ~12 of 85 chunks in the tomato article and the crop-calendar month headers (`Jul` is misread as `inr`/`nf`/`ot`).
- **Chunks under 15 tokens are dropped** as page furniture (journal labels like "Article", running heads). Every dropped chunk is printed, never silently discarded.
- OCR bake-off for scanned Hindi (`rag-design.md` §8) is **not** done yet: both Phase 3 documents are digital-native English PDFs, so there is nothing to bake off until a scanned Hindi source is registered.

See `docs/rag/rag-design.md` §7–8 and `docs/decisions/ADR-0007-multilingual-retrieval.md`.
