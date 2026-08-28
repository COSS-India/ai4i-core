"""
Shared caller-scope authorization for Institution-scoped resources.

Application Management (ApplicationService) and Allocation Management
(AllocationService — PUT /auth/allocations) enforce the exact same "who may
touch this Institution's data" rule, so it lives here once instead of being
copy-pasted a second time.
"""

from fastapi import HTTPException, status

from app.core.constants import RoleName
from app.core.exceptions import InsufficientPermissionsError
from app.models.user import User
from app.repositories.role_repository import RoleRepository


async def authorize_institution_scope(
    role_repo: RoleRepository, user: User, tenant_id: int
) -> None:
    """Only Adopter Admin (ADMIN) and Institution Admin (TENANT_ADMIN) may
    touch an Institution's Application/Allocation data — everyone else,
    MODERATOR included, is rejected. A higher role carries every permission a
    lower one has: ADMIN may act on any Institution's data (the edge case —
    normally this is the Institution Admin's own job); TENANT_ADMIN is
    restricted to their own tenant. DB-verified via RoleRepository, same as
    TenantService._deny_moderator / _assert_can_reveal_pii — never trust the
    gateway-set X-Permission-IDs header for this, since auth-service can be
    reached directly, bypassing the gateway entirely.

    Two distinct rejections, matching TenantService's own split (enforce_scope's
    403 TENANT_FORBIDDEN vs _deny_moderator's 403 INSUFFICIENT_PERMISSIONS)
    rather than collapsing both into one code:
      * No qualifying role at all -> 403 INSUFFICIENT_PERMISSIONS. The tenant
        is real and the caller may even belong to it; they just aren't the
        right role. Saying "not found" here would be false.
      * TENANT_ADMIN, but a DIFFERENT tenant -> 404, masked per the contract
        ("identical whether the tenant doesn't exist or belongs to another
        tenant") — this is the enumeration-prevention case.
    """
    roles = await role_repo.get_user_roles(user.id)
    if RoleName.ADMIN.value in roles:
        return
    if RoleName.TENANT_ADMIN.value in roles:
        if user.tenant_id == tenant_id:
            return
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Tenant not found."},
        )
    raise InsufficientPermissionsError()
