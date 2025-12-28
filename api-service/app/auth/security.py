"""JWT security utilities"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from .config import auth_config


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenData(BaseModel):
    """Token payload data"""
    sub: str  # Subject (user email or ID)
    exp: datetime  # Expiration time
    iat: datetime  # Issued at
    type: str = "access"  # Token type


class User(BaseModel):
    """Authenticated user model"""
    email: str
    name: Optional[str] = None
    roles: list[str] = []

    @property
    def id(self) -> str:
        """User ID (email for now)"""
        return self.email


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token

    Args:
        data: Payload data (should include 'sub' for subject/user id)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=auth_config.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "access"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        auth_config.SECRET_KEY,
        algorithm=auth_config.ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """
    Verify and decode a JWT token

    Args:
        token: JWT token string

    Returns:
        TokenData if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token,
            auth_config.SECRET_KEY,
            algorithms=[auth_config.ALGORITHM]
        )

        sub: str = payload.get("sub")
        if sub is None:
            return None

        return TokenData(
            sub=sub,
            exp=datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc),
            iat=datetime.fromtimestamp(payload.get("iat"), tz=timezone.utc),
            type=payload.get("type", "access")
        )
    except JWTError:
        return None


def get_user_from_token(token: str) -> Optional[User]:
    """
    Extract user information from a valid token

    Args:
        token: JWT token string

    Returns:
        User object if token is valid, None otherwise
    """
    token_data = verify_token(token)
    if token_data is None:
        return None

    # In a real app, you'd look up the user in the database
    # For now, we create a User from the token data
    return User(
        email=token_data.sub,
        name=token_data.sub.split("@")[0] if "@" in token_data.sub else token_data.sub
    )


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)
