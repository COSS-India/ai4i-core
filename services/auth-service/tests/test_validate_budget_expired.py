"""Regression coverage for /auth/validate's budget-expired enforcement.

Before this, tenants.budget_effective_to was written (TenantCreate, and now
PATCH /auth/tenants/{id}/budget) but never read anywhere — /auth/validate had
no concept of a lapsed budget window at all, so a request against an
API key whose tenant's window had ended still succeeded exactly as if the
window never existed (see the conversation's own walkthrough of the prior
behavior). The Kafka billing consumer now pushes a "budget-expired" flag
onto the API key's Redis hash (TenantService.refresh_budget_expiry_flag, via
POST /internal/ppu/tenant/{id}/budget-expiry-check) and this is where
_validate_api_key is expected to act on it.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response

from app.routes.validation import _validate_api_key


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.headers = {}  # no X-Original-Method/URI -> endpoint check passes through
    return request


@pytest.mark.asyncio
class TestValidateBudgetExpired:
    async def test_expired_budget_rejected_with_403_budget_expired(self) -> None:
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
            "budget-expired": "1",
        }
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"BUDGET_EXPIRED" in result.body
        assert b"effective window" in result.body

    async def test_expired_takes_priority_over_exhausted(self) -> None:
        """A window that's ended is a harder stop than merely running out of
        budget within a still-valid one — a caller must not see 429
        BUDGET_EXHAUSTED (which implies "wait for the period to reset")
        when the real problem is there's no valid period to reset into."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
            "budget-expired": "1",
            "budget-exhausted": "1",
        }
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"BUDGET_EXPIRED" in result.body

    async def test_not_expired_falls_through_to_normal_success(self) -> None:
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
            "budget-expired": "0",
        }
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_flag_absent_falls_through_to_normal_success(self) -> None:
        """A tenant that never had refresh_budget_expiry_flag run against it
        (no billed traffic yet) has no field at all — absence must not be
        misread as expired."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
        }
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True
