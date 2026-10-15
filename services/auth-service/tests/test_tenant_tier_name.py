"""Unit tests for tier_name on GET /auth/tenants/{tenant_id}.

``tier_name`` is not a tenants column — ``TenantService.resolve_tier_name``
reads it from platform-core's ``tiers`` table so the Institution Admin's
"My Institution" view can show the assigned tier. The lookup fails soft:
any problem blanks the name rather than failing the GET.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.tenant import Tenant, TenantStatus
from app.services.tenant_service import TenantService


def _db(row) -> MagicMock:
    result = MagicMock()
    result.first.return_value = row
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


class TestResolveTierName:
    @pytest.mark.asyncio
    async def test_returns_name_for_assigned_tier(self) -> None:
        db = _db(SimpleNamespace(name="Gold"))
        assert await TenantService.resolve_tier_name(uuid4(), db) == "Gold"
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_tier_skips_lookup(self) -> None:
        db = _db(None)
        assert await TenantService.resolve_tier_name(None, db) is None
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_tier_returns_none(self) -> None:
        assert await TenantService.resolve_tier_name(uuid4(), _db(None)) is None

    @pytest.mark.asyncio
    async def test_platform_core_unconfigured_returns_none(self) -> None:
        assert await TenantService.resolve_tier_name(uuid4(), None) is None

    @pytest.mark.asyncio
    async def test_lookup_error_returns_none(self) -> None:
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("platform-core down"))
        assert await TenantService.resolve_tier_name(uuid4(), db) is None


def test_tenant_response_carries_tier_and_budget_fields() -> None:
    tier_id = uuid4()
    tenant = Tenant(
        id=152,
        name="Inst Eight Admin A",
        organisation="Inst Eight",
        email="a@example.com",
        status=TenantStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        tier_id=tier_id,
        allocated_budget=Decimal("50000.00"),
    )
    out = TenantService.build_tenant_response(tenant)
    assert out["tier_id"] == str(tier_id)
    assert out["tier_name"] is None  # filled in by the GET route only
    assert Decimal(out["allocated_budget"]) == Decimal("50000.00")
