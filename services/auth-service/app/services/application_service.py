"""
Application business logic — Application CRUD.

Routes are thin pass-throughs, same convention as TenantService: scope
enforcement and repository access all live here.

Note: budget reallocation (rebalancing allocated_percentage across
Applications/Keys within a tenant — the three Budget Allocation endpoints,
PUT /auth/tenants/{id}/budget-allocation and friends) is NOT part of this
file — see AllocationService.
"""

from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError
from app.models.application import Application, ApplicationStatus
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.application_repository import ApplicationRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tenant_repository import TenantRepository
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.services.authorization import authorize_institution_scope

_HUNDRED = Decimal("100")
_CENTS = Decimal("0.01")

_NAME_CONFLICT_CONSTRAINT = "uq_applications_tenant_name_lower"
_NAME_CONFLICT_DETAIL = {
    "code": "APPLICATION_NAME_ALREADY_EXISTS",
    "message": "This name is already used by another Application in this Institution.",
}


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
        """Institution-scope check for Application Management — see
        authorize_institution_scope's docstring for the full rationale.
        AllocationService (the three Budget Allocation endpoints) enforces
        the identical rule via the same shared helper, not a second copy of
        this logic.
        """
        await authorize_institution_scope(self._roles, user, tenant_id)

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
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=dict(_NAME_CONFLICT_DETAIL))

        allocated_budget = None
        if body.allocated_percentage is not None:
            locked_tenant = await self._assert_allocation_within_cap(
                tenant_id, body.allocated_percentage
            )
            # Derive from the just-locked, just-refreshed row, not the
            # earlier unlocked `tenant` read from _load_tenant_or_404 above —
            # see _assert_allocation_within_cap's docstring.
            allocated_budget = self._derive_budget(
                locked_tenant.allocated_budget, body.allocated_percentage
            )

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
        await self._commit_or_raise_name_conflict()
        await self._applications.refresh(app)
        return app

    async def _commit_or_raise_name_conflict(self) -> None:
        """Commit, translating a raced unique-constraint violation into the
        same 409 the pre-check (get_by_name) raises.

        The pre-check is TOCTOU: two concurrent creates/renames with the same
        name can both pass get_by_name (neither sees the other's uncommitted
        row) and both reach here. Only uq_applications_tenant_name_lower is
        translated — matched by constraint name off the real asyncpg
        exception, verified live — so an unrelated IntegrityError (a
        different constraint, a different bug) still surfaces as a 500
        instead of being misreported as a name conflict.
        """
        try:
            await self._applications.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            cause = getattr(exc.orig, "__cause__", None)
            if getattr(cause, "constraint_name", None) == _NAME_CONFLICT_CONSTRAINT:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=dict(_NAME_CONFLICT_DETAIL)
                ) from exc
            raise

    async def _assert_allocation_within_cap(
        self, tenant_id: int, new_percentage: Decimal
    ) -> Tenant:
        # Locks the TENANT row, not the Application rows: "SELECT ... FOR
        # UPDATE" takes no lock when it matches zero rows, so locking children
        # doesn't serialize a tenant's first two concurrent creates (both see
        # zero locked rows, both read sum=0, both pass, total exceeds 100%).
        # The tenant row always exists, so locking it serializes every
        # concurrent create for that tenant regardless of how many
        # Applications currently exist — same pattern TenantRepository's own
        # get_by_id_for_update already uses to serialize status changes.
        #
        # Returns the locked tenant so the caller derives allocated_budget
        # from it instead of an earlier unlocked read: get_by_id_for_update
        # now uses populate_existing() so this return value is guaranteed
        # fresh even if the tenant was already in the session's identity map
        # (e.g. from _load_tenant_or_404 just above create_application's own
        # call site) — without that, a concurrent PATCH .../budget commit
        # between the two reads would lock the row but still hand back the
        # pre-revision allocated_budget.
        locked_tenant = await self._tenants.get_by_id_for_update(tenant_id)
        if locked_tenant is None:
            # Existence was already confirmed by _load_tenant_or_404 before
            # this is ever called, and tenants are never hard-deleted — this
            # is unreachable in practice, but fail loudly rather than let a
            # caller silently derive a budget from a stale/absent tenant.
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        current_sum = await self._applications.sum_allocated_percentage(tenant_id)
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
        return locked_tenant

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
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=dict(_NAME_CONFLICT_DETAIL))

        if data.get("status") == ApplicationStatus.INACTIVE and app.status == ApplicationStatus.ACTIVE:
            # Release this Application's own allocation on deactivation —
            # not just excluded from AllocationService's sibling-sum/
            # feasibility checks while INACTIVE (_active_applications), but
            # actually cleared. Unlike a revoked API key, an INACTIVE
            # Application isn't terminal: it can be reactivated. Without
            # clearing this, a sibling that already grew into the room this
            # Application's exclusion freed would leave the Tenant holding
            # MORE ceilings than its budget the moment this one comes back —
            # and sum_allocated_percentage (no status filter of its own
            # otherwise) would count its stale share again too, rejecting
            # legitimate new Applications until someone manually fixes it.
            # A reactivated Application comes back with no allocation at
            # all, same as a freshly created one — an explicit fresh
            # allocation via the Budget Allocation endpoints is required
            # either way, so there's no "restore its old share" path to
            # get wrong.
            data["allocated_budget"] = None
            data["allocated_percentage"] = None

        data["updated_by"] = current_user.id
        await self._applications.update(app, data)
        await self._commit_or_raise_name_conflict()
        await self._applications.refresh(app)
        return app
