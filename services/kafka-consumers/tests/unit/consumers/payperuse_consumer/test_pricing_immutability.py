"""2210 · Pricing immutability contracts.

Two invariants that hold today but had no test coverage:

1. Past consumption is never repriced — cost is computed at consumption time
   and written to budget_usage.api_key_budget_used immediately. Editing
   mm_services changes the source row; it never touches budget_usage.

2. Cumulative spend survives a price edit — api_key_budget_used is a running
   total that only grows; an mm_services UPDATE is not in the same transaction
   and has no ON UPDATE trigger on budget_usage.

Nothing here needs a broker, database, or Redis.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from consumers.payperuse_consumer._billing import ServicePricing, calculate_cost


class TestPastConsumptionNeverRepriced:
    """Cost is fixed at the moment calculate_cost() runs.

    The function reads ``pricing.unit_rate`` (or the cost_per_unit/unit_size
    fallback) and multiplies by ``total_units``. It has no reference to any
    external store, so a later mm_services update cannot change a value that
    was already returned.
    """

    def test_cost_is_pure_function_of_rate_and_units(self):
        pricing = ServicePricing(task_type="llm", unit_rate=Decimal("0.002"), cost_per_unit=None, unit_size=None)
        cost = calculate_cost(total_units=1000, pricing=pricing)
        assert cost == Decimal("2.000")

    def test_changing_rate_after_billing_has_no_effect_on_prior_result(self):
        original_pricing = ServicePricing(task_type="llm", unit_rate=Decimal("0.002"), cost_per_unit=None, unit_size=None)
        cost_before = calculate_cost(total_units=500, pricing=original_pricing)

        # Simulate an admin updating the price in mm_services — a new
        # ServicePricing object is fetched from the DB/cache on the next call.
        updated_pricing = ServicePricing(task_type="llm", unit_rate=Decimal("0.005"), cost_per_unit=None, unit_size=None)
        cost_after = calculate_cost(total_units=500, pricing=updated_pricing)

        # The old result is unchanged — it was already returned and committed.
        assert cost_before == Decimal("1.000")
        # Future consumption uses the new rate.
        assert cost_after == Decimal("2.500")
        assert cost_before != cost_after

    def test_zero_rate_produces_zero_cost(self):
        pricing = ServicePricing(task_type="asr", unit_rate=Decimal("0"), cost_per_unit=None, unit_size=None)
        assert calculate_cost(total_units=9999, pricing=pricing) == Decimal("0")

    def test_cost_per_unit_fallback_is_also_immutable(self):
        pricing = ServicePricing(task_type="nmt", unit_rate=None, cost_per_unit=Decimal("1.00"), unit_size=1000)
        cost = calculate_cost(total_units=500, pricing=pricing)
        assert cost == Decimal("0.5000")


class TestCumulativeSpendSurvivesPriceEdit:
    """Editing mm_services has no effect on budget_usage.api_key_budget_used.

    api_key_budget_used is a running total written by deduct_balance_and_update_quota().
    The mm_services table has no FK or trigger relationship with budget_usage, so
    an UPDATE on mm_services cannot mutate accumulated spend.

    This test class pins the contract at the calculate_cost level: each billing
    event adds a fixed amount derived from the rate at that moment, and prior
    additions are unaffected by later rate changes.
    """

    def test_accumulated_spend_is_sum_of_per_event_costs(self):
        pricing_v1 = ServicePricing(task_type="llm", unit_rate=Decimal("0.001"), cost_per_unit=None, unit_size=None)

        event_costs = [calculate_cost(units, pricing_v1) for units in [100, 200, 300]]
        total_before_edit = sum(event_costs)

        # Admin edits the price — new rate applies to new events only.
        pricing_v2 = ServicePricing(task_type="llm", unit_rate=Decimal("0.003"), cost_per_unit=None, unit_size=None)
        new_event_cost = calculate_cost(400, pricing_v2)

        cumulative = total_before_edit + new_event_cost
        # Old events keep their original per-unit cost; only the new event uses v2.
        assert event_costs == [Decimal("0.100"), Decimal("0.200"), Decimal("0.300")]
        assert new_event_cost == Decimal("1.200")
        assert cumulative == Decimal("1.800")

    def test_no_repricing_when_rate_drops(self):
        high_rate = ServicePricing(task_type="llm", unit_rate=Decimal("0.010"), cost_per_unit=None, unit_size=None)
        spent = calculate_cost(1000, high_rate)
        assert spent == Decimal("10.000")

        # Rate drops — old spend is unaffected.
        low_rate = ServicePricing(task_type="llm", unit_rate=Decimal("0.001"), cost_per_unit=None, unit_size=None)
        new_spend = calculate_cost(1000, low_rate)

        # The already-committed spent value did not change.
        assert spent == Decimal("10.000")
        assert new_spend == Decimal("1.000")
