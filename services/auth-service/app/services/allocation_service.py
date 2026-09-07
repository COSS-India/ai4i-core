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
repository holds the parent," "is the parent's own share also up for
resolution this call, or is it fixed and echoed back," and "does an
unlisted sibling move." That last one splits along a parent/child vs.
sibling/sibling line, not per-endpoint: a child whose OWN parent's total is
what's actually changing this call is unconditionally re-fit to track that
change (refit_unlisted=True) — an Application explicitly resized by the
Tenant-level endpoint still cascades into its own un-listed Keys, same as
it always has. But a SIBLING of whatever's being explicitly edited never
moves just because it wasn't listed (refit_unlisted=False) — resizing one
Application never moves another Application, resizing one Key never moves
another Key under the same Application; the explicit edit is checked
against whatever's genuinely unallocated instead, and rejected
(ALLOCATION_TOTAL_EXCEEDED) if it doesn't fit. See each method's own
docstring for which rule applies where.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.api_key import APIKey
from app.models.application import Application, ApplicationStatus
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
from app.services.api_key_service import APIKeyService
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
        api_key_service: Optional[APIKeyService] = None,
    ) -> None:
        self._applications = application_repo
        self._api_keys = api_key_repo
        self._tenants = tenant_repo
        self._roles = role_repo
        self._db = db
        # Distinct from self._api_keys (the repository, used throughout this
        # file for plain row access) — this is the service layer, injected
        # only for its set_budget_exhausted_for_keys write-through (see
        # _sync_key_exhaustion_flags). Optional so existing tests that
        # construct AllocationService without it keep working; the sync is
        # skipped, not crashed, when it's absent.
        self._api_key_service = api_key_service

    # ── Edge 1: Tenant -> Applications ──────────────────────────────────

    async def update_tenant_application_allocations(
        self,
        tenant_id: int,
        body: TenantBudgetAllocationRequest,
        current_user: User,
        platform_core_db: Optional[AsyncSession],
    ) -> list[ApplicationAllocationResponseItem]:
        """PUT /auth/tenants/{tenant_id}/budget-allocation.

        The Tenant's own total isn't changing in this call, and an
        Application NOT listed here is left exactly as it is
        (refit_unlisted=False) — resizing one Application never moves
        another Application. An explicit row is checked against whatever's
        genuinely unallocated (the Tenant's total minus every OTHER
        Application's current ₹, listed or not); it's rejected
        (ALLOCATION_TOTAL_EXCEEDED) rather than made to fit by shrinking a
        sibling. Every Application under the Tenant is still locked up
        front — not because an unlisted one might be written (it can't
        be), but so the feasibility check reads a consistent, race-free
        snapshot of every sibling's current ₹.

        An explicitly-resized Application's OWN Keys are a different
        story: that Application's own total genuinely IS changing, so its
        Keys are unconditionally re-fit to track it (refit_unlisted=True,
        same as always) — a parent/child relationship, not a sibling one.
        This can (rarely) fail one of those Keys' own
        ALLOCATION_BELOW_CONSUMED check; when it does, the WHOLE call is
        rejected, including the Application's own resize. But if a caller
        submits an Application at its CURRENT value (unchanged) purely to
        nest explicit ``api_keys`` edits under it, that Application's total
        isn't actually moving — its un-listed Keys follow the same sibling
        rule as everywhere else this call (refit_unlisted=False), not the
        parent/child one, since there's no genuine total change forcing
        them to react (see _cascade_into_keys).
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
        # ones — the feasibility check needs a consistent, race-free
        # snapshot of every sibling's current ₹, whether or not this call
        # ends up writing them. One batched SELECT ... FOR UPDATE
        # (list_by_tenant_for_update), not one round trip per Application —
        # the result is already the locked, up-to-date rows, so no
        # separate unlocked list_by_tenant call is needed first.
        locked_applications = await self._applications.list_by_tenant_for_update(tenant_id)
        applications = self._active_applications(locked_applications)
        if not applications:
            raise EntityNotFoundError(f"Applications for tenant {tenant_id}")
        active_ids = {app.id for app in applications}

        # An explicitly-listed Application that's INACTIVE (not merely
        # unknown) gets its own error here, before resolve_level ever runs —
        # otherwise it falls out of resolve_level's known ids the same way a
        # genuinely nonexistent one does, and surfaces as a generic 404
        # naming an Application that actually exists and is visible in the
        # UI. Same reasoning _resolve_and_persist_keys' API_KEY_REVOKED
        # check already applies one level down for a revoked Key.
        for row in body.applications:
            if row.application_id in active_ids:
                continue
            inactive_app = next(
                (app for app in locked_applications if app.id == row.application_id), None
            )
            if inactive_app is not None:
                raise ValidationError(
                    message=f"application_id={row.application_id} is INACTIVE — its Budget "
                    f"allocation cannot be edited. Reactivate it first.",
                    code="APPLICATION_INACTIVE",
                )
                # else: unknown everywhere — resolve_level below raises
                # EntityNotFoundError for it, same as any other unknown id.

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

        # refit_unlisted=False: only explicitly-listed Applications come
        # back resolved — an unlisted one is never touched, merged back
        # in from its current DB values below instead.
        resolved_apps = resolve_level(tenant.allocated_budget, children, explicit, refit_unlisted=False)

        request_row_by_id: dict[int, ApplicationAllocationRow] = {
            row.application_id: row for row in body.applications
        }
        snapshot_writes: dict[int, Decimal] = {}
        response_rows: list[ApplicationAllocationResponseItem] = []
        resolved_ids: set = set()

        for resolved in resolved_apps:
            resolved_ids.add(resolved.id)
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

            # Every row here was explicitly listed (refit_unlisted=False
            # means only explicit rows are ever resolved), so a request
            # row always exists.
            nested_api_keys = request_row_by_id[resolved.id].api_keys
            # None (not []) when this Application's Keys aren't resolved
            # this call — [] would be indistinguishable from "resolved,
            # and this Application genuinely has zero Keys" (see
            # ApplicationAllocationResponseItem.api_keys's own docstring).
            # application_amount_changed=resolved.changed selects the rule
            # one level down: when the Application's own ₹ actually moved,
            # its Keys unconditionally re-fit to track that (parent/child).
            # When it DIDN'T move — a caller submitting this Application at
            # its current value just to nest Key edits under it — its
            # un-listed Keys follow the SAME sibling rule this level itself
            # follows: left exactly as they are, not swept into a re-fit
            # that has nothing forcing it. Without this, a nested edit
            # under an unchanged Application would silently reintroduce
            # the sibling Key re-fit the direct Key endpoints deliberately
            # removed.
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
                    application_amount_changed=resolved.changed,
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

        # Every Application NOT listed — merged back in from its current
        # DB values, untouched; api_keys=None since it wasn't resolved.
        for app in applications:
            if app.id in resolved_ids:
                continue
            response_rows.append(
                ApplicationAllocationResponseItem(
                    application_id=app.id,
                    allocation=AllocationValue(
                        type="PERCENTAGE", value=app.allocated_percentage or _ZERO
                    ),
                    allocated_budget=app.allocated_budget or _ZERO,
                    api_keys=None,
                )
            )

        await self._db.commit()
        await budget_usage.write_budget_snapshot(snapshot_writes, platform_core_db)
        await self._sync_key_exhaustion_flags(snapshot_writes, usage_map)
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

        The Application's own total isn't changing in this call, and a Key
        NOT listed in ``api_keys`` is left exactly as it is
        (refit_unlisted=False) — resizing one Key never moves another Key
        under the same Application. An explicit row is checked against
        whatever's genuinely unallocated within the Application (its total
        minus every OTHER Key's current ₹, listed or not); it's rejected
        (ALLOCATION_TOTAL_EXCEEDED) rather than made to fit by shrinking a
        sibling Key. Every Key under the Application is still returned in
        the response, though: the untouched ones are merged back in from
        their current DB values, since resolve_level itself only returns
        rows it actually resolved.
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
            nested_explicit=body.api_keys,
            existing_keys=existing_keys,
            usage_map=usage_map,
            current_user=current_user,
            snapshot_writes=snapshot_writes,
            refit_unlisted=False,
            owning_application_id=application_id,
        )

        await self._db.commit()
        await budget_usage.write_budget_snapshot(snapshot_writes, platform_core_db)
        await self._sync_key_exhaustion_flags(snapshot_writes, usage_map)

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

        Resizing this Key never moves its siblings (refit_unlisted=False,
        same as update_application_key_allocations) — the request is
        checked against whatever's genuinely unallocated within the
        Application and rejected (ALLOCATION_TOTAL_EXCEEDED) rather than
        made to fit by shrinking another Key. The response is still the
        complete parent Application object, same shape as the
        Application-level endpoint's response — every sibling Key
        included, merged back in from its current (untouched) DB values —
        not just the one Key edited. Internally this is exactly
        update_application_key_allocations with a single-row api_keys
        list — same resolve_and_persist call, same refit_unlisted=False
        behavior — the Application itself is just derived from the Key
        instead of given directly.
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
            nested_explicit=[APIKeyAllocationRow(api_key_id=key_id, allocation=body.allocation)],
            existing_keys=existing_keys,
            usage_map=usage_map,
            current_user=current_user,
            snapshot_writes=snapshot_writes,
            refit_unlisted=False,
            owning_application_id=application.id,
        )

        await self._db.commit()
        await budget_usage.write_budget_snapshot(snapshot_writes, platform_core_db)
        await self._sync_key_exhaustion_flags(snapshot_writes, usage_map)

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
        current_user: User,
        platform_core_db: Optional[AsyncSession],
    ) -> tuple[int, int, dict[int, Decimal]]:
        """A Tenant budget revision (top-up/top-down) never moves an
        Application's own ₹ — Applications are this event's "siblings" in
        the same sense every other rebalancing edge now follows: the
        Tenant's total is what's changing, but no Application is forced to
        react just because it exists. Instead:

          - Every Application's allocated_budget stays EXACTLY what it
            was. Only allocated_percentage is recomputed (the same ₹ is
            now a different share of a different-sized total) and
            persisted where it actually changed.
          - A top-up always fits (the growth becomes additional
            unallocated headroom) — the MAX_TENANT_BUDGET ceiling is
            revise_tenant_budget's own separate check.
          - A top-down is rejected outright (ALLOCATION_TOTAL_EXCEEDED) if
            the sum of every Application's CURRENT allocated_budget would
            no longer fit inside the new, smaller total — nothing
            auto-shrinks to make room; the caller must free room via the
            rebalancing endpoints first, or top down by less.
          - No Application's own Keys are touched either — since no
            Application's ₹ moves here, there's nothing forcing its Keys
            to react.

        This intentionally does NOT reuse resolve_level's refit_unlisted=True
        proportional-scaling path any more — only its refit_unlisted=False
        feasibility gate (called with every Application as an unlisted,
        untouched row and no explicit rows at all), purely to get the
        "does this fit" check and the BUDGET_OVERCOMMITTED/
        ALLOCATION_TOTAL_EXCEEDED errors for free instead of re-deriving
        them. Its return value (always empty, since nothing is ever
        "explicit" here) is discarded.

        Every Application is still locked up front (one batched
        SELECT ... FOR UPDATE) so the feasibility check reads a
        consistent, race-free snapshot — not because any of them might be
        written beyond their own allocated_percentage.

        Deliberately does NOT commit — the caller
        (TenantService.revise_tenant_budget) is expected to stage the
        Tenant's own allocated_budget change in the SAME uncommitted
        transaction and commit exactly once, after this returns
        successfully. A feasibility failure raises straight out of
        resolve_level, before anything here is persisted — the caller's
        session rollback on that exception is what makes "the whole
        revision is rejected, not just the piece that broke" actually
        true, not anything this method does specially.

        Returns (applications_recomputed, keys_recomputed, snapshot_writes)
        — keys_recomputed and snapshot_writes are always 0/{} now (no Key
        is ever touched by a Tenant budget revision); kept in the return
        shape for the caller/response fields of the same name.
        """
        # One batched SELECT ... FOR UPDATE, not one round trip per
        # Application — see update_tenant_application_allocations's own
        # comment on list_by_tenant_for_update for why. Filtered to ACTIVE
        # only, same reasoning as that method's own filter: an INACTIVE
        # Application's allocated_budget must not permanently block room
        # a top-down needs to free (see _active_applications).
        applications = self._active_applications(
            await self._applications.list_by_tenant_for_update(tenant_id)
        )
        if not applications:
            return 0, 0, {}

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

        # Feasibility-only: no explicit rows, refit_unlisted=False — every
        # Application is counted at its CURRENT ₹ toward the sibling-sum
        # gate. Raises BUDGET_OVERCOMMITTED (already-spent > new total) or
        # ALLOCATION_TOTAL_EXCEEDED (already-allocated > new total) before
        # anything below runs; the return value (always []) is unused.
        resolve_level(new_amount, children, explicit=[], refit_unlisted=False)

        # Recomputing each Application's percentage independently with
        # ROUND_HALF_UP (each one rounding to its own nearest cent) can
        # leave the STORED SUM reading above the true allocated share —
        # several apps each rounding up by a fraction can compound into a
        # sum that looks like more than what's actually allocated, which
        # sum_allocated_percentage (create_application's own room check)
        # would then read at face value. Same fix resolve_level's own
        # refit_unlisted=True branch already uses one level down: quantize
        # every app but the last with ROUND_DOWN (never rounds UP past its
        # true share), and let the last one absorb whatever residual that
        # leaves — so the group's stored sum is exactly the single,
        # once-quantized total_target_percentage below, not the coincidental
        # result of N independent roundings.
        applications_recomputed = 0
        if new_amount:
            total_allocated = sum((app.allocated_budget or _ZERO) for app in applications)
            total_target_percentage = (total_allocated / new_amount * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            running_total = _ZERO
            for index, app in enumerate(applications):
                is_last = index == len(applications) - 1
                if not app.allocated_budget:
                    new_percentage = _ZERO
                elif is_last:
                    new_percentage = total_target_percentage - running_total
                else:
                    new_percentage = (app.allocated_budget / new_amount * Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_DOWN
                    )
                running_total += new_percentage
                if new_percentage != (app.allocated_percentage or _ZERO):
                    applications_recomputed += 1
                    await self._applications.update(
                        app,
                        {
                            "allocated_percentage": new_percentage,
                            "updated_by": current_user.id,
                        },
                    )
        else:
            # new_amount == 0: the feasibility gate above already rejects
            # this unless every Application is also at 0 allocated_budget —
            # nothing to divide by, every percentage is trivially 0.
            for app in applications:
                if (app.allocated_percentage or _ZERO) != _ZERO:
                    applications_recomputed += 1
                    await self._applications.update(
                        app, {"allocated_percentage": _ZERO, "updated_by": current_user.id}
                    )

        return applications_recomputed, 0, {}

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
    def _active_applications(applications: list[Application]) -> list[Application]:
        """The Application-level analogue of ``_active`` above: an INACTIVE
        Application is excluded from allocation eligibility — its
        allocated_budget doesn't count toward a sibling-sum/feasibility
        check, and it isn't returned in a Budget Allocation response —
        same reasoning as a revoked Key, one level up. This matters more
        here than it might look: with the sibling re-fit gone, a Tenant's
        or Application's siblings never auto-shrink any more, so an
        INACTIVE Application's ₹ — uneditable through the UI once
        deactivated — would otherwise permanently block that room from
        ever being reallocated to an active sibling, with no path to free
        it. Call this on the locked list before building ``children`` (and
        before the merge-back-untouched loop), same call sites _active
        governs for Keys."""
        return [app for app in applications if app.status == ApplicationStatus.ACTIVE]

    @staticmethod
    def _consumed_total(
        keys: list[APIKey], usage_map: dict[int, tuple[Decimal, Decimal]]
    ) -> Decimal:
        return sum((usage_map.get(k.id, (_ZERO, None))[0] for k in keys), _ZERO)

    async def _sync_key_exhaustion_flags(
        self,
        snapshot_writes: dict[int, Decimal],
        usage_map: dict[int, tuple[Decimal, Decimal]],
    ) -> None:
        """After write_budget_snapshot persists new ceilings, recompute
        every changed Key's own ``budget-exhausted`` cache flag from that
        new ceiling and its already-known usage — the same ``used >= snap``
        comparison the Kafka billing consumer uses (payperuse_consumer.
        _billing), evaluated here instead of waiting for that Key's next
        billed request to eventually self-correct it. Without this, an
        allocation edit that resolves a Key's ceiling down to (or below)
        its current usage leaves the flag exactly where it was — usually
        unset — so every request in between is let through with nothing
        left to spend.

        Safe to both SET and CLEAR here, unlike the tenant-aggregate
        recompute in TenantService._sync_ppu_wallet_and_exhaustion (which
        deliberately never clears a key that might still be individually
        over ITS OWN ceiling despite the tenant aggregate looking fine):
        this recomputes each Key's flag from that same Key's own new
        ceiling and own usage, so there's no aggregate to mask an
        independent constraint — a resize that gives a Key real headroom
        back genuinely un-exhausts it.

        No-op when this AllocationService wasn't given an APIKeyService
        (kept optional so existing direct-construction tests don't need to
        supply one) or when nothing was actually written.
        """
        if self._api_key_service is None or not snapshot_writes:
            return
        now_exhausted = []
        now_clear = []
        for key_id, new_snap in snapshot_writes.items():
            used, _ = usage_map.get(key_id, (_ZERO, None))
            (now_exhausted if used >= new_snap else now_clear).append(key_id)
        if now_exhausted:
            await self._api_key_service.set_budget_exhausted_for_keys(now_exhausted, True)
        if now_clear:
            await self._api_key_service.set_budget_exhausted_for_keys(now_clear, False)

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
        application_amount_changed: bool,
    ) -> list[APIKeyAllocationResponseItem]:
        """Two different reasons this gets called, two different rules:

        - The Application's own amount actually changed this call
          (``application_amount_changed=True``): its Keys are
          unconditionally re-fit to track that change (refit_unlisted=True)
          — a parent/child relationship, not a sibling one.
        - The Application's own amount did NOT change, but the caller
          nested explicit ``api_keys`` edits under it anyway
          (``application_amount_changed=False``): the Application's total
          is fixed, so this is exactly the same shape as the direct
          Application-level/single-Key endpoints editing some of an
          Application's Keys while its own total holds still — un-listed
          Keys are left exactly as they are (refit_unlisted=False), not
          swept into a re-fit that has no forcing function behind it.

        ``old_application_amount`` is only meaningful for the True case —
        required so that re-fit can scale each Key by the Application's
        actual change instead of normalizing to fill whatever room the
        resize left (see resolve_level's docstring). resolve_level itself
        already returns every Key when refit_unlisted=True, so no
        merge-back-in step is needed here for that path; the False path's
        merge-back happens inside _resolve_and_persist_keys, same as the
        direct endpoints."""
        return await self._resolve_and_persist_keys(
            parent_amount=new_application_amount,
            parent_old_amount=old_application_amount,
            nested_explicit=nested_explicit,
            existing_keys=existing_keys,
            usage_map=usage_map,
            current_user=current_user,
            snapshot_writes=snapshot_writes,
            refit_unlisted=application_amount_changed,
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
        refit_unlisted: bool,
        owning_application_id: Optional[int] = None,
        parent_old_amount: Optional[Decimal] = None,
    ) -> list[APIKeyAllocationResponseItem]:
        """The one place every Key-resolution call site (the Application-scope
        cascade, the direct Application-level endpoint, and the single-Key
        endpoint) actually resolves + persists Keys — same resolve_level
        call, same persistence, same snapshot bookkeeping; only
        ``refit_unlisted`` and the KEY_APPLICATION_MISMATCH check (only
        meaningful when nested under a specific Application) differ per
        call site. ``refit_unlisted=True`` is for _cascade_into_keys only
        (an Application's own total genuinely changing forces its Keys to
        react); the two direct-edit endpoints
        (update_application_key_allocations,
        update_single_api_key_allocation) always pass False — resizing one
        Key never moves another.

        When refit_unlisted=False, resolve_level only returns the rows it
        actually resolved (the explicit ones) — every OTHER existing Key is
        merged back into the response here from its current DB values
        (untouched, always reported as PERCENTAGE — see
        _response_allocation), since the response contract for all three
        endpoints is "every Key under the Application," not just the
        edited ones.
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
            refit_unlisted=refit_unlisted,
            parent_old_amount=parent_old_amount,
        )

        keys_by_id = {key.id: key for key in existing_keys}
        response_rows: list[APIKeyAllocationResponseItem] = []
        resolved_ids: set = set()
        for resolved in resolved_keys:
            resolved_ids.add(resolved.id)
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

        if not refit_unlisted:
            for key in existing_keys:
                if key.id in resolved_ids:
                    continue
                response_rows.append(
                    APIKeyAllocationResponseItem(
                        api_key_id=key.id,
                        allocation=AllocationValue(
                            type="PERCENTAGE", value=key.allocated_percentage or _ZERO
                        ),
                        allocated_budget=key.allocated_budget or _ZERO,
                    )
                )

        return response_rows
