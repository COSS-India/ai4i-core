"""validate_api_key's Redis-miss DB fallback and the is_already_invalid tombstone.

Covers the two TODOs on validate_api_key: a cache hit carrying is_already_invalid
short-circuits without touching the DB; a cache miss falls back to Postgres and
rehydrates Redis verbatim from api_key.cached_data — the sole source of truth for
this path, since it can carry a PPU tier_id that's only safe to compute at
create_api_key time, never on this hot path. A token that's absent, no longer
eligible, or has no cached_data snapshot yet is rejected with InvalidAPIKeyError
(the absent/ineligible cases are also negatively cached so repeats stay Redis-only).
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.exceptions import InvalidAPIKeyError
from app.models.api_key import APIKey
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.api_key_service import APIKeyService

_TOKEN = "a" * 32


@asynccontextmanager
async def _patched_db_fallback(repo: AsyncMock):
    """_resolve_from_db_or_tombstone opens its own session and builds its own
    APIKeyRepository — independent of any repo passed to APIKeyService's
    constructor. Patch both at their import site in api_key_service so the
    ad hoc session/repo resolve to a controllable mock instead of a real DB."""

    @asynccontextmanager
    async def _fake_session():
        yield MagicMock(name="fake-session")

    with (
        patch("app.services.api_key_service.APIKeyRepository", return_value=repo),
        patch("app.services.api_key_service._open_db_session", _fake_session),
    ):
        yield


def _api_key(*, cached_data: dict | None = None, expires_at: object = ...) -> APIKey:
    return APIKey(
        id=1,
        user_id=uuid4(),
        key_name="test-key",
        api_key=_TOKEN,
        permissions=[12],
        expires_at=(datetime.now(timezone.utc) + timedelta(days=30)) if expires_at is ... else expires_at,
        is_active=True,
        cached_data=cached_data,
    )


def _user(*, is_active: bool = True, is_delete: bool = False, is_tenant_active: bool = True) -> User:
    return User(
        id=uuid4(),
        email="test-user@example.invalid",
        username=uuid4().hex[:12],
        tenant_id=1,
        is_active=is_active,
        is_delete=is_delete,
        is_tenant_active=is_tenant_active,
    )


def _tenant(*, status: TenantStatus = TenantStatus.ACTIVE) -> Tenant:
    return Tenant(
        id=1,
        name="Acme",
        organisation="Acme",
        email="test-contact@example.invalid",
        status=status,
    )


def _db_key(*, key: APIKey | None = None, user: object = ..., tenant: object = ...) -> APIKey:
    """Wire key.user and key.user.tenant the way get_by_api_key_if_valid's
    joinedload delivers them."""
    key = key if key is not None else _api_key()
    user = _user() if user is ... else user
    if user is not None:
        user.tenant = _tenant() if tenant is ... else tenant
    key.user = user
    return key


def _service(*, repo: object = ...) -> tuple:
    repo = AsyncMock() if repo is ... else repo
    cache = AsyncMock()
    return APIKeyService(repo, cache), repo, cache


class _AnyInt:
    """Matches any int — used where a real TTL value isn't the point of the assertion."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, int)


class TestValidateAPIKeyHitPath:
    @pytest.mark.asyncio
    async def test_malformed_token_returns_invalid_without_touching_cache(self) -> None:
        svc, _repo, cache = _service()
        result = await svc.validate_api_key("not-a-hex-key")
        assert result == {"valid": False, "message": "Invalid API key format."}
        cache.get_api_key_cache.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_hit_returns_cached_fields_plus_valid_and_permission_ids(self) -> None:
        svc, _repo, cache = _service()
        cache.get_api_key_cache = AsyncMock(
            return_value={"api_key": _TOKEN, "permissions": [12, 15], "tenant_id": "1"}
        )
        result = await svc.validate_api_key(_TOKEN)
        assert result["valid"] is True
        assert result["permission_ids"] == [12, 15]

    @pytest.mark.asyncio
    async def test_tombstoned_hit_raises_without_db_or_cache_write(self) -> None:
        svc, _repo, cache = _service()
        cache.get_api_key_cache = AsyncMock(return_value={"is_already_invalid": "1"})
        with patch("app.services.api_key_service.APIKeyRepository") as repo_cls:
            with pytest.raises(InvalidAPIKeyError):
                await svc.validate_api_key(_TOKEN)
            repo_cls.assert_not_called()
        cache.set_api_key_cache.assert_not_awaited()


class TestValidateAPIKeyCacheMissDBFallback:
    """validate_api_key's DB fallback opens its own session/repo (see
    _resolve_from_db_or_tombstone) regardless of what repo — if any — was
    passed into APIKeyService's constructor, so every service instance here
    is built with repo=None to prove that. cached_data is required for a
    successful rehydrate; tests that aren't specifically exercising that gate
    seed it via _api_key(cached_data=...)."""

    @pytest.mark.asyncio
    async def test_miss_with_no_db_row_tombstones_then_raises(self) -> None:
        svc, _repo, cache = _service(repo=None)
        cache.get_api_key_cache = AsyncMock(return_value=None)
        mock_repo = AsyncMock()
        mock_repo.get_by_api_key_if_valid = AsyncMock(return_value=None)
        async with _patched_db_fallback(mock_repo):
            with pytest.raises(InvalidAPIKeyError):
                await svc.validate_api_key(_TOKEN)
        assert cache.set_api_key_cache.await_args.args == (
            _TOKEN,
            settings.invalid_api_key_cache_ttl_seconds,
            {"is_already_invalid": "1"},
        )
        mock_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inactive_user_tombstones_then_raises(self) -> None:
        svc, _repo, cache = _service(repo=None)
        cache.get_api_key_cache = AsyncMock(return_value=None)
        mock_repo = AsyncMock()
        mock_repo.get_by_api_key_if_valid = AsyncMock(
            return_value=_db_key(user=_user(is_active=False))
        )
        async with _patched_db_fallback(mock_repo):
            with pytest.raises(InvalidAPIKeyError):
                await svc.validate_api_key(_TOKEN)
        assert cache.set_api_key_cache.await_args.args[2] == {"is_already_invalid": "1"}

    @pytest.mark.asyncio
    async def test_suspended_tenant_tombstones_then_raises(self) -> None:
        svc, _repo, cache = _service(repo=None)
        cache.get_api_key_cache = AsyncMock(return_value=None)
        mock_repo = AsyncMock()
        mock_repo.get_by_api_key_if_valid = AsyncMock(
            return_value=_db_key(tenant=_tenant(status=TenantStatus.SUSPENDED))
        )
        async with _patched_db_fallback(mock_repo):
            with pytest.raises(InvalidAPIKeyError):
                await svc.validate_api_key(_TOKEN)
        assert cache.set_api_key_cache.await_args.args[2] == {"is_already_invalid": "1"}

    @pytest.mark.asyncio
    async def test_user_without_tenant_is_eligible_and_has_no_tenant_id(self) -> None:
        """A tenant-less user must not crash — user_may_use_api_keys(user, None) is True."""
        svc, _repo, cache = _service(repo=None)
        cache.get_api_key_cache = AsyncMock(return_value=None)
        user = _user()
        user.tenant_id = None
        snapshot = {"api_key": _TOKEN, "permissions": [12], "user_id": "u", "tenant_id": None}
        mock_repo = AsyncMock()
        mock_repo.get_by_api_key_if_valid = AsyncMock(
            return_value=_db_key(key=_api_key(cached_data=snapshot), user=user, tenant=None)
        )
        async with _patched_db_fallback(mock_repo):
            result = await svc.validate_api_key(_TOKEN)
        assert result["valid"] is True
        assert cache.set_api_key_cache.await_args.args[2]["tenant_id"] is None

    @pytest.mark.asyncio
    async def test_missing_owner_row_tombstones_then_raises(self) -> None:
        svc, _repo, cache = _service(repo=None)
        cache.get_api_key_cache = AsyncMock(return_value=None)
        mock_repo = AsyncMock()
        mock_repo.get_by_api_key_if_valid = AsyncMock(return_value=_db_key(user=None))
        async with _patched_db_fallback(mock_repo):
            with pytest.raises(InvalidAPIKeyError):
                await svc.validate_api_key(_TOKEN)
        assert cache.set_api_key_cache.await_args.args[2] == {"is_already_invalid": "1"}

    @pytest.mark.asyncio
    async def test_eligible_with_cached_data_rehydrates_verbatim_and_skips_persist(self) -> None:
        svc, _repo, cache = _service(repo=None)
        cache.get_api_key_cache = AsyncMock(return_value=None)
        snapshot = {"api_key": _TOKEN, "permissions": [12], "user_id": "u", "tenant_id": "1", "tier_id": "t1"}
        mock_repo = AsyncMock()
        mock_repo.get_by_api_key_if_valid = AsyncMock(
            return_value=_db_key(key=_api_key(cached_data=snapshot))
        )
        async with _patched_db_fallback(mock_repo):
            result = await svc.validate_api_key(_TOKEN)
        assert result["valid"] is True
        assert result["tier_id"] == "t1"
        cache.set_api_key_cache.assert_awaited_once_with(_TOKEN, _AnyInt(), snapshot)
        mock_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_eligible_without_cached_data_raises_without_tombstoning(self) -> None:
        """cached_data is the sole source of truth for this path — an eligible key
        that hasn't been through create_api_key/an update/the backfill yet still
        can't be served here (no live PPU tier lookup on this hot path), but this
        case isn't negatively cached: it's a data-completeness gap, not a
        revocation, and should self-resolve once something populates cached_data."""
        svc, _repo, cache = _service(repo=None)
        cache.get_api_key_cache = AsyncMock(return_value=None)
        db_key = _db_key(key=_api_key(cached_data=None))
        mock_repo = AsyncMock()
        mock_repo.get_by_api_key_if_valid = AsyncMock(return_value=db_key)
        async with _patched_db_fallback(mock_repo):
            with pytest.raises(InvalidAPIKeyError):
                await svc.validate_api_key(_TOKEN)
        cache.set_api_key_cache.assert_not_awaited()
        mock_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_key_at_ttl_boundary_returns_payload_without_writing_cache(self) -> None:
        """Race window: eligible at the DB-filter instant but expires_at has since
        passed, so ttl <= 0. The rehydrate returns the payload for this one request
        without writing Redis (mirrors the pre-existing _refresh_redis_cache guard)."""
        svc, _repo, cache = _service(repo=None)
        cache.get_api_key_cache = AsyncMock(return_value=None)
        snapshot = {"api_key": _TOKEN, "permissions": [12], "user_id": "u", "tenant_id": "1"}
        expired = _api_key(
            cached_data=snapshot, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        mock_repo = AsyncMock()
        mock_repo.get_by_api_key_if_valid = AsyncMock(return_value=_db_key(key=expired))
        async with _patched_db_fallback(mock_repo):
            result = await svc.validate_api_key(_TOKEN)
        assert result["valid"] is True
        cache.set_api_key_cache.assert_not_awaited()
        mock_repo.update.assert_not_awaited()


class TestRefreshAndCreatePersistCachedData:
    @pytest.mark.asyncio
    async def test_refresh_redis_cache_persists_snapshot_minus_billing_flags(self) -> None:
        svc, repo, cache = _service()
        cache.get_api_key_cache = AsyncMock(
            return_value={"budget-exhausted": "1", "quota-nmt": "1", "tier_id": "old"}
        )
        key = _api_key()
        await svc._refresh_redis_cache(key, "1")
        written = cache.set_api_key_cache.await_args.args[2]
        assert written["budget-exhausted"] == "1"
        assert written["quota-nmt"] == "1"
        persisted = repo.update.await_args.args[1]["cached_data"]
        assert "budget-exhausted" not in persisted
        assert "quota-nmt" not in persisted
        assert persisted["tenant_id"] == "1"
        repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refresh_redis_cache_zero_ttl_skips_persist(self) -> None:
        svc, repo, cache = _service()
        expired = _api_key(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        await svc._refresh_redis_cache(expired, "1")
        cache.set_api_key_cache.assert_not_awaited()
        repo.update.assert_not_awaited()
