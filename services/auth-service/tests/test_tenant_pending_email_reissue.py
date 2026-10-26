"""Unit tests for PENDING-tenant email change → activation re-issue (AI4IDS-1678).

Covers the logic added in update_tenant: admin lookup, the admin-aware email
collision check, the SETUP-token re-issue, and the commit/email-after-commit
ordering.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _make_service() -> TenantService:
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock()
    tenant_repo.get_by_email = AsyncMock(return_value=None)
    tenant_repo.get_by_organisation = AsyncMock(return_value=None)
    tenant_repo.update = AsyncMock()
    tenant_repo.commit = AsyncMock()
    tenant_repo.refresh = AsyncMock()
    tenant_repo.save_and_refresh = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_by_email = AsyncMock(return_value=None)
    svc = TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=MagicMock(),
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )
    # Isolate the update_tenant logic from authorization.
    svc.enforce_scope = AsyncMock()
    return svc


def _tenant(status: TenantStatus, email: str = "old@tenant.com", id: int = 1) -> Tenant:
    return Tenant(id=id, name="Acme", organisation="Acme", email=email, status=status)


def _user(email: str, tenant_id, uid=None) -> User:
    return User(id=uid or uuid4(), email=email, username=uuid4().hex[:12], tenant_id=tenant_id)


def _body(email: str) -> MagicMock:
    body = MagicMock()
    body.model_dump.return_value = {"email": email}
    return body


def _acting() -> User:
    return User(id=uuid4(), email="test-caller@example.invalid", username=uuid4().hex[:12])


class TestPendingEmailReissue:
    @pytest.mark.asyncio
    async def test_pending_email_change_reissues_activation(self) -> None:
        """Happy path: admin email re-aligned, token re-issued, email enqueued after commit."""
        svc = _make_service()
        tenant = _tenant(TenantStatus.PENDING, "old@tenant.com")
        admin = _user("old@tenant.com", tenant_id=1)
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)
        # admin found by old email; new email free for both tenant and user lookups
        svc._users.get_by_email = AsyncMock(
            side_effect=lambda e: admin if e == "old@tenant.com" else None
        )

        with patch("app.services.tenant_service.reissue_setup_token",
                   new=AsyncMock(return_value="new-token")) as reissue, \
             patch("app.services.tenant_service.enqueue_email") as enqueue:
            await svc.update_tenant(_acting(), 1, _body("new@tenant.com"),
                                    background_tasks=MagicMock())

        assert admin.email == "new@tenant.com"           # admin re-aligned
        reissue.assert_awaited_once()                     # token re-issued
        assert reissue.await_args.args[0] is admin        # for the admin user
        svc._tenants.commit.assert_awaited_once()         # single commit
        enqueue.assert_called_once()                      # email enqueued (after commit)

    @pytest.mark.asyncio
    async def test_admin_not_found_raises_409_and_no_commit(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(TenantStatus.PENDING, "old@tenant.com"))
        svc._users.get_by_email = AsyncMock(return_value=None)  # no admin for old email

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(_acting(), 1, _body("new@tenant.com"),
                                    background_tasks=MagicMock())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "TENANT_ADMIN_NOT_FOUND"
        svc._tenants.commit.assert_not_awaited()          # aborts before any write

    @pytest.mark.asyncio
    async def test_new_email_owned_by_other_user_raises_409(self) -> None:
        """PENDING reissue: new email held by a different user (any tenant) → 409, no commit."""
        svc = _make_service()
        tenant = _tenant(TenantStatus.PENDING, "old@tenant.com")
        admin = _user("old@tenant.com", tenant_id=1)
        other = _user("new@tenant.com", tenant_id=1)  # same tenant, but NOT the admin
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)
        svc._users.get_by_email = AsyncMock(
            side_effect=lambda e: admin if e == "old@tenant.com" else other
        )

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(_acting(), 1, _body("new@tenant.com"),
                                    background_tasks=MagicMock())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "DUPLICATE_EMAIL"
        svc._tenants.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_another_tenant_has_email_raises_409(self) -> None:
        # ACTIVE tenant: no admin-lookup precedence, so the tenant-email
        # uniqueness check is what fires.
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(TenantStatus.ACTIVE, "old@tenant.com"))
        svc._tenants.get_by_email = AsyncMock(return_value=_tenant(TenantStatus.ACTIVE, "new@tenant.com", id=2))

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(_acting(), 1, _body("new@tenant.com"),
                                    background_tasks=MagicMock())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "DUPLICATE_TENANT_EMAIL"
        svc._tenants.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_tenant_same_tenant_user_allowed_no_reissue(self) -> None:
        """Non-PENDING: a same-tenant user sharing the address is allowed; no re-issue."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(TenantStatus.ACTIVE, "old@tenant.com"))
        svc._users.get_by_email = AsyncMock(return_value=_user("new@tenant.com", tenant_id=1))

        with patch("app.services.tenant_service.reissue_setup_token",
                   new=AsyncMock()) as reissue, \
             patch("app.services.tenant_service.enqueue_email") as enqueue:
            await svc.update_tenant(_acting(), 1, _body("new@tenant.com"),
                                    background_tasks=MagicMock())

        svc._tenants.update.assert_awaited_once()
        svc._tenants.commit.assert_awaited_once()
        reissue.assert_not_awaited()   # not PENDING → no activation re-issue
        enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_tenant_cross_tenant_user_raises_409(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(TenantStatus.ACTIVE, "old@tenant.com"))
        svc._users.get_by_email = AsyncMock(return_value=_user("new@tenant.com", tenant_id=99))

        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(_acting(), 1, _body("new@tenant.com"),
                                    background_tasks=MagicMock())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "DUPLICATE_EMAIL"
        svc._tenants.commit.assert_not_awaited()
