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


# ⚠️ ARCH-1 S4c (2026-07-29): ``require_auth`` 自此在整个 API 层**零使用点**。
# 唯一的使用者是 ``POST /test-plans`` (建计划), 随 S4b 计划链拆除而删。
# 后果: ``AUTH_MODE=required`` 这个配置项**不再保护任何端点** —— 其余端点本来
# 就没挂鉴权, 不是本片新开的洞, 但本片让这个事实彻底裸露。
# 显式记在这里而不是悄悄留着: 谁下次配 AUTH_MODE 时该一眼看见它现在是空转的。
# 真做鉴权是独立立项 (定哪些端点要保护 + 怎么发/验 token)。
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
