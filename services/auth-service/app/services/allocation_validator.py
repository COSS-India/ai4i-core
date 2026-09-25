"""
Allocation & Reallocation — the one shared validator.

The single algorithm for resolving a parent's ₹ total across its children.
Every write path that does this (PATCH /auth/tenants/{id}/budget, and each
of the three Budget Allocation endpoints — Tenant->Applications,
Application->Keys, and the single-Key endpoint) calls ``resolve_level`` for
that one level; none of them re-derives any part of this math independently.

This module is deliberately pure — no DB session, no I/O. The orchestration
around it (locking the parent, loading children plus their consumed
amounts, persisting resolved rows, cascading into a changed child's own
children) lives in AllocationService, which is what actually talks to the
database. Keeping the algorithm pure is what makes it trivially unit
testable.
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
    # Display-only — an Application's name or a Key's key_name, when the caller has
    # one. Used solely to name names in an ALLOCATION_TOTAL_EXCEEDED message; every
    # other comparison in this module keys strictly off `id`. Falls back to "id=<id>"
    # wherever it's None, so passing it is optional, not required.
    label: Optional[str] = None


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


def _label(row: AllocationRow) -> str:
    return row.label if row.label else f"id={row.id}"


def resolve_level(
    parent_new_amount: Decimal,
    children: list[AllocationRow],
    explicit: list[ExplicitInput],
    *,
    parent_label: str = "the parent",
) -> list[ResolvedRow]:
    """Resolve one parent's children against parent_new_amount.

    Every explicit row is converted (percentage <-> amount) and floor-checked
    against what it's already consumed. A child NOT listed is left exactly as
    it is — not resolved, not returned — only counted at its CURRENT amount
    toward the sibling-sum feasibility gate below: a sibling nobody mentioned
    keeps whatever it already had, full stop. No child's ₹ is ever auto-resized
    just because its parent's total changed or a sibling was explicitly edited
    — the same rule at every level and every call site (see AllocationService's
    module docstring). A sibling-sum check closes the loop as a defensive gate.

    Cascading into a resolved child's OWN children (e.g. an Application's
    own Keys, once the Application's amount changes) is NOT done here —
    that needs DB access (loading the child's own children) and belongs in
    the orchestrator (AllocationService), which calls this function again,
    one level down, for each child whose amount actually changed or whose
    own children were explicitly edited.

    ``parent_label`` names the parent in an ALLOCATION_TOTAL_EXCEEDED message only
    (e.g. "This Institution's Budget", "Application App1's Budget") — purely
    cosmetic, defaults to the generic "the parent" when the caller doesn't have
    (or doesn't need) a friendlier name. Each ``AllocationRow.label`` does the same
    for a child named in that same message.

    Raises ValidationError (422) for PERCENTAGE_AMOUNT_MISMATCH,
    ALLOCATION_BELOW_CONSUMED, ALLOCATION_TOTAL_EXCEEDED, or
    BUDGET_OVERCOMMITTED; EntityNotFoundError (404) if an explicit row's id
    isn't among ``children``.

    Historical note: this function used to also offer a refit_unlisted=True
    mode — proportionally re-fitting every unlisted child to track the
    PARENT's own change, rather than leaving it exactly as it was. Removed
    (not merely disabled) once every call site had migrated off it — no
    Application or Key auto-resizes just because its parent was resized any
    more, at either edge of the hierarchy. See git history on this file /
    AllocationService for the removed algorithm if a future edge genuinely
    needs proportional re-fitting again.
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
        # amount != child.allocated_amount: an explicit row that resolves to
        # EXACTLY what the child already has isn't an active reduction —
        # it's a no-op re-affirmation of a ceiling the system already
        # tolerates in steady state (e.g. a 0%-allocated Key that picked up
        # a sliver of consumed spend via the one-call-past-exhaustion
        # design). The floor check exists to stop a call from actively
        # pushing a ceiling below what's already spent, not to permanently
        # lock out every future request that happens to touch a child
        # already in that state without changing it.
        if amount < child.consumed_amount and amount != child.allocated_amount:
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
        )

    # Reject here, before the sibling-sum gate below, whenever the explicit
    # rows alone already exceed the parent's new total — same code that
    # gate would eventually raise for the equivalent case, just earlier
    # and correctly attributed to the explicit ask itself rather than
    # conflated with every untouched sibling's total too.
    if explicit_total > parent_new_amount:
        parts = ", ".join(f"{_label(children_by_id[cid])} ({resolved[cid].amount})" for cid in explicit_by_id)
        raise ValidationError(
            message=(
                f"{parent_label} only has {parent_new_amount} available, but this request "
                f"alone would allocate {explicit_total} across {parts} — before any other "
                f"sibling is even considered."
            ),
            code="ALLOCATION_TOTAL_EXCEEDED",
        )

    # Untouched siblings keep their current amount exactly — not resolved,
    # not returned. Still counted at their CURRENT amount for the
    # feasibility gate below: the explicit rows must still fit alongside
    # every sibling this call leaves alone.
    unlisted = [c for c in children if c.id not in explicit_by_id]
    sibling_total = explicit_total + sum((c.allocated_amount for c in unlisted), Decimal("0"))

    # Sibling-sum check — the final defensive gate. sibling_total includes
    # every UNTOUCHED sibling's stored ₹ exactly as persisted, which can
    # carry a few cents of legacy drift from independently-rounded
    # percentage->₹ derivations at creation time (see
    # ApplicationService._assert_allocation_within_cap, now ₹-gated to stop
    # new drift from accruing). Without some tolerance here, a tenant that
    # already drifted a cent over its true ceiling — through no fault of
    # whichever sibling THIS call happens to be resolving — would be
    # permanently unable to edit ANY sibling ever again, since "siblings
    # never move unless explicitly listed" means this call can't silently
    # correct their stored ₹ either. Bounded to a cent per sibling in this
    # resolution: enough to absorb that legacy rounding debt (bounded by
    # construction to well under a cent per independently-rounded row),
    # never enough to mask a genuine over-allocation, which would be off by
    # whole rupees, not fractions of a cent per row.
    drift_tolerance = _AMT_QUANT * len(children)
    if sibling_total > parent_new_amount + drift_tolerance:
        # Name what actually collided, not just the two totals — an admin
        # reducing a parent (or growing one explicit child) otherwise sees
        # two numbers with no indication that its OTHER children are what
        # it collided with (e.g. an Application's own API Keys).
        detail = ""
        holders = [c for c in unlisted if c.allocated_amount > 0]
        if holders:
            parts = ", ".join(f"{_label(c)} ({c.allocated_amount})" for c in holders)
            detail = f" Already allocated to {parts}."
        raise ValidationError(
            message=(
                f"{parent_label} only has {parent_new_amount} available, which cannot "
                f"cover the {sibling_total} this resolves to.{detail}"
            ),
            code="ALLOCATION_TOTAL_EXCEEDED",
        )

    # Preserve input order (children as given), not dict insertion order.
    # ``resolved`` only ever holds explicit rows, so untouched siblings are
    # correctly absent from the return value too.
    return [resolved[c.id] for c in children if c.id in resolved]
