"""Shared SQLAlchemy setup and models for the QKD backend."""

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
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


class SimulationRun(Base):
    """One executed protocol simulation, owned by the user who ran it.

    Summary columns mirror the fields of protocols.bb84.BB84Result so the
    run list never has to deserialize the big JSON blob. The full result
    (every intermediate stage) lives in ``result_json``.
    """

    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    n_qubits: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qber: Mapped[float | None] = mapped_column(Float, nullable=True)
    aborted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attack_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attack_intensity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    abort_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sifted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_key_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )


class HardwareJob(Base):
    """A real-hardware execution request, owned by its user.

    Security: the IBM Quantum token is deliberately NOT a column here (and
    must never become one). The token lives only in request memory for the
    instant needed to construct the runtime service; this row records the
    handle (IBM job id) and public status so progress can be streamed.
    """

    __tablename__ = "hardware_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    ibm_job_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    backend_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    n_qubits: Mapped[int] = mapped_column(Integer, nullable=False)
    shots: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class Report(Base):
    """A shareable, read-only snapshot of one simulation run.

    Intentionally NOT linked to the users table: the row is keyed by an
    unguessable UUID, readable by anyone who has the link, and deliberately
    detached from user accounts (no user_id column, no cascade). Deleting a
    user must not break shared report links.
    """

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )


class ProtocolStageLog(Base):
    """One completed stage of a simulation run, in execution order.

    Emitted both to the WebSocket (as JSON) and to this table, so a past run
    can be replayed stage-by-stage from the DB alone.
    """

    __tablename__ = "protocol_stage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
