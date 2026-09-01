"""consumers/payperuse_consumer/handler.py — OTel attribute coercion helpers.

Span attributes arrive as strings from request headers via APISIX.  A single
malformed value (e.g. "abc" for api_key_id) used to raise ValueError inside
_get_otel_attributes, which propagated out of _prepare_billing_context and
caused main.py to retry the Kafka message three times before dropping it —
stalling the billing partition for ~3 s and losing that span's billing record.

_to_int and _to_float catch both TypeError (None) and ValueError (non-numeric
string) and fall back to 0.  These tests pin that contract so the fallback
cannot be accidentally removed.

Nothing here needs a broker, database, or Redis.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from consumers.payperuse_consumer.handler import (
    _get_otel_attributes,
    _post_billing,
    _to_float,
    _to_int,
)


class TestToFloat:
    def test_none_returns_zero(self):
        assert _to_float(None) == 0.0

    def test_empty_string_returns_zero(self):
        assert _to_float("") == 0.0

    def test_numeric_string_is_parsed(self):
        assert _to_float("42.5") == 42.5

    def test_integer_string_is_parsed(self):
        assert _to_float("100") == 100.0

    def test_non_numeric_string_returns_zero_not_raises(self):
        # This was the production bug: "abc" is truthy so `or 0` did not fire,
        # then float("abc") raised ValueError and stalled the billing partition.
        assert _to_float("abc") == 0.0

    def test_custom_fallback_is_returned_on_bad_value(self):
        assert _to_float("bad", fallback=99.0) == 99.0

    def test_zero_numeric_returns_zero(self):
        assert _to_float(0) == 0.0

    def test_numeric_int_is_coerced(self):
        assert _to_float(7) == 7.0


class TestToInt:
    def test_none_returns_zero(self):
        assert _to_int(None) == 0

    def test_empty_string_returns_zero(self):
        assert _to_int("") == 0

    def test_numeric_string_is_parsed(self):
        assert _to_int("42") == 42

    def test_non_numeric_string_returns_zero_not_raises(self):
        # Same root cause as _to_float: "abc" or 0 == "abc", int("abc") raises.
        assert _to_int("abc") == 0

    def test_float_string_returns_zero_not_raises(self):
        # "3.7" is truthy; int("3.7") raises ValueError — must fall back, not crash.
        assert _to_int("3.7") == 0

    def test_custom_fallback_is_returned_on_bad_value(self):
        assert _to_int("bad", fallback=-1) == -1

    def test_zero_numeric_returns_zero(self):
        assert _to_int(0) == 0

    def test_numeric_int_is_passed_through(self):
        assert _to_int(99) == 99


class TestGetOtelAttributes:
    def _attrs(self, **overrides) -> dict:
        base = {
            "tenantId": "tenant-123",
            "service_id": "svc-abc",
            "input_tokens": "10",
            "output_tokens": "5",
            "correlation_id": "corr-xyz",
            "api_key_id": "7",
            "tier_id": "tier-999",
        }
        base.update(overrides)
        return base

    def test_valid_attrs_are_parsed_correctly(self):
        tid, sid, inp, out, corr, aki, tier = _get_otel_attributes(self._attrs())
        assert tid == "tenant-123"
        assert sid == "svc-abc"
        assert inp == 10.0
        assert out == 5.0
        assert corr == "corr-xyz"
        assert aki == 7
        assert tier == "tier-999"

    def test_non_numeric_api_key_id_falls_back_to_zero(self):
        _, _, _, _, _, aki, _ = _get_otel_attributes(self._attrs(api_key_id="not-a-number"))
        assert aki == 0

    def test_non_numeric_input_tokens_falls_back_to_zero(self):
        _, _, inp, _, _, _, _ = _get_otel_attributes(self._attrs(input_tokens="bad"))
        assert inp == 0.0

    def test_non_numeric_output_tokens_falls_back_to_zero(self):
        _, _, _, out, _, _, _ = _get_otel_attributes(self._attrs(output_tokens="bad"))
        assert out == 0.0

    def test_missing_api_key_id_defaults_to_zero(self):
        _, _, _, _, _, aki, _ = _get_otel_attributes(self._attrs(api_key_id=None))
        assert aki == 0

    def test_missing_tokens_default_to_zero(self):
        _, _, inp, out, _, _, _ = _get_otel_attributes(
            self._attrs(input_tokens=None, output_tokens=None)
        )
        assert inp == 0.0
        assert out == 0.0

    def test_empty_tier_id_is_normalised_to_none(self):
        # validation.py ships X-Tier-ID="" for keyless-tier requests; that must
        # not reach deduct_balance_and_update_quota as an empty string or Postgres
        # raises "invalid input syntax for type uuid".
        _, _, _, _, _, _, tier = _get_otel_attributes(self._attrs(tier_id=""))
        assert tier is None

    def test_absent_tier_id_is_none(self):
        _, _, _, _, _, _, tier = _get_otel_attributes(self._attrs(tier_id=None))
        assert tier is None

    def test_correlation_id_is_stripped(self):
        _, _, _, _, corr, _, _ = _get_otel_attributes(self._attrs(correlation_id="  abc  "))
        assert corr == "abc"

    def test_empty_attrs_dict_returns_safe_defaults(self):
        tid, sid, inp, out, corr, aki, tier = _get_otel_attributes({})
        assert tid == ""
        assert sid == ""
        assert inp == 0.0
        assert out == 0.0
        assert corr == ""
        assert aki == 0
        assert tier is None


class TestPostBilling:
    """_post_billing had no coverage on either side of the per-key rescope —
    the whole point of the change (one Key's own usage notifying by
    api_key_id, not tenant_id, and skipping entirely when there's no key on
    the span) had nothing pinning it."""

    async def test_wallet_exhausted_notifies_by_api_key_id_not_tenant_id(self):
        with patch("consumers.payperuse_consumer.handler._notify_auth", AsyncMock()) as notify:
            await _post_billing(True, False, "tenant-1", 42, "nmt")
        notify.assert_awaited_once_with(
            "/internal/ppu/api-key/42/budget-exhausted", {"exhausted": True}
        )

    async def test_wallet_exhausted_but_no_api_key_id_is_skipped(self):
        """api_key_id=0 means no Key on this span (a JWT-authenticated
        request, or the gateway not yet forwarding X-API-Key-ID) — nothing
        to flag; must not notify about api_key_id "0"."""
        with patch("consumers.payperuse_consumer.handler._notify_auth", AsyncMock()) as notify:
            await _post_billing(True, False, "tenant-1", 0, "nmt")
        notify.assert_not_awaited()

    async def test_not_exhausted_never_notifies_regardless_of_api_key_id(self):
        with patch("consumers.payperuse_consumer.handler._notify_auth", AsyncMock()) as notify:
            await _post_billing(False, False, "tenant-1", 42, "nmt")
        notify.assert_not_awaited()

    async def test_quota_exhausted_still_notifies_by_tenant_id(self):
        """Unaffected by the per-key rescope — quota is a tier-wide
        entitlement, not a per-Key ₹ ceiling, so it stays tenant-scoped."""
        with patch("consumers.payperuse_consumer.handler._notify_auth", AsyncMock()) as notify:
            await _post_billing(False, True, "tenant-1", 0, "nmt")
        notify.assert_awaited_once_with(
            "/internal/ppu/tenant/tenant-1/quota-exhausted", {"inference_name": "nmt"}
        )

    async def test_both_exhausted_notifies_both_paths(self):
        with patch("consumers.payperuse_consumer.handler._notify_auth", AsyncMock()) as notify:
            await _post_billing(True, True, "tenant-1", 42, "nmt")
        assert notify.await_count == 2
        calls = [c.args for c in notify.await_args_list]
        assert ("/internal/ppu/api-key/42/budget-exhausted", {"exhausted": True}) in calls
        assert ("/internal/ppu/tenant/tenant-1/quota-exhausted", {"inference_name": "nmt"}) in calls


class TestBillUsageThreadsInferenceTypeId:
    """_bill_usage must resolve inference_type_id and pass it to the upsert.

    The resolution and the write are separately unit-tested in test_billing.py;
    what is asserted here is the wiring between them, which is the part a
    refactor of _bill_usage can silently drop. If the argument stops being
    passed, every quota_usage row written from then on carries a NULL FK and
    nothing fails — the bug only surfaces at the phase-2 SET NOT NULL.
    """

    class _FakeDb:
        """_bill_usage commits before returning; nothing else is called on db
        here because the two functions that use it are stubbed out."""

        def __init__(self):
            self.commits = 0

        async def commit(self):
            self.commits += 1

    def _ctx(self, **overrides):
        from consumers.payperuse_consumer.handler import BillingContext

        base = dict(
            tenant_id="tenant-1",
            service_id="svc-1",
            input_tokens=10.0,
            total_tokens=15.0,
            correlation_id="corr-1",
            span_id="span-1",
            billed_key="ppu:billed:corr-1:span-1",
            is_already_billed=False,
            billing_month="2026-08",
            offset=0,
            api_key_id=0,
            tier_id="tier-1",
        )
        base.update(overrides)
        return BillingContext(**base)

    def _patch(self, monkeypatch, *, resolved_id, task_type="asr"):
        """Stub pricing + the two billing calls; return the captured kwargs."""
        from decimal import Decimal

        from consumers.payperuse_consumer import handler as h
        from consumers.payperuse_consumer._billing import (
            BillingWriteResult,
            ServicePricing,
        )

        captured: dict = {}

        async def _pricing(db, service_id):
            return ServicePricing(
                task_type=task_type,
                unit_rate=Decimal("0.5"),
                cost_per_unit=None,
                unit_size=None,
            )

        async def _resolve(db, inference_name):
            captured["resolve_arg"] = inference_name
            return resolved_id

        async def _write(db, **kwargs):
            captured.update(kwargs)
            return BillingWriteResult(
                api_key_budget_used=Decimal("0"),
                api_key_budget_snap=None,
                tier_id="tier-1",
                budget_exhausted=False,
                quota_recorded=True,
                quota_exhausted=False,
            )

        monkeypatch.setattr(h, "get_service_pricing", _pricing)
        monkeypatch.setattr(h, "get_inference_type_id", _resolve)
        monkeypatch.setattr(h, "deduct_balance_and_update_quota", _write)
        return captured

    async def test_resolved_id_is_passed_to_the_upsert(self, monkeypatch):
        from consumers.payperuse_consumer.handler import _bill_usage

        captured = self._patch(monkeypatch, resolved_id=2)
        outcome = await _bill_usage(self._FakeDb(), self._ctx())

        assert outcome is not None
        assert captured["inference_type_id"] == 2

    async def test_none_is_still_passed_through(self, monkeypatch):
        from consumers.payperuse_consumer.handler import _bill_usage

        captured = self._patch(monkeypatch, resolved_id=None)
        await _bill_usage(self._FakeDb(), self._ctx())

        # A catalogue miss must not abort billing — the column is nullable and
        # the write keys off inference_name regardless.
        assert captured["inference_type_id"] is None

    async def test_resolution_uses_the_pricing_task_type(self, monkeypatch):
        from consumers.payperuse_consumer.handler import _bill_usage

        captured = self._patch(monkeypatch, resolved_id=3, task_type="nmt")
        await _bill_usage(self._FakeDb(), self._ctx())

        # task_type comes from mm_services via get_service_pricing — it is the
        # same value bound as inference_name, so the two must not diverge.
        assert captured["resolve_arg"] == "nmt"
        assert captured["inference_name"] == "nmt"

    async def test_not_resolved_when_pricing_is_missing(self, monkeypatch):
        from consumers.payperuse_consumer import handler as h
        from consumers.payperuse_consumer.handler import _bill_usage

        called = {"resolve": False}

        async def _no_pricing(db, service_id):
            return None

        async def _resolve(db, inference_name):
            called["resolve"] = True
            return 1

        monkeypatch.setattr(h, "get_service_pricing", _no_pricing)
        monkeypatch.setattr(h, "get_inference_type_id", _resolve)

        assert await _bill_usage(self._FakeDb(), self._ctx()) is None
        # No pricing means no billing at all; resolving an id would be a wasted
        # round-trip on every unpriced service's spans.
        assert called["resolve"] is False
