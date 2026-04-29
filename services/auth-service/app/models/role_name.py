"""Canonical platform role names (mirror ai4iplatform_auth seed data)."""

from __future__ import annotations

import enum


class RoleName(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"
    GUEST = "GUEST"
    MODERATOR = "MODERATOR"
    TENANT_ADMIN = "TENANT ADMIN"


def role_name_to_str(name: RoleName | str) -> str:
    """Normalize ORM enum members or API strings to plain str."""
    return name.value if isinstance(name, RoleName) else name
