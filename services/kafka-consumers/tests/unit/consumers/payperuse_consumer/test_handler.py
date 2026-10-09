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

from decimal import Decimal

from consumers.payperuse_consumer.handler import (
    _display_pct,
    _get_otel_attributes,
    _post_billing,
    _to_float,
    _to_int,
)


class TestDisplayPct:
    """QUOTA_THRESHOLD/BUDGET_THRESHOLD's current_value (design doc §9.5)
    must never show more than 100% — a debit can push used past snap (e.g.
    concurrent requests racing past the ceiling), and "2900%" in an alert
    email reads as a bug, not "very over budget". Display-only: the pipeline
    still evaluates the raw, uncapped value."""

    def test_under_100_is_unchanged(self):
        assert _display_pct(Decimal("82")) == Decimal("82")

    def test_exactly_100_is_unchanged(self):
        assert _display_pct(Decimal("100")) == Decimal("100")

    def test_over_100_is_capped_to_100(self):
        assert _display_pct(Decimal("2900")) == Decimal("100")

    def test_just_over_100_is_capped_to_100(self):
        assert _display_pct(Decimal("100.5")) == Decimal("100")


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
    the span) had nothing pinning it.

    No longer covers a budget-expiry-check call — that push was removed
    (see _post_billing's own docstring): /auth/validate now compares
    budget_effective_to directly from the key's cached payload instead of
    a boolean this consumer used to push on every message."""

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
    refactor of _bill_usage can silently drop. The id is now the upsert's join
    and conflict key, so if the argument stops being passed the write matches
    nothing and quota silently stops being recorded.
    """

    class _FakeDb:
        """_bill_usage commits before returning; nothing else is called on db
        here because the two functions that use it are stubbed out."""

        def __init__(self):
            self.commits = 0

        async def commit(self):
            self.commits += 1

    class _FakeAuthSessionScope:
        """Stub for bootstrap.lifecycle.session_scope(name="auth") — _bill_usage
        opens this unconditionally now (fetch_tenant_budget_status needs a
        tenant-level read regardless of any one key's own budget_usage row),
        so every test reaching that far needs it to be usable as an async
        context manager even though these tests stub fetch_tenant_budget_status
        itself and never actually touch the yielded object."""

        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc_info):
            return False

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

    def _patch(self, monkeypatch, *, resolved_id, task_type="asr", pricing=None):
        """Stub pricing + the two billing calls; return the captured kwargs."""
        from decimal import Decimal

        from consumers.payperuse_consumer import handler as h
        from consumers.payperuse_consumer._billing import (
            BillingWriteResult,
            ServicePricing,
        )

        captured: dict = {}

        async def _pricing(db, service_id):
            return pricing or ServicePricing(
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

        async def _no_tenant_budget(auth_db, core_db, tenant_id):
            # Not under test here (see TestPublishUsageCrossingEvents /
            # TestFetchTenantBudgetStatus) — None mirrors "tenant has no
            # allocated_budget configured", so _publish_usage_crossing_events'
            # budget block is a no-op, same as this class's tests intend.
            return None

        monkeypatch.setattr(h, "get_service_pricing", _pricing)
        monkeypatch.setattr(h, "get_inference_type_id", _resolve)
        monkeypatch.setattr(h, "deduct_balance_and_update_quota", _write)
        monkeypatch.setattr(h, "fetch_tenant_budget_status", _no_tenant_budget)
        # Not under test here (see TestPublishUsageCrossingEvents): no
        # pipeline configured means no usage alert is evaluated at all.
        monkeypatch.setattr(h, "notifications_configured", lambda: False)
        monkeypatch.setattr(
            h, "session_scope", lambda name=None: self._FakeAuthSessionScope()
        )
        return captured

    async def test_llm_is_charged_by_token_category(self, monkeypatch):
        from decimal import Decimal

        from consumers.payperuse_consumer._billing import ServicePricing
        from consumers.payperuse_consumer.handler import _bill_usage

        pricing = ServicePricing(
            task_type="llm", unit_rate=None, cost_per_unit=Decimal("0.10"), unit_size=1000,
            cached_input_cost_per_unit=Decimal("0.04"), output_cost_per_unit=Decimal("0.25"),
        )
        captured = self._patch(monkeypatch, resolved_id=1, task_type="llm", pricing=pricing)
        ctx = self._ctx(input_tokens=1200.0, cached_input_tokens=1024.0, output_tokens=150.0, total_tokens=1350.0)

        await _bill_usage(self._FakeDb(), ctx)

        assert captured["cost"] == Decimal("0.09606")   # 176 input + 1,024 cached + 150 output
        assert captured["units"] == Decimal("1350.0")    # quota still counts every token

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

        # task_type comes from mm_services via get_service_pricing, and it is
        # the only thing the id is resolved from. No name is passed to the write
        # any more — the upsert takes it from the catalogue row it joins.
        assert captured["resolve_arg"] == "nmt"
        assert "inference_name" not in captured

    async def test_unresolvable_task_type_fails_open_not_exhausted(self, monkeypatch, caplog):
        """The single most important assertion in phase 2.

        A task type absent from the catalogue means the upsert matches nothing,
        so quota_recorded comes back False. Reading that as exhaustion would 429
        every tenant on an otherwise-working tier. It must fail OPEN, loudly.
        """
        import logging

        from consumers.payperuse_consumer.handler import _bill_usage

        self._patch(monkeypatch, resolved_id=None, task_type="brand-new-type")
        with caplog.at_level(logging.ERROR):
            outcome = await _bill_usage(self._FakeDb(), self._ctx())

        assert outcome is not None
        assert outcome.quota_exhausted is False, (
            "an unresolvable task type must not be reported as quota-exhausted"
        )
        # The stable key an OpenSearch monitor alerts on. Renaming it silently
        # breaks that alert, which is the only thing making this gap visible.
        assert any(
            getattr(r, "event", None) == "ppu.inference_type.unresolved"
            for r in caplog.records
        ), "the unresolved-type ERROR event must be emitted"

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


class TestPublishUsageCrossingEvents:
    """_publish_usage_crossing_events builds the BAND items for the shared
    pipeline (ai4i_core.kafka.emit_band_batch), which owns the gate, the
    dedup, recipients and the publish. Pinned here: BUDGET_* use the
    TENANT's pooled budget (never one API key's own row) with the
    allocated_budget as the period key; QUOTA_* use this month's quota row
    with billing_month as the period key; and the email details."""

    class _AuthScope:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc_info):
            return False

    def _ctx(self, **overrides):
        from consumers.payperuse_consumer.handler import BillingContext

        base = dict(
            tenant_id="1",
            service_id="svc-1",
            input_tokens=10.0,
            total_tokens=15.0,
            correlation_id="corr-1",
            span_id="span-1",
            billed_key="ppu:billed:corr-1:span-1",
            is_already_billed=False,
            billing_month="2026-08",
            offset=0,
            api_key_id=7,
            tier_id="tier-1",
        )
        base.update(overrides)
        return BillingContext(**base)

    def _write(self, **overrides):
        from consumers.payperuse_consumer._billing import BillingWriteResult

        base = dict(
            api_key_budget_used=Decimal("999"),   # deliberately NOT what the
            api_key_budget_snap=Decimal("1000"),  # tenant-level check must use
            tier_id="tier-1",
            budget_exhausted=False,
            quota_recorded=False,
            quota_exhausted=False,
        )
        base.update(overrides)
        return BillingWriteResult(**base)

    def _patch(self, monkeypatch, *, tenant_budget=None, budget_can_fire=True):
        from consumers.payperuse_consumer import handler as h
        from consumers.payperuse_consumer._billing import TenantBudgetStatus

        calls: dict = {"items": [], "budget_reads": 0}

        async def _can_fire(names, tenant_id):
            return list(names) if budget_can_fire else []

        async def _tenant_budget(auth_db, core_db, tenant_id):
            calls["budget_reads"] += 1
            if tenant_budget is None:
                return None
            used, snap, *window = tenant_budget
            effective_from, effective_to = (list(window) + [None, None])[:2]
            return TenantBudgetStatus(
                used=Decimal(used), snap=None if snap is None else Decimal(snap),
                effective_from=effective_from, effective_to=effective_to,
            )

        async def _emit(items):
            calls["items"].extend(items)
            return []

        monkeypatch.setattr(h, "notifications_configured", lambda: True)
        monkeypatch.setattr(h, "names_that_can_fire", _can_fire)
        monkeypatch.setattr(h, "fetch_tenant_budget_status", _tenant_budget)
        monkeypatch.setattr(h, "emit_band_batch", _emit)
        monkeypatch.setattr(h, "session_scope", lambda name=None: self._AuthScope())
        return calls

    @staticmethod
    def _fire(item, band_value):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        context = SimpleNamespace(
            band=SimpleNamespace(value=Decimal(band_value)),
            observed=item.observed,
            occurred_at=datetime(2026, 8, 10, 11, 22, tzinfo=timezone.utc),
        )
        return item.details(context)

    async def _run(self, write=None, task="asr", db=None):
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events

        await _publish_usage_crossing_events(db or object(), self._ctx(), write or self._write(), task)

    async def test_budget_items_use_the_tenant_totals_and_ceiling(self, monkeypatch):
        from ai4i_core.kafka import NotificationName

        calls = self._patch(monkeypatch, tenant_budget=("820", "1000"))
        await self._run()

        by_name = {i.name: i for i in calls["items"]}
        assert set(by_name) == {NotificationName.BUDGET_THRESHOLD, NotificationName.BUDGET_EXHAUSTED}
        for item in by_name.values():
            assert item.tenant_id == "1"
            # The tenant's allocated_budget and current window are the
            # period key; no api_key_id. No window configured here, so
            # budget_window is the "none_none" sentinel.
            assert item.subject == {"budget_ceiling": "1000.00", "budget_window": "none_none"}
            assert item.observed.value == Decimal("82")

    async def test_budget_window_change_is_part_of_the_subject(self, monkeypatch):
        """A renewed/reactivated window (new effective_from/_to) must change
        the ledger subject, the same way quota's billing_month does every
        month — otherwise a window renewal can never re-arm an
        already-triggered band (AI4IDS: Budget Threshold stayed silent
        after a mid-window reset/renewal)."""
        from datetime import datetime, timezone

        from ai4i_core.kafka import NotificationName

        calls = self._patch(monkeypatch, tenant_budget=(
            "100", "1000", datetime(2026, 9, 17, tzinfo=timezone.utc), datetime(2026, 9, 30, tzinfo=timezone.utc),
        ))
        await self._run()
        old_subject = next(i for i in calls["items"] if i.name == NotificationName.BUDGET_THRESHOLD).subject

        calls = self._patch(monkeypatch, tenant_budget=(
            "100", "1000", datetime(2026, 9, 17, tzinfo=timezone.utc), datetime(2026, 10, 10, tzinfo=timezone.utc),
        ))
        await self._run()
        new_subject = next(i for i in calls["items"] if i.name == NotificationName.BUDGET_THRESHOLD).subject

        assert old_subject["budget_ceiling"] == new_subject["budget_ceiling"]
        assert old_subject["budget_window"] != new_subject["budget_window"]

    async def test_budget_details(self, monkeypatch):
        from ai4i_core.kafka import NotificationName

        calls = self._patch(monkeypatch, tenant_budget=("2900", "100"))
        await self._run()

        by_name = {i.name: i for i in calls["items"]}
        assert self._fire(by_name[NotificationName.BUDGET_THRESHOLD], "90") == ["90", "10 Aug 2026, 04:52 PM IST", "100%"]
        assert self._fire(by_name[NotificationName.BUDGET_EXHAUSTED], "100") == ["INR", "100.00"]

    async def test_budget_is_not_read_when_no_budget_alert_can_fire(self, monkeypatch):
        calls = self._patch(monkeypatch, tenant_budget=("820", "1000"), budget_can_fire=False)
        await self._run()

        assert calls["budget_reads"] == 0
        assert calls["items"] == []

    async def test_no_tenant_ceiling_means_no_budget_items(self, monkeypatch):
        calls = self._patch(monkeypatch, tenant_budget=("820", None))
        await self._run()

        assert calls["items"] == []

    async def test_quota_items_use_billing_month_and_task_type(self, monkeypatch):
        from ai4i_core.kafka import NotificationName

        calls = self._patch(monkeypatch, budget_can_fire=False)
        await self._run(self._write(quota_recorded=True, quota_used=Decimal("810"), quota_snap=Decimal("1000")), task="ASR")

        by_name = {i.name: i for i in calls["items"]}
        assert set(by_name) == {NotificationName.QUOTA_THRESHOLD, NotificationName.QUOTA_EXHAUSTED}
        for item in by_name.values():
            assert item.subject == {"billing_month": "2026-08", "model_task_type": "asr"}
            assert item.observed.value == Decimal("81")
        assert self._fire(by_name[NotificationName.QUOTA_THRESHOLD], "80") == [
            "80", "10 Aug 2026, 04:52 PM IST", "81% (ASR)",
        ]

    async def test_quota_exhausted_details_carry_tier_name_and_reset_date(self, monkeypatch):
        from ai4i_core.kafka import NotificationName
        from consumers.payperuse_consumer import handler as h

        calls = self._patch(monkeypatch, budget_can_fire=False)

        async def _tier_name(db, tier_id):
            return "Gold" if tier_id == "tier-1" else tier_id

        monkeypatch.setattr(h, "_fetch_tier_name", _tier_name)
        await self._run(self._write(quota_recorded=True, quota_used=Decimal("1000"), quota_snap=Decimal("1000")))

        item = next(i for i in calls["items"] if i.name is NotificationName.QUOTA_EXHAUSTED)
        assert await self._fire(item, "100") == ["Gold", ["ASR: Quota Limit 1,000, Resets on 2026-09-01"]]

    async def test_no_quota_row_means_no_quota_items(self, monkeypatch):
        calls = self._patch(monkeypatch, budget_can_fire=False)
        await self._run(self._write(quota_recorded=False, quota_used=Decimal("10"), quota_snap=Decimal("100")))

        assert calls["items"] == []

    async def test_nothing_is_evaluated_without_the_pipeline(self, monkeypatch):
        from consumers.payperuse_consumer import handler as h

        calls = self._patch(monkeypatch, tenant_budget=("820", "1000"))
        monkeypatch.setattr(h, "notifications_configured", lambda: False)
        await self._run(self._write(quota_recorded=True, quota_used=Decimal("810"), quota_snap=Decimal("1000")))

        assert calls["items"] == [] and calls["budget_reads"] == 0

    async def test_budget_lookup_failure_never_reaches_billing(self, monkeypatch):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from ai4i_core.kafka import NotificationName
        from consumers.payperuse_consumer import handler as h

        calls = self._patch(monkeypatch, tenant_budget=("820", "1000"))

        async def _down(auth_db, core_db, tenant_id):
            raise ConnectionError("auth db down")

        failures = SimpleNamespace(record=AsyncMock())
        monkeypatch.setattr(h, "fetch_tenant_budget_status", _down)
        monkeypatch.setattr(h, "get_notification_runtime", lambda: SimpleNamespace(failures=failures))
        await self._run()  # must not raise

        assert calls["items"] == []
        recorded = [c.kwargs["notification_name"] for c in failures.record.await_args_list]
        assert recorded == [NotificationName.BUDGET_THRESHOLD, NotificationName.BUDGET_EXHAUSTED]
        stage, code = failures.record.await_args.args
        assert stage.value == "SOURCE" and code.value == "TENANT_LOOKUP_FAILED"

    async def test_quota_exhausted_has_fallback_details_for_a_failed_tier_lookup(self, monkeypatch):
        from ai4i_core.kafka import NotificationName

        calls = self._patch(monkeypatch, budget_can_fire=False)
        await self._run(self._write(quota_recorded=True, quota_used=Decimal("1000"), quota_snap=Decimal("1000")))

        item = next(i for i in calls["items"] if i.name is NotificationName.QUOTA_EXHAUSTED)
        assert list(item.fallback_details) == ["tier-1", ["ASR: Quota Limit 1,000, Resets on 2026-09-01"]]



class TestGetCachedInputTokens:
    def test_reads_the_span_attribute(self):
        from consumers.payperuse_consumer.handler import _get_cached_input_tokens

        assert _get_cached_input_tokens({"cached_input_tokens": 1024}) == 1024.0

    def test_absent_or_bad_means_zero(self):
        from consumers.payperuse_consumer.handler import _get_cached_input_tokens

        assert _get_cached_input_tokens({}) == 0.0
        assert _get_cached_input_tokens({"cached_input_tokens": "bad"}) == 0.0
