"""Shared SQLAlchemy setup and models for the QKD backend."""

from collections.abc import Generator

from sqlalchemy import DateTime, Integer, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings

DATABASE_URL = get_settings().database_url

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db() -> str:
    """Return 'ok' if the database answers a trivial query, else an error string."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 - health endpoint must not raise
        return f"error: {exc.__class__.__name__}"


class HealthCheck(Base):
    """Example table so metadata is non-empty from day one.

    Replace with real QKD domain models (sessions, keys, runs) as they are built.
    """

    __tablename__ = "health_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checked_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
