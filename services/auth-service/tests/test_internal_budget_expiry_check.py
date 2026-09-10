"""POST /internal/ppu/tenant/{tenant_id}/budget-expiry-check — the Kafka
billing consumer's hook to recompute a tenant's budget-expired flag on every
billed message (see payperuse_consumer.handler._post_billing). Thin
delegation to TenantService.refresh_budget_expiry_flag, same shape as the
sibling /ppu/tenant/{tenant_id}/quota-exhausted route.
"""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routes.internal import check_tenant_budget_expiry


@pytest.mark.asyncio
class TestCheckTenantBudgetExpiry:
    async def test_delegates_to_service_with_integer_tenant_id(self) -> None:
        svc = AsyncMock()

        await check_tenant_budget_expiry("42", svc)

        svc.refresh_budget_expiry_flag.assert_awaited_once_with(42)

    async def test_invalid_tenant_id_rejected_before_reaching_the_service(self) -> None:
        svc = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await check_tenant_budget_expiry("not-a-number", svc)

        assert exc_info.value.status_code == 400
        svc.refresh_budget_expiry_flag.assert_not_awaited()
