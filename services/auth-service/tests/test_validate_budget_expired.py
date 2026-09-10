"""Regression coverage for /auth/validate's budget-expired enforcement.

Before this, tenants.budget_effective_to was written (TenantCreate, and
PATCH /auth/tenants/{id}/budget) but never read anywhere — /auth/validate
had no concept of a lapsed budget window at all, so a request against an
API key whose tenant's window had ended still succeeded exactly as if the
window never existed.

The first version of this enforcement pushed a computed "budget-expired"
boolean onto the API key's Redis hash from the Kafka billing consumer, on
every billed message. That had two real gaps: the first request after a
window lapsed always succeeded (the flag could only be set AFTER a request
already went through and got billed), and a tenant whose spans never
reached billing at all (no pricing row for the service, or cost == 0, both
early-return in payperuse_consumer._bill_usage) was never blocked, no
matter how expired. This version instead caches the raw budget_effective_to
value itself in the key's payload (see APIKeyService._build_cache_payload)
and _validate_api_key compares it directly against "now" on every request —
deterministic on the first request, and independent of whether the tenant
has ever generated a billed message.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response

from app.routes.validation import _validate_api_key


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.headers = {}  # no X-Original-Method/URI -> endpoint check passes through
    return request


def _result(**overrides) -> dict:
    base = {
        "id": 42,
        "application_id": "7",
        "tenant_id": "1",
        "permissions": [1, 2, 3],
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
class TestValidateBudgetExpired:
    async def test_expired_budget_rejected_with_403_budget_expired(self) -> None:
        """The core scenario: a cached budget_effective_to in the past
        blocks the request on this very call — no prior Kafka message
        needs to have run for this tenant at all."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(budget_effective_to=past.isoformat())
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"BUDGET_EXPIRED" in result.body
        assert b"effective window" in result.body

    async def test_a_tenant_that_never_billed_anything_is_still_blocked(self) -> None:
        """The exact gap the Kafka-pushed-flag design had: a tenant whose
        traffic only ever hits unpriced/zero-cost services, so
        _bill_usage's early returns mean no billed message — and therefore
        no push — has ever happened for them. The cached date is set at
        create_api_key time regardless of billing, so this still blocks
        correctly with zero billed messages in the picture."""
        past = datetime.now(timezone.utc) - timedelta(days=200)
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(budget_effective_to=past.isoformat())
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"BUDGET_EXPIRED" in result.body

    async def test_expired_takes_priority_over_exhausted(self) -> None:
        """A window that's ended is a harder stop than merely running out of
        budget within a still-valid one — a caller must not see 429
        BUDGET_EXHAUSTED (which implies "wait for the period to reset")
        when the real problem is there's no valid period to reset into."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(
            budget_effective_to=past.isoformat(), **{"budget-exhausted": "1"}
        )
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"BUDGET_EXPIRED" in result.body

    async def test_future_effective_to_falls_through_to_normal_success(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=30)
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(budget_effective_to=future.isoformat())
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_empty_string_falls_through_to_normal_success(self) -> None:
        """A tenant with no window at all is cached as budget_effective_to="" —
        see APIKeyService._build_cache_payload — must not be misread as
        expired."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(budget_effective_to="")
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_field_absent_falls_through_to_normal_success(self) -> None:
        """A pre-fix key whose cached_data predates this field entirely has
        no key at all (not even an empty string) — must not be misread as
        expired either."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result()
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_unparseable_value_fails_open_not_closed(self) -> None:
        """Cache corruption (a malformed ISO string) must not itself become
        an outage that blocks every request for the tenant — fails open
        with a logged warning instead of raising past this check."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(budget_effective_to="not-a-date")
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_exact_instant_counts_as_expired(self) -> None:
        """"Reached" is inclusive — a budget_effective_to equal to (not
        just before) "now" must already read as expired."""
        api_key_svc = AsyncMock()

        async def _validate_at_exact_instant(_token):
            now = datetime.now(timezone.utc)
            return _result(budget_effective_to=now.isoformat())

        api_key_svc.validate_api_key = _validate_at_exact_instant
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        # By the time _cached_budget_window_is_expired runs, real time has
        # moved past "now" captured above, so this is >= by construction —
        # covered precisely (not just "a bit later") in test_budget_window.py's
        # own frozen-clock test; this only confirms the wiring reaches that
        # same inclusive comparison.
        assert result.status_code == 403
