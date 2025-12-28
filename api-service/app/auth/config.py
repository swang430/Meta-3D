"""Authentication configuration"""
import os
from pydantic import BaseModel


class AuthConfig(BaseModel):
    """Authentication configuration settings"""

    # JWT Settings
    SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY",
        "dev-secret-key-change-in-production"  # Default for development
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

    # Auth mode: "required", "optional", "disabled"
    # - required: All protected endpoints require valid JWT
    # - optional: JWT is validated if present, but not required
    # - disabled: No authentication (development mode)
    AUTH_MODE: str = os.getenv("AUTH_MODE", "optional")

    @property
    def is_auth_required(self) -> bool:
        return self.AUTH_MODE == "required"

    @property
    def is_auth_disabled(self) -> bool:
        return self.AUTH_MODE == "disabled"


# Global config instance
auth_config = AuthConfig()
