"""Authentication core: password hashing, JWTs, sessions, rate limiting.

The JWT secret comes from the JWT_SECRET env var via app.config; there is
no hardcoded fallback anywhere in this module.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, UserSession, get_db

settings = get_settings()
logger = logging.getLogger("auth")

# ---------------------------------------------------------------------------
# Password hashing (passlib + bcrypt)
# ---------------------------------------------------------------------------

# Real hashes are always produced by bcrypt, so this constant is only ever
# *compared against*, never used to hash. Running the comparison on the
# "unknown email" path costs the same bcrypt work as a wrong password, so
# response timing does not reveal whether an email is registered.
_DUMMY_BCRYPT_HASH = (
    "$2b$12$C6UzMDM.H6dfI/f/IKcEeO7ZBpFqzMzE8lKZq0nOuL9B0mNtO2zXu"
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Constant-work bcrypt comparison against a stored hash."""
    return pwd_context.verify(password, hashed)


def verify_password_or_dummy(password: str, hashed: str | None) -> bool:
    """Verify a password, falling back to a dummy hash when the user is absent.

    Both the wrong-email and wrong-password paths run exactly one bcrypt
    comparison, so response timing does not leak account existence.
    """
    if hashed is None:
        hashed = _DUMMY_BCRYPT_HASH
    return verify_password(password, hashed)


# ---------------------------------------------------------------------------
# JWT (python-jose)
# ---------------------------------------------------------------------------


def create_access_token(*, user_id: int, expires_delta: timedelta) -> str:
    """Mint a signed JWT for the user."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Validate signature/expiry and return the user id, or raise 401."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        sub = payload.get("sub")
        if sub is None:
            raise JWTError("missing sub claim")
        return int(sub)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


# ---------------------------------------------------------------------------
# Rate limiting (slowapi) — shared by /auth/login and /auth/register
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

LOGIN_RATE_LIMIT = "5/minute"
REGISTER_RATE_LIMIT = "3/minute"


# ---------------------------------------------------------------------------
# Session rows
# ---------------------------------------------------------------------------


def issue_session(
    db: Session, *, user_id: int, token: str, expires_at: datetime
) -> None:
    """Insert the session row, log it, and commit — all in one transaction.

    Anything else the caller staged on ``db`` lands in the same transaction,
    so the session row and its audit log are written together or not at all.
    """
    db.add(UserSession(user_id=user_id, token=token, expires_at=expires_at))
    logger.info("auth: session issued for user_id=%s", user_id)
    db.commit()


def revoke_session(db: Session, token: str) -> bool:
    """Delete the session row for ``token``, log it, and commit.

    Returns True if a live row was found and deleted.
    """
    deleted = (
        db.query(UserSession)
        .filter(UserSession.token == token)
        .delete(synchronize_session=False)
    )
    if deleted:
        logger.info("auth: session revoked")
    db.commit()
    return deleted > 0


# ---------------------------------------------------------------------------
# Current-user dependency
# ---------------------------------------------------------------------------


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    qkd_session: Annotated[str | None, Cookie()] = None,
) -> User:
    """Resolve the logged-in user from the httpOnly session cookie.

    The cookie carries a JWT. The JWT must validate AND match a live
    (non-expired) user_sessions row, so server-side logout revokes access
    immediately, even before the JWT itself expires.
    """
    if qkd_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_id = decode_access_token(qkd_session)
    now = datetime.now(UTC)

    session_row = (
        db.execute(
            select(UserSession).where(
                UserSession.token == qkd_session,
                UserSession.expires_at > now,
            )
        )
        .scalars()
        .first()
    )
    if session_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or revoked",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
