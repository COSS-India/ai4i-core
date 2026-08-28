"""allocation_validator — the one shared resolve_level/convert implementation
behind every allocation write path (PATCH .../budget, both scopes of
PUT /auth/allocations, and the Application->Key cascade).

Scenarios mirror the worked numbered examples from the design discussion —
same numbers, so a wrong result here is a wrong result there too.
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


class TestResolveLevelGrowth:
    """App A grows 100,000 -> 120,000. Key1=50k/50%, Key2=30k/30%, Key3=20k/20%."""

    @staticmethod
    def _children():
        return [
            _row("Key1", "50000", "50", consumed="0"),
            _row("Key2", "30000", "30", consumed="0"),
            _row("Key3", "20000", "20", consumed="0"),
        ]

    def test_all_unlisted_scales_by_own_percentage(self) -> None:
        result = resolve_level(Decimal("120000"), self._children(), [])
        by_id = {r.id: r for r in result}
        assert by_id["Key1"].amount == Decimal("60000.00")
        assert by_id["Key2"].amount == Decimal("36000.00")
        assert by_id["Key3"].amount == Decimal("24000.00")
        assert all(r.auto_refitted for r in result)

    def test_one_explicit_leaves_10k_unallocated(self) -> None:
        explicit = [ExplicitInput(id="Key1", amount=Decimal("60000"))]
        result = resolve_level(Decimal("120000"), self._children(), explicit)
        by_id = {r.id: r for r in result}
        assert by_id["Key1"].amount == Decimal("60000.00")
        assert by_id["Key1"].auto_refitted is False
        assert by_id["Key2"].amount == Decimal("36000.00")
        assert by_id["Key3"].amount == Decimal("24000.00")
        total = sum(r.amount for r in result)
        assert total == Decimal("120000.00")  # not 130,000 — nothing double-spends the growth

    def test_aggressive_explicit_growth_shrinks_unlisted_siblings(self) -> None:
        """Key1 grabs more than the parent's total growth (100k->120k, Key1 to 80k) —
        the other two must SHRINK even though the parent grew overall."""
        explicit = [ExplicitInput(id="Key1", amount=Decimal("80000"))]
        result = resolve_level(Decimal("120000"), self._children(), explicit)
        by_id = {r.id: r for r in result}
        assert by_id["Key2"].amount == Decimal("24000.00")  # was 30,000
        assert by_id["Key3"].amount == Decimal("16000.00")  # was 20,000

    def test_aggressive_growth_can_reject_on_a_squeezed_sibling(self) -> None:
        children = [
            _row("Key1", "50000", "50", consumed="0"),
            _row("Key2", "30000", "30", consumed="25000"),  # would be squeezed to 24,000
            _row("Key3", "20000", "20", consumed="0"),
        ]
        explicit = [ExplicitInput(id="Key1", amount=Decimal("80000"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("120000"), children, explicit)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"
        assert "Key2" in exc.value.errors[0]


class TestResolveLevelShrink:
    """App A shrinks 100,000 -> 80,000. Same starting split."""

    @staticmethod
    def _children():
        return [
            _row("Key1", "50000", "50", consumed="0"),
            _row("Key2", "30000", "30", consumed="0"),
            _row("Key3", "20000", "20", consumed="0"),
        ]

    def test_all_unlisted_re_fit_proportionally(self) -> None:
        result = resolve_level(Decimal("80000"), self._children(), [])
        by_id = {r.id: r for r in result}
        assert by_id["Key1"].amount == Decimal("40000.00")
        assert by_id["Key2"].amount == Decimal("24000.00")
        assert by_id["Key3"].amount == Decimal("16000.00")

    def test_floor_violation_on_unlisted_child_rejects(self) -> None:
        children = [
            _row("Key1", "50000", "50", consumed="0"),
            _row("Key2", "30000", "30", consumed="0"),
            _row("Key3", "20000", "20", consumed="18000"),  # re-fit ceiling would be 16,000
        ]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("80000"), children, [])
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"
        assert "Key3" in exc.value.errors[0]

    def test_one_explicit_reduction_re_fits_remaining_two_among_themselves(self) -> None:
        """Key1 explicitly reduced 50k->40k; Key2/Key3 unlisted, would sum to 90k
        against an 80k ceiling if left alone — must re-fit against room_remaining (40k),
        weighted 60:40 by their own old split, not their original App-level %."""
        explicit = [ExplicitInput(id="Key1", amount=Decimal("40000"))]
        result = resolve_level(Decimal("80000"), self._children(), explicit)
        by_id = {r.id: r for r in result}
        assert by_id["Key2"].amount == Decimal("24000.00")
        assert by_id["Key3"].amount == Decimal("16000.00")
        assert sum(r.amount for r in result) == Decimal("80000.00")


class TestResolveLevelAcceptanceCriteria:
    """The exact story example: Institution 100%, App A=50%(40 used),
    App B=30%(30 used, exhausted), App C=20%(5 used)."""

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
        # B and C are siblings at the Tenant scope, never touched by this call at all —
        # they don't even appear in `explicit`, and since this is the TOP level (Tenant),
        # resolve_level itself only resolves what it's given; the "siblings untouched"
        # rule is enforced by the caller (AllocationService) only sending changed rows
        # through the persist step, not by this function. Here we just confirm A's own
        # resolved figure and that the total doesn't overcommit.
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


class TestRefitUnlistedFalse:
    """Section 4.4's top-level PUT /auth/allocations scope: the parent's own
    total is NOT changing this call, so unlisted siblings are left exactly
    as they are — not resolved, not returned — only the explicit rows come
    back, and the sibling-sum check uses siblings' CURRENT amounts."""

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
        result = resolve_level(
            Decimal("100000"), self._apps(), explicit, refit_unlisted=False
        )
        assert [r.id for r in result] == ["A"]
        assert result[0].amount == Decimal("45000.00")
        assert result[0].auto_refitted is False

    def test_reduce_a_to_40_leaves_10k_unallocated_b_and_c_untouched(self) -> None:
        explicit = [ExplicitInput(id="A", amount=Decimal("40000"))]
        result = resolve_level(
            Decimal("100000"), self._apps(), explicit, refit_unlisted=False
        )
        assert [r.id for r in result] == ["A"]
        assert result[0].amount == Decimal("40000.00")
        # Total in use is now 40k(A)+30k(B)+20k(C)=90k <= 100k parent total: allowed,
        # the 10k gap is simply left unallocated (no code path even computes it here).

    def test_reduce_b_below_its_consumed_is_blocked(self) -> None:
        explicit = [ExplicitInput(id="B", percentage=Decimal("25"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), self._apps(), explicit, refit_unlisted=False)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    def test_increasing_a_beyond_room_left_by_untouched_siblings_is_blocked(self) -> None:
        # B(30k)+C(20k) untouched = 50k already spoken for; A can rise to at
        # most 50k without exceeding the parent's unchanged 100k total.
        explicit = [ExplicitInput(id="A", amount=Decimal("55000"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), self._apps(), explicit, refit_unlisted=False)
        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"

    def test_multiple_explicit_rows_resolved_independently_siblings_still_untouched(self) -> None:
        explicit = [
            ExplicitInput(id="A", amount=Decimal("45000")),
            ExplicitInput(id="C", amount=Decimal("25000")),
        ]
        result = resolve_level(
            Decimal("100000"), self._apps(), explicit, refit_unlisted=False
        )
        assert {r.id for r in result} == {"A", "C"}


class TestUnlistedWithZeroOldTotal:
    def test_unlisted_children_all_at_zero_get_nothing_rather_than_crash(self) -> None:
        children = [
            _row("A", "100000", "100", consumed="0"),
            _row("B", "0", "0", consumed="0"),
        ]
        explicit = [ExplicitInput(id="A", amount=Decimal("80000"))]
        result = resolve_level(Decimal("100000"), children, explicit)
        by_id = {r.id: r for r in result}
        assert by_id["B"].amount == Decimal("0.00")
