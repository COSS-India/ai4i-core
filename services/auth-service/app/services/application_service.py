"""
Application business logic — Application CRUD.

Routes are thin pass-throughs, same convention as TenantService: scope
enforcement and repository access all live here.

Note: budget reallocation (rebalancing allocated_percentage across
Applications/Keys within a tenant, e.g. PUT /auth/allocations) is NOT part of
this file. That endpoint's business rules were left unwritten in the API
contract and are being implemented separately by someone else later.
"""

from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RoleName
from app.core.exceptions import EntityNotFoundError, InsufficientPermissionsError
from app.models.application import Application
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.application_repository import ApplicationRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tenant_repository import TenantRepository
from app.schemas.application import ApplicationCreate, ApplicationUpdate

_HUNDRED = Decimal("100")
_CENTS = Decimal("0.01")


class ApplicationService:
    def __init__(
        self,
        application_repo: ApplicationRepository,
        tenant_repo: TenantRepository,
        role_repo: RoleRepository,
        db: AsyncSession,
    ) -> None:
        self._applications = application_repo
        self._tenants = tenant_repo
        self._roles = role_repo
        self._db = db

    # ── Scope / lookups ─────────────────────────────────────────────────

    async def _authorize(self, user: User, tenant_id: int) -> None:
        """Only Adopter Admin (ADMIN) and Institution Admin (TENANT_ADMIN) may
        touch Application Management — everyone else, MODERATOR included, is
        rejected. A higher role carries every permission a lower one has: ADMIN
        may act on any Institution's Applications (the edge case — normally
        this is the Institution Admin's own job); TENANT_ADMIN is restricted to
        their own tenant. DB-verified via RoleRepository, same as
        TenantService._deny_moderator / _assert_can_reveal_pii — never trust
        the gateway-set X-Permission-IDs header for this, since auth-service
        can be reached directly, bypassing the gateway entirely.

        Two distinct rejections, matching TenantService's own split
        (enforce_scope's 403 TENANT_FORBIDDEN vs _deny_moderator's 403
        INSUFFICIENT_PERMISSIONS) rather than collapsing both into one code:
          * No qualifying role at all -> 403 INSUFFICIENT_PERMISSIONS. The
            tenant is real and the caller may even belong to it; they just
            aren't the right role. Saying "not found" here would be false.
          * TENANT_ADMIN, but a DIFFERENT tenant -> 404, masked per the
            contract ("identical whether the tenant doesn't exist or belongs
            to another tenant") — this is the enumeration-prevention case.
        """
        roles = await self._roles.get_user_roles(user.id)
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

    async def _load_tenant_or_404(self, tenant_id: int) -> Tenant:
        tenant = await self._tenants.get_by_id(tenant_id)
        if not tenant:
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        return tenant

    async def _load_application_or_404(self, tenant_id: int, application_id: int) -> Application:
        """404 identically whether the id doesn't exist or belongs to another
        tenant — avoids leaking which application ids exist under other tenants.
        """
        app = await self._applications.get_by_id(application_id)
        if not app or app.tenant_id != tenant_id:
            raise EntityNotFoundError(f"Application {application_id}")
        return app

    @staticmethod
    def _derive_budget(parent_budget: Optional[Decimal], percentage: Decimal) -> Optional[Decimal]:
        """NULL parent -> NULL amount (no ceiling to resolve the percentage against)."""
        if parent_budget is None:
            return None
        return (parent_budget * percentage / _HUNDRED).quantize(_CENTS)

    # ── CRUD ─────────────────────────────────────────────────────────────

    async def create_application(
        self,
        tenant_id: int,
        body: ApplicationCreate,
        current_user: User,
    ) -> Application:
        await self._authorize(current_user, tenant_id)
        tenant = await self._load_tenant_or_404(tenant_id)

        if await self._applications.get_by_name(tenant_id, body.name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "APPLICATION_NAME_ALREADY_EXISTS",
                    "message": "This name is already used by another Application in this Institution.",
                },
            )

        allocated_budget = None
        if body.allocated_percentage is not None:
            await self._assert_allocation_within_cap(tenant_id, body.allocated_percentage)
            allocated_budget = self._derive_budget(tenant.allocated_budget, body.allocated_percentage)

        app = Application(
            tenant_id=tenant_id,
            name=body.name,
            description=body.description,
            domain=body.domain,
            allocated_percentage=body.allocated_percentage,
            allocated_budget=allocated_budget,
            created_by=current_user.id,
        )
        await self._applications.create(app)
        await self._applications.commit()
        await self._applications.refresh(app)
        return app

    async def _assert_allocation_within_cap(
        self, tenant_id: int, new_percentage: Decimal, *, exclude_id: Optional[int] = None
    ) -> None:
        # Locks every Application row for the tenant so a concurrent reallocation
        # can't read the same stale sum and also commit over 100%.
        await self._applications.list_all_for_tenant_for_update(tenant_id)
        current_sum = await self._applications.sum_allocated_percentage(
            tenant_id, exclude_id=exclude_id
        )
        total = current_sum + new_percentage
        if total > _HUNDRED:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "ALLOCATION_TOTAL_EXCEEDED",
                    "message": (
                        f"Sum of Application budget allocations ({total}%) would exceed "
                        "100% of the Institution's Budget."
                    ),
                },
            )

    async def get_application(
        self, tenant_id: int, application_id: int, current_user: User
    ) -> Application:
        await self._authorize(current_user, tenant_id)
        return await self._load_application_or_404(tenant_id, application_id)

    async def list_applications(
        self,
        tenant_id: int,
        current_user: User,
        *,
        search: Optional[str] = None,
        domain: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[Application], int]:
        await self._authorize(current_user, tenant_id)
        await self._load_tenant_or_404(tenant_id)
        return await self._applications.list_for_tenant(
            tenant_id, search=search, domain=domain, offset=offset, limit=limit
        )

    async def update_application(
        self,
        tenant_id: int,
        application_id: int,
        body: ApplicationUpdate,
        current_user: User,
    ) -> Application:
        await self._authorize(current_user, tenant_id)
        app = await self._load_application_or_404(tenant_id, application_id)

        data = body.model_dump(exclude_unset=True)
        if "name" in data and data["name"].strip().casefold() != app.name.strip().casefold():
            existing = await self._applications.get_by_name(tenant_id, data["name"])
            if existing and existing.id != application_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "APPLICATION_NAME_ALREADY_EXISTS",
                        "message": "This name is already used by another Application in this Institution.",
                    },
                )

        data["updated_by"] = current_user.id
        await self._applications.update(app, data)
        await self._applications.commit()
        await self._applications.refresh(app)
        return app
