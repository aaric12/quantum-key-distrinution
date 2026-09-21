"""Application settings loaded from environment variables (or a local .env)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings

# Local Vite dev server + `vite preview` ports.
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://localhost:4173,"
    "http://127.0.0.1:4173"
)


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
    # SameSite policy for the session cookie. "lax" is right when frontend
    # and API share a site (local dev, same-origin deploys). A split deploy
    # (frontend on vercel.app, API on onrender.com) is cross-site: browsers
    # never attach Lax cookies to cross-site fetch/WS handshakes, so auth
    # silently fails there — set SESSION_COOKIE_SAMESITE=none on the API
    # host. Chrome requires Secure with None, which uvicorn derives from
    # the request scheme; run it with --proxy-headers behind Render's TLS.
    session_cookie_samesite: str = "lax"

    # AI summaries (optional). Any OpenAI-compatible chat-completions API
    # works: point OPENAI_BASE_URL elsewhere (Groq, Together, local vLLM, ...)
    # and set OPENAI_MODEL accordingly. Empty key -> deterministic local
    # fallback summaries are served instead.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # CORS origins the browser frontend may call the API from. Comma-separated
    # via ALLOWED_ORIGINS, e.g. "https://app.example.com,https://staging.example.com".
    # Unset or blank -> the local Vite dev/preview defaults (localhost:5173/4173).
    allowed_origins: str = _DEFAULT_CORS_ORIGINS

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def cors_origins(settings: Settings | None = None) -> list[str]:
    """ALLOWED_ORIGINS split on commas into an origin list for CORSMiddleware.

    Whitespace and empty entries are dropped, so "a.com, b.com,," works.
    Blank/unset falls back to the localhost defaults (docker-compose passes
    the variable through, so "unset" arrives here as an empty string).
    """
    raw = (settings or get_settings()).allowed_origins.strip()
    if not raw:
        raw = _DEFAULT_CORS_ORIGINS
    return [o.strip() for o in raw.split(",") if o.strip()]
