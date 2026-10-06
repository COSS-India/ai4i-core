"""DELETE /auth/tenants/{id}/tier — removing a tenant's tier assignment.

The bug this pins: tenants.tier_id is not the only copy of a tenant's tier.
Every already-issued API key carries its own cached tier_id (Redis hash +
api_key.cached_data), computed once at create_api_key and carried forward by
every other cache writer (APIKeyService._preserved_tier_id). So:

* Clearing only tenants.tier_id leaves every existing key served — and
  billed, and entitlement-checked — under the OLD tier.
* Deleting the cached field instead is worse: /auth/validate then emits
  X-Tier-ID="", and inference-service skips its tier entitlement check
  entirely on an empty header (orchestrator.py / llm_service.py), so the
  key could reach every tier-restricted service.

The fix writes an explicit UNASSIGNED_TIER_ID ("") onto every key and
/auth/validate rejects exactly that value with 403 NO_ACTIVE_TIER, while an
ABSENT tier_id (legacy pre-tier key) keeps being served unchanged.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Response

from app.core.constants import UNASSIGNED_TIER_ID
from app.core.exceptions import EntityNotFoundError
from app.core.permission_checker import PermissionChecker
from app.models.api_key import APIKey
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.routes.validation import _validate_api_key
from app.services.api_key_service import APIKeyService
from app.services.tenant_service import TenantService


def _admin_user() -> User:
    return User(id=uuid4(), email="test-admin@example.invalid", username=uuid4().hex[:12])


def _tenant(*, tier_id=None, tenant_id=1) -> Tenant:
    return Tenant(
        id=tenant_id, name="Acme", organisation="Acme", email="test-contact@example.invalid",
        status=TenantStatus.ACTIVE, tier_id=tier_id,
    )


def _svc(*, roles=("ADMIN",), tenant=None) -> TenantService:
    svc = TenantService(
        tenant_repo=AsyncMock(),
        user_repo=AsyncMock(),
        role_service=AsyncMock(),
        verification_repo=AsyncMock(),
        credentials_repo=AsyncMock(),
        token_service=AsyncMock(),
        email_client=AsyncMock(),
        api_key_service=AsyncMock(),
        allocation_service=AsyncMock(),
    )
    svc._roles.get_user_roles = AsyncMock(return_value=list(roles))
    svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
    svc._tenants.update = AsyncMock()
    svc._tenants.save_and_refresh = AsyncMock()
    return svc


@pytest.fixture(autouse=True)
def _no_notifications(monkeypatch):
    """assign_tenant_tier (used by the re-assign test) fires the
    TIER_ASSIGNED pipeline; keep it off platform_core_db's mock queue.

    raising=False throughout: the notification hand-off in tenant_service
    is being reworked in parallel (the first three names are replaced by
    the last two), so this file must pass whichever version it runs on
    instead of erroring at setup on a name that module no longer has."""
    for name, stub in (
        ("is_notification_enabled", AsyncMock(return_value=False)),
        ("check_and_record_action", AsyncMock(return_value=False)),
        ("publish_notification_event", MagicMock()),
        ("publish_tier_event", MagicMock()),
        ("refresh_tenant_subscriptions", MagicMock()),
    ):
        monkeypatch.setattr(f"app.services.tenant_service.{name}", stub, raising=False)


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.headers = {}  # no X-Original-Method/URI -> endpoint check passes through
    return request


def _tier_cache(status=None, rate_limit=None) -> MagicMock:
    """CacheService stand-in for the core:tier:{id} read; default is an unknown tier."""
    cache = MagicMock()
    cache.get_tier_cache = AsyncMock(return_value=(status, rate_limit) if status is not None else None)
    cache.set_tier_cache = AsyncMock()
    return cache


def _validate_result(**overrides) -> dict:
    base = {"id": 42, "application_id": "7", "tenant_id": "1", "permissions": [1, 2, 3]}
    base.update(overrides)
    return base


async def _validate(result: dict, tier_cache: MagicMock | None = None):
    api_key_svc = AsyncMock()
    api_key_svc.validate_api_key.return_value = result
    response = Response()
    with patch("app.routes.validation._resolve_service", AsyncMock(return_value=None)):
        out = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc, tier_cache or _tier_cache())
    return out, response


# ── Service: TenantService.unassign_tenant_tier ─────────────────────────────


class TestUnassignTenantTierService:
    @pytest.mark.asyncio
    async def test_assigned_tenant_is_cleared_and_keys_are_marked(self) -> None:
        """The exact scenario: Institution on Premium → Remove from Tier.
        tenants.tier_id must become NULL AND every existing key's cached
        tier must be overwritten — the DB write alone leaves keys on Premium."""
        premium = uuid4()
        tenant = _tenant(tier_id=premium)
        svc = _svc(tenant=tenant)
        user = _admin_user()

        result, previous = await svc.unassign_tenant_tier(user, 1)

        assert result is tenant
        assert previous == premium
        svc._tenants.update.assert_awaited_once_with(
            tenant, {"tier_id": None, "updated_by": user.id}
        )
        svc._tenants.save_and_refresh.assert_awaited_once_with(tenant)
        svc._api_keys.mark_tier_unassigned_for_tenant.assert_awaited_once_with(1)
        # Never routed through the assign path's "force a real tier" writer.
        svc._api_keys.set_tier_id_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_admin_rejected_before_any_read_or_write(self) -> None:
        svc = _svc(roles=["TENANT ADMIN"], tenant=_tenant(tier_id=uuid4()))

        with pytest.raises(HTTPException) as exc_info:
            await svc.unassign_tenant_tier(_admin_user(), 1)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._tenants.get_by_id_for_update.assert_not_awaited()
        svc._tenants.update.assert_not_awaited()
        svc._api_keys.mark_tier_unassigned_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_tenant_is_404(self) -> None:
        svc = _svc(tenant=None)

        with pytest.raises(EntityNotFoundError):
            await svc.unassign_tenant_tier(_admin_user(), 999)

        svc._tenants.update.assert_not_awaited()
        svc._api_keys.mark_tier_unassigned_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_already_unassigned_is_a_safe_no_op(self) -> None:
        """Repeat call: 200, no DB write, previous_tier_id None. The cache
        mark still runs — it's what lets a retry repair a previous call whose
        DB write committed but whose cache write failed."""
        tenant = _tenant(tier_id=None)
        svc = _svc(tenant=tenant)

        result, previous = await svc.unassign_tenant_tier(_admin_user(), 1)

        assert result is tenant
        assert previous is None
        svc._tenants.update.assert_not_awaited()
        svc._tenants.save_and_refresh.assert_not_awaited()
        svc._api_keys.mark_tier_unassigned_for_tenant.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_twice_in_a_row_writes_the_db_only_once(self) -> None:
        tenant = _tenant(tier_id=uuid4())
        svc = _svc(tenant=tenant)

        async def _apply(_tenant_obj, data):
            for k, v in data.items():
                setattr(_tenant_obj, k, v)
        svc._tenants.update = AsyncMock(side_effect=_apply)

        await svc.unassign_tenant_tier(_admin_user(), 1)
        _, second_previous = await svc.unassign_tenant_tier(_admin_user(), 1)

        assert tenant.tier_id is None
        assert second_previous is None
        assert svc._tenants.update.await_count == 1

    @pytest.mark.asyncio
    async def test_only_the_target_tenant_is_touched(self) -> None:
        tenant = _tenant(tier_id=uuid4(), tenant_id=7)
        svc = _svc(tenant=tenant)

        await svc.unassign_tenant_tier(_admin_user(), 7)

        svc._tenants.get_by_id_for_update.assert_awaited_once_with(7)
        assert svc._tenants.update.await_args.args[0] is tenant
        assert set(svc._tenants.update.await_args.args[1]) == {"tier_id", "updated_by"}
        svc._api_keys.mark_tier_unassigned_for_tenant.assert_awaited_once_with(7)

    @pytest.mark.asyncio
    async def test_api_keys_service_missing_does_not_block_unassignment(self) -> None:
        tenant = _tenant(tier_id=uuid4())
        svc = _svc(tenant=tenant)
        svc._api_keys = None

        result, _ = await svc.unassign_tenant_tier(_admin_user(), 1)

        assert result is tenant
        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reassign_after_unassign_restores_a_real_cached_tier(self) -> None:
        """Unassign → assign again must hand keys a real tier back (which
        /auth/validate serves), not leave the unassigned marker in place."""
        tenant = _tenant(tier_id=uuid4())
        svc = _svc(tenant=tenant)

        async def _apply(_tenant_obj, data):
            for k, v in data.items():
                setattr(_tenant_obj, k, v)
        svc._tenants.update = AsyncMock(side_effect=_apply)

        await svc.unassign_tenant_tier(_admin_user(), 1)

        gold = uuid4()
        tier_row = MagicMock(id=gold)
        tier_row.name = "Gold"
        core_db = AsyncMock()
        core_db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=tier_row)))
        await svc.assign_tenant_tier(_admin_user(), 1, str(gold), core_db)

        assert tenant.tier_id == gold
        svc._api_keys.set_tier_id_for_tenant.assert_awaited_once_with(1, str(gold))


# ── Cache: APIKeyService.mark_tier_unassigned_for_tenant ────────────────────


def _key(cached_data=None) -> APIKey:
    return APIKey(
        id=1, application_id=1, key_name="test", api_key="a" * 32, permissions=[1],
        is_active=True, cached_data=cached_data if cached_data is not None else {"api_key": "x"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )


class TestMarkTierUnassignedForTenant:
    @pytest.mark.asyncio
    async def test_overwrites_only_keys_that_carry_a_tier(self) -> None:
        """Both stores go through their only-if-present variant — the
        unconditional writers would add the marker to legacy keys too."""
        repo, cache, key = AsyncMock(), AsyncMock(), _key()
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])
        svc = APIKeyService(repo, cache)

        await svc.mark_tier_unassigned_for_tenant(1)

        cache.patch_api_key_cache_field_if_present.assert_awaited_once_with(
            key.api_key, "tier_id", UNASSIGNED_TIER_ID
        )
        cache.patch_api_key_cache_field.assert_not_awaited()
        repo.patch_cached_data_field_for_tenant.assert_awaited_once_with(
            1, "tier_id", UNASSIGNED_TIER_ID, only_if_present=True
        )
        repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_tenant_wide_writers_stay_unconditional(self) -> None:
        """Assign must still ADD tier_id to a key that lacks it (that's how a
        legacy key joins a tier) — only unassign is restricted."""
        repo, cache, key = AsyncMock(), AsyncMock(), _key()
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])
        svc = APIKeyService(repo, cache)
        tier = str(uuid4())

        await svc.set_tier_id_for_tenant(1, tier)

        cache.patch_api_key_cache_field.assert_awaited_once_with(key.api_key, "tier_id", tier)
        cache.patch_api_key_cache_field_if_present.assert_not_awaited()
        repo.patch_cached_data_field_for_tenant.assert_awaited_once_with(1, "tier_id", tier)

    @pytest.mark.asyncio
    async def test_field_is_never_deleted(self) -> None:
        """An absent tier_id is how legacy keys look and is still served —
        HDEL here would silently turn an unassigned tenant into one."""
        repo, cache, key = AsyncMock(), AsyncMock(), _key()
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])
        svc = APIKeyService(repo, cache)

        await svc.mark_tier_unassigned_for_tenant(1)

        cache.delete_api_key_cache_field.assert_not_awaited()
        cache.delete_api_key_cache_fields.assert_not_awaited()
        repo.remove_cached_data_fields_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_repo_skips_everything(self) -> None:
        cache = AsyncMock()
        svc = APIKeyService(None, cache)

        await svc.mark_tier_unassigned_for_tenant(1)

        cache.patch_api_key_cache_field.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_marker_survives_a_later_cache_refresh(self) -> None:
        """Adversarial: after unassign, an unrelated edit (key rename,
        tenant update) rebuilds the key's cache via _refresh_redis_cache.
        _preserved_tier_id must carry the marker forward — dropping it would
        make the key look legacy (served, no tier restriction)."""
        repo, cache = AsyncMock(), AsyncMock()
        key = _key(cached_data={"api_key": "x", "tier_id": UNASSIGNED_TIER_ID})
        cache.get_api_key_cache = AsyncMock(return_value={"tier_id": UNASSIGNED_TIER_ID})
        svc = APIKeyService(repo, cache)

        await svc._refresh_redis_cache(key, "1")

        payload = cache.set_api_key_cache.await_args.args[2]
        assert "tier_id" in payload
        assert payload["tier_id"] == UNASSIGNED_TIER_ID


# ── /auth/validate ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestValidateRejectsUnassignedTier:
    async def test_unassigned_key_is_403_no_active_tier(self) -> None:
        out, response = await _validate(_validate_result(tier_id=UNASSIGNED_TIER_ID))

        assert out.status_code == 403
        assert b"NO_ACTIVE_TIER" in out.body
        # Must not reach the success path that would emit X-Tier-ID="".
        assert "X-Tier-ID" not in response.headers

    async def test_unassigned_outranks_budget_exhausted(self) -> None:
        out, _ = await _validate(
            _validate_result(tier_id=UNASSIGNED_TIER_ID, **{"budget-exhausted": "1"})
        )

        assert out.status_code == 403
        assert b"NO_ACTIVE_TIER" in out.body

    async def test_legacy_key_without_tier_field_is_still_served(self) -> None:
        """Compatibility: pre-tier keys never had tier_id in their payload.
        They must keep working exactly as before this change."""
        out, response = await _validate(_validate_result())

        assert getattr(out, "status_code", 200) == 200
        assert response.headers["X-Tier-ID"] == ""

    async def test_assigned_key_is_unchanged(self) -> None:
        tier = str(uuid4())
        out, response = await _validate(_validate_result(tier_id=tier), _tier_cache("ACTIVE"))

        assert getattr(out, "status_code", 200) == 200
        assert response.headers["X-Tier-ID"] == tier


# ── Contract: authorization map + OpenAPI ───────────────────────────────────


_PERMISSIONS_JSON = pathlib.Path(__file__).parent.parent / "api_permissions.json"


class TestUnassignContract:
    def test_gateway_permission_matches_assign(self) -> None:
        """An endpoint absent from api_permissions.json is PUBLIC at the
        gateway (get_required_permission → None), so the DELETE must be
        listed, with the exact permission the assign PATCH uses."""
        mapping = {
            m["endpoint"]: int(m["permissionRequired"])
            for m in json.loads(_PERMISSIONS_JSON.read_text())["apiMappings"]
        }
        checker = PermissionChecker()
        checker._api_permission_map = mapping

        delete_perm = checker.get_required_permission("DELETE", "/api/v1/auth/tenants/42/tier")
        patch_perm = checker.get_required_permission("PATCH", "/api/v1/auth/tenants/42/tier")

        assert delete_perm is not None
        assert delete_perm == patch_perm

    def test_openapi_documents_delete_and_keeps_patch(self) -> None:
        from app.routes.tenants import router

        app = FastAPI()
        app.include_router(router)
        paths = app.openapi()["paths"]
        tier_path = next(p for p in paths if p.endswith("/{tenant_id}/tier"))
        ops = paths[tier_path]

        assert "patch" in ops, "existing assign endpoint must remain"
        delete = ops["delete"]
        assert "requestBody" not in delete
        assert {"200", "403", "404"} <= set(delete["responses"])
        data_ref = app.openapi()["components"]["schemas"]["TenantTierUnassignData"]["properties"]
        assert {"tenant_id", "tier_id", "previous_tier_id", "updated_at", "updated_by"} <= set(data_ref)


# ── Review fix: never-tiered tenants' legacy keys stay untouched ────────────


def _redis_with_hashes(hashes: dict) -> MagicMock:
    """A redis mock whose eval honours _HSET_IF_FIELD_EXISTS's contract
    against an in-memory {redis_key: {field: value}} map, so the whole
    TenantService → APIKeyService → CacheService chain can run for real.
    The script's own semantics on a real Redis are pinned separately by
    TestHsetIfFieldExistsLiveRedis."""
    redis = MagicMock()

    async def _eval(_script, _numkeys, key, field, value):
        h = hashes.get(key)
        if h is None or field not in h:
            return 0
        h[field] = value
        return 1

    redis.eval = AsyncMock(side_effect=_eval)
    redis.hset = AsyncMock()
    return redis


def _chain(tenant: Tenant, keys: list[APIKey], hashes: dict):
    """TenantService wired to a REAL APIKeyService and CacheService — only
    the DB repos and the Redis client are doubles."""
    from app.services.cache_service import CacheService

    api_repo = AsyncMock()
    api_repo.list_active_keys_for_tenant = AsyncMock(return_value=keys)
    redis = _redis_with_hashes(hashes)
    api_keys = APIKeyService(api_repo, CacheService(redis))
    svc = _svc(tenant=tenant)
    svc._api_keys = api_keys
    return svc, api_repo, redis


class TestNeverTieredTenantLegacyKeys:
    @pytest.mark.asyncio
    async def test_unassign_on_never_tiered_tenant_leaves_legacy_key_servable(self) -> None:
        """The exact review scenario: tenant never had a tier, still holds a
        pre-tier key whose cache has no tier_id. DELETE returns the 200
        no-op — and the key must keep validating afterwards."""
        from app.services.cache_service import REDIS_API_KEY_PREFIX

        legacy = _key(cached_data={"api_key": "a" * 32, "tenant_id": "5"})
        redis_key = f"{REDIS_API_KEY_PREFIX}{legacy.api_key}"
        legacy_hash = {"id": "1", "tenant_id": "5", "permissions": "[1, 2, 3]"}
        hashes = {redis_key: legacy_hash}
        svc, api_repo, redis = _chain(_tenant(tier_id=None, tenant_id=5), [legacy], hashes)

        _, previous = await svc.unassign_tenant_tier(_admin_user(), 5)

        assert previous is None
        assert "tier_id" not in hashes[redis_key], "legacy Redis hash must not gain the marker"
        redis.hset.assert_not_awaited()
        api_repo.patch_cached_data_field_for_tenant.assert_awaited_once_with(
            5, "tier_id", UNASSIGNED_TIER_ID, only_if_present=True
        )
        # And the key's actual payload still validates.
        out, response = await _validate(_validate_result(tenant_id="5"))
        assert getattr(out, "status_code", 200) == 200
        assert response.headers["X-Tier-ID"] == ""

    @pytest.mark.asyncio
    async def test_first_unassign_blocks_tiered_keys_but_spares_legacy_ones(self) -> None:
        """Same tenant holding both kinds (tier_id set by migration, not
        PATCH): only the key issued under the tier gets the marker."""
        from app.services.cache_service import REDIS_API_KEY_PREFIX

        premium = str(uuid4())
        tiered = _key(cached_data={"api_key": "b" * 32, "tier_id": premium})
        tiered.api_key = "b" * 32
        legacy = _key(cached_data={"api_key": "c" * 32})
        legacy.api_key = "c" * 32
        hashes = {
            f"{REDIS_API_KEY_PREFIX}{'b' * 32}": {"tier_id": premium},
            f"{REDIS_API_KEY_PREFIX}{'c' * 32}": {"id": "2"},
        }
        svc, _, _ = _chain(_tenant(tier_id=uuid4()), [tiered, legacy], hashes)

        await svc.unassign_tenant_tier(_admin_user(), 1)

        assert hashes[f"{REDIS_API_KEY_PREFIX}{'b' * 32}"]["tier_id"] == UNASSIGNED_TIER_ID
        assert "tier_id" not in hashes[f"{REDIS_API_KEY_PREFIX}{'c' * 32}"]

    @pytest.mark.asyncio
    async def test_retry_still_repairs_a_key_left_on_the_old_tier(self) -> None:
        """The reason the no-op path writes at all: DB already NULL, but a
        key still carries the old tier from a failed earlier fan-out."""
        from app.services.cache_service import REDIS_API_KEY_PREFIX

        stale = _key(cached_data={"api_key": "d" * 32, "tier_id": str(uuid4())})
        stale.api_key = "d" * 32
        hashes = {f"{REDIS_API_KEY_PREFIX}{'d' * 32}": {"tier_id": str(uuid4())}}
        svc, _, _ = _chain(_tenant(tier_id=None), [stale], hashes)

        _, previous = await svc.unassign_tenant_tier(_admin_user(), 1)

        assert previous is None
        assert hashes[f"{REDIS_API_KEY_PREFIX}{'d' * 32}"]["tier_id"] == UNASSIGNED_TIER_ID


class TestPatchApiKeyCacheFieldIfPresent:
    @pytest.mark.asyncio
    async def test_runs_the_atomic_script_and_reports_the_write(self) -> None:
        from app.services.cache_service import (
            REDIS_API_KEY_PREFIX, CacheService, _HSET_IF_FIELD_EXISTS,
        )

        redis = MagicMock()
        redis.eval = AsyncMock(return_value=1)
        assert await CacheService(redis).patch_api_key_cache_field_if_present("k", "tier_id", "") is True
        redis.eval.assert_awaited_once_with(
            _HSET_IF_FIELD_EXISTS, 1, f"{REDIS_API_KEY_PREFIX}k", "tier_id", ""
        )

    @pytest.mark.asyncio
    async def test_field_absent_is_reported_as_not_written(self) -> None:
        from app.services.cache_service import CacheService

        redis = MagicMock()
        redis.eval = AsyncMock(return_value=0)
        assert await CacheService(redis).patch_api_key_cache_field_if_present("k", "tier_id", "") is False

    @pytest.mark.asyncio
    async def test_non_hash_key_is_deleted_like_the_unconditional_writer(self) -> None:
        from redis.exceptions import ResponseError

        from app.services.cache_service import REDIS_API_KEY_PREFIX, CacheService

        redis = MagicMock()
        redis.eval = AsyncMock(side_effect=ResponseError("WRONGTYPE"))
        redis.delete = AsyncMock()
        assert await CacheService(redis).patch_api_key_cache_field_if_present("k", "tier_id", "") is False
        redis.delete.assert_awaited_once_with(f"{REDIS_API_KEY_PREFIX}k")


class TestPatchCachedDataFieldOnlyIfPresent:
    @staticmethod
    async def _compiled_sql(**kwargs) -> str:
        from sqlalchemy.dialects import postgresql

        from app.repositories.api_key_repository import APIKeyRepository

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
        await APIKeyRepository(db).patch_cached_data_field_for_tenant(1, "tier_id", "", **kwargs)
        stmt = db.execute.await_args.args[0]
        return str(stmt.compile(dialect=postgresql.dialect()))

    @pytest.mark.asyncio
    async def test_only_if_present_adds_the_jsonb_key_exists_filter(self) -> None:
        assert "api_key.cached_data ? " in await self._compiled_sql(only_if_present=True)

    @pytest.mark.asyncio
    async def test_default_is_unchanged(self) -> None:
        assert " ? " not in await self._compiled_sql()


class TestHsetIfFieldExistsLiveRedis:
    """Runs the real Lua script against the dev Redis (skipped when it
    isn't reachable) — the in-memory double above only mirrors it."""

    @pytest_asyncio.fixture()
    async def redis(self):
        import os

        import redis.asyncio as aioredis

        from app.core.config import settings

        password = settings.redis_password.get_secret_value() if settings.redis_password else None
        client = aioredis.Redis(
            host=os.environ.get("TEST_REDIS_HOST", "localhost"),
            port=settings.redis_port, password=password, decode_responses=True,
        )
        try:
            await client.ping()
        except Exception as exc:
            await client.aclose()
            pytest.skip(f"dev Redis unreachable: {exc}")
        prefix = f"test-tier-unassign-{uuid4().hex}"
        yield client, prefix
        for k in await client.keys(f"auth:apikey:{prefix}*"):
            await client.delete(k)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_semantics_on_real_redis(self, redis) -> None:
        from app.services.cache_service import REDIS_API_KEY_PREFIX, CacheService

        client, prefix = redis
        cache = CacheService(client)
        legacy, tiered, missing = f"{prefix}-legacy", f"{prefix}-tiered", f"{prefix}-missing"
        await client.hset(f"{REDIS_API_KEY_PREFIX}{legacy}", mapping={"id": "1"})
        await client.hset(f"{REDIS_API_KEY_PREFIX}{tiered}", mapping={"id": "2", "tier_id": "old"})
        await client.expire(f"{REDIS_API_KEY_PREFIX}{tiered}", 600)

        assert await cache.patch_api_key_cache_field_if_present(legacy, "tier_id", "") is False
        assert await cache.patch_api_key_cache_field_if_present(tiered, "tier_id", "") is True
        assert await cache.patch_api_key_cache_field_if_present(missing, "tier_id", "") is False

        assert await client.hgetall(f"{REDIS_API_KEY_PREFIX}{legacy}") == {"id": "1"}
        assert await client.hget(f"{REDIS_API_KEY_PREFIX}{tiered}", "tier_id") == ""
        assert 0 < await client.ttl(f"{REDIS_API_KEY_PREFIX}{tiered}") <= 600, "TTL must survive"
        assert await client.exists(f"{REDIS_API_KEY_PREFIX}{missing}") == 0, "no partial hash created"
