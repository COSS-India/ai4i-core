"""
SQLAlchemy ORM models.

Import order: Tenant first (FK dependency for User), then User,
then all tables that FK back to users.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

from app.models.tenant import Tenant  # noqa: E402
from app.models.tenant_plan import TenantPlan  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.credentials import UserCredentials  # noqa: E402
from app.models.role import Role, Permission, UserRole, RolePermission  # noqa: E402
from app.models.application import Application  # noqa: E402
from app.models.api_key import APIKey  # noqa: E402
from app.models.verification import TokenVerification  # noqa: E402
from app.models.refresh import RefreshToken  # noqa: E402

__all__ = [
    "Base",
    "Tenant",
    "TenantPlan",
    "User",
    "UserCredentials",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "Application",
    "APIKey",
    "TokenVerification",
    "RefreshToken",
]
