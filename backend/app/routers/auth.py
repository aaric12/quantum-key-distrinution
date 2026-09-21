"""Auth endpoints: register, login, logout, me.

- Passwords: passlib[bcrypt].
- Tokens:    python-jose JWT (HS256, secret from JWT_SECRET env var).
- Cookie:    JWT lives in an httpOnly cookie; never exposed to JS.
- Sessions:  a user_sessions row is created on login and deleted on logout;
              session creation + audit logging run in one DB transaction.
- Login verifies against a dummy bcrypt hash when the email is unknown, so
  response timing does not reveal whether an account exists.
- /auth/login and /auth/register are rate-limited with slowapi.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.models import User, get_db

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_session_cookie(
    request: Request, response: Response, token: str, expires_at: datetime
) -> None:
    """Store the JWT in an httpOnly cookie (never localStorage).

    ``Secure`` follows the request scheme so the cookie actually round-trips
    on plain-http local dev while staying https-only in production. Behind a
    TLS-terminating proxy, run uvicorn with --proxy-headers so the scheme
    reflects the original request.
    """
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        expires=max_age,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def _issue_login(
    db: Session, *, user: User, request: Request, response: Response
) -> None:
    """Mint the JWT, insert the session row, and set the cookie.

    JWT expiry matches the session row's expiry: the server-side row is the
    revocation gate, so the two must not disagree about how long a login
    lasts. Session insert + audit log commit together inside
    auth.issue_session — a crash cannot leave a cookie-valid token with no
    server-side row.
    """
    expires_delta = timedelta(days=settings.session_expire_days)
    expires_at = datetime.now(UTC) + expires_delta
    token = auth.create_access_token(user_id=user.id, expires_delta=expires_delta)
    auth.issue_session(db, user_id=user.id, token=token, expires_at=expires_at)
    _set_session_cookie(request, response, token, expires_at)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@auth.limiter.limit(auth.REGISTER_RATE_LIMIT)
def register(
    request: Request,
    payload: RegisterIn,
    db: DbDep,
) -> User:
    email = payload.email.lower().strip()

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=auth.hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # race with a concurrent registration
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    db.refresh(user)
    return user


@router.post("/login", response_model=UserOut)
@auth.limiter.limit(auth.LOGIN_RATE_LIMIT)
def login(
    request: Request,
    payload: LoginIn,
    db: DbDep,
    response: Response,
) -> User:
    email = payload.email.lower().strip()

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    # Always run exactly one bcrypt comparison — against the real hash when
    # the user exists, against a dummy hash otherwise — so a wrong email and
    # a wrong password take the same time.
    if not auth.verify_password_or_dummy(
        payload.password, user.password_hash if user else None
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    _issue_login(db, user=user, request=request, response=response)
    return user


@router.post("/logout")
def logout(
    db: DbDep,
    response: Response,
    qkd_session: Annotated[
        str | None, Cookie(alias=settings.session_cookie_name)
    ] = None,
) -> dict[str, bool]:
    """Revoke the server-side session and clear the cookie.

    Works even when the JWT itself is already expired: the cookie value is
    read directly so the session row can always be deleted.
    """
    if qkd_session is not None:
        auth.revoke_session(db, token=qkd_session)
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: auth.CurrentUser) -> User:
    return user
