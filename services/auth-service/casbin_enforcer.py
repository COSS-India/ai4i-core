import os
import logging
from typing import Iterable, Optional

import casbin
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import Role, Permission, RolePermission, UserRole

logger = logging.getLogger(__name__)

# Global enforcer instance (will be initialized from DB)
_enforcer: Optional[casbin.Enforcer] = None


def get_enforcer() -> casbin.Enforcer:
    """
    Get the Casbin enforcer instance.
    
    The enforcer is initialized from the database on startup.
    If not initialized yet, creates a basic enforcer (for testing/fallback).
    """
    global _enforcer
    if _enforcer is None:
        # Fallback: create enforcer with empty policy (will be loaded from DB)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(base_dir, "casbin_model.conf")
        _enforcer = casbin.Enforcer(model_path)
    return _enforcer


async def load_policies_from_db(db: AsyncSession) -> None:
    """
    Load role-permission policies from the database into Casbin enforcer.
    
    This function:
    1. Clears existing policies
    2. Loads all role-permission mappings from role_permissions table
    3. Loads all user-role mappings from user_roles table
    
    Should be called on startup and whenever policies change.
    """
    global _enforcer
    
    # Initialize enforcer if not already done
    if _enforcer is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(base_dir, "casbin_model.conf")
        _enforcer = casbin.Enforcer(model_path)
    
    # Clear existing policies
    _enforcer.clear_policy()
    
    # Load role-permission policies
    # Query: Join Role, RolePermission, Permission to get (role_name, resource, action)
    result = await db.execute(
        select(Role.name, Permission.resource, Permission.action)
        .join(RolePermission, Role.id == RolePermission.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
    )
    
    role_perms = result.all()
    tenant = "default"  # tenant-ready: can be parameterized later
    
    for role_name, resource, action in role_perms:
        sub = f"role:{role_name}"
        _enforcer.add_policy(sub, tenant, resource, action)
    
    # Load user-role mappings (g = _, _, _ means user has role in tenant)
    user_role_result = await db.execute(
        select(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
    )
    
    user_roles = user_role_result.all()
    for user_id, role_name in user_roles:
        user_sub = f"user:{user_id}"
        role_sub = f"role:{role_name}"
        # Use grouping policy for RBAC with domains: g, sub, role, dom
        _enforcer.add_grouping_policy(user_sub, role_sub, tenant)
    
    logger.info(f"Loaded {len(role_perms)} role-permission policies and {len(user_roles)} user-role mappings into Casbin")


async def check_roles_permission(
    roles: Iterable[str],
    obj: str,
    act: str,
    tenant: str = "default",
) -> bool:
    """
    Check if any of the given roles is allowed to perform (obj, act) in a tenant.

    Roles should be plain names like 'ADMIN', 'MODERATOR', 'USER', 'GUEST'.
    They are mapped to Casbin subjects 'role:<NAME>'.
    
    Policies are loaded from the database (role_permissions table).
    """
    e = get_enforcer()
    for role in roles:
        sub = f"role:{role}"
        if e.enforce(sub, tenant, obj, act):
            return True
    return False


async def check_user_permission(
    user_id: int,
    obj: str,
    act: str,
    tenant: str = "default",
) -> bool:
    """
    Check if a user (by ID) is allowed to perform (obj, act) in a tenant.
    
    This checks the user's roles (from user_roles table) and their permissions.
    """
    e = get_enforcer()
    user_sub = f"user:{user_id}"
    return e.enforce(user_sub, tenant, obj, act)


async def check_apikey_permission(
    api_key_id: int,
    permissions: Iterable[str],
    obj: str,
    act: str,
    tenant: str = "default",
) -> bool:
    """
    Check API key permission using Casbin, based on the key's permission strings.

    - api_key_id: primary key of the API key record.
    - permissions: list like 'asr.inference', 'tts.read', etc.

    We map each permission into a temporary policy for subject 'apikey:<id>'.
    This keeps code ready for a future DB-backed policy store without changing
    enforcement call sites.
    """
    e = get_enforcer()
    sub = f"apikey:{api_key_id}"

    # Remove any existing policies for this API key subject
    existing = e.get_filtered_policy(0, sub)
    for rule in list(existing):
        e.remove_policy(*rule)

    # Add current permissions as policies
    for perm in permissions:
        if "." not in perm:
            continue
        service, action = perm.split(".", 1)
        e.add_policy(sub, tenant, service, action)

    return e.enforce(sub, tenant, obj, act)


