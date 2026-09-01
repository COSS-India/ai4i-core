"""
AllocationService — orchestrator behind the three Budget Allocation
endpoints (PUT /auth/tenants/{id}/budget-allocation,
PUT /auth/applications/{id}/budget-allocation,
PUT /auth/api-keys/{id}/budget-allocation).

allocation_validator.resolve_level is the one place the actual reallocation
math lives; everything here is orchestration around it: authorizing the
caller, locking the right parent row(s), loading children plus their
consumed (₹ used) amounts from platform-core's budget_usage ledger, calling
resolve_level for the scope requested, cascading into a changed
Application's own Keys, persisting everything in one transaction, and
writing through the resolved ₹ ceiling into budget_usage.api_key_budget_snap
for every key that changed.

Three entry points, one shared implementation of every step except "which
repository holds the parent" and "is the parent's own share also up for
resolution this call, or is it fixed and echoed back." All three
proportionally re-fit any unlisted child (refit_unlisted=True): resizing
one Application affects its tenant-siblings, resizing one Key affects its
application-siblings — see each method's own docstring for the exact room
each re-fit draws from.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.api_key import APIKey
from app.models.application import Application
from app.models.user import User
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tenant_repository import TenantRepository
from app.schemas.allocation import (
    AllocationValue,
    APIKeyAllocationResponseItem,
    APIKeyAllocationRow,
    APIKeyBudgetAllocationRequest,
    ApplicationAllocationResponseItem,
    ApplicationAllocationRow,
    ApplicationBudgetAllocationRequest,
    TenantBudgetAllocationRequest,
)
from app.services import budget_usage
from app.services.allocation_validator import AllocationRow, ExplicitInput, ResolvedRow, resolve_level
from app.services.authorization import authorize_institution_scope

_ZERO = Decimal("0")


def _explicit_input(id_, allocation: AllocationValue) -> ExplicitInput:
    """{type, value} -> the (percentage, amount) shape allocation_validator
    already works with — PERCENTAGE maps to percentage, FIXED to amount."""
    if allocation.type == "PERCENTAGE":
        return ExplicitInput(id=id_, percentage=allocation.value)
    return ExplicitInput(id=id_, amount=allocation.value)


def _response_allocation(id_, amount: Decimal, percentage: Decimal, fixed_ids: set) -> AllocationValue:
    """A response row reports type=FIXED only when that id was JUST
    submitted as FIXED in this same request — never persisted, never
    inferred for an unlisted/re-fit/otherwise-untouched row, which always
    reports PERCENTAGE (see allocation-reallocation-flow.md Section 4.4)."""
    if id_ in fixed_ids:
        return AllocationValue(type="FIXED", value=amount)
    return AllocationValue(type="PERCENTAGE", value=percentage)


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

    # ── Edge 1: Tenant -> Applications ──────────────────────────────────

    async def update_tenant_application_allocations(
        self,
        tenant_id: int,
        body: TenantBudgetAllocationRequest,
        current_user: User,
        platform_core_db: Optional[AsyncSession],
    ) -> list[ApplicationAllocationResponseItem]:
        """PUT /auth/tenants/{tenant_id}/budget-allocation.

        The Tenant's own total isn't changing in this call, but — unlike
        the Application->Keys edge below — an Application NOT listed here
        is not left untouched: it's proportionally re-fit against what's
        left of the Tenant's (unchanged) total, the same unconditional
        re-fit rule used everywhere a parent's children are being resolved
        (refit_unlisted=True). Every Application under the Tenant is
        therefore locked up front, not just the ones explicitly listed —
        any of them may end up written. This also means an unmentioned
        Application can (rarely) fail ALLOCATION_BELOW_CONSUMED if the
        re-fit would drop it below its own spend.
        """
        await authorize_institution_scope(self._roles, current_user, tenant_id)

        tenant = await self._tenants.get_by_id_for_update(tenant_id)
        if tenant is None:
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        if tenant.allocated_budget is None:
            raise ValidationError(
                message="This Institution has no Budget set yet — set one via "
                "PATCH /auth/tenants/{id}/budget before allocating it across Applications.",
                code="TENANT_BUDGET_NOT_SET",
            )

        # Every Application under the Tenant is locked, not just the listed
        # ones — refit_unlisted=True means any of them may be re-fit and
        # written by this call, not only the rows the caller mentioned.
        # One batched SELECT ... FOR UPDATE (list_by_tenant_for_update),
        # not one round trip per Application — the result is already the
        # locked, up-to-date rows, so no separate unlocked list_by_tenant
        # call is needed first.
        applications = await self._applications.list_by_tenant_for_update(tenant_id)
        if not applications:
            raise EntityNotFoundError(f"Applications for tenant {tenant_id}")
        applications_by_id = {app.id: app for app in applications}

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
        # Captured before any .update() call below mutates these same
        # (identity-mapped) Application objects in place — resolve_level's
        # unlisted-Key re-fit needs each cascaded Application's amount from
        # BEFORE this call, and app_obj.allocated_budget stops being that
        # the instant it's persisted.
        old_amounts_by_id = {app.id: (app.allocated_budget or _ZERO) for app in applications}
        explicit = [
            _explicit_input(row.application_id, row.allocation) for row in body.applications
        ]
        fixed_ids = {row.application_id for row in body.applications if row.allocation.type == "FIXED"}

        resolved_apps = resolve_level(
            tenant.allocated_budget, children, explicit,
            refit_unlisted=True, parent_old_amount=tenant.allocated_budget,
        )

        request_row_by_id: dict[int, ApplicationAllocationRow] = {
            row.application_id: row for row in body.applications
        }
        snapshot_writes: dict[int, Decimal] = {}
        response_rows: list[ApplicationAllocationResponseItem] = []

        for resolved in resolved_apps:
            app_obj = applications_by_id[resolved.id]
            old_amount = old_amounts_by_id[resolved.id]
            if resolved.changed:
                await self._applications.update(
                    app_obj,
                    {
                        "allocated_budget": resolved.amount,
                        "allocated_percentage": resolved.percentage,
                        "updated_by": current_user.id,
                    },
                )

            # An auto-refitted Application (re-fit by the unconditional
            # rule, never mentioned by the caller) has no request row at
            # all — only an explicitly-listed one can carry nested api_keys.
            request_row = request_row_by_id.get(resolved.id)
            nested_api_keys = request_row.api_keys if request_row is not None else []
            # None (not []) when this Application's Keys aren't resolved
            # this call — [] would be indistinguishable from "resolved,
            # and this Application genuinely has zero Keys" (see
            # ApplicationAllocationResponseItem.api_keys's own docstring).
            key_allocations_out: Optional[list[APIKeyAllocationResponseItem]] = None
            if resolved.changed or nested_api_keys:
                key_allocations_out = await self._cascade_into_keys(
                    application_id=resolved.id,
                    new_application_amount=resolved.amount,
                    old_application_amount=old_amount,
                    nested_explicit=nested_api_keys,
                    existing_keys=self._active(keys_by_app.get(resolved.id, [])),
                    usage_map=usage_map,
                    current_user=current_user,
                    snapshot_writes=snapshot_writes,
                )

            response_rows.append(
                ApplicationAllocationResponseItem(
                    application_id=resolved.id,
                    allocation=_response_allocation(
                        resolved.id, resolved.amount, resolved.percentage, fixed_ids
                    ),
                    allocated_budget=resolved.amount,
                    api_keys=key_allocations_out,
                )
            )

        await self._db.commit()
        await budget_usage.write_budget_snapshot(snapshot_writes, platform_core_db)
        return response_rows

    # ── Edge 2: Application -> API Keys ─────────────────────────────────

    async def update_application_key_allocations(
        self,
        application_id: int,
        body: ApplicationBudgetAllocationRequest,
        current_user: User,
        platform_core_db: Optional[AsyncSession],
    ) -> ApplicationAllocationResponseItem:
        """PUT /auth/applications/{application_id}/budget-allocation.

        ``body.allocation`` (the Application's own value) is echo-only —
        this endpoint never changes an Application's share of the Tenant
        (that's the Tenant-level endpoint's job); it must match what's
        already stored, checked before anything else, or the call is
        rejected rather than silently accepted with a different value than
        what's shown.

        The Application's own total isn't changing in this call, but — same
        as the Tenant-level endpoint's own Applications — a Key NOT listed
        in ``api_keys`` is not left untouched: it's proportionally re-fit
        against what's left of the Application's (unchanged) total
        (refit_unlisted=True), so that resizing one Key genuinely does
        affect its siblings under the same Application rather than only
        succeeding when there happens to be free headroom lying around.
        This can (rarely) fail an unlisted Key's own
        ALLOCATION_BELOW_CONSUMED check, same as the Tenant-level re-fit
        can for an unmentioned Application.
        """
        if body.application_id != application_id:
            raise ValidationError(
                message=f"application_id={body.application_id} in the request body does not "
                f"match {application_id} in the path.",
                code="APPLICATION_ID_MISMATCH",
            )

        application = await self._applications.get_by_id(application_id)
        if application is None:
            raise EntityNotFoundError(f"Application {application_id}")
        await authorize_institution_scope(self._roles, current_user, application.tenant_id)

        # get_by_id_for_update's populate_existing=True refreshes the same
        # identity-mapped ``application`` object in place — but it CAN
        # legitimately return None if the row was deleted between the
        # unlocked lookup above and this lock attempt.
        application = await self._applications.get_by_id_for_update(application_id)
        if application is None:
            raise EntityNotFoundError(f"Application {application_id}")
        if application.allocated_budget is None:
            raise ValidationError(
                message="This Application has no Budget allocation yet — it must be given a "
                "share of the Institution's Budget before its own Keys can be reallocated.",
                code="APPLICATION_BUDGET_NOT_SET",
            )

        self._assert_matches_current_application_allocation(application, body.allocation)

        # Revoked Keys are terminal (no reissue) — excluded from this
        # screen entirely, not just left unlisted: they no longer hold a
        # valid share of anything going forward, so they aren't eligible
        # resolve_level children (see _active's docstring).
        existing_keys = self._active(await self._api_keys.list_by_application(application_id))
        usage_map = await budget_usage.fetch_budget_usage(
            [k.id for k in existing_keys], platform_core_db
        )

        snapshot_writes: dict[int, Decimal] = {}
        key_allocations_out = await self._resolve_and_persist_keys(
            parent_amount=application.allocated_budget,
            parent_old_amount=application.allocated_budget,
            nested_explicit=body.api_keys,
            existing_keys=existing_keys,
            usage_map=usage_map,
            current_user=current_user,
            snapshot_writes=snapshot_writes,
            owning_application_id=application_id,
        )

        await self._db.commit()
        await budget_usage.write_budget_snapshot(snapshot_writes, platform_core_db)

        return ApplicationAllocationResponseItem(
            application_id=application_id,
            allocation=body.allocation,
            allocated_budget=application.allocated_budget,
            api_keys=key_allocations_out,
        )

    # ── API Key ──────────────────────────────────────────────────────────

    async def update_single_api_key_allocation(
        self,
        key_id: int,
        body: APIKeyBudgetAllocationRequest,
        current_user: User,
        platform_core_db: Optional[AsyncSession],
    ) -> ApplicationAllocationResponseItem:
        """PUT /auth/api-keys/{key_id}/budget-allocation.

        Resizing one Key changes its siblings' ₹ — every other Key under
        the same Application is proportionally re-fit against what's left
        of the Application's (unchanged) total (refit_unlisted=True), same
        as update_application_key_allocations — so the response is the
        complete parent Application object, same shape as the
        Application-level endpoint's response, not just the one Key
        edited. Internally this is exactly update_application_key_allocations
        with a single-row api_keys list — same resolve_and_persist call,
        same refit_unlisted=True behavior — the Application itself is just
        derived from the Key instead of given directly.
        """
        if body.api_key_id != key_id:
            raise ValidationError(
                message=f"api_key_id={body.api_key_id} in the request body does not match "
                f"{key_id} in the path.",
                code="KEY_ID_MISMATCH",
            )

        key = await self._api_keys.get_by_id(key_id)
        if key is None:
            raise EntityNotFoundError(f"API key {key_id}")
        if not key.is_active:
            raise ValidationError(
                message=f"API key {key_id} has been revoked — its Budget allocation "
                f"cannot be edited.",
                code="API_KEY_REVOKED",
            )

        application = await self._applications.get_by_id(key.application_id)
        if application is None:
            raise EntityNotFoundError(f"Application {key.application_id}")
        await authorize_institution_scope(self._roles, current_user, application.tenant_id)

        application = await self._applications.get_by_id_for_update(key.application_id)
        if application is None:
            raise EntityNotFoundError(f"Application {key.application_id}")
        if application.allocated_budget is None:
            raise ValidationError(
                message="This Application has no Budget allocation yet — it must be given a "
                "share of the Institution's Budget before its own Keys can be reallocated.",
                code="APPLICATION_BUDGET_NOT_SET",
            )

        existing_keys = self._active(await self._api_keys.list_by_application(application.id))
        usage_map = await budget_usage.fetch_budget_usage(
            [k.id for k in existing_keys], platform_core_db
        )

        snapshot_writes: dict[int, Decimal] = {}
        key_allocations_out = await self._resolve_and_persist_keys(
            parent_amount=application.allocated_budget,
            parent_old_amount=application.allocated_budget,
            nested_explicit=[APIKeyAllocationRow(api_key_id=key_id, allocation=body.allocation)],
            existing_keys=existing_keys,
            usage_map=usage_map,
            current_user=current_user,
            snapshot_writes=snapshot_writes,
            owning_application_id=application.id,
        )

        await self._db.commit()
        await budget_usage.write_budget_snapshot(snapshot_writes, platform_core_db)

        return ApplicationAllocationResponseItem(
            application_id=application.id,
            allocation=AllocationValue(
                type="PERCENTAGE", value=application.allocated_percentage or _ZERO
            ),
            allocated_budget=application.allocated_budget,
            api_keys=key_allocations_out,
        )

    # ── Tenant's own budget revision (PATCH /auth/tenants/{id}/budget) ──

    async def cascade_tenant_budget_revision(
        self,
        tenant_id: int,
        new_amount: Decimal,
        old_amount: Decimal,
        current_user: User,
        platform_core_db: Optional[AsyncSession],
    ) -> tuple[int, int, dict[int, Decimal]]:
        """Proportionally re-fits every Application under the Tenant — and,
        for any Application whose own amount actually changes, its own Keys
        in turn — to track a change in the TENANT's own total. This is
        PATCH /auth/tenants/{id}/budget's own cascade, distinct from the
        rebalancing endpoints above (which take the Tenant's total as a
        given, unchanged value and only redistribute it).

        No explicit rows at all: every Application is "unlisted" from this
        call's point of view, which reduces resolve_level's general
        algorithm to the simple case Section 2b describes — each child's
        own percentage applied directly to new_amount (or, if the Tenant
        wasn't fully allocated before, its slack scales proportionally
        too, staying unallocated rather than being silently absorbed — see
        TestSlackSurvivesAResize in test_allocation_validator.py).

        Every Application is locked up front, same reasoning as the
        rebalancing endpoint's own refit_unlisted=True path — any of them
        may end up written.

        Deliberately does NOT commit and does NOT write through to
        budget_usage — the caller (TenantService.revise_tenant_budget) is
        expected to stage the Tenant's own allocated_budget change in the
        SAME uncommitted transaction and commit exactly once, after this
        returns successfully. A floor-check failure anywhere below (an
        Application or one of its Keys dropping below its own spend)
        raises straight out of resolve_level, before anything here is
        persisted — the caller's session rollback on that exception is
        what makes "the whole revision is rejected, not just the piece
        that broke" actually true, not anything this method does
        specially.

        Returns (applications_recomputed, keys_recomputed, snapshot_writes)
        — the first two for the response's own fields of the same name;
        snapshot_writes for the caller to push through to budget_usage
        after it commits.
        """
        # One batched SELECT ... FOR UPDATE, not one round trip per
        # Application — see update_tenant_application_allocations's own
        # comment on list_by_tenant_for_update for why.
        applications = await self._applications.list_by_tenant_for_update(tenant_id)
        if not applications:
            return 0, 0, {}
        applications_by_id = {app.id: app for app in applications}

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
        old_amounts_by_id = {app.id: (app.allocated_budget or _ZERO) for app in applications}

        resolved_apps = resolve_level(
            new_amount, children, explicit=[], refit_unlisted=True, parent_old_amount=old_amount
        )

        snapshot_writes: dict[int, Decimal] = {}
        applications_recomputed = 0
        keys_recomputed = 0

        for resolved in resolved_apps:
            if not resolved.changed:
                continue
            applications_recomputed += 1
            app_obj = applications_by_id[resolved.id]
            await self._applications.update(
                app_obj,
                {
                    "allocated_budget": resolved.amount,
                    "allocated_percentage": resolved.percentage,
                    "updated_by": current_user.id,
                },
            )
            before = len(snapshot_writes)
            await self._cascade_into_keys(
                application_id=resolved.id,
                new_application_amount=resolved.amount,
                old_application_amount=old_amounts_by_id[resolved.id],
                nested_explicit=[],
                existing_keys=self._active(keys_by_app.get(resolved.id, [])),
                usage_map=usage_map,
                current_user=current_user,
                snapshot_writes=snapshot_writes,
            )
            keys_recomputed += len(snapshot_writes) - before

        return applications_recomputed, keys_recomputed, snapshot_writes

    # ── Shared helpers ───────────────────────────────────────────────────

    @staticmethod
    def _assert_matches_current_application_allocation(
        application: Application, allocation: AllocationValue
    ) -> None:
        """The Application-level endpoint's own ``allocation`` field is
        echo-only (see update_application_key_allocations's docstring) —
        reject outright if it disagrees with what's actually stored,
        rather than silently accepting a value the call was never going to
        act on."""
        current = (
            application.allocated_percentage if allocation.type == "PERCENTAGE"
            else application.allocated_budget
        )
        if current is None or allocation.value != current:
            raise ValidationError(
                message=(
                    f"allocation ({allocation.type}={allocation.value}) does not match this "
                    f"Application's current allocation — this endpoint does not change an "
                    f"Application's own share of the Institution's Budget, only its Keys' "
                    f"shares of the Application. Use PUT /auth/tenants/{{tenant_id}}/"
                    f"budget-allocation to change the Application's own allocation."
                ),
                code="APPLICATION_ALLOCATION_MISMATCH",
            )

    async def _load_keys_and_usage(
        self, application_ids: list[int], platform_core_db: Optional[AsyncSession]
    ) -> tuple[dict[int, list[APIKey]], dict[int, tuple[Decimal, Decimal]]]:
        """One batched query for every Key under every given Application, plus
        one batched cross-DB usage lookup — reused for both the tenant-scope
        feasibility check (every Application's consumed total) and, for a
        resized Application, its own cascade (no second round trip).

        Deliberately UNFILTERED — includes revoked Keys. The Application's
        own consumed total must still count what a now-revoked Key already
        spent (that ₹ is genuinely gone); it's the Keys-level cascade that
        must exclude them from allocation eligibility, so callers passing
        this into resolve_level's ``existing_keys`` do that themselves via
        ``self._active(...)`` — see _active's docstring for why the split
        matters."""
        all_keys = await self._api_keys.list_by_applications(application_ids)
        usage_map = await budget_usage.fetch_budget_usage(
            [k.id for k in all_keys], platform_core_db
        )
        keys_by_app: dict[int, list[APIKey]] = {}
        for key in all_keys:
            keys_by_app.setdefault(key.application_id, []).append(key)
        return keys_by_app, usage_map

    @staticmethod
    def _active(keys: list[APIKey]) -> list[APIKey]:
        """A revoked Key is terminal, never reissued — it's excluded from
        every re-fit/allocation-eligibility computation (it can no longer
        hold a share of anything going forward, so it isn't a valid
        resolve_level child), but NOT from consumed-spend accounting: what
        it already spent is real and stays counted toward its parent
        Application's own consumed total (see _consumed_total, which is
        deliberately called on the UNFILTERED key list, not this one) —
        revocation doesn't undo money already spent. Call this only where
        the result feeds resolve_level's ``children``/``existing_keys``,
        never where it feeds a consumed-total sum."""
        return [k for k in keys if k.is_active]

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
        old_application_amount: Decimal,
        nested_explicit: list[APIKeyAllocationRow],
        existing_keys: list[APIKey],
        usage_map: dict[int, tuple[Decimal, Decimal]],
        current_user: User,
        snapshot_writes: dict[int, Decimal],
    ) -> list[APIKeyAllocationResponseItem]:
        """This Application's own un-listed Keys are NOT left untouched just
        because the caller didn't mention them — every Key under it is
        unconditionally re-fit to track the Application's own change,
        same as everywhere else that a parent's own total just changed.
        ``old_application_amount`` is what the Application held
        immediately before this call — required so the re-fit can scale
        each Key by the Application's actual change instead of normalizing
        to fill whatever room the resize left (see resolve_level's
        docstring). resolve_level itself already returns every Key, so no
        merge-back-in step is needed here."""
        return await self._resolve_and_persist_keys(
            parent_amount=new_application_amount,
            parent_old_amount=old_application_amount,
            nested_explicit=nested_explicit,
            existing_keys=existing_keys,
            usage_map=usage_map,
            current_user=current_user,
            snapshot_writes=snapshot_writes,
            owning_application_id=application_id,
        )

    async def _resolve_and_persist_keys(
        self,
        *,
        parent_amount: Decimal,
        nested_explicit: list[APIKeyAllocationRow],
        existing_keys: list[APIKey],
        usage_map: dict[int, tuple[Decimal, Decimal]],
        current_user: User,
        snapshot_writes: dict[int, Decimal],
        owning_application_id: Optional[int] = None,
        parent_old_amount: Optional[Decimal] = None,
    ) -> list[APIKeyAllocationResponseItem]:
        """The one place every Key-resolution call site (the Application-scope
        cascade, the direct Application-level endpoint, and the single-Key
        endpoint) actually resolves + persists Keys — same resolve_level
        call (always refit_unlisted=True — every call site proportionally
        re-fits unlisted Keys, so there's no other mode left to select
        here; resolve_level's own refit_unlisted=False mode still exists
        and is still tested at that level, it's just not reachable through
        this method), same persistence, same snapshot bookkeeping; only
        the KEY_APPLICATION_MISMATCH check (only meaningful when nested
        under a specific Application) differs per call site.
        """
        known_key_ids = {k.id for k in existing_keys}
        if owning_application_id is not None:
            for row in nested_explicit:
                if row.api_key_id not in known_key_ids:
                    other = await self._api_keys.get_by_id(row.api_key_id)
                    if other is not None and other.application_id == owning_application_id:
                        # Belongs here but isn't in existing_keys (already
                        # filtered to is_active by the caller) — it's
                        # revoked, not misattributed. Distinct code: the
                        # mismatch message below would be actively wrong
                        # ("doesn't belong") for a key that does belong.
                        raise ValidationError(
                            message=f"api_key_id={row.api_key_id} has been revoked — its "
                            f"Budget allocation cannot be edited.",
                            code="API_KEY_REVOKED",
                        )
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

        explicit = [_explicit_input(row.api_key_id, row.allocation) for row in nested_explicit]
        fixed_ids = {row.api_key_id for row in nested_explicit if row.allocation.type == "FIXED"}
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
            parent_amount,
            key_rows,
            explicit,
            refit_unlisted=True,
            parent_old_amount=parent_old_amount,
        )

        keys_by_id = {key.id: key for key in existing_keys}
        response_rows: list[APIKeyAllocationResponseItem] = []
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
                APIKeyAllocationResponseItem(
                    api_key_id=resolved.id,
                    allocation=_response_allocation(
                        resolved.id, resolved.amount, resolved.percentage, fixed_ids
                    ),
                    allocated_budget=resolved.amount,
                )
            )

        return response_rows
