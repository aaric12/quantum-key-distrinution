"""Application settings loaded from environment variables (or a local .env)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "qkd-backend"
    debug: bool = False

    # Postgres in docker-compose; override via env DATABASE_URL if needed.
    database_url: str = "postgresql+psycopg://qkd:qkd@localhost:5432/qkd"

    # Auth. JWT_SECRET has NO default: the app refuses to start without it
    # (get_settings() raises at import time). Generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    session_expire_days: int = 7
    session_cookie_name: str = "qkd_session"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
