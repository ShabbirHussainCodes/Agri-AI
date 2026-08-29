"""App settings, read from AGRIAI_* environment variables (see .env).

One Settings object, built once at import time, used everywhere else in
the app instead of calling os.environ directly — keeps config in one
place and gives us validation for free (Pydantic).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()
