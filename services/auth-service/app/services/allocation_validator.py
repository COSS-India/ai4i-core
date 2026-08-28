"""
Allocation & Reallocation — the one shared validator.

Implements allocation-reallocation-flow.md Section 2b's algorithm exactly
once. Every write path that resolves a parent's ₹ total across its children
(PATCH /auth/tenants/{id}/budget, and both scopes of PUT /auth/allocations —
Tenant→Applications and Application→Keys) calls ``resolve_level`` for that
one level; none of them re-derives any part of this math independently.

This module is deliberately pure — no DB session, no I/O. The orchestration
around it (locking the parent, loading children plus their consumed
amounts, persisting resolved rows, cascading into a changed child's own
children) lives in AllocationService, which is what actually talks to the
database. Keeping the algorithm pure is what makes it trivially unit
testable and unambiguous to read against the design doc's own pseudocode.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.core.exceptions import EntityNotFoundError, ValidationError

# Column precision: applications.allocated_percentage / api_key.allocated_percentage
# are NUMERIC(5, 2); allocated_budget columns are NUMERIC(15, 2). Both round to
# 2 decimal places — quantizing here (not leaving it to the DB driver) is what
# guarantees the server's own resolved figures are exactly what gets persisted,
# not something the DB silently truncates differently on write.
_PCT_QUANT = Decimal("0.01")
_AMT_QUANT = Decimal("0.01")


def _quantize(value: Decimal, quant: Decimal) -> Decimal:
    return value.quantize(quant, rounding=ROUND_HALF_UP)


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
) -> list[ResolvedRow]:
    """Resolve one parent's children against parent_new_amount.

    Section 2b, steps 2–6 + 8, for a single level:
      - every explicit row gets converted (percentage <-> amount) and floor-checked
      - a sibling check closes the loop as a defensive gate

    ``refit_unlisted`` picks which of Section 2b vs. Section 4.4's two-rule
    split applies, and is the one thing that differs between this function's
    three callers — everything else here is identical for all of them:

      - True (default): every child NOT listed is proportionally re-fit
        against whatever's left (room_remaining), weighted by its own share
        of the unlisted group's old total — unconditional, on both growth
        and shrink; never just "left alone". Correct whenever the PARENT's
        own total is what actually changed this call: PATCH .../budget's
        cascade into its Applications, and PUT /auth/allocations' cascade
        from a just-resized row into its own un-listed children (Section
        4.4: "within a row you DID list and resize... go through the
        unconditional re-fit rule... NOT left untouched").
      - False: unlisted children are left exactly as they are — not
        resolved, not returned — only counted at their CURRENT amount
        toward the sibling-sum feasibility gate below. Correct for
        PUT /auth/allocations' own top-level scope, where the parent's
        total is explicitly NOT changing in this call (Section 4.4:
        "Sibling rows you don't mention are left exactly as they are —
        full stop... there's no pie to reslice for a row you never
        mentioned").

    Cascading into a resolved child's OWN children (step 7) is NOT done here —
    that needs DB access (loading the child's own children) and belongs in the
    orchestrator (AllocationService), which calls this function again, one
    level down, for each child whose amount actually changed.

    Raises ValidationError (422) for PERCENTAGE_AMOUNT_MISMATCH,
    ALLOCATION_BELOW_CONSUMED, or ALLOCATION_TOTAL_EXCEEDED; EntityNotFoundError
    (404) if an explicit row's id isn't among ``children``.
    """
    children_by_id = {c.id: c for c in children}
    explicit_by_id = {e.id: e for e in explicit}

    unknown_ids = explicit_by_id.keys() - children_by_id.keys()
    if unknown_ids:
        raise EntityNotFoundError(f"Allocation target(s) {sorted(map(str, unknown_ids))}")

    # Step 2 — feasibility: is the parent already over its own new total, independent
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

    # Step 3 — every explicit row.
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
        # Steps 4–6 — every unlisted child, unconditionally re-fit against what's left.
        room_remaining = parent_new_amount - explicit_total
        unlisted_old_total = sum((c.allocated_amount for c in unlisted), Decimal("0"))

        for child in unlisted:
            if unlisted_old_total > 0:
                share = child.allocated_amount / unlisted_old_total
                amount = _quantize(room_remaining * share, _AMT_QUANT)
            else:
                # Nothing to weight by — every unlisted child currently holds 0.
                # Room stays unallocated rather than guessing a split.
                amount = Decimal("0")
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
        # not returned (Section 4.4: "left exactly as they are — full stop").
        # Still counted at their CURRENT amount for the feasibility gate below:
        # the parent's own total isn't changing in this call, so the explicit
        # rows must still fit alongside every sibling this call leaves alone.
        sibling_total = explicit_total + sum((c.allocated_amount for c in unlisted), Decimal("0"))

    # Step 8 — sibling check. Should always hold by construction when
    # refit_unlisted=True (room_remaining IS the unlisted group's target sum)
    # — kept as the final defensive gate, not the primary mechanism. When
    # refit_unlisted=False it's the ONLY thing stopping an explicit increase
    # from pushing the level over its parent's unchanged total.
    if sibling_total > parent_new_amount:
        raise ValidationError(
            message=f"Resolved total ({sibling_total}) exceeds the parent's amount ({parent_new_amount}).",
            code="ALLOCATION_TOTAL_EXCEEDED",
        )

    # Preserve input order (children as given), not dict insertion order.
    # With refit_unlisted=False, ``resolved`` only holds explicit rows, so
    # untouched siblings are correctly absent from the return value too.
    return [resolved[c.id] for c in children if c.id in resolved]
