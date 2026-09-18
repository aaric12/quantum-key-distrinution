"""Shared SQLAlchemy setup and models for the QKD backend."""

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, text
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


def create_all() -> None:
    """Create tables from metadata if they do not exist yet.

    Good enough while the schema is small; swap for Alembic migrations when
    it grows.
    """
    Base.metadata.create_all(bind=engine)


def check_db() -> str:
    """Return 'ok' if the database answers a trivial query, else an error string."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 - health endpoint must not raise
        return f"error: {exc.__class__.__name__}"


def _utcnow() -> datetime:
    """Timezone-aware UTC now, used as a portable Python-side default.

    SQLite discards tzinfo, but since *every* timestamp is written with this
    same default, comparisons stay consistent (see get_current_user).
    """
    return datetime.now(UTC)


class User(Base):
    """Registered user. Passwords stored as passlib/bcrypt hashes only."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class UserSession(Base):
    """Server-side session row paired with the JWT stored in the auth cookie.

    Named UserSession: ``Session`` is already the SQLAlchemy sessionmaker
    import in this module. Deleting a user cascades to their sessions.
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
