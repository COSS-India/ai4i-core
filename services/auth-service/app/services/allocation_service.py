"""
AllocationService — orchestrator behind PUT /auth/allocations.

allocation_validator.resolve_level is the one place the actual reallocation
math lives (Section 2b/4.4 of allocation-reallocation-flow.md); everything
here is orchestration around it: authorizing the caller, locking the right
parent row, loading children plus their consumed (₹ used) amounts from
platform-core's budget_usage ledger, calling resolve_level for the scope
requested, cascading into a changed Application's own Keys, persisting
everything in one transaction, and writing through the resolved ₹ ceiling
into budget_usage.api_key_budget_snap for every key that changed.

Two scopes, one shared implementation of every step except "which repository
holds the parent" and "which resolve_level flag applies" — see each method's
docstring for the two-rule split from Section 4.4.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.api_key import APIKey
from app.models.user import User
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tenant_repository import TenantRepository
from app.schemas.allocation import (
    AllocationUpdateData,
    AllocationUpdateRequest,
    APIKeyAllocationInput,
    ResolvedAPIKeyAllocation,
    ResolvedApplicationAllocation,
)
from app.services.allocation_validator import AllocationRow, ExplicitInput, ResolvedRow, resolve_level
from app.services.api_key_service import APIKeyService
from app.services.authorization import authorize_institution_scope

_ZERO = Decimal("0")


class AllocationService:
    def __init__(
        self,
        application_repo: ApplicationRepository,
        api_key_repo: APIKeyRepository,
        tenant_repo: TenantRepository,
        role_repo: RoleRepository,
        db: AsyncSession,
    ) -> None:
        self._applications = application_repo
        self._api_keys = api_key_repo
        self._tenants = tenant_repo
        self._roles = role_repo
        self._db = db

    # ── Scope 1: tenant_id -> Applications ──────────────────────────────

    async def update_tenant_application_allocations(
        self,
        tenant_id: int,
        body: AllocationUpdateRequest,
        current_user: User,
        platform_core_db: Optional[AsyncSession],
    ) -> AllocationUpdateData:
        """PUT /auth/allocations?tenant_id=X.

        The Tenant's own total isn't changing in this call — only the
        Applications explicitly listed are touched (refit_unlisted=False);
        a listed Application's own un-listed Keys still cascade
        (refit_unlisted=True), since THAT parent's amount just changed.
        """
        await authorize_institution_scope(self._roles, current_user, tenant_id)

        if body.api_key_allocations is not None:
            raise ValidationError(
                message="api_key_allocations is not valid when scoped by tenant_id — "
                "use application_allocations, nesting per-Application Key edits under it.",
                code="ROW_SCOPE_MISMATCH",
            )
        if not body.application_allocations:
            raise ValidationError(
                message="application_allocations is required when scoped by tenant_id.",
                code="ROW_SCOPE_MISMATCH",
            )

        tenant = await self._tenants.get_by_id_for_update(tenant_id)
        if tenant is None:
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        if tenant.allocated_budget is None:
            raise ValidationError(
                message="This Institution has no Budget set yet — set one via "
                "PATCH /auth/tenants/{id}/budget before allocating it across Applications.",
                code="TENANT_BUDGET_NOT_SET",
            )

        applications = await self._applications.list_by_tenant(tenant_id)
        if not applications:
            raise EntityNotFoundError(f"Applications for tenant {tenant_id}")

        keys_by_app, usage_map = await self._load_keys_and_usage(
            [app.id for app in applications], platform_core_db
        )

        children = [
            AllocationRow(
                id=app.id,
                allocated_amount=app.allocated_budget or _ZERO,
                allocated_percentage=app.allocated_percentage or _ZERO,
                consumed_amount=self._consumed_total(keys_by_app.get(app.id, []), usage_map),
                has_children=True,
            )
            for app in applications
        ]
        explicit = [
            ExplicitInput(id=row.application_id, percentage=row.allocated_percentage, amount=row.allocated_budget)
            for row in body.application_allocations
        ]

        resolved_apps = resolve_level(tenant.allocated_budget, children, explicit, refit_unlisted=False)

        applications_by_id = {app.id: app for app in applications}
        request_row_by_id = {row.application_id: row for row in body.application_allocations}
        snapshot_writes: dict[int, Decimal] = {}
        response_rows: list[ResolvedApplicationAllocation] = []

        for resolved in resolved_apps:
            app_obj = applications_by_id[resolved.id]
            if resolved.changed:
                await self._applications.update(
                    app_obj,
                    {
                        "allocated_budget": resolved.amount,
                        "allocated_percentage": resolved.percentage,
                        "updated_by": current_user.id,
                    },
                )

            request_row = request_row_by_id[resolved.id]
            key_allocations_out: Optional[list[ResolvedAPIKeyAllocation]] = None
            if resolved.changed or request_row.api_key_allocations:
                key_allocations_out = await self._cascade_into_keys(
                    application_id=resolved.id,
                    new_application_amount=resolved.amount,
                    nested_explicit=request_row.api_key_allocations or [],
                    existing_keys=keys_by_app.get(resolved.id, []),
                    usage_map=usage_map,
                    current_user=current_user,
                    snapshot_writes=snapshot_writes,
                )

            response_rows.append(
                ResolvedApplicationAllocation(
                    application_id=resolved.id,
                    allocated_percentage=resolved.percentage,
                    allocated_budget=resolved.amount,
                    api_key_allocations=key_allocations_out,
                )
            )

        await self._db.commit()
        await APIKeyService.write_budget_snapshot(snapshot_writes, platform_core_db)

        total_pct = await self._applications.sum_allocated_percentage(tenant_id)
        return AllocationUpdateData(
            parent_id=str(tenant_id),
            total_allocated_percentage=total_pct,
            application_allocations=response_rows,
        )

    # ── Scope 2: application_id -> API Keys ─────────────────────────────

    async def update_application_key_allocations(
        self,
        application_id: int,
        body: AllocationUpdateRequest,
        current_user: User,
        platform_core_db: Optional[AsyncSession],
    ) -> AllocationUpdateData:
        """PUT /auth/allocations?application_id=Y.

        The Application's own total isn't changing in this call either —
        only the Keys explicitly listed are touched (refit_unlisted=False).
        Keys are leaves, so there's no further cascade below this level.
        """
        if body.application_allocations is not None:
            raise ValidationError(
                message="application_allocations is not valid when scoped by application_id — "
                "use api_key_allocations.",
                code="ROW_SCOPE_MISMATCH",
            )
        if not body.api_key_allocations:
            raise ValidationError(
                message="api_key_allocations is required when scoped by application_id.",
                code="ROW_SCOPE_MISMATCH",
            )

        # tenant_id for the scope check comes from the Application itself —
        # there's no tenant_id in this call's query params at all. A 404 here
        # (id doesn't exist) and the masked 404 authorize_institution_scope
        # raises for a TENANT_ADMIN of a different tenant are indistinguishable
        # to the caller either way, matching this codebase's existing
        # "identical 404 whether it doesn't exist or belongs to another
        # tenant" convention (see ApplicationService._load_application_or_404).
        application = await self._applications.get_by_id(application_id)
        if application is None:
            raise EntityNotFoundError(f"Application {application_id}")
        await authorize_institution_scope(self._roles, current_user, application.tenant_id)

        locked_application = await self._applications.get_by_id_for_update(application_id)
        if locked_application is not None:
            application = locked_application
        if application.allocated_budget is None:
            raise ValidationError(
                message="This Application has no Budget allocation yet — it must be given a "
                "share of the Institution's Budget before its own Keys can be reallocated.",
                code="APPLICATION_BUDGET_NOT_SET",
            )

        existing_keys = await self._api_keys.list_by_application(application_id)
        usage_map = await APIKeyService.fetch_budget_usage(
            [k.id for k in existing_keys], platform_core_db
        )

        snapshot_writes: dict[int, Decimal] = {}
        response_rows = await self._resolve_and_persist_keys(
            parent_amount=application.allocated_budget,
            nested_explicit=body.api_key_allocations,
            existing_keys=existing_keys,
            usage_map=usage_map,
            current_user=current_user,
            snapshot_writes=snapshot_writes,
            refit_unlisted=False,
        )

        await self._db.commit()
        await APIKeyService.write_budget_snapshot(snapshot_writes, platform_core_db)

        total_pct = await self._applications.sum_api_key_allocated_percentage(application_id)
        return AllocationUpdateData(
            parent_id=str(application_id),
            total_allocated_percentage=total_pct,
            api_key_allocations=response_rows,
        )

    # ── Shared helpers ───────────────────────────────────────────────────

    async def _load_keys_and_usage(
        self, application_ids: list[int], platform_core_db: Optional[AsyncSession]
    ) -> tuple[dict[int, list[APIKey]], dict[int, tuple[Decimal, Decimal]]]:
        """One batched query for every Key under every given Application, plus
        one batched cross-DB usage lookup — reused for both the tenant-scope
        feasibility check (every Application's consumed total) and, for a
        resized Application, its own cascade (no second round trip)."""
        all_keys = await self._api_keys.list_by_applications(application_ids)
        usage_map = await APIKeyService.fetch_budget_usage(
            [k.id for k in all_keys], platform_core_db
        )
        keys_by_app: dict[int, list[APIKey]] = {}
        for key in all_keys:
            keys_by_app.setdefault(key.application_id, []).append(key)
        return keys_by_app, usage_map

    @staticmethod
    def _consumed_total(
        keys: list[APIKey], usage_map: dict[int, tuple[Decimal, Decimal]]
    ) -> Decimal:
        return sum((usage_map.get(k.id, (_ZERO, None))[0] for k in keys), _ZERO)

    async def _cascade_into_keys(
        self,
        *,
        application_id: int,
        new_application_amount: Decimal,
        nested_explicit: list[APIKeyAllocationInput],
        existing_keys: list[APIKey],
        usage_map: dict[int, tuple[Decimal, Decimal]],
        current_user: User,
        snapshot_writes: dict[int, Decimal],
    ) -> list[ResolvedAPIKeyAllocation]:
        """Section 2b step 7 / Section 4.4's "within a row you DID list and
        resize" rule: this Application's own un-listed Keys are NOT left
        untouched — every Key under it is unconditionally re-fit against the
        Application's new amount (refit_unlisted=True), same as everywhere
        else that a parent's own total just changed."""
        return await self._resolve_and_persist_keys(
            parent_amount=new_application_amount,
            nested_explicit=nested_explicit,
            existing_keys=existing_keys,
            usage_map=usage_map,
            current_user=current_user,
            snapshot_writes=snapshot_writes,
            refit_unlisted=True,
            owning_application_id=application_id,
        )

    async def _resolve_and_persist_keys(
        self,
        *,
        parent_amount: Decimal,
        nested_explicit: list[APIKeyAllocationInput],
        existing_keys: list[APIKey],
        usage_map: dict[int, tuple[Decimal, Decimal]],
        current_user: User,
        snapshot_writes: dict[int, Decimal],
        refit_unlisted: bool,
        owning_application_id: Optional[int] = None,
    ) -> list[ResolvedAPIKeyAllocation]:
        """The one place both Key-resolution call sites (the Application-scope
        cascade and the direct Key-scope endpoint) actually resolve + persist
        Keys — same resolve_level call, same persistence, same snapshot
        bookkeeping; only ``refit_unlisted`` and the KEY_APPLICATION_MISMATCH
        check (only meaningful when nested under a specific Application)
        differ between the two callers."""
        known_key_ids = {k.id for k in existing_keys}
        if owning_application_id is not None:
            for row in nested_explicit:
                if row.api_key_id not in known_key_ids:
                    other = await self._api_keys.get_by_id(row.api_key_id)
                    if other is not None:
                        raise ValidationError(
                            message=(
                                f"api_key_id={row.api_key_id} does not belong to "
                                f"application_id={owning_application_id}."
                            ),
                            code="KEY_APPLICATION_MISMATCH",
                        )
                        # else: unknown everywhere — resolve_level below raises
                        # EntityNotFoundError for it, same as any other unknown id.

        explicit = [
            ExplicitInput(id=row.api_key_id, percentage=row.allocated_percentage, amount=row.allocated_budget)
            for row in nested_explicit
        ]
        key_rows = [
            AllocationRow(
                id=key.id,
                allocated_amount=key.allocated_budget or _ZERO,
                allocated_percentage=key.allocated_percentage or _ZERO,
                consumed_amount=usage_map.get(key.id, (_ZERO, None))[0],
            )
            for key in existing_keys
        ]

        resolved_keys: list[ResolvedRow] = resolve_level(
            parent_amount, key_rows, explicit, refit_unlisted=refit_unlisted
        )

        keys_by_id = {key.id: key for key in existing_keys}
        response_rows: list[ResolvedAPIKeyAllocation] = []
        for resolved in resolved_keys:
            if resolved.changed:
                key_obj = keys_by_id[resolved.id]
                await self._api_keys.update(
                    key_obj,
                    {
                        "allocated_budget": resolved.amount,
                        "allocated_percentage": resolved.percentage,
                        "updated_by": current_user.id,
                    },
                )
                snapshot_writes[resolved.id] = resolved.amount
            response_rows.append(
                ResolvedAPIKeyAllocation(
                    api_key_id=resolved.id,
                    allocated_percentage=resolved.percentage,
                    allocated_budget=resolved.amount,
                    auto_refitted=resolved.auto_refitted,
                )
            )
        return response_rows
