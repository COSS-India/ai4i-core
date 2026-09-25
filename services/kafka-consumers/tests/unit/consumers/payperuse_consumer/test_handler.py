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
    email reads as a bug, not "very over budget". Display-only: the raw,
    uncapped pre_pct/post_pct still drive crossed_bands/crossed_exhaustion
    in _thresholds.py, which this helper must not affect."""

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

        async def _no_tenant_budget(auth_db, core_db, tenant_id):
            # Not under test here (see TestPublishUsageCrossingEvents /
            # TestFetchTenantBudgetStatus) — None mirrors "tenant has no
            # allocated_budget configured", so _publish_usage_crossing_events'
            # budget block is a no-op, same as this class's tests intend.
            return None

        async def _disabled(db, event_name, tenant_id=None):
            # Not under test here — _bill_usage now checks this (in-memory
            # cache read) *before* deciding whether to open the "auth"
            # session at all (see handler.py). False means it never does,
            # so _FakeAuthSessionScope/fetch_tenant_budget_status below are
            # only there in case a future test in this class needs them.
            return False

        monkeypatch.setattr(h, "get_service_pricing", _pricing)
        monkeypatch.setattr(h, "get_inference_type_id", _resolve)
        monkeypatch.setattr(h, "deduct_balance_and_update_quota", _write)
        monkeypatch.setattr(h, "fetch_tenant_budget_status", _no_tenant_budget)
        monkeypatch.setattr(h, "is_notification_enabled", _disabled)
        monkeypatch.setattr(
            h, "session_scope", lambda name=None: self._FakeAuthSessionScope()
        )
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


class TestPublishUsageCrossingEventsBudgetIsTenantLevel:
    """_publish_usage_crossing_events — BUDGET_THRESHOLD/BUDGET_EXHAUSTED must
    fire off the TENANT's pooled budget (fetch_tenant_budget_status), never
    one API key's own budget_usage row. Design doc section 4's subject rule
    already specified {} for these two events (Budget is a property of the
    whole Tenant, same as Tier) — this suite pins the code actually matching
    that, including the subject shape carrying no api_key_id any more.

    QUOTA_THRESHOLD/QUOTA_EXHAUSTED are untouched by this change (quota_usage
    is already keyed by tenant_id, not api_key_id) — one test below confirms
    the budget change doesn't disturb them.
    """

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

    def _patch_kafka_helpers(self, monkeypatch, *, tenant_budget):
        """Stub every ai4i_core.kafka call _publish_usage_crossing_events
        makes, plus fetch_tenant_budget_status — records every
        check_and_record_threshold/check_and_record_exhaustion/
        publish_notification_event call for assertions."""
        from consumers.payperuse_consumer import handler as h

        calls: dict = {"threshold": [], "exhaustion": [], "published": []}

        async def _tenant_budget(auth_db, core_db, tenant_id):
            return tenant_budget

        async def _enabled(db, event_name, tenant_id=None):
            return True

        async def _bands(db, event_name):
            return [50, 75, 90]

        async def _record_threshold(db, event_name, tenant_id, subject, band):
            calls["threshold"].append((event_name, tenant_id, dict(subject), band))
            return True  # "fired" — not already recorded at this band

        async def _record_exhaustion(db, event_name, tenant_id, subject):
            calls["exhaustion"].append((event_name, tenant_id, dict(subject)))
            return True  # "fired" — 0 -> 1 transition

        async def _notification_id(db, event_name):
            return 1

        async def _resolve_recipients(core_db, auth_db, *, notification_id, tenant_id):
            return ["admin@example.com"]

        def _publish(*, event_name, tenant_id, subject, details, recipients=None, **kwargs):
            calls["published"].append(
                {
                    "event_name": event_name, "tenant_id": tenant_id, "subject": dict(subject),
                    "details": details, "recipients": recipients,
                }
            )

        monkeypatch.setattr(h, "fetch_tenant_budget_status", _tenant_budget)
        monkeypatch.setattr(h, "is_notification_enabled", _enabled)
        monkeypatch.setattr(h, "get_threshold_bands", _bands)
        monkeypatch.setattr(h, "get_notification_id", _notification_id)
        monkeypatch.setattr(h, "check_and_record_threshold", _record_threshold)
        monkeypatch.setattr(h, "check_and_record_exhaustion", _record_exhaustion)
        monkeypatch.setattr(h, "resolve_recipients", _resolve_recipients)
        monkeypatch.setattr(h, "publish_notification_event", _publish)
        return calls

    async def test_budget_subject_carries_no_api_key_id(self, monkeypatch):
        """The whole point of the design change: one crossing per tenant, so
        the ledger dedup subject needs nothing more specific than event_name
        + tenant_id — no api_key_id, unlike the old per-key subject."""
        from consumers.payperuse_consumer._billing import TenantBudgetStatus
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events

        # pre = (955-60)/1000 = 89.5%, post = 95.5% — crosses the 90% band.
        tenant_budget = TenantBudgetStatus(used=Decimal("955"), snap=Decimal("1000"))
        calls = self._patch_kafka_helpers(monkeypatch, tenant_budget=tenant_budget)

        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=self._write(),
            cost=Decimal("60"), billed_units=Decimal("100"), inference_name="llm",
            budget_threshold_enabled=True, budget_exhausted_enabled=True,
        )

        assert calls["threshold"], "expected at least one BUDGET_THRESHOLD band crossed"
        for event_name, tenant_id, subject, band in calls["threshold"]:
            assert event_name == "BUDGET_THRESHOLD"
            assert "api_key_id" not in subject
        for event_name, tenant_id, subject in calls["exhaustion"]:
            assert "api_key_id" not in subject
        # The resolved recipients must actually reach publish_notification_event
        # — _publish's old fake silently dropped **kwargs, so a call that
        # omitted recipients entirely still passed this suite.
        assert calls["published"][0]["recipients"] == ["admin@example.com"]

    async def test_only_the_highest_crossed_band_fires_not_every_one(self, monkeypatch):
        """A single debit that jumps straight past more than one configured
        band (bands are 50/75/90 per _patch_kafka_helpers's _bands stub) must
        fire exactly one BUDGET_THRESHOLD email — for the HIGHEST band
        reached — not one email per band it happened to pass through.
        check_and_record_threshold's ledger dedup only compares "does this
        differ from what's stored"; it has no notion of "highest" on its
        own, so this is enforced by only ever calling it once, with
        max(crossed_bands(...))."""
        from consumers.payperuse_consumer._billing import TenantBudgetStatus
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events

        # pre = (920-330)/1000 = 59.0%, post = 92.0% — crosses BOTH the 75%
        # and 90% bands in this one debit.
        tenant_budget = TenantBudgetStatus(used=Decimal("920"), snap=Decimal("1000"))
        calls = self._patch_kafka_helpers(monkeypatch, tenant_budget=tenant_budget)

        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=self._write(),
            cost=Decimal("330"), billed_units=Decimal("100"), inference_name="llm",
            budget_threshold_enabled=True, budget_exhausted_enabled=False,
        )

        assert len(calls["threshold"]) == 1, (
            f"expected exactly one BUDGET_THRESHOLD call, got {calls['threshold']!r}"
        )
        assert calls["threshold"][0][3] == 90, "must report the highest band crossed (90), not 75"
        assert len(calls["published"]) == 1
        assert calls["published"][0]["details"][0] == "90"

    async def test_gradual_progression_across_separate_messages_fires_each_band(self, monkeypatch):
        """The opposite scenario from the one above: usage crossing bands
        one at a time across SEPARATE billing messages (not one debit
        spanning several bands) must still fire once per band — 50, then
        75, then 90 — not collapse to a single email. max(crossed_bands())
        only picks the highest band within ONE call's own pre/post range;
        it has no memory across calls, so a message whose own pre/post only
        spans one band reports that one band regardless of what an earlier,
        separate message already reported. Each call here gets its own
        fresh pre/post, exactly as three real, separate billed messages
        would (each recomputing tenant_budget.used from scratch)."""
        from consumers.payperuse_consumer._billing import TenantBudgetStatus
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events
        from consumers.payperuse_consumer import handler as h

        calls = self._patch_kafka_helpers(monkeypatch, tenant_budget=None)  # overridden per-call below

        def _stub_tenant_budget_at(used: Decimal):
            """A fresh async stub per message — real separate billed
            messages each re-query fetch_tenant_budget_status from
            scratch, so each call here must too, not share one canned
            return value."""
            async def _fetch(auth_db, core_db, tenant_id):
                return TenantBudgetStatus(used=used, snap=Decimal("1000"))
            return _fetch

        # Message 1: 45% -> 55% (used 450 -> 550 of 1000) — crosses only 50.
        monkeypatch.setattr(h, "fetch_tenant_budget_status", _stub_tenant_budget_at(Decimal("550")))
        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=self._write(),
            cost=Decimal("100"), billed_units=Decimal("10"), inference_name="llm",
            budget_threshold_enabled=True, budget_exhausted_enabled=False,
        )

        # Message 2: 55% -> 78% (used 550 -> 780) — crosses only 75 (50 is
        # already behind pre, so it must not re-fire).
        monkeypatch.setattr(h, "fetch_tenant_budget_status", _stub_tenant_budget_at(Decimal("780")))
        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=self._write(),
            cost=Decimal("230"), billed_units=Decimal("10"), inference_name="llm",
            budget_threshold_enabled=True, budget_exhausted_enabled=False,
        )

        # Message 3: 78% -> 93% (used 780 -> 930) — crosses only 90.
        monkeypatch.setattr(h, "fetch_tenant_budget_status", _stub_tenant_budget_at(Decimal("930")))
        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=self._write(),
            cost=Decimal("150"), billed_units=Decimal("10"), inference_name="llm",
            budget_threshold_enabled=True, budget_exhausted_enabled=False,
        )

        bands_fired = [band for _, _, _, band in calls["threshold"]]
        assert bands_fired == [50, 75, 90], (
            f"gradual progression must fire once per newly-crossed band, in order; got {bands_fired!r}"
        )
        assert len(calls["published"]) == 3

    async def test_percentage_comes_from_tenant_totals_not_the_one_keys_row(self, monkeypatch):
        """write.api_key_budget_used/snap (this one key's own row) must be
        completely ignored for BUDGET_THRESHOLD/BUDGET_EXHAUSTED now — only
        tenant_budget.used/snap may drive the percentage."""
        from consumers.payperuse_consumer._billing import TenantBudgetStatus
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events

        # This key's own row reads 99.9% used — if that leaked in, every
        # band (and exhaustion) would fire. The tenant total is a much
        # healthier 55%, and crosses only the 50% band.
        write = self._write(api_key_budget_used=Decimal("999"), api_key_budget_snap=Decimal("1000"))
        tenant_budget = TenantBudgetStatus(used=Decimal("550"), snap=Decimal("1000"))
        cost = Decimal("60")  # pre = (550-60)/1000 = 49.0%, post = 55.0%
        calls = self._patch_kafka_helpers(monkeypatch, tenant_budget=tenant_budget)

        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=write,
            cost=cost, billed_units=Decimal("100"), inference_name="llm",
            budget_threshold_enabled=True, budget_exhausted_enabled=True,
        )

        bands_crossed = [band for _, _, _, band in calls["threshold"]]
        assert bands_crossed == [50]
        assert calls["exhaustion"] == []  # 55% does not cross 100%

    async def test_no_tenant_budget_configured_skips_both_checks_entirely(self, monkeypatch):
        """fetch_tenant_budget_status returning None (no allocated_budget on
        the tenant) must skip BUDGET_THRESHOLD/BUDGET_EXHAUSTED outright —
        even though this key's own write.api_key_budget_snap is set."""
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events

        write = self._write(api_key_budget_used=Decimal("999"), api_key_budget_snap=Decimal("1000"))
        calls = self._patch_kafka_helpers(monkeypatch, tenant_budget=None)

        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=write,
            cost=Decimal("50"), billed_units=Decimal("100"), inference_name="llm",
            budget_threshold_enabled=True, budget_exhausted_enabled=True,
        )

        assert calls["threshold"] == []
        assert calls["exhaustion"] == []
        assert calls["published"] == []

    async def test_exhaustion_subject_uses_the_tenants_snap_not_the_keys(self, monkeypatch):
        from consumers.payperuse_consumer._billing import TenantBudgetStatus
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events

        write = self._write(api_key_budget_used=Decimal("1"), api_key_budget_snap=Decimal("2"))
        tenant_budget = TenantBudgetStatus(used=Decimal("1000"), snap=Decimal("1000"))
        calls = self._patch_kafka_helpers(monkeypatch, tenant_budget=tenant_budget)

        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=write,
            cost=Decimal("1"), billed_units=Decimal("100"), inference_name="llm",
            budget_threshold_enabled=True, budget_exhausted_enabled=True,
        )

        assert calls["exhaustion"] == [("BUDGET_EXHAUSTED", "1", {"budget_snap": "1000"})]
        published = next(p for p in calls["published"] if p["event_name"] == "BUDGET_EXHAUSTED")
        assert published["details"] == ["INR", "1000"]

    async def test_quota_block_is_unaffected_by_the_budget_change(self, monkeypatch):
        """Quota was already tenant-level (quota_usage is keyed by tenant_id,
        not api_key_id) — this change must not touch its subject shape or
        its data source (write.quota_used/quota_snap, not tenant_budget)."""
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events

        write = self._write(
            api_key_budget_snap=None,  # no budget ceiling at all — budget block fully skipped
            quota_recorded=True,
            quota_used=Decimal("80"),
            quota_snap=Decimal("100"),
        )
        calls = self._patch_kafka_helpers(monkeypatch, tenant_budget=None)

        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=write,
            cost=Decimal("10"), billed_units=Decimal("10"), inference_name="nmt",
            budget_threshold_enabled=True, budget_exhausted_enabled=True,
        )

        assert calls["threshold"] == [("QUOTA_THRESHOLD", "1", {"model_task_type": "nmt"}, 75)]
        assert "api_key_id" not in calls["threshold"][0][2]

    async def test_quota_threshold_only_fires_for_the_highest_band_too(self, monkeypatch):
        """Same "highest band only" fix as BUDGET_THRESHOLD, applied to
        QUOTA_THRESHOLD too — it shares the identical loop-over-every-
        crossed-band bug before this fix."""
        from consumers.payperuse_consumer.handler import _publish_usage_crossing_events

        # pre = (92-33)/100 = 59%, post = 92% — crosses both 75 and 90.
        write = self._write(
            api_key_budget_snap=None,
            quota_recorded=True,
            quota_used=Decimal("92"),
            quota_snap=Decimal("100"),
        )
        calls = self._patch_kafka_helpers(monkeypatch, tenant_budget=None)

        await _publish_usage_crossing_events(
            db=object(), auth_db=object(), ctx=self._ctx(), write=write,
            cost=Decimal("1"), billed_units=Decimal("33"), inference_name="nmt",
            budget_threshold_enabled=True, budget_exhausted_enabled=True,
        )

        assert len(calls["threshold"]) == 1, (
            f"expected exactly one QUOTA_THRESHOLD call, got {calls['threshold']!r}"
        )
        assert calls["threshold"][0][3] == 90, "must report the highest band crossed (90), not 75"


class TestResolveRecipientsHelper:
    """_resolve_recipients — the two fail-safe paths that make it return []
    without ever calling ai4i_core.kafka.recipients.resolve_recipients: an
    unknown event_name (no catalog row -> no notification_id), and a
    missing auth_db (the second, named connection recipient resolution
    reads ai4iplatform_auth through). Both must degrade to an empty list,
    not raise — _publish_usage_crossing_events still publishes with
    whatever this returns (see resolve_recipients's own module docstring:
    an empty list is what makes the consumer settle the ledger row to
    "failed" instead of leaving it wedged, not something this helper
    should hide by raising)."""

    async def test_unknown_notification_id_returns_empty_list_without_calling_resolve(self, monkeypatch):
        from consumers.payperuse_consumer import handler as h

        called = {"resolve": False}

        async def _no_id(db, event_name):
            return None

        async def _resolve(core_db, auth_db, *, notification_id, tenant_id):
            called["resolve"] = True
            return ["should-not-be-reached@example.com"]

        monkeypatch.setattr(h, "get_notification_id", _no_id)
        monkeypatch.setattr(h, "resolve_recipients", _resolve)

        result = await h._resolve_recipients(object(), object(), "SOME_EVENT", "1")

        assert result == []
        assert called["resolve"] is False

    async def test_missing_auth_db_returns_empty_list_without_calling_resolve(self, monkeypatch):
        from consumers.payperuse_consumer import handler as h

        called = {"resolve": False}

        async def _has_id(db, event_name):
            return 7

        async def _resolve(core_db, auth_db, *, notification_id, tenant_id):
            called["resolve"] = True
            return ["should-not-be-reached@example.com"]

        monkeypatch.setattr(h, "get_notification_id", _has_id)
        monkeypatch.setattr(h, "resolve_recipients", _resolve)

        result = await h._resolve_recipients(object(), None, "SOME_EVENT", "1")

        assert result == []
        assert called["resolve"] is False

    async def test_happy_path_forwards_notification_id_and_tenant_id(self, monkeypatch):
        from consumers.payperuse_consumer import handler as h

        captured = {}

        async def _has_id(db, event_name):
            return 7

        async def _resolve(core_db, auth_db, *, notification_id, tenant_id):
            captured["notification_id"] = notification_id
            captured["tenant_id"] = tenant_id
            return ["admin@example.com"]

        monkeypatch.setattr(h, "get_notification_id", _has_id)
        monkeypatch.setattr(h, "resolve_recipients", _resolve)

        result = await h._resolve_recipients(object(), object(), "QUOTA_THRESHOLD", 42)

        assert result == ["admin@example.com"]
        assert captured["notification_id"] == 7
        assert captured["tenant_id"] == "42"  # coerced to str, per the call site
