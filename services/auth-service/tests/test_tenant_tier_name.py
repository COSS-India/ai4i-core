"""Unit tests for tier_name and tier_limits on GET /auth/tenants/{tenant_id}.

``tier_name`` is not a tenants column — ``TenantService.resolve_tier_name``
reads it from platform-core's ``tiers`` table so the Institution Admin's
"My Institution" view can show the assigned tier. The lookup fails soft:
an assigned tier whose name can't be resolved comes back as "Unknown"
(shown as-is by the client) rather than failing the GET, and never as
null, which would read as "no tier assigned".

``tier_limits`` (rate limit + monthly quota per task type) backs the
read-only "Tier and usage limits" section of the same view. It is read live
from platform-core's ``tiers`` / ``tier_quotas`` / ``inference_types`` and is
null when no tier is assigned or the lookup fails.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.tenant import Tenant, TenantStatus
from app.services.tenant_service import UNKNOWN_TIER_NAME, TenantService


def _db(row) -> MagicMock:
    result = MagicMock()
    result.first.return_value = row
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _tier_db(name="Gold", rate_limit=600, quotas=()) -> MagicMock:
    """Platform-core session answering each lookup by the table it reads."""
    tier = SimpleNamespace(name=name, rate_limit=rate_limit)
    quota_rows = [SimpleNamespace(task_type=t, monthly_quota=Decimal(q), unit=u) for t, q, u in quotas]

    async def execute(stmt, params):
        result = MagicMock()
        if "tier_quotas" in str(stmt):
            result.all.return_value = quota_rows
        else:
            result.first.return_value = tier
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute)
    return db


_QUOTAS = (
    ("asr", "99999999.0000", "audio_minutes"),
    ("llm", "99999999.0000", "tokens"),
)


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
    async def test_missing_tiers_row_returns_unknown(self) -> None:
        assert await TenantService.resolve_tier_name(uuid4(), _db(None)) == UNKNOWN_TIER_NAME

    @pytest.mark.asyncio
    async def test_platform_core_unconfigured_returns_unknown(self) -> None:
        assert await TenantService.resolve_tier_name(uuid4(), None) == UNKNOWN_TIER_NAME

    @pytest.mark.asyncio
    async def test_lookup_error_returns_unknown(self) -> None:
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("platform-core down"))
        assert await TenantService.resolve_tier_name(uuid4(), db) == UNKNOWN_TIER_NAME


class TestResolveTierLimits:
    @pytest.mark.asyncio
    async def test_returns_rate_limit_and_quotas(self) -> None:
        limits = await TenantService.resolve_tier_limits(uuid4(), _tier_db(quotas=_QUOTAS))
        assert limits == {
            "rate_limit": 600,
            "quotas": [
                {"task_type": "asr", "monthly_quota": Decimal("99999999.0000"), "unit": "audio_minutes"},
                {"task_type": "llm", "monthly_quota": Decimal("99999999.0000"), "unit": "tokens"},
            ],
        }

    @pytest.mark.asyncio
    async def test_tier_without_rate_limit_or_quotas(self) -> None:
        limits = await TenantService.resolve_tier_limits(uuid4(), _tier_db(rate_limit=None))
        assert limits == {"rate_limit": None, "quotas": []}

    @pytest.mark.asyncio
    async def test_no_tier_skips_lookup(self) -> None:
        db = _tier_db()
        assert await TenantService.resolve_tier_limits(None, db) is None
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_tiers_row_returns_none(self) -> None:
        db = _db(None)
        assert await TenantService.resolve_tier_limits(uuid4(), db) is None
        db.execute.assert_awaited_once()  # no quota query for a tier that isn't there

    @pytest.mark.asyncio
    async def test_platform_core_unconfigured_returns_none(self) -> None:
        assert await TenantService.resolve_tier_limits(uuid4(), None) is None

    @pytest.mark.asyncio
    async def test_lookup_error_returns_none(self) -> None:
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("platform-core down"))
        assert await TenantService.resolve_tier_limits(uuid4(), db) is None


def _tenant(tier_id=None) -> Tenant:
    return Tenant(
        id=152,
        name="Inst Eight Admin A",
        organisation="Inst Eight",
        email="a@example.com",
        status=TenantStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        tier_id=tier_id,
        allocated_budget=Decimal("50000.00"),
    )


class TestGetTenantRouteTierName:
    """Through the real GET /auth/tenants/{tenant_id} route, so dropping the
    tier_name / tier_limits assignment in the route fails a test, not just
    the helper."""

    @staticmethod
    def _client(tenant: Tenant, platform_core_db):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.database import get_platform_core_db
        from app.core.exceptions import register_exception_handlers
        from app.dependencies.auth import get_current_user
        from app.dependencies.services import get_tenant_service
        from app.routes import tenants as tenant_routes

        svc = MagicMock()
        svc.get_tenant = AsyncMock(return_value=tenant)
        svc.build_tenant_response = TenantService.build_tenant_response
        svc.resolve_tier_name = TenantService.resolve_tier_name
        svc.resolve_tier_limits = TenantService.resolve_tier_limits

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(tenant_routes.router)
        app.dependency_overrides[get_current_user] = lambda: MagicMock(id=uuid4(), tenant_id=152)
        app.dependency_overrides[get_tenant_service] = lambda: svc
        app.dependency_overrides[get_platform_core_db] = lambda: platform_core_db
        return TestClient(app)

    def test_returns_tier_name_for_assigned_tier(self) -> None:
        tier_id = uuid4()
        client = self._client(_tenant(tier_id), _tier_db(quotas=_QUOTAS))

        response = client.get("/auth/tenants/152")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["tier_id"] == str(tier_id)
        assert data["tier_name"] == "Gold"
        assert Decimal(data["allocated_budget"]) == Decimal("50000.00")

    def test_returns_tier_limits_for_assigned_tier(self) -> None:
        client = self._client(_tenant(uuid4()), _tier_db(quotas=_QUOTAS))

        limits = client.get("/auth/tenants/152").json()["data"]["tier_limits"]

        assert limits["rate_limit"] == 600
        assert [(q["task_type"], Decimal(q["monthly_quota"]), q["unit"]) for q in limits["quotas"]] == [
            ("asr", Decimal("99999999"), "audio_minutes"),
            ("llm", Decimal("99999999"), "tokens"),
        ]

    def test_unassigned_tenant_returns_null_tier_name(self) -> None:
        client = self._client(_tenant(None), _db(None))

        data = client.get("/auth/tenants/152").json()["data"]

        assert data["tier_id"] is None
        assert data["tier_name"] is None
        assert data["tier_limits"] is None

    def test_failed_lookup_keeps_get_working_with_tier_id_set(self) -> None:
        # The client shows tier_name as-is, so "Unknown" — never "—".
        tier_id = uuid4()
        client = self._client(_tenant(tier_id), None)

        response = client.get("/auth/tenants/152")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["tier_id"] == str(tier_id)
        assert data["tier_name"] == UNKNOWN_TIER_NAME
        assert data["tier_limits"] is None


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
    assert out["tier_limits"] is None
    assert Decimal(out["allocated_budget"]) == Decimal("50000.00")
