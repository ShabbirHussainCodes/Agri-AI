"""App settings, read from AGRIAI_* environment variables (see .env).

One Settings object, built once at import time, used everywhere else in
the app instead of calling os.environ directly — keeps config in one
place and gives us validation for free (Pydantic).
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/core/config.py -> repo root is four levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGRIAI_", env_file=".env", extra="ignore")

    # Postgres connection string. Local dev: the local Supabase stack's DB
    # (from `supabase start`). Production: the real agriai-db project.
    database_url: str

    # "local" | "production" — lets code (and logs) know which environment
    # they're in without re-deriving it from the database_url.
    env: str = "local"

    # Supabase-issued user JWTs are asymmetrically signed (ES256, verified
    # against a public JWKS endpoint) — both locally and on the real
    # agriai-db project, just different URLs/keys. We only ever verify
    # tokens here; Supabase Auth is what issues them.
    jwks_url: str
    jwt_audience: str = "authenticated"

    # Groq (ADR-0004). gpt-oss-120b is the "quality" model -- used for
    # both agent turns in Phase 2 (tool-call decisions and the final
    # strict-schema answer). gpt-oss-20b is kept here for later use
    # (e.g. a faster Turn A) but nothing calls it yet.
    groq_api_key: str
    groq_chat_model: str = "openai/gpt-oss-120b"
    groq_chat_model_fast: str = "openai/gpt-oss-20b"

    # Phase 4: local ONNX query embedder (app/retrieval/embedder.py).
    # Defaults to the SAME cache the ingest job already downloaded the
    # ~470 MB model into (ingest/config.py, gitignored), so local dev does
    # not download it twice. A deployed API host sets AGRIAI_EMBED_CACHE_DIR
    # to its own writable path.
    embed_cache_dir: Path = REPO_ROOT / "ingest" / "_cache" / "models"

    # How many fused chunks Turn B sees. The retrieval baseline
    # (evals/results/retrieval-2026-09-25.md) puts the gold page in the top 5
    # for 61% of questions and the top 20 for 82%; every extra passage costs
    # ~500 tokens against Groq's free-tier limits and gives the model more to
    # get distracted by. 6 is a starting point to be MEASURED by the full
    # eval, not a tuned value.
    rag_context_chunks: int = 6


settings = Settings()
