"""
Allocation & Reallocation — the one shared validator.

The single algorithm for resolving a parent's ₹ total across its children.
Every write path that does this (PATCH /auth/tenants/{id}/budget, and both
scopes of PUT /auth/allocations — Tenant->Applications and Application->Keys)
calls ``resolve_level`` for that one level; none of them re-derives any part
of this math independently.

This module is deliberately pure — no DB session, no I/O. The orchestration
around it (locking the parent, loading children plus their consumed
amounts, persisting resolved rows, cascading into a changed child's own
children) lives in AllocationService, which is what actually talks to the
database. Keeping the algorithm pure is what makes it trivially unit
testable.
"""

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Optional

from app.core.exceptions import EntityNotFoundError, ValidationError

# Column precision: applications.allocated_percentage / api_key.allocated_percentage
# are NUMERIC(5, 2); allocated_budget columns are NUMERIC(15, 2). Both round to
# 2 decimal places — quantizing here (not leaving it to the DB driver) is what
# guarantees the server's own resolved figures are exactly what gets persisted,
# not something the DB silently truncates differently on write.
_PCT_QUANT = Decimal("0.01")
_AMT_QUANT = Decimal("0.01")


def _quantize(value: Decimal, quant: Decimal, rounding=ROUND_HALF_UP) -> Decimal:
    return value.quantize(quant, rounding=rounding)


@dataclass(frozen=True)
class AllocationRow:
    """One child's current state, as read from the DB under the parent's lock."""

    id: object
    allocated_amount: Decimal
    allocated_percentage: Decimal
    consumed_amount: Decimal
    has_children: bool = False


@dataclass(frozen=True)
class ExplicitInput:
    """One caller-submitted row — exactly one of percentage/amount."""

    id: object
    percentage: Optional[Decimal] = None
    amount: Optional[Decimal] = None


@dataclass(frozen=True)
class ResolvedRow:
    id: object
    amount: Decimal
    percentage: Decimal
    changed: bool
    auto_refitted: bool  # True for an unlisted child the cascade touched, not an explicit row


def convert(explicit: ExplicitInput, parent_amount: Decimal) -> tuple[Decimal, Decimal]:
    """Resolve one explicit row to (amount, percentage).

    Exactly one of percentage/amount must be given — the server always
    computes the other from it, here, regardless of what a client-side
    preview may have already shown for that other field. Nothing from a
    request body is ever trusted for both; giving both (even if they'd
    agree) is rejected the same as giving neither, so there's exactly one
    source of truth per row, always.
    """
    has_pct = explicit.percentage is not None
    has_amt = explicit.amount is not None
    if has_pct == has_amt:  # both or neither
        raise ValidationError(
            message=(
                "Exactly one of allocated_percentage or allocated_budget must be given "
                f"for id={explicit.id}."
            ),
            code="PERCENTAGE_AMOUNT_MISMATCH",
        )
    if has_amt:
        amount = _quantize(explicit.amount, _AMT_QUANT)
        percentage = _quantize(
            (amount / parent_amount * 100) if parent_amount else Decimal("0"), _PCT_QUANT
        )
    else:
        percentage = _quantize(explicit.percentage, _PCT_QUANT)
        amount = _quantize(parent_amount * percentage / 100, _AMT_QUANT)
    return amount, percentage


def resolve_level(
    parent_new_amount: Decimal,
    children: list[AllocationRow],
    explicit: list[ExplicitInput],
    *,
    refit_unlisted: bool = True,
    parent_old_amount: Optional[Decimal] = None,
) -> list[ResolvedRow]:
    """Resolve one parent's children against parent_new_amount.

    Every explicit row is converted (percentage <-> amount) and floor-checked
    against what it's already consumed. What happens to the children NOT
    listed depends on ``refit_unlisted``:

      - True (default): every unlisted child is proportionally re-fit to
        track the PARENT's own change, rather than normalized to fill
        whatever room is left. Concretely: the unlisted group's new combined
        total = its own old total, scaled by (room now available to the
        group) / (room that was available to it before this call) — so a
        child that already held less than its share of the parent's old
        room keeps holding proportionally less of the new room too, instead
        of being topped up to fill the gap just because it wasn't listed.
        Requires ``parent_old_amount`` (the parent's amount immediately
        before this call — raises ``ValueError`` if omitted, since without
        it "the room available before" is undefined). Correct whenever the
        PARENT's own total is what actually changed this call: a Tenant's
        or Application's own budget revision cascading into its children,
        or one call's own just-resized row cascading into ITS un-listed
        children one level down.
      - False: unlisted children are left exactly as they are — not
        resolved, not returned — only counted at their CURRENT amount
        toward the sibling-sum feasibility gate below. Correct when the
        parent's own total is NOT changing in this call and only a subset
        of its children are being explicitly rebalanced among themselves —
        a sibling nobody mentioned keeps whatever it already had, full stop.

    Within the True branch, each unlisted child's share is quantized to
    cents independently except the last (by ``children`` order), which
    absorbs whatever the others' rounding left over — so the group's
    resolved total is exact by construction, not by luck of the rounding;
    two children independently rounding up by half a cent each must not be
    able to trip the sibling-sum check below on their own.

    A sibling-sum check closes the loop as a defensive gate in both cases.

    Cascading into a resolved child's OWN children (e.g. an Application's
    own Keys, once the Application's amount changes) is NOT done here —
    that needs DB access (loading the child's own children) and belongs in
    the orchestrator (AllocationService), which calls this function again,
    one level down, for each child whose amount actually changed or whose
    own children were explicitly edited.

    Raises ValidationError (422) for PERCENTAGE_AMOUNT_MISMATCH,
    ALLOCATION_BELOW_CONSUMED, ALLOCATION_TOTAL_EXCEEDED, or
    BUDGET_OVERCOMMITTED; EntityNotFoundError (404) if an explicit row's id
    isn't among ``children``; ValueError (a caller bug, not a request-shape
    one) if ``refit_unlisted=True`` and ``parent_old_amount`` is omitted.
    """
    children_by_id = {c.id: c for c in children}
    explicit_by_id = {e.id: e for e in explicit}

    unknown_ids = explicit_by_id.keys() - children_by_id.keys()
    if unknown_ids:
        raise EntityNotFoundError(f"Allocation target(s) {sorted(map(str, unknown_ids))}")

    # Feasibility gate: is the parent already over its own new total, independent
    # of anything being edited in this call? Catches "already broken before this
    # request touched it" rather than surfacing as a confusing sibling-check failure.
    already_spent = sum((c.consumed_amount for c in children), Decimal("0"))
    if already_spent > parent_new_amount:
        raise ValidationError(
            message=(
                f"Already-consumed total ({already_spent}) exceeds the proposed new "
                f"amount ({parent_new_amount})."
            ),
            code="BUDGET_OVERCOMMITTED",
        )

    resolved: dict[object, ResolvedRow] = {}

    # Every explicit row.
    explicit_total = Decimal("0")
    for child_id, row in explicit_by_id.items():
        child = children_by_id[child_id]
        amount, percentage = convert(row, parent_new_amount)
        if amount < child.consumed_amount:
            raise ValidationError(
                message=(
                    f"id={child_id} has already consumed {child.consumed_amount}, which is "
                    f"above the requested ceiling of {amount}."
                ),
                code="ALLOCATION_BELOW_CONSUMED",
                errors=[f"id={child_id} consumed_amount={child.consumed_amount} requested_budget={amount}"],
            )
        explicit_total += amount
        resolved[child_id] = ResolvedRow(
            id=child_id,
            amount=amount,
            percentage=percentage,
            changed=(amount != child.allocated_amount),
            auto_refitted=False,
        )

    unlisted = [c for c in children if c.id not in explicit_by_id]

    if refit_unlisted:
        if parent_old_amount is None:
            raise ValueError(
                "resolve_level(refit_unlisted=True) requires parent_old_amount — the "
                "unlisted group's re-fit tracks the parent's own change, it doesn't "
                "normalize to fill whatever room happens to be left."
            )
        room_remaining = parent_new_amount - explicit_total
        unlisted_old_total = sum((c.allocated_amount for c in unlisted), Decimal("0"))
        explicit_old_total = sum(
            (children_by_id[child_id].allocated_amount for child_id in explicit_by_id), Decimal("0")
        )
        # Room historically available to the unlisted group, before this call —
        # NOT the same as unlisted_old_total whenever the group didn't already
        # fill it. Scaling by (new room / old room) rather than normalizing to
        # unlisted_old_total is what keeps deliberately-left-unallocated room
        # unallocated (proportionally scaled, not silently absorbed) instead of
        # inflating an under-allocated child to fill whatever's left.
        old_room_for_unlisted = parent_old_amount - explicit_old_total

        if old_room_for_unlisted > 0 and unlisted_old_total > 0:
            unlisted_target_total = _quantize(
                unlisted_old_total * (room_remaining / old_room_for_unlisted), _AMT_QUANT
            )
        else:
            # Either nothing was historically available to this group, or every
            # member of it currently holds 0 — nothing to scale from either way;
            # the room stays unallocated rather than guessing a split.
            unlisted_target_total = Decimal("0")

        running_total = Decimal("0")
        for index, child in enumerate(unlisted):
            is_last = index == len(unlisted) - 1
            if unlisted_target_total == 0:
                amount = Decimal("0")
            elif is_last:
                # Absorbs whatever the independently-rounded amounts above left
                # over, so the group's total is exact by construction. For a
                # non-negative unlisted_target_total, this residual is also
                # never negative: every non-last child below is rounded DOWN,
                # so none of them is ever quantized above its own ideal share,
                # which keeps running_total from ever exceeding the target.
                amount = unlisted_target_total - running_total
            else:
                # ROUND_DOWN, not the module's usual ROUND_HALF_UP — see the
                # `is_last` branch above for why: truncating instead of
                # rounding is what makes "the last child's residual is never
                # negative" a guarantee rather than a fix bolted on after the
                # fact.
                share = child.allocated_amount / unlisted_old_total
                amount = _quantize(unlisted_target_total * share, _AMT_QUANT, rounding=ROUND_DOWN)
            running_total += amount
            percentage = _quantize(
                (amount / parent_new_amount * 100) if parent_new_amount else Decimal("0"), _PCT_QUANT
            )
            if amount < child.consumed_amount:
                raise ValidationError(
                    message=(
                        f"id={child.id} would be re-fit to {amount} (from {child.allocated_amount}), "
                        f"below its already-consumed {child.consumed_amount}."
                    ),
                    code="ALLOCATION_BELOW_CONSUMED",
                    errors=[f"id={child.id} consumed_amount={child.consumed_amount} requested_budget={amount}"],
                )
            resolved[child.id] = ResolvedRow(
                id=child.id,
                amount=amount,
                percentage=percentage,
                changed=(amount != child.allocated_amount),
                auto_refitted=True,
            )
        sibling_total = sum((r.amount for r in resolved.values()), Decimal("0"))
    else:
        # Untouched siblings keep their current amount exactly — not resolved,
        # not returned. Still counted at their CURRENT amount for the
        # feasibility gate below: the parent's own total isn't changing in
        # this call, so the explicit rows must still fit alongside every
        # sibling this call leaves alone.
        sibling_total = explicit_total + sum((c.allocated_amount for c in unlisted), Decimal("0"))

    # Sibling-sum check. Should always hold by construction when
    # refit_unlisted=True and unlisted_target_total is non-negative:
    # unlisted_target_total never exceeds room_remaining, and the group
    # always resolves to EXACTLY unlisted_target_total — every non-last
    # child's ROUND_DOWN amount never exceeds its own ideal share, so the
    # last child's residual is never negative, so nothing is ever clamped or
    # otherwise made inexact. This is kept as the final defensive gate, not
    # the primary mechanism, precisely so a future change to the rounding
    # above that breaks that guarantee fails loudly here instead of silently
    # persisting an over-committed total. When refit_unlisted=False it's the
    # ONLY thing stopping an explicit increase from pushing the level over
    # its parent's unchanged total.
    if sibling_total > parent_new_amount:
        raise ValidationError(
            message=f"Resolved total ({sibling_total}) exceeds the parent's amount ({parent_new_amount}).",
            code="ALLOCATION_TOTAL_EXCEEDED",
        )

    # Preserve input order (children as given), not dict insertion order.
    # With refit_unlisted=False, ``resolved`` only holds explicit rows, so
    # untouched siblings are correctly absent from the return value too.
    return [resolved[c.id] for c in children if c.id in resolved]
