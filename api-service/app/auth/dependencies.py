"""FastAPI authentication dependencies"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import auth_config
from .security import get_user_from_token, User


# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """
    Dependency that requires authentication.

    Returns the authenticated user or raises 401 if not authenticated.
    """
    # If auth is disabled, return a default dev user
    if auth_config.is_auth_disabled:
        return User(email="dev@localhost", name="Developer")

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_from_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """
    Dependency that optionally extracts the authenticated user.

    Returns the user if authenticated, None otherwise.
    Does not raise errors - useful for endpoints that work both
    with and without authentication.
    """
    # If auth is disabled, return a default dev user
    if auth_config.is_auth_disabled:
        return User(email="dev@localhost", name="Developer")

    if credentials is None:
        return None

    return get_user_from_token(credentials.credentials)


def require_auth():
    """
    Dependency that enforces authentication based on AUTH_MODE.

    Use this for endpoints that should require auth in production
    but can be accessed without auth in development.

    Usage:
        @router.post("/endpoint")
        def endpoint(
            user: User = Depends(require_auth())
        ):
            ...
    """
    async def _require_auth(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> Optional[User]:
        # If auth mode is "optional", don't require but validate if present
        if auth_config.AUTH_MODE == "optional":
            if credentials is None:
                return None
            user = get_user_from_token(credentials.credentials)
            if user is None:
                # Invalid token provided - still reject
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user

        # If auth is disabled, return default user
        if auth_config.is_auth_disabled:
            return User(email="dev@localhost", name="Developer")

        # Auth is required
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = get_user_from_token(credentials.credentials)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user

    return _require_auth
