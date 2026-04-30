"""
Casbin RBAC enforcer — real implementation.

Loads role-permission and user-role policies from the database into
an in-memory Casbin enforcer. Supports tenant-scoped (domain) RBAC.

Model: (sub, dom, obj, act)
  - sub = "role:<NAME>" or "user:<ID>" or "apikey:<ID>"
  - dom = tenant ID ("default" if no multi-tenancy)
  - obj = resource (e.g., "asr", "tts", "nmt", "users")
  - act = action (e.g., "inference", "read", "write", "delete")
"""

import logging
import os
from typing import Iterable, Optional

import casbin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, Role, RolePermission, UserRole

logger = logging.getLogger(__name__)

_enforcer: Optional[casbin.Enforcer] = None


def get_enforcer() -> casbin.Enforcer:
    """Get the Casbin enforcer. Initializes with empty policy if not loaded yet."""
    global _enforcer
    if _enforcer is None:
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "casbin_model.conf")
        _enforcer = casbin.Enforcer(model_path)
    return _enforcer


async def load_policies_from_db(db: AsyncSession) -> None:
    """
    Load role-permission and user-role policies from DB into Casbin.
    Call on startup and whenever policies change.
    """
    global _enforcer

    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "casbin_model.conf")
    _enforcer = casbin.Enforcer(model_path)

    tenant = "default"

    # Load role → permission policies
    result = await db.execute(
        select(Role.name, Permission.resource, Permission.action)
        .join(RolePermission, Role.id == RolePermission.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
    )
    role_perms = result.all()
    for role_name, resource, action in role_perms:
        _enforcer.add_policy(f"role:{role_name}", tenant, resource, action)

    # Load user → role groupings
    result = await db.execute(
        select(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
    )
    user_roles = result.all()
    for user_id, role_name in user_roles:
        _enforcer.add_grouping_policy(f"user:{user_id}", f"role:{role_name}", tenant)

    logger.info(
        "Casbin policies loaded: %d role-permissions, %d user-roles",
        len(role_perms), len(user_roles),
    )


async def check_user_permission(
    user_id: int,
    resource: str,
    action: str,
    tenant: str = "default",
) -> bool:
    """Check if a user has permission via their roles."""
    e = get_enforcer()
    return e.enforce(f"user:{user_id}", tenant, resource, action)


async def check_roles_permission(
    roles: Iterable[str],
    resource: str,
    action: str,
    tenant: str = "default",
) -> bool:
    """Check if any of the given roles has the permission."""
    e = get_enforcer()
    for role in roles:
        if e.enforce(f"role:{role}", tenant, resource, action):
            return True
    return False


async def check_apikey_permission(
    api_key_id: int,
    permissions: list[str],
    resource: str,
    action: str,
    tenant: str = "default",
) -> bool:
    """
    Check API key permission using Casbin.
    Adds temporary policies for the API key's permission list.
    """
    e = get_enforcer()
    sub = f"apikey:{api_key_id}"

    # Clear existing policies for this API key
    existing = e.get_filtered_policy(0, sub)
    for rule in list(existing):
        e.remove_policy(*rule)

    # Add current permissions
    for perm in permissions:
        if "." not in perm:
            continue
        svc, act = perm.split(".", 1)
        # Normalize hyphens to underscores for resource matching
        normalized_resource = svc.replace("-", "_")
        e.add_policy(sub, tenant, normalized_resource, act)

    # Also check with original resource name (hyphens)
    normalized_check = resource.replace("-", "_")
    return e.enforce(sub, tenant, normalized_check, action)
