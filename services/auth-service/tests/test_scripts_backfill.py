"""Unit tests for the pure decision logic in the two one-off backfill
scripts (scripts/backfill_*.py) — the parts worth pinning before either
script runs against production data. The scripts' I/O (DB/Redis wiring,
argparse, dry-run printing) isn't covered here; only what decides which
rows get touched.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from scripts.backfill_allocated_percentage_for_budget_keys import (
    applications_over_100,
    compute_percentage,
    sum_new_percentages_by_application,
)
from scripts.backfill_clear_stale_tenant_wide_exhaustion_flags import (
    UsageLookupFailedError,
    check_usage_lookup_succeeded,
    is_truly_exhausted,
)


class TestComputePercentage:
    def test_matches_create_api_keys_own_conversion(self):
        """15000 out of a 50000 Application budget -> 30.00%, the same
        shape create_api_key computes live for a fresh `budget` request."""
        assert compute_percentage(Decimal("15000"), Decimal("50000")) == Decimal("30.00")

    def test_rounds_half_up_to_two_decimals(self):
        # 1/3 * 100 = 33.3333...% -> rounds to 33.33, not truncates to 33.34/33.32
        assert compute_percentage(Decimal("10000"), Decimal("30000")) == Decimal("33.33")

    def test_exact_multiple_has_no_rounding_error(self):
        assert compute_percentage(Decimal("25000"), Decimal("100000")) == Decimal("25.00")

    def test_full_allocation_is_100_percent(self):
        assert compute_percentage(Decimal("50000"), Decimal("50000")) == Decimal("100.00")


class TestSumNewPercentagesByApplication:
    def test_groups_and_sums_by_application(self):
        totals = sum_new_percentages_by_application(
            application_id_by_key={11: 1, 12: 1, 21: 2},
            percentage_by_key={11: Decimal("30"), 12: Decimal("40"), 21: Decimal("60")},
        )
        assert totals == {1: Decimal("70"), 2: Decimal("60")}

    def test_empty_input_is_empty_output(self):
        assert sum_new_percentages_by_application({}, {}) == {}


class TestApplicationsOver100:
    def test_application_pushed_over_100_is_reported(self):
        """The exact scenario this check exists for: an Application already
        at 80% from its known keys, plus 25% newly revealed by the
        backfill, lands at 105% — invisible until this check runs."""
        over = applications_over_100(
            new_total_by_application={1: Decimal("25")},
            existing_total_by_application={1: Decimal("80")},
        )
        assert over == {1: Decimal("105")}

    def test_application_at_exactly_100_is_not_reported(self):
        over = applications_over_100(
            new_total_by_application={1: Decimal("20")},
            existing_total_by_application={1: Decimal("80")},
        )
        assert over == {}

    def test_application_with_no_existing_total_uses_zero(self):
        """An Application whose only percentage-bearing keys are the ones
        being backfilled has no sum_api_key_allocated_percentage entry."""
        over = applications_over_100(
            new_total_by_application={1: Decimal("150")},
            existing_total_by_application={},
        )
        assert over == {1: Decimal("150")}

    def test_application_within_100_is_not_reported(self):
        over = applications_over_100(
            new_total_by_application={1: Decimal("10")},
            existing_total_by_application={1: Decimal("50")},
        )
        assert over == {}


class TestIsTrulyExhausted:
    def test_used_at_or_above_snap_is_exhausted(self):
        assert is_truly_exhausted(Decimal("30000"), Decimal("30000")) is True
        assert is_truly_exhausted(Decimal("30001"), Decimal("30000")) is True

    def test_used_below_snap_is_not_exhausted(self):
        assert is_truly_exhausted(Decimal("29999"), Decimal("30000")) is False

    def test_no_snapshot_ceiling_is_never_exhausted(self):
        """A key with no budget_usage.api_key_budget_snap has no ceiling at
        all — can't be over a limit that doesn't exist, regardless of used."""
        assert is_truly_exhausted(Decimal("999999"), None) is False

    def test_no_budget_usage_row_at_all_is_not_exhausted(self):
        """fetch_budget_usage's (None, None) default for a key with no row —
        no usage on record, definitely not over budget."""
        assert is_truly_exhausted(None, None) is False


class TestCheckUsageLookupSucceeded:
    def test_empty_usage_for_nonempty_flagged_ids_raises(self):
        """fetch_budget_usage returning {} for a non-empty flagged_ids is
        indistinguishable from a platform-core outage or an unset
        PLATFORM_CORE_DB_NAME — must abort rather than treat every flagged
        key as 'not exhausted' and clear them all."""
        with pytest.raises(UsageLookupFailedError):
            check_usage_lookup_succeeded([1, 2, 3], {})

    def test_empty_flagged_ids_with_empty_usage_is_fine(self):
        """Nothing was flagged in the first place — an empty usage_by_key
        here is the expected, legitimate shape, not a failure signal."""
        check_usage_lookup_succeeded([], {})

    def test_partial_usage_result_does_not_raise(self):
        """Some flagged keys genuinely having no budget_usage row (the
        wrongly-flagged siblings this whole script exists to fix) is
        expected and fine, as long as the lookup produced SOMETHING."""
        check_usage_lookup_succeeded([1, 2, 3], {1: (Decimal("100"), Decimal("200"))})

    def test_full_usage_result_does_not_raise(self):
        check_usage_lookup_succeeded(
            [1, 2],
            {1: (Decimal("100"), Decimal("200")), 2: (Decimal("50"), Decimal("50"))},
        )
