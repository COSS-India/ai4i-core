"""allocation_validator — the one shared resolve_level/convert implementation
behind every allocation write path (PATCH .../budget, each of the three
Budget Allocation endpoints, and the Application->Key cascade).

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
        result = resolve_level(
            Decimal("120000"), self._children(), [], parent_old_amount=Decimal("100000")
        )
        by_id = {r.id: r for r in result}
        assert by_id["Key1"].amount == Decimal("60000.00")
        assert by_id["Key2"].amount == Decimal("36000.00")
        assert by_id["Key3"].amount == Decimal("24000.00")
        assert all(r.auto_refitted for r in result)

    def test_one_explicit_leaves_10k_unallocated(self) -> None:
        explicit = [ExplicitInput(id="Key1", amount=Decimal("60000"))]
        result = resolve_level(
            Decimal("120000"), self._children(), explicit, parent_old_amount=Decimal("100000")
        )
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
        result = resolve_level(
            Decimal("120000"), self._children(), explicit, parent_old_amount=Decimal("100000")
        )
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
            resolve_level(Decimal("120000"), children, explicit, parent_old_amount=Decimal("100000"))
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"
        assert "Key2" in exc.value.errors[0]

    def test_refit_unlisted_without_parent_old_amount_is_a_caller_bug(self) -> None:
        """The unlisted group's target scales off the parent's own OLD amount —
        omitting it is a caller mistake (not a request-shape 422), so this is a
        plain ValueError, not ValidationError."""
        with pytest.raises(ValueError):
            resolve_level(Decimal("120000"), self._children(), [])

    def test_explicit_row_alone_over_parent_rejects_before_the_refit_loop(self) -> None:
        """An explicit request that alone exceeds the parent's (unchanged)
        total must reject as ALLOCATION_TOTAL_EXCEEDED against the request
        itself — not let refit_unlisted=True's room_remaining go negative,
        re-fit every unlisted sibling toward a negative amount, and have
        the first one trip ALLOCATION_BELOW_CONSUMED instead, naming a
        sibling the caller never mentioned with a negative ceiling."""
        explicit = [ExplicitInput(id="Key1", amount=Decimal("120000"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(
                Decimal("100000"), self._children(), explicit,
                parent_old_amount=Decimal("100000"),
            )
        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"


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
        result = resolve_level(
            Decimal("80000"), self._children(), [], parent_old_amount=Decimal("100000")
        )
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
            resolve_level(Decimal("80000"), children, [], parent_old_amount=Decimal("100000"))
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"
        assert "Key3" in exc.value.errors[0]

    def test_one_explicit_reduction_re_fits_remaining_two_among_themselves(self) -> None:
        """Key1 explicitly reduced 50k->40k; Key2/Key3 unlisted, would sum to 90k
        against an 80k ceiling if left alone — must re-fit against room_remaining (40k),
        weighted 60:40 by their own old split, not their original App-level %."""
        explicit = [ExplicitInput(id="Key1", amount=Decimal("40000"))]
        result = resolve_level(
            Decimal("80000"), self._children(), explicit, parent_old_amount=Decimal("100000")
        )
        by_id = {r.id: r for r in result}
        assert by_id["Key2"].amount == Decimal("24000.00")
        assert by_id["Key3"].amount == Decimal("16000.00")
        assert sum(r.amount for r in result) == Decimal("80000.00")


class TestResolveLevelAcceptanceCriteria:
    """The exact story example: Institution 100%, App A=50%(40 used),
    App B=30%(30 used, exhausted), App C=20%(5 used), exercised here with
    refit_unlisted=False — the Application->Keys edge's own top scope
    (an unlisted Key is left exactly as it is when the Application's own
    total isn't changing), and what AllocationService.
    update_application_key_allocations actually calls. The Tenant->
    Applications edge now calls this with refit_unlisted=True instead — an
    unlisted Application IS proportionally re-fit, even though the Tenant's
    own total isn't changing either (same refit_unlisted=True math the
    other tests below already cover, e.g. TestSlackSurvivesAResize)."""

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
            resolve_level(Decimal("100000"), self._apps(), explicit, refit_unlisted=False)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    def test_reducing_app_a_to_45_percent_is_allowed(self) -> None:
        explicit = [ExplicitInput(id="A", percentage=Decimal("45"))]
        result = resolve_level(Decimal("100000"), self._apps(), explicit, refit_unlisted=False)
        by_id = {r.id: r for r in result}
        assert by_id["A"].amount == Decimal("45000.00")

    def test_reducing_app_a_to_38_percent_is_blocked(self) -> None:
        explicit = [ExplicitInput(id="A", percentage=Decimal("38"))]
        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), self._apps(), explicit, refit_unlisted=False)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    def test_reducing_app_a_to_40_leaves_10_percent_unallocated(self) -> None:
        explicit = [ExplicitInput(id="A", percentage=Decimal("40"))]
        result = resolve_level(Decimal("100000"), self._apps(), explicit, refit_unlisted=False)
        by_id = {r.id: r for r in result}
        # B and C are siblings at the Tenant scope, never touched by this call
        # at all — they don't even appear in `explicit`, and with
        # refit_unlisted=False they're not resolved or returned either.
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


class TestRefitUnlistedFalse:
    """resolve_level's own refit_unlisted=False mode, tested here at the
    validator level: when the parent's total is NOT changing this call,
    unlisted children can be left exactly as they are — not resolved, not
    returned — only the explicit rows come back, and the sibling-sum check
    uses siblings' CURRENT amounts.

    Not currently reachable through AllocationService — every one of its
    call sites resolves Keys with refit_unlisted=True (resizing one Key
    proportionally re-fits its unlisted siblings; see allocation_service.
    _resolve_and_persist_keys), so this mode has no live caller today. Kept
    and tested here because it's a real, distinct mode of the shared
    algorithm, not because anything currently invokes it that way."""

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

        result = resolve_level(Decimal("100000"), children, explicit, refit_unlisted=False)

        assert result[0].amount == Decimal("0.00")
        assert result[0].changed is False

    def test_explicit_row_actively_reduced_below_consumed_is_still_blocked(self) -> None:
        """The no-op exemption doesn't neuter the floor check for a REAL
        reduction — only a re-fit that lands exactly back where the row
        already was is exempt."""
        children = [_row("D", "10", "0.01", consumed="8")]
        explicit = [ExplicitInput(id="D", amount=Decimal("5"))]

        with pytest.raises(ValidationError) as exc:
            resolve_level(Decimal("100000"), children, explicit, refit_unlisted=False)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    def test_sibling_sum_tolerates_a_cent_of_legacy_rounding_drift_per_sibling(self) -> None:
        """Three Applications whose stored ₹ already sum to 100,000.01 —
        one cent over the Tenant's real 100,000.00 Budget, the kind of
        drift independently-rounded percentage->₹ derivations at creation
        time can leave behind. An edit that doesn't touch any of that
        drift must still be allowed through — refit_unlisted=False can't
        silently correct the untouched siblings' stored ₹ (they never
        move unless explicitly listed), so the check has to tolerate
        drift it didn't cause and can't fix here."""
        children = [
            _row("A", "33333.34", "33.33"),
            _row("B", "33333.33", "33.33"),
            _row("C", "33333.34", "33.34"),
        ]
        result = resolve_level(Decimal("100000.00"), children, [], refit_unlisted=False)
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
            resolve_level(Decimal("100000.00"), children, [], refit_unlisted=False)
        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"


class TestUnlistedRefitNoOpExemption:
    """resolve_level's refit_unlisted=True branch: the reviewed bug from
    the "Edit Budget" Application flow. Editing an Application's own ₹
    forces every one of its unlisted Keys through this branch — including
    a Key holding a 0% ceiling that picked up a sliver of consumed spend
    via the one-call-past-exhaustion design. Its proportional re-fit
    naturally lands back at 0 (0% of anything is 0), identical to what it
    already had — that must not be treated as a reduction."""

    def test_unlisted_key_refit_back_to_its_existing_zero_ceiling_is_allowed(self) -> None:
        # KeyX holds the Application's entire 80,000 room; id707 holds 0%
        # but has consumed 0.03 (the one-call-past-exhaustion residue).
        # Application's own ₹ is unchanged (100,000 -> 100,000), still
        # forcing the refit branch since it's what a genuine ₹/% edit to
        # the Application elsewhere in the same request would trigger.
        children = [
            _row("KeyX", "80000", "80", consumed="70000"),
            _row("id707", "0", "0", consumed="0.03"),
        ]
        result = resolve_level(
            Decimal("100000"), children, [], refit_unlisted=True, parent_old_amount=Decimal("100000")
        )
        by_id = {r.id: r for r in result}
        assert by_id["id707"].amount == Decimal("0")
        assert by_id["id707"].changed is False

    def test_unlisted_key_actively_refit_below_its_consumed_is_still_blocked(self) -> None:
        """A shrink that genuinely pushes an unlisted Key's re-fit ceiling
        below what it's consumed — not a no-op — must still be rejected."""
        children = [
            _row("KeyX", "80000", "80", consumed="0"),
            _row("KeyY", "20000", "20", consumed="15000"),
        ]
        # Application shrinks 100,000 -> 50,000: KeyY's proportional share
        # shrinks from 20,000 to 10,000, below its own 15,000 consumed —
        # a real change (20,000 -> 10,000), not a no-op.
        with pytest.raises(ValidationError) as exc:
            resolve_level(
                Decimal("50000"), children, [], refit_unlisted=True,
                parent_old_amount=Decimal("100000"),
            )
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"


class TestUnlistedWithZeroOldTotal:
    def test_unlisted_children_all_at_zero_get_nothing_rather_than_crash(self) -> None:
        # A held the entire parent (100,000 of 100,000) — no historical room
        # was ever available to unlisted B, so B gets 0 regardless of the new
        # room, rather than dividing by an old_room_for_unlisted of 0.
        children = [
            _row("A", "100000", "100", consumed="0"),
            _row("B", "0", "0", consumed="0"),
        ]
        explicit = [ExplicitInput(id="A", amount=Decimal("80000"))]
        result = resolve_level(
            Decimal("100000"), children, explicit, parent_old_amount=Decimal("100000")
        )
        by_id = {r.id: r for r in result}
        assert by_id["B"].amount == Decimal("0.00")

    def test_unlisted_members_at_zero_but_historical_room_existed_still_get_nothing(self) -> None:
        # Unlike the case above, the parent's OLD total (100,000) exceeds what
        # its listed child held (60,000 explicit-old) — 40,000 of historical
        # room existed, just never assigned to any particular unlisted child
        # (both hold 0). Still nothing to weight a split by, so both stay 0 —
        # distinct code path (unlisted_old_total == 0) from the test above
        # (old_room_for_unlisted == 0), both must land on the same outcome.
        children = [
            _row("A", "60000", "60", consumed="0"),
            _row("B", "0", "0", consumed="0"),
            _row("C", "0", "0", consumed="0"),
        ]
        explicit = [ExplicitInput(id="A", amount=Decimal("50000"))]
        result = resolve_level(
            Decimal("90000"), children, explicit, parent_old_amount=Decimal("100000")
        )
        by_id = {r.id: r for r in result}
        assert by_id["B"].amount == Decimal("0.00")
        assert by_id["C"].amount == Decimal("0.00")


class TestSlackSurvivesAResize:
    """The bug: normalizing an unlisted group to fill 100% of whatever room
    is left inflates an under-allocated child instead of preserving the
    slack it never claimed. An Application holds one Key at 10,000 of its
    own 100,000 budget (90,000 deliberately never assigned to any Key); the
    Application is resized down to 40,000. The Key must land at 4,000 (its
    same 10% share, scaled) — 40,000 would silently hand it the entire new
    budget just because it was the only unlisted child."""

    def test_under_allocated_unlisted_child_keeps_its_own_share_not_the_whole_room(self) -> None:
        children = [_row("Key1", "10000", "10", consumed="0")]
        result = resolve_level(
            Decimal("40000"), children, [], parent_old_amount=Decimal("100000")
        )
        by_id = {r.id: r for r in result}
        assert by_id["Key1"].amount == Decimal("4000.00")

    def test_slack_scales_proportionally_alongside_a_partially_allocated_group(self) -> None:
        # Two unlisted Keys share 20,000 of a 100,000 Application (80,000
        # slack); Application resized to 50,000 (half). Each Key's share
        # should halve too (2,000 -> and so on), not jump to fill 50,000.
        children = [
            _row("Key1", "12000", "12", consumed="0"),
            _row("Key2", "8000", "8", consumed="0"),
        ]
        result = resolve_level(
            Decimal("50000"), children, [], parent_old_amount=Decimal("100000")
        )
        by_id = {r.id: r for r in result}
        assert by_id["Key1"].amount == Decimal("6000.00")
        assert by_id["Key2"].amount == Decimal("4000.00")
        # Slack (100,000-20,000=80,000, scaled by 0.5) stays unallocated: 40,000
        # of the new 50,000 total is not handed to Key1/Key2.
        assert sum(r.amount for r in result) == Decimal("10000.00")

    def test_growth_also_preserves_proportional_slack(self) -> None:
        # Same 10%-held Key, Application GROWS 100,000 -> 200,000. Slack must
        # scale up too, not just down — the Key gets 10% of 200,000, not all
        # of it.
        children = [_row("Key1", "10000", "10", consumed="0")]
        result = resolve_level(
            Decimal("200000"), children, [], parent_old_amount=Decimal("100000")
        )
        by_id = {r.id: r for r in result}
        assert by_id["Key1"].amount == Decimal("20000.00")

    def test_fully_allocated_group_still_fills_the_room_exactly(self) -> None:
        # Sanity check the fix doesn't change behaviour when there WAS no
        # slack to begin with (every prior test in this file already covers
        # this implicitly, but this one states the invariant directly).
        children = [
            _row("Key1", "50000", "50", consumed="0"),
            _row("Key2", "50000", "50", consumed="0"),
        ]
        result = resolve_level(
            Decimal("40000"), children, [], parent_old_amount=Decimal("100000")
        )
        assert sum(r.amount for r in result) == Decimal("40000.00")


class TestRoundingRemainderAbsorption:
    """The bug: quantizing each unlisted child's share independently can
    drift the group's sum a cent or two past room_remaining, tripping
    ALLOCATION_TOTAL_EXCEEDED on an otherwise-valid request. Two equal
    children splitting an odd total is the minimal repro: naive independent
    rounding of 1000.05/2 gives 500.03 + 500.03 = 1000.06 > 1000.05."""

    def test_two_equal_children_splitting_an_odd_total_does_not_overflow(self) -> None:
        children = [
            _row("Key1", "50000", "50", consumed="0"),
            _row("Key2", "50000", "50", consumed="0"),
        ]
        # parent_new_amount chosen so unlisted_target_total works out to
        # 1000.05 (an odd number of cents split two ways: 500.025 each,
        # rounds to 500.03 + 500.03 = 1000.06 if done independently).
        result = resolve_level(
            Decimal("1000.05"), children, [], parent_old_amount=Decimal("100000")
        )
        total = sum(r.amount for r in result)
        assert total == Decimal("1000.05")

    def test_three_way_split_of_a_non_round_total_stays_exact(self) -> None:
        children = [
            _row("Key1", "10000", "10", consumed="0"),
            _row("Key2", "10000", "10", consumed="0"),
            _row("Key3", "10000", "10", consumed="0"),
        ]
        result = resolve_level(
            Decimal("100.01"), children, [], parent_old_amount=Decimal("30000")
        )
        assert sum(r.amount for r in result) == Decimal("100.01")

    def test_last_child_never_goes_negative_when_earlier_shares_are_awkward(self) -> None:
        """8 Keys, an Application cut drastically from 702.09 to 18.96 (~2.7%
        of its old size) — a genuinely valid request (every Key has consumed
        0, so any split of 18.96 across them is fine). Each of the first 7
        Keys' near-1/7th share rounds DOWN to 2.70 (never up — see
        resolve_level's ROUND_DOWN on non-last shares), so running_total
        after all seven is 18.90, and the 8th Key (which only ever held 0.90)
        absorbs the exact remainder: 0.06. Never negative, and the group
        still lands on exactly 18.96 — the bug this class exists to prevent
        (drifting a cent or two off target) would have shown up here as
        EITHER a negative last share OR a total past 18.96; neither happens."""
        children = [_row(f"Key{i}", "100.17", "0", consumed="0") for i in range(7)]
        children.append(_row("Key7", "0.90", "0", consumed="0"))
        result = resolve_level(
            Decimal("18.96"), children, [], parent_old_amount=Decimal("702.09")
        )
        assert sum(r.amount for r in result) == Decimal("18.96")
        assert all(r.amount >= 0 for r in result)
        by_id = {r.id: r for r in result}
        assert by_id["Key7"].amount == Decimal("0.06")
