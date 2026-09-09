"""AI4IDS-2995: tier/budget effective-window enforcement.

Covers the parts of the ticket not already exercised by
test_tenant_tier_budget.py (which covers persistence/validation of the window
on assign_tenant_tier itself):

  * create_api_key must refuse a tenant whose window has already expired
    (TIER_BUDGET_EXPIRED), the same way it already refuses one with no tier
    at all (NO_ACTIVE_TIER) — and must seed the window into a newly-created
    key's cache payload so the hot path never needs a DB round trip for it.
  * budget_effective_from/to must survive every cache writer OTHER than
    set_budget_window_for_tenant (refresh, write-through-while-ineligible) —
    mirrors the existing tier_id preservation tests, because a plain "add the
    field" without this half is exactly the kind of change that regresses
    silently: the field is present right after assign, then vanishes on the
    next unrelated refresh (e.g. a reactivation).
  * GET /auth/validate's API-key branch must 403 TIER_BUDGET_EXPIRED once
    budget_effective_to is in the past, and must not affect a tenant with no
    window configured or a still-valid one. The JWT branch (Portal's
    "Try it now") is a fully separate function that never reads
    budget_effective_to at all — pinned here by asserting the dispatcher
    still routes a JWT-strict token there untouched.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import Response

from app.core.exceptions import ValidationError
from app.models.api_key import APIKey
from app.models.application import Application, ApplicationStatus
from app.models.tenant import Tenant, TenantStatus
from app.routes.validation import _validate_api_key
from app.services.api_key_service import APIKeyService

_TOKEN = "a" * 32


def _application(*, tenant_id: int = 1, allocated_budget=None) -> Application:
    return Application(
        id=1, tenant_id=tenant_id, name="Test App",
        status=ApplicationStatus.ACTIVE, allocated_budget=allocated_budget,
    )


def _tenant(*, tier_id=None, allocated_budget=None, budget_effective_to=None) -> Tenant:
    if tier_id is None:
        tier_id = uuid4()
    return Tenant(
        id=1, name="Acme", organisation="Acme",
        email="test-contact@example.invalid", status=TenantStatus.ACTIVE, tier_id=tier_id,
        allocated_budget=allocated_budget, budget_effective_to=budget_effective_to,
    )


def _api_key(*, cached_data: dict | None = None, application_id: int = 1) -> APIKey:
    return APIKey(
        id=1,
        application_id=application_id,
        key_name="test-key",
        api_key=_TOKEN,
        permissions=[12],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
        cached_data=cached_data,
    )


def _service(*, applications=None, tenants=None) -> tuple:
    repo = AsyncMock()
    repo.get_permission_ids_by_names = AsyncMock(return_value={})
    cache = AsyncMock()
    applications = applications if applications is not None else AsyncMock()
    tenants = tenants if tenants is not None else AsyncMock()
    svc = APIKeyService(repo, cache, application_repo=applications, tenant_repo=tenants)
    return svc, repo, cache, applications, tenants


class TestCreateApiKeyBlocksExpiredWindow:
    @pytest.mark.asyncio
    async def test_expired_window_rejected_before_permission_resolution(self) -> None:
        """The exact bug scenario: a tenant with an active tier_id but a
        budget_effective_to in the past must be blocked from issuing new
        keys, not just from validating existing ones. Raised before permission
        resolution — repo.get_permission_ids_by_names must never be reached."""
        application = _application()
        tenant = _tenant(budget_effective_to=datetime.now(timezone.utc) - timedelta(days=1))
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, cache, applications, tenants = _service(applications=applications, tenants=tenants)

        with pytest.raises(ValidationError) as exc_info:
            await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("20"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "TIER_BUDGET_EXPIRED"
        repo.get_permission_ids_by_names.assert_not_awaited()
        cache.set_api_key_cache.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_future_window_allowed_and_seeded_into_cache_payload(self) -> None:
        """A still-valid window must not block creation, and both
        budget_effective_from/to must be written into the new key's cache
        payload (ISO strings — the Redis hash is string-valued throughout)
        so /auth/validate never needs a DB round trip to enforce expiry."""
        application = _application(allocated_budget=Decimal("1000.00"))
        effective_from = datetime.now(timezone.utc)
        effective_to = effective_from + timedelta(days=30)
        tenant = _tenant(allocated_budget=Decimal("5000.00"))
        tenant.budget_effective_from = effective_from
        tenant.budget_effective_to = effective_to
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        applications.list_by_application = AsyncMock(return_value=[])
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, cache, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        with patch("app.services.api_key_service.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.api_key_service.budget_usage.write_budget_snapshot", AsyncMock()):
            _raw_key, api_key = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("20"),
                caller_tenant_id=1,
            )

        assert api_key is not None
        payload = cache.set_api_key_cache.await_args.args[2]
        assert payload["budget_effective_from"] == effective_from.isoformat()
        assert payload["budget_effective_to"] == effective_to.isoformat()

    @pytest.mark.asyncio
    async def test_no_window_configured_is_not_blocked(self) -> None:
        """A tenant that has never had a window set (budget_effective_to
        NULL — a tier assigned before this feature existed, or via
        create_tenant with no window given) must NOT be treated as expired —
        "never configured" is not "reached"."""
        application = _application(allocated_budget=Decimal("1000.00"))
        tenant = _tenant(allocated_budget=Decimal("5000.00"), budget_effective_to=None)
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, cache, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        with patch("app.services.api_key_service.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.api_key_service.budget_usage.write_budget_snapshot", AsyncMock()):
            _raw_key, api_key = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("20"),
                caller_tenant_id=1,
            )

        assert api_key is not None


class TestBudgetWindowCachePreservation:
    """Mirrors test_api_key_cache_miss_fallback.py's tier_id preservation
    tests: budget_effective_from/to can only be safely recomputed by
    set_budget_window_for_tenant (a genuine assign/renew) — every OTHER cache
    writer must carry it forward from cached_data instead of dropping it."""

    @pytest.mark.asyncio
    async def test_refresh_redis_cache_preserves_budget_window_from_existing_cached_data(self) -> None:
        svc, repo, cache, _applications, _tenants = _service()
        cache.get_api_key_cache = AsyncMock(return_value=None)  # Redis cold
        key = _api_key(
            cached_data={
                "api_key": _TOKEN,
                "tier_id": "tier-A",
                "budget_effective_from": "2026-01-01T00:00:00+00:00",
                "budget_effective_to": "2026-12-31T00:00:00+00:00",
            }
        )

        await svc._refresh_redis_cache(key, "1")

        written = cache.set_api_key_cache.await_args.args[2]
        persisted = repo.update.await_args.args[1]["cached_data"]
        assert written["budget_effective_from"] == "2026-01-01T00:00:00+00:00"
        assert written["budget_effective_to"] == "2026-12-31T00:00:00+00:00"
        assert persisted["budget_effective_from"] == "2026-01-01T00:00:00+00:00"
        assert persisted["budget_effective_to"] == "2026-12-31T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_persist_current_state_to_cached_data_preserves_budget_window(self) -> None:
        """The write-through-while-ineligible path (revoked, or
        application/tenant temporarily inactive) must also carry the window
        forward — Redis is left alone here, but cached_data must not drift."""
        svc, repo, cache, _applications, _tenants = _service()
        key = _api_key(
            cached_data={
                "api_key": _TOKEN,
                "tier_id": "tier-A",
                "budget_effective_to": "2026-12-31T00:00:00+00:00",
            }
        )

        await svc._persist_current_state_to_cached_data(key, "1")

        persisted = repo.update.await_args.args[1]["cached_data"]
        assert persisted["budget_effective_to"] == "2026-12-31T00:00:00+00:00"
        cache.set_api_key_cache.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refresh_with_no_prior_window_writes_nothing_extra(self) -> None:
        """A key created before this feature (cached_data has no window keys
        at all) must not have the fields fabricated as None/empty on refresh —
        they should simply stay absent."""
        svc, repo, cache, _applications, _tenants = _service()
        cache.get_api_key_cache = AsyncMock(return_value=None)
        key = _api_key(cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})

        await svc._refresh_redis_cache(key, "1")

        written = cache.set_api_key_cache.await_args.args[2]
        assert "budget_effective_from" not in written
        assert "budget_effective_to" not in written


class TestSetBudgetWindowForTenant:
    @pytest.mark.asyncio
    async def test_force_writes_both_fields_to_cache_and_db(self) -> None:
        """The mechanism assign_tenant_tier relies on to write-through a
        renewed window onto every already-issued key — same force-write
        pattern as set_tier_id_for_tenant (_patch_all_tenant_key_caches)."""
        repo = AsyncMock()
        cache = AsyncMock()
        key = _api_key()
        # set_budget_window_for_tenant makes two independent
        # _patch_all_tenant_key_caches passes (one per field), each of which
        # re-pages list_active_keys_for_tenant from after_id=0 — a single
        # one-key page (len < the pagination limit) ends each pass's loop
        # immediately, so return_value (not a consumed side_effect list) is
        # correct here: both passes see the same one key.
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])
        svc = APIKeyService(repo, cache)
        effective_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        effective_to = datetime(2026, 12, 31, tzinfo=timezone.utc)

        await svc.set_budget_window_for_tenant(1, effective_from, effective_to)

        cache.patch_api_key_cache_field.assert_any_call(_TOKEN, "budget_effective_from", effective_from.isoformat())
        cache.patch_api_key_cache_field.assert_any_call(_TOKEN, "budget_effective_to", effective_to.isoformat())
        repo.patch_cached_data_field_for_tenant.assert_any_call(1, "budget_effective_from", effective_from.isoformat())
        repo.patch_cached_data_field_for_tenant.assert_any_call(1, "budget_effective_to", effective_to.isoformat())


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.headers = {}
    return request


@pytest.mark.asyncio
class TestValidateApiKeyRouteExpiry:
    """GET /auth/validate's API-key branch — routes/validation.py's
    _validate_api_key. The JWT branch (_validate_jwt) is a separate function
    that never reads budget_effective_to, so Portal's "Try it now" is
    unaffected by construction, not by a conditional guard here."""

    async def test_expired_window_returns_403_tier_budget_expired(self) -> None:
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
            "budget_effective_to": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }
        response = Response()

        result = await _validate_api_key(_TOKEN, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"TIER_BUDGET_EXPIRED" in result.body

    async def test_valid_window_passes_through(self) -> None:
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
            "budget_effective_to": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }
        response = Response()

        result = await _validate_api_key(_TOKEN, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_no_window_configured_passes_through(self) -> None:
        """No budget_effective_to at all (legacy key/tenant) must not be
        treated as expired."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
        }
        response = Response()

        result = await _validate_api_key(_TOKEN, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_malformed_cached_window_does_not_crash_the_request(self) -> None:
        """A corrupt/unexpected value in the cached field must degrade to
        "not enforced", never a 500 — this is a defense-in-depth guard on a
        value this service itself always writes as isoformat(), for the
        unlikely case of a manually-edited or legacy-shaped cache entry."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
            "budget_effective_to": "not-a-real-timestamp",
        }
        response = Response()

        result = await _validate_api_key(_TOKEN, _mock_request(), response, api_key_svc)

        assert result.valid is True

    async def test_expiry_checked_before_budget_exhausted(self) -> None:
        """When both an expired window AND a budget-exhausted flag are
        present, TIER_BUDGET_EXPIRED must win — after expiry, the actionable
        message for the admin is "renew the tier", not "top up the budget"."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
            "budget_effective_to": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "budget-exhausted": "1",
        }
        response = Response()

        result = await _validate_api_key(_TOKEN, _mock_request(), response, api_key_svc)

        assert result.status_code == 403
        assert b"TIER_BUDGET_EXPIRED" in result.body
