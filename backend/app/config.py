"""Application settings loaded from environment variables (or a local .env)."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "qkd-backend"
    debug: bool = False

    # Postgres in docker-compose; override via env DATABASE_URL if needed.
    database_url: str = "postgresql+psycopg://qkd:qkd@localhost:5432/qkd"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
