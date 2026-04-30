"""
SQLAlchemy ORM models.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

from app.models.user import User  # noqa: E402
from app.models.session import UserSession  # noqa: E402
from app.models.api_key import APIKey  # noqa: E402
from app.models.role import Role, Permission, UserRole, RolePermission  # noqa: E402
from app.models.oauth import OAuthProvider  # noqa: E402

__all__ = [
    "Base",
    "User",
    "UserSession",
    "APIKey",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "OAuthProvider",
]
