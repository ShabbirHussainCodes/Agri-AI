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


settings = Settings()
