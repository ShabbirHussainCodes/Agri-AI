"""Ingest configuration, read from the same AGRIAI_* environment variables
as the API (see .env.example).

Kept separate from apps/api/app/core/config.py on purpose: the ingest job
runs on the laptop, needs different settings (model cache paths), and must
not drag API-only requirements (Groq keys, JWKS URLs) into scope just to
parse a PDF.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

INGEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = INGEST_DIR.parent


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGRIAI_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",
    )

    # Where the chunks land. Local Supabase stack for a first run; the real
    # agriai-db project only once the output has been eyeballed locally.
    # NOTE: ingestion writes with the service role / direct Postgres
    # connection, which bypasses RLS -- that is the design (see the corpus
    # migration's header comment), not an oversight.
    #
    # Optional on purpose: `run.py --dry-run` and `probe.py` do useful work
    # (parse, chunk, inspect) with no database at all, and requiring a URL to
    # do them would be a pointless setup step. run.py raises a clear error if
    # a real run is attempted without it.
    database_url: str | None = None

    # Hugging Face cache for the ONNX embedder. Under ingest/_cache/, which
    # is gitignored -- a ~470 MB model must never enter Git.
    embed_cache_dir: Path = INGEST_DIR / "_cache" / "models"

    # rag-design.md section 1: ~500 tokens per chunk for v1.
    chunk_max_tokens: int = 500

    # Docling OCR. Default ON -- measured, not assumed.
    #
    # Hypothesis (2026-09-07): OCR was corrupting the text layer, because
    # Docling's own docs say OCR "replaces or supplements programmatic text
    # extraction", RapidOCR returned empty on every page, and the prose came
    # out with dropped characters. An A/B run FALSIFIED this:
    #
    #   doc 10568/180732 (tomato): ocr-on vs ocr-off differ by 10 lines out of
    #     a 119 KB dump. Every truncation ("Pla height", "b ometric",
    #     "Fu thermore") and every prose/table interleave is present in BOTH.
    #     OCR contributed only Figure 5's axis labels (T1..T6, location names).
    #   doc 10568/180614 (kitchen gardens): ocr-off drops from 47 chunks to 19
    #     and pages 11-13 vanish entirely -- the Appendix 1 crop calendar is an
    #     IMAGE, and OCR is the only thing that reads it at all.
    #
    # So OCR is not the corruption source; it is the only reader of image-based
    # tables and figures. Turning it off loses the crop calendar, which is the
    # most directly useful content in that manual. Keep it ON.
    #
    # The real corruption is Docling's reading order on these two-column PDFs
    # and is unfixed -- see the Phase 3 notes.
    docling_ocr: bool = True


settings = IngestSettings()
