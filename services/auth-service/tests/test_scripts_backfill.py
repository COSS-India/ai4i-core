"""Unit tests for the pure decision logic in the two one-off backfill
scripts (scripts/backfill_*.py) — the parts worth pinning before either
script runs against production data. The scripts' I/O (DB/Redis wiring,
argparse, dry-run printing) isn't covered here; only what decides which
rows get touched.
"""
from __future__ import annotations

from decimal import Decimal

from scripts.backfill_allocated_percentage_for_budget_keys import compute_percentage
from scripts.backfill_clear_stale_tenant_wide_exhaustion_flags import is_truly_exhausted


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
