"""Unit tests for organisation-name uniqueness enforcement on tenant create and update."""

from unittest.mock import AsyncMock, MagicMock
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
    tenant_repo.create = AsyncMock()
    tenant_repo.update = AsyncMock()
    tenant_repo.save_and_refresh = AsyncMock()
    tenant_repo.commit = AsyncMock()
    tenant_repo.refresh = AsyncMock()
    # update_tenant calls enforce_scope first; act as a system admin so these
    # tests isolate the organisation-uniqueness logic (scope is covered in
    # test_tenant_update_scope.py).
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=["ADMIN"])
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=MagicMock(),
        role_service=role_service,
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _tenant(id: int, organisation: str = "Acme Corp") -> Tenant:
    return Tenant(
        id=id,
        name="Contact",
        organisation=organisation,
        email=f"contact@tenant{id}.com",
        status=TenantStatus.ACTIVE,
    )


class TestCreateTenantOrganisationUniqueness:
    @pytest.mark.asyncio
    async def test_duplicate_org_raises_409(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_organisation = AsyncMock(return_value=_tenant(99))

        body = MagicMock()
        body.organisation = "Acme Corp"
        body.email = "new@other.com"
        body.plan_id = None

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant(body, MagicMock(), MagicMock())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_TENANT_ORGANISATION"

    @pytest.mark.asyncio
    async def test_duplicate_org_case_variant_raises_409(self) -> None:
        """Case-insensitive: 'acme corp' must conflict with 'ACME CORP'."""
        svc = _make_service()
        # The repo's case-insensitive lookup returns a match; the service trusts it.
        svc._tenants.get_by_organisation = AsyncMock(return_value=_tenant(99, "ACME CORP"))

        body = MagicMock()
        body.organisation = "acme corp"
        body.email = "new@other.com"
        body.plan_id = None

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant(body, MagicMock(), MagicMock())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_TENANT_ORGANISATION"


class TestUpdateTenantOrganisationUniqueness:
    @pytest.mark.asyncio
    async def test_update_to_another_tenants_org_raises_409(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "Old Name"))
        svc._tenants.get_by_organisation = AsyncMock(return_value=_tenant(2, "Acme Corp"))

        body = MagicMock()
        body.model_dump.return_value = {"organisation": "Acme Corp"}

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_TENANT_ORGANISATION"

    @pytest.mark.asyncio
    async def test_update_keeping_own_org_is_allowed(self) -> None:
        """Self-exclusion: patching other fields while retaining the same org must not 409."""
        svc = _make_service()
        own = _tenant(1, "Acme Corp")
        svc._tenants.get_by_id = AsyncMock(return_value=own)
        # Repo returns the same tenant — existing.id == tenant_id → no conflict.
        svc._tenants.get_by_organisation = AsyncMock(return_value=own)

        body = MagicMock()
        body.model_dump.return_value = {"organisation": "Acme Corp", "contact_name": "New Name"}

        await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_case_variant_of_another_tenants_org_raises_409(self) -> None:
        """Case-insensitive: 'acme corp' must conflict with 'Acme Corp'."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "Old Name"))
        svc._tenants.get_by_organisation = AsyncMock(return_value=_tenant(2, "Acme Corp"))

        body = MagicMock()
        body.model_dump.return_value = {"organisation": "acme corp"}

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_TENANT_ORGANISATION"
