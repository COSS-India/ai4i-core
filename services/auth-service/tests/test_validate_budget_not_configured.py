"""Regression coverage for /auth/validate's BUDGET_NOT_CONFIGURED enforcement.

Before this, an Institution with no Budget allocated anywhere in the
tenant -> application -> API-key chain (all unset/0%) could still make real,
billable LLM inference calls indefinitely: no budget_usage row ever existed
for the key, so the Kafka billing consumer's deduction UPDATE was a silent
no-op, "budget-exhausted" was never set, and /auth/validate had nothing to
check against — "no allocation" was treated as "unlimited", not the invalid
state allocation_service.py's own TENANT_BUDGET_NOT_SET/APPLICATION_BUDGET_NOT_SET
checks already consider it on the allocation-management endpoints.

This mirrors test_validate_budget_expired.py's own shape: the enforcement
signal (tenant_budget_unset) is cached directly on the API key's payload —
see APIKeyService._build_cache_payload — and read here with no DB round
trip, deterministic on the very first request regardless of whether the
tenant has ever generated a billed message.
"""
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
class TestValidateBudgetNotConfigured:
    async def test_no_budget_anywhere_in_chain_is_blocked_with_403(self) -> None:
        """The core scenario: a tenant with no Budget ever allocated to it
        (and therefore none cascaded to its Applications or Keys either)
        must not be allowed to run billable inference indefinitely."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(tenant_budget_unset="1")
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"BUDGET_NOT_CONFIGURED" in result.body
        assert b"administrator must allocate" in result.body

    async def test_takes_priority_over_budget_expired_and_exhausted(self) -> None:
        """"Never allocated" is a more fundamental gate than "the window
        lapsed" or "the ceiling was crossed" — both of those presuppose a
        Budget existed in the first place."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(
            tenant_budget_unset="1",
            budget_effective_to="",
            **{"budget-exhausted": "1"},
        )
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"BUDGET_NOT_CONFIGURED" in result.body

    async def test_configured_budget_falls_through_to_normal_success(self) -> None:
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result(tenant_budget_unset="")
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_field_absent_falls_through_to_normal_success(self) -> None:
        """A pre-fix key whose cached_data predates this field entirely has
        no key at all (not even an empty string) — treated as configured,
        not blocked; it self-heals the next time this key's cache is
        rebuilt for any other reason, or the moment its tenant is given a
        real Budget (APIKeyService.set_tenant_budget_unset_for_tenant)."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = _result()
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True
