"""
SQLAlchemy ORM models.

Import order matters: Tenant must be registered before User (FK dependency),
and User before UserRole / UserPassword / OAuthProvider.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.password import UserPassword  # noqa: E402
from app.models.role import Role, Permission, UserRole  # noqa: E402
from app.models.api_key import APIKey  # noqa: E402
from app.models.oauth import OAuthProvider  # noqa: E402
from app.models.verification import TokenVerification  # noqa: E402

__all__ = [
    "Base",
    "Tenant",
    "User",
    "UserPassword",
    "Role",
    "Permission",
    "UserRole",
    "APIKey",
    "OAuthProvider",
    "TokenVerification",
]
