"""Unit tests for "Change contact" on PATCH /auth/tenants/{id} (AI4IDS-3401).

The contact is switched by ``contact_user_id`` to an existing, set-up
Institution Admin of the same tenant — applied immediately, no email sent.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError as PydanticValidationError

from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.schemas.tenant import TenantUpdate
from app.services.tenant_service import TenantService


def _tenant(email: str = "old@tenant.com", status=TenantStatus.ACTIVE,
            organisation: str = "Acme") -> Tenant:
    return Tenant(id=1, name="Acme", organisation=organisation, email=email, status=status)


def _user(email: str = "new.admin@tenant.com", tenant_id=1, is_active: bool = True) -> User:
    return User(id=uuid4(), email=email, username=uuid4().hex[:12], tenant_id=tenant_id,
                is_active=is_active)


def _body(**fields) -> MagicMock:
    body = MagicMock()
    body.model_dump.return_value = fields
    return body


def _service(tenant: Tenant, candidate, roles=("TENANT ADMIN",), has_credentials=True) -> TenantService:
    tenant_repo = MagicMock()
    for name in ("update", "commit", "refresh"):
        setattr(tenant_repo, name, AsyncMock())
    tenant_repo.get_by_id = AsyncMock(return_value=tenant)
    tenant_repo.get_by_email = AsyncMock(return_value=None)
    tenant_repo.get_by_organisation = AsyncMock(return_value=None)
    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=candidate)
    # The picked admin is the only holder of their own address (same tenant).
    user_repo.get_by_email = AsyncMock(
        side_effect=lambda e: candidate if candidate is not None and e == candidate.email else None
    )
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=list(roles))
    credentials = MagicMock()
    credentials.get_by_user_id = AsyncMock(return_value=MagicMock() if has_credentials else None)
    svc = TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        credentials_repo=credentials,
        token_service=MagicMock(),
        email_client=MagicMock(),
    )
    svc.enforce_scope = AsyncMock()
    return svc


async def _change(svc: TenantService, user_id, **fields):
    return await svc.update_tenant(
        MagicMock(id=uuid4()), 1, _body(contact_user_id=user_id, **fields),
        background_tasks=MagicMock(),
    )


class TestChangeContact:
    @pytest.mark.asyncio
    async def test_switches_contact_immediately_without_email(self) -> None:
        admin = _user()
        svc = _service(_tenant(), admin)

        with patch("app.services.tenant_service.reissue_setup_token", new=AsyncMock()) as reissue, \
             patch("app.services.tenant_service.enqueue_email") as enqueue:
            _, link_sent = await _change(svc, admin.id, contact_name="Jane Doe")

        staged = svc._tenants.update.await_args.args[1]
        assert staged["email"] == "new.admin@tenant.com"
        assert staged["name"] == "Jane Doe"          # other fields still saved
        assert "contact_user_id" not in staged       # not a tenants column
        assert link_sent is False                    # → email_verification_sent: false
        reissue.assert_not_awaited()
        enqueue.assert_not_called()
        svc._tenants.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_echoed_email_is_replaced_by_picked_admins(self) -> None:
        admin = _user()
        svc = _service(_tenant(), admin)

        await _change(svc, admin.id, email="old@tenant.com")

        assert svc._tenants.update.await_args.args[1]["email"] == "new.admin@tenant.com"



class TestChangeContactRejected:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", ["missing", "other_tenant", "not_admin", "inactive"])
    async def test_not_an_active_institution_admin(self, case) -> None:
        candidate = {
            "missing": None,
            "other_tenant": _user(tenant_id=2),
            "not_admin": _user(),
            "inactive": _user(is_active=False),
        }[case]
        roles = ("USER",) if case == "not_admin" else ("TENANT ADMIN",)
        svc = _service(_tenant(), candidate, roles=roles)

        with pytest.raises(HTTPException) as exc:
            await _change(svc, uuid4() if candidate is None else candidate.id)

        assert exc.value.status_code == 409
        assert exc.value.code == "CONTACT_NOT_INSTITUTION_ADMIN"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_without_finished_setup(self) -> None:
        admin = _user()
        svc = _service(_tenant(), admin, has_credentials=False)

        with pytest.raises(HTTPException) as exc:
            await _change(svc, admin.id)

        assert exc.value.code == "CONTACT_NOT_VERIFIED"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_already_the_contact(self) -> None:
        admin = _user("Old@Tenant.com")  # case-insensitive match
        svc = _service(_tenant("old@tenant.com"), admin)

        with pytest.raises(HTTPException) as exc:
            await _change(svc, admin.id)

        assert exc.value.code == "CONTACT_ALREADY_CURRENT"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("locked", [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED])
    async def test_locked_statuses(self, locked) -> None:
        admin = _user()
        svc = _service(_tenant(status=locked), admin)

        with pytest.raises(HTTPException) as exc:
            await _change(svc, admin.id)

        assert exc.value.status_code == 409
        assert exc.value.code == "TENANT_EMAIL_EDIT_NOT_ALLOWED"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pending_tenant(self) -> None:
        """Activation fires only when the contact sets their password; a picked
        admin who already has one would leave the tenant PENDING for good."""
        admin = _user()
        svc = _service(_tenant(status=TenantStatus.PENDING), admin)

        with patch("app.services.tenant_service.reissue_setup_token", new=AsyncMock()) as reissue:
            with pytest.raises(HTTPException) as exc:
                await _change(svc, admin.id)

        assert exc.value.status_code == 409
        assert exc.value.code == "TENANT_EMAIL_EDIT_NOT_ALLOWED"
        svc._tenants.update.assert_not_awaited()
        reissue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_organisation(self) -> None:
        admin = _user()
        svc = _service(_tenant(organisation="Default Organisation"), admin)

        with pytest.raises(HTTPException) as exc:
            await _change(svc, admin.id)

        assert exc.value.code == "TENANT_EMAIL_EDIT_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_address_used_by_another_tenant(self) -> None:
        admin = _user()
        svc = _service(_tenant(), admin)
        svc._tenants.get_by_email = AsyncMock(
            return_value=Tenant(id=2, name="X", organisation="Other", email=admin.email,
                                status=TenantStatus.ACTIVE)
        )

        with pytest.raises(HTTPException) as exc:
            await _change(svc, admin.id)

        assert exc.value.code == "DUPLICATE_TENANT_EMAIL"
        svc._tenants.update.assert_not_awaited()


class TestContactUserIdSchema:
    def test_accepts_uuid(self) -> None:
        uid = uuid4()
        assert TenantUpdate(contact_user_id=str(uid)).contact_user_id == uid

    def test_rejects_non_uuid(self) -> None:
        with pytest.raises(PydanticValidationError):
            TenantUpdate(contact_user_id="not-a-uuid")


class TestUpdateTenantRouteResponse:
    def test_contact_switch_response_shape(self) -> None:
        """email_verification_sent is false and pending_email is gone."""
        from datetime import datetime, timezone

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.exceptions import register_exception_handlers
        from app.dependencies.auth import get_current_user
        from app.dependencies.services import get_tenant_service
        from app.routes import tenants as tenant_routes

        tenant = _tenant("new.admin@tenant.com")
        tenant.created_at = datetime.now(timezone.utc)
        svc = MagicMock()
        svc.update_tenant = AsyncMock(return_value=(tenant, False))
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(tenant_routes.router)
        app.dependency_overrides[get_current_user] = lambda: MagicMock(id=uuid4(), tenant_id=1)
        app.dependency_overrides[get_tenant_service] = lambda: svc

        response = TestClient(app).patch(
            "/auth/tenants/1", json={"contact_user_id": str(uuid4()), "contact_name": "Jane Doe"}
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["email_verification_sent"] is False
        assert "pending_email" not in data
        assert data["email"] != "new.admin@tenant.com" and "*" in data["email"]  # masked
