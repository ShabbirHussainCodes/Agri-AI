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
    # ~380 prompt tokens (measured) against the free-tier limits and gives the model more to
    # get distracted by. MEASURED 2026-09-30 (evals/results/token-budget-
    # 2026-09-30.md): 4 saves 14.6% of tokens but loses multi-002, whose
    # evidence is ranked 5th, so 6 stays until better ranking (Phase 10).
    rag_context_chunks: int = 6

    # Phase 5 (ADR-0015): the crop/soil reference table used by the irrigation
    # water balance. Unset = data/crop_water/crop-water-v1.json in the repo.
    # Tests and the eval set this to a SYNTHETIC table; production must not.
    crop_water_table: Path | None = None

    # Phase 6 (ADR-0016): the verified agrochemical label table. Unset = data/agrochemical/
    # major-uses-v1.json in the repo (no rows ship). Tests use a SYNTHETIC one; production must not.
    agrochem_table: Path | None = None

    # ADR-0017: the browser app. The API answers cross-origin requests only from
    # this origin (plus any extras, e.g. a Vercel preview URL). JWT travels in a
    # header, never a cookie, so credentials are not allowed.
    web_base_url: str = "http://localhost:3000"
    cors_extra_origins: list[str] = []

    # ADR-0017: /ask is capped because the free-tier LLM budget is ~40 questions a
    # day (CLAUDE.md section 11) and signup is open. Rolling 24 hours. 0 = no cap:
    # use it for local development and for the eval runner, never in production.
    ask_limit_per_user_per_day: int = 10
    ask_limit_global_per_day: int = 35


settings = Settings()
