"""round_parts / round_shares: a breakdown's rounded parts add up to its total."""
from decimal import Decimal as D

from app.utils.rounding import round_parts, round_shares


class TestRoundParts:
    def test_residual_goes_to_the_largest_part(self):
        # 0.333 + 0.333 + 0.334 → 0.33 + 0.33 + 0.33 = 0.99, a cent short of 1.00.
        assert round_parts([D("0.333"), D("0.333"), D("0.334")], D("1")) == [D("0.33"), D("0.33"), D("0.34")]

    def test_rounding_up_too_far_takes_from_the_largest(self):
        # 0.005 + 0.005 + 0.010 rounds to 0.01 + 0.01 + 0.01 = 0.03 against 0.02.
        assert round_parts([D("0.005"), D("0.005"), D("0.010")], D("0.02")) == [D("0.01"), D("0.01"), D("0.00")]

    def test_parts_always_sum_to_the_rounded_total(self):
        parts = [D("0.0176"), D("0.04096"), D("0.0375")]
        rounded = round_parts(parts, sum(parts))
        assert sum(rounded) == D("0.10")

    def test_exact_parts_are_left_alone(self):
        assert round_parts([D("1.25"), D("2.50")], D("3.75")) == [D("1.25"), D("2.50")]

    def test_empty(self):
        assert round_parts([], D("0")) == []


class TestRoundShares:
    def test_thirds_add_up_to_100(self):
        shares = round_shares([D(1), D(1), D(1)])
        assert sum(shares) == D("100.00")
        assert sorted(shares) == [D("33.33"), D("33.33"), D("33.34")]

    def test_all_zero_is_all_zero(self):
        assert round_shares([D(0), D(0)]) == [D("0.00"), D("0.00")]
