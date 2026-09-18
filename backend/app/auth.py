"""Authentication scaffolding.

Intentionally minimal for now: endpoints stay open during initial development.
Wire real token verification here (e.g. python-jose + passlib) before locking
routes down.
"""

from typing import Annotated

from fastapi import Depends


class User:
    """Minimal user identity placeholder."""

    def __init__(self, username: str = "anonymous") -> None:
        self.username = username


async def get_current_user() -> User:
    """Dependency that will later validate JWTs / sessions and raise 401."""
    return User()


CurrentUser = Annotated[User, Depends(get_current_user)]
