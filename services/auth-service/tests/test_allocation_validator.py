"""allocation_validator — the one shared resolve_level/convert implementation
behind every allocation write path (PATCH .../budget and each of the three
Budget Allocation endpoints).

Scenarios mirror the worked numbered examples from the design discussion —
same numbers, so a wrong result here is a wrong result there too.

resolve_level used to also offer a refit_unlisted=True mode — proportionally
re-fitting every unlisted child to track the PARENT's own change. Removed
(not merely disabled) once every AllocationService call site had migrated
off it — no Application or Key auto-resizes just because its parent was
resized any more, at either edge of the hierarchy. The tests that used to
pin that mode directly (growth/shrink re-fit, the no-op exemption on an
unlisted child's re-fit, the zero-old-total/stored-percentage fallbacks, the
slack-preservation cases, and the unlisted-group rounding-remainder
absorption) went with it — none of that code exists to test any more. See
git history on this file / allocation_validator.py if a future edge
genuinely needs proportional re-fitting again.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.services.allocation_validator import (
    AllocationRow,
    ExplicitInput,
    convert,
    resolve_level,
)


def _row(id_, amount, pct, consumed="0", has_children=False) -> AllocationRow:
    return AllocationRow(
        id=id_,
        allocated_amount=Decimal(amount),
        allocated_percentage=Decimal(pct),
        consumed_amount=Decimal(consumed),
        has_children=has_children,
    )


class TestConvert:
    def test_amount_given_derives_percentage(self) -> None:
        amount, pct = convert(ExplicitInput(id=1, amount=Decimal("40000")), Decimal("100000"))
        assert amount == Decimal("40000.00")
        assert pct == Decimal("40.00")

    def test_percentage_given_derives_amount(self) -> None:
        amount, pct = convert(ExplicitInput(id=1, percentage=Decimal("40")), Decimal("100000"))
        assert amount == Decimal("40000.00")
        assert pct == Decimal("40.00")

    def test_both_given_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            convert(ExplicitInput(id=1, percentage=Decimal("40"), amount=Decimal("40000")), Decimal("100000"))
        assert exc.value.code == "PERCENTAGE_AMOUNT_MISMATCH"

    def test_neither_given_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            convert(ExplicitInput(id=1), Decimal("100000"))
        assert exc.value.code == "PERCENTAGE_AMOUNT_MISMATCH"

    def test_rounds_to_two_decimal_places(self) -> None:
        # 33333 / 100000 * 100 = 33.333 -> rounds to 33.33
        amount, pct = convert(ExplicitInput(id=1, amount=Decimal("33333")), Decimal("100000"))
        assert pct == Decimal("33.33")


class TestResolveLevelUnknownRow:
    def test_explicit_row_for_unknown_id_raises_not_found(self) -> None:
        children = [_row("A", "50000", "50")]
        with pytest.raises(EntityNotFoundError):
            resolve_level(
                Decimal("100000"), children,
                [ExplicitInput(id="ZZZ", percentage=Decimal("10"))],
            )


class TestResolveLevelAcceptanceCriteria:
    """The exact story example: Institution 100%, App A=50%(40 used),
    App B=30%(30 used, exhausted), App C=20%(5 used). An unlisted child is
    left exactly as it is — not resolved, not returned — full stop. This is
    what every AllocationService call site actually uses today:
    update_application_key_allocations and update_single_api_key_allocation
    (a sibling Key edit never moves another Key), the Tenant-level
    endpoint's own un-listed Applications (a sibling Application edit
    never moves another Application), AND — via
    cascade_tenant_budget_revision / _cascade_into_keys — the cascade into
    an un-listed Application/Key when its OWN parent resizes too (that
    case additionally recomputes the un-listed child's
    allocated_percentage outside resolve_level itself; see those methods'
    own docstrings)."""

    @staticmethod
    def _apps():
        return [
            _row("A", "50000", "50", consumed="40000", has_children=True),
            _row("B", "30000", "30", consumed="30000", has_children=True),
            _row("C", "20000", "20", consumed="5000", has_children=True),
        ]

    def test_reducing_fully_exhausted_app_b_is_blocked(self) -> None:
        explicit = [ExplicitInput(id="B", percentage=Decimal("25"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), self._apps(), explicit)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    def test_reducing_app_a_to_45_percent_is_allowed(self) -> None:
        explicit = [ExplicitInput(id="A", percentage=Decimal("45"))]
        result = resolve_level(Decimal("100000"), self._apps(), explicit)
        by_id = {r.id: r for r in result}
        assert by_id["A"].amount == Decimal("45000.00")

    def test_reducing_app_a_to_38_percent_is_blocked(self) -> None:
        explicit = [ExplicitInput(id="A", percentage=Decimal("38"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), self._apps(), explicit)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    def test_reducing_app_a_to_40_leaves_10_percent_unallocated(self) -> None:
        explicit = [ExplicitInput(id="A", percentage=Decimal("40"))]
        result = resolve_level(Decimal("100000"), self._apps(), explicit)
        by_id = {r.id: r for r in result}
        # B and C are siblings at the Tenant scope, never touched by this call
        # at all — they don't even appear in `explicit`, and an unlisted
        # child is never resolved or returned either.
        assert set(by_id) == {"A"}
        assert by_id["A"].amount == Decimal("40000.00")


class TestFeasibility:
    def test_already_overcommitted_rejects_before_resolving_anything(self) -> None:
        children = [
            _row("A", "50000", "50", consumed="45000"),
            _row("B", "50000", "50", consumed="50000"),
        ]
        # Total consumed = 95,000; proposed new parent total = 90,000.
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("90000"), children, [])
        assert exc.value.code == "BUDGET_OVERCOMMITTED"


class TestUnlistedChildrenLeftExactlyAsTheyAre:
    """resolve_level's actual (only) behavior for a child not named in
    ``explicit``: left exactly as it is — not resolved, not returned — only
    the explicit rows come back, and the sibling-sum check uses siblings'
    CURRENT amounts.

    This is what every AllocationService call site resolves Keys/
    Applications with today: resizing one Key never moves another Key
    under the same Application (update_application_key_allocations,
    update_single_api_key_allocation), resizing one Application never
    moves another Application (the Tenant-level endpoint's own un-listed
    Applications), and a parent's own resize no longer re-fits its
    un-listed children's ₹ either (see _cascade_into_keys /
    cascade_tenant_budget_revision, which recompute an un-listed child's
    allocated_percentage separately, outside resolve_level)."""

    @staticmethod
    def _apps():
        # Tenant's current allocated_budget = 100,000, fully split already.
        return [
            _row("A", "50000", "50", consumed="40000"),
            _row("B", "30000", "30", consumed="30000"),
            _row("C", "20000", "20", consumed="5000"),
        ]

    def test_unlisted_siblings_are_not_returned(self) -> None:
        explicit = [ExplicitInput(id="A", amount=Decimal("45000"))]
        result = resolve_level(Decimal("100000"), self._apps(), explicit)
        assert [r.id for r in result] == ["A"]
        assert result[0].amount == Decimal("45000.00")

    def test_reduce_a_to_40_leaves_10k_unallocated_b_and_c_untouched(self) -> None:
        explicit = [ExplicitInput(id="A", amount=Decimal("40000"))]
        result = resolve_level(Decimal("100000"), self._apps(), explicit)
        assert [r.id for r in result] == ["A"]
        assert result[0].amount == Decimal("40000.00")
        # Total in use is now 40k(A)+30k(B)+20k(C)=90k <= 100k parent total: allowed,
        # the 10k gap is simply left unallocated (no code path even computes it here).

    def test_reduce_b_below_its_consumed_is_blocked(self) -> None:
        explicit = [ExplicitInput(id="B", percentage=Decimal("25"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), self._apps(), explicit)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    def test_increasing_a_beyond_room_left_by_untouched_siblings_is_blocked(self) -> None:
        # B(30k)+C(20k) untouched = 50k already spoken for; A can rise to at
        # most 50k without exceeding the parent's unchanged 100k total.
        explicit = [ExplicitInput(id="A", amount=Decimal("55000"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), self._apps(), explicit)
        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"

    def test_multiple_explicit_rows_resolved_independently_siblings_still_untouched(self) -> None:
        explicit = [
            ExplicitInput(id="A", amount=Decimal("45000")),
            ExplicitInput(id="C", amount=Decimal("25000")),
        ]
        result = resolve_level(Decimal("100000"), self._apps(), explicit)
        assert {r.id for r in result} == {"A", "C"}

    def test_explicit_row_resubmitted_at_its_unchanged_value_below_consumed_is_allowed(
        self,
    ) -> None:
        """A row that resolves to EXACTLY what it already has isn't an
        active reduction — it's a no-op re-affirmation of a ceiling the
        system already tolerates in steady state (e.g. a 0%-allocated Key
        that picked up a sliver of consumed spend via the one-call-past-
        exhaustion design). Must not be blocked just because it happens to
        already be below its own consumed amount."""
        children = [_row("D", "0", "0", consumed="0.03")]
        explicit = [ExplicitInput(id="D", amount=Decimal("0"))]

        result = resolve_level(Decimal("100000"), children, explicit)

        assert result[0].amount == Decimal("0.00")
        assert result[0].changed is False

    def test_explicit_row_actively_reduced_below_consumed_is_still_blocked(self) -> None:
        """The no-op exemption doesn't neuter the floor check for a REAL
        reduction — only a re-fit that lands exactly back where the row
        already was is exempt."""
        children = [_row("D", "10", "0.01", consumed="8")]
        explicit = [ExplicitInput(id="D", amount=Decimal("5"))]

        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), children, explicit)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    def test_sibling_sum_tolerates_a_cent_of_legacy_rounding_drift_per_sibling(self) -> None:
        """Three Applications whose stored ₹ already sum to 100,000.01 —
        one cent over the Tenant's real 100,000.00 Budget, the kind of
        drift independently-rounded percentage->₹ derivations at creation
        time can leave behind. An edit that doesn't touch any of that
        drift must still be allowed through — the sibling-sum check can't
        silently correct the untouched siblings' stored ₹ (they never move
        unless explicitly listed), so it has to tolerate drift it didn't
        cause and can't fix here."""
        children = [
            _row("A", "33333.34", "33.33"),
            _row("B", "33333.33", "33.33"),
            _row("C", "33333.34", "33.34"),
        ]
        result = resolve_level(Decimal("100000.00"), children, [])
        assert result == []  # nothing explicit, nothing resolved/returned — just didn't raise

    def test_sibling_sum_still_rejects_drift_beyond_the_per_sibling_tolerance(self) -> None:
        """The tolerance is bounded, not a blank check — ten cents of
        overage across three siblings is real over-allocation, not
        rounding noise, and must still be rejected."""
        children = [
            _row("A", "33333.34", "33.33"),
            _row("B", "33333.33", "33.33"),
            _row("C", "33333.43", "33.34"),  # +0.10 vs the tolerated scenario above
        ]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000.00"), children, [])
        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"


class TestAllocationTotalExceededNamesWhatCollided:
    """The message doesn't just report two totals — it names the parent
    (via ``parent_label``) and the specific untouched siblings already
    holding room (via each ``AllocationRow.label``), so an admin can see
    what actually collided instead of guessing."""

    def test_message_names_parent_and_colliding_siblings(self) -> None:
        children = [
            _row("A", "50000", "50", consumed="40000"),
            AllocationRow(
                id="B", allocated_amount=Decimal("30000"), allocated_percentage=Decimal("30"),
                consumed_amount=Decimal("30000"), label="Key B",
            ),
        ]
        explicit = [ExplicitInput(id="A", amount=Decimal("80000"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(
                Decimal("100000"), children, explicit,
                parent_label="Application App1's Budget",
            )
        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        assert "Application App1's Budget" in exc.value.message
        assert "Key B (30000)" in exc.value.message

    def test_unlabeled_child_falls_back_to_its_id(self) -> None:
        children = [
            _row("A", "50000", "50", consumed="40000"),
            _row("B", "30000", "30", consumed="30000"),
        ]
        explicit = [ExplicitInput(id="A", amount=Decimal("80000"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), children, explicit)
        assert "id=B" in exc.value.message
        assert "the parent" in exc.value.message  # default parent_label

    def test_explicit_alone_over_parent_names_the_explicit_rows(self) -> None:
        children = [AllocationRow(
            id="A", allocated_amount=Decimal("50000"), allocated_percentage=Decimal("50"),
            consumed_amount=Decimal("0"), label="App1",
        )]
        explicit = [ExplicitInput(id="A", amount=Decimal("120000"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), children, explicit)
        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        assert "App1 (120000.00)" in exc.value.message
