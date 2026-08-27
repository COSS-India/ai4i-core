"""Unit tests for Application CRUD (create/get/list/update) — mock-repo pattern,
mirroring tests/test_tenant_organisation_uniqueness.py.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.application import Application, ApplicationStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.repositories.application_repository import _escape_like
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.services.application_service import ApplicationService


def _make_service(roles=("ADMIN",)) -> ApplicationService:
    application_repo = MagicMock()
    application_repo.get_by_id = AsyncMock()
    application_repo.get_by_name = AsyncMock(return_value=None)
    application_repo.list_for_tenant = AsyncMock(return_value=([], 0))
    application_repo.list_all_for_tenant_for_update = AsyncMock(return_value=[])
    application_repo.sum_allocated_percentage = AsyncMock(return_value=Decimal("0"))
    application_repo.create = AsyncMock()
    application_repo.update = AsyncMock()
    application_repo.commit = AsyncMock()
    application_repo.refresh = AsyncMock()

    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock(
        return_value=_tenant(101, allocated_budget=Decimal("100000.00"))
    )

    role_repo = MagicMock()
    role_repo.get_user_roles = AsyncMock(return_value=list(roles))

    return ApplicationService(
        application_repo=application_repo,
        tenant_repo=tenant_repo,
        role_repo=role_repo,
        db=MagicMock(),
    )


def _tenant(id: int, allocated_budget=None) -> Tenant:
    return Tenant(
        id=id,
        name="Contact",
        organisation="Acme Corp",
        email="contact@acme.com",
        status=TenantStatus.ACTIVE,
        allocated_budget=allocated_budget,
    )


def _application(id: int, tenant_id: int = 101, name: str = "Marketing Bot", **kw) -> Application:
    return Application(
        id=id,
        tenant_id=tenant_id,
        name=name,
        status=ApplicationStatus.ACTIVE,
        **kw,
    )


def _user(tenant_id=None) -> User:
    return User(id=uuid4(), email="a@b.com", username="u", tenant_id=tenant_id)


class TestCreateApplication:
    @pytest.mark.asyncio
    async def test_create_derives_budget_from_percentage(self) -> None:
        svc = _make_service()
        body = ApplicationCreate(name="Marketing Bot", domain="marketing", allocated_percentage=Decimal("30.0"))

        app = await svc.create_application(101, body, _user())

        assert app.allocated_percentage == Decimal("30.0")
        assert app.allocated_budget == Decimal("30000.00")
        svc._applications.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_persists_description(self) -> None:
        svc = _make_service()
        body = ApplicationCreate(name="Marketing Bot", description="Runs marketing campaigns")

        app = await svc.create_application(101, body, _user())

        assert app.description == "Runs marketing campaigns"

    @pytest.mark.asyncio
    async def test_create_blank_description_becomes_none(self) -> None:
        body = ApplicationCreate(name="App", description="   ")
        assert body.description is None

    @pytest.mark.asyncio
    async def test_create_without_percentage_leaves_budget_null(self) -> None:
        svc = _make_service()
        body = ApplicationCreate(name="No Budget App")

        app = await svc.create_application(101, body, _user())

        assert app.allocated_percentage is None
        assert app.allocated_budget is None

    @pytest.mark.asyncio
    async def test_duplicate_name_raises_409(self) -> None:
        svc = _make_service()
        svc._applications.get_by_name = AsyncMock(return_value=_application(5, name="Marketing Bot"))
        body = ApplicationCreate(name="Marketing Bot")

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_application(101, body, _user())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "APPLICATION_NAME_ALREADY_EXISTS"

    @pytest.mark.asyncio
    async def test_allocation_total_exceeded_raises_422(self) -> None:
        svc = _make_service()
        svc._applications.sum_allocated_percentage = AsyncMock(return_value=Decimal("80"))
        body = ApplicationCreate(name="App B", allocated_percentage=Decimal("30.0"))

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_application(101, body, _user())

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "ALLOCATION_TOTAL_EXCEEDED"

    @pytest.mark.asyncio
    async def test_allocation_total_at_exactly_100_is_allowed(self) -> None:
        svc = _make_service()
        svc._applications.sum_allocated_percentage = AsyncMock(return_value=Decimal("70"))
        body = ApplicationCreate(name="App B", allocated_percentage=Decimal("30.0"))

        app = await svc.create_application(101, body, _user())

        assert app.allocated_percentage == Decimal("30.0")

    @pytest.mark.asyncio
    async def test_zero_percent_allocation_is_valid(self) -> None:
        svc = _make_service()
        svc._applications.sum_allocated_percentage = AsyncMock(return_value=Decimal("100"))
        body = ApplicationCreate(name="App C", allocated_percentage=Decimal("0"))

        app = await svc.create_application(101, body, _user())

        assert app.allocated_percentage == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_tenant_not_found_raises_404(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=None)
        body = ApplicationCreate(name="App")

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_application(999, body, _user())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_tenant_admin_cross_tenant_raises_404(self) -> None:
        svc = _make_service(roles=("TENANT ADMIN",))
        body = ApplicationCreate(name="App")
        caller = _user(tenant_id=55)

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_application(101, body, caller)

        assert exc_info.value.status_code == 404
        svc._applications.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tenant_admin_own_tenant_is_allowed(self) -> None:
        svc = _make_service(roles=("TENANT ADMIN",))
        body = ApplicationCreate(name="App")
        caller = _user(tenant_id=101)

        await svc.create_application(101, body, caller)

        svc._applications.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_moderator_is_rejected_even_for_own_tenant(self) -> None:
        svc = _make_service(roles=("MODERATOR",))
        body = ApplicationCreate(name="App")
        caller = _user(tenant_id=101)

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_application(101, body, caller)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
        svc._applications.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_plain_user_is_rejected_even_for_own_tenant(self) -> None:
        svc = _make_service(roles=("USER",))
        body = ApplicationCreate(name="App")
        caller = _user(tenant_id=101)

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_application(101, body, caller)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
        svc._applications.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_can_create_for_any_tenant(self) -> None:
        svc = _make_service(roles=("ADMIN",))
        body = ApplicationCreate(name="App")
        caller = _user(tenant_id=None)

        await svc.create_application(101, body, caller)

        svc._applications.create.assert_awaited_once()


class TestGetApplication:
    @pytest.mark.asyncio
    async def test_not_found_raises_404(self) -> None:
        svc = _make_service()
        svc._applications.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await svc.get_application(101, 12, _user())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_application_in_other_tenant_raises_404(self) -> None:
        """Same 404 whether the id doesn't exist or belongs to another tenant — no enumeration."""
        svc = _make_service()
        svc._applications.get_by_id = AsyncMock(return_value=_application(12, tenant_id=202))

        with pytest.raises(HTTPException) as exc_info:
            await svc.get_application(101, 12, _user())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_found_returns_application(self) -> None:
        svc = _make_service()
        svc._applications.get_by_id = AsyncMock(return_value=_application(12))

        app = await svc.get_application(101, 12, _user())

        assert app.id == 12


class TestUpdateApplication:
    @pytest.mark.asyncio
    async def test_rename_to_existing_name_raises_409(self) -> None:
        svc = _make_service()
        svc._applications.get_by_id = AsyncMock(return_value=_application(12, name="Old Name"))
        svc._applications.get_by_name = AsyncMock(return_value=_application(99, name="Taken Name"))
        body = ApplicationUpdate(name="Taken Name")

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_application(101, 12, body, _user())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "APPLICATION_NAME_ALREADY_EXISTS"

    @pytest.mark.asyncio
    async def test_rename_keeping_own_name_case_variant_is_allowed(self) -> None:
        svc = _make_service()
        own = _application(12, name="Marketing Bot")
        svc._applications.get_by_id = AsyncMock(return_value=own)
        svc._applications.get_by_name = AsyncMock(return_value=own)
        body = ApplicationUpdate(name="marketing bot", domain="new-domain")

        await svc.update_application(101, 12, body, _user())

        svc._applications.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sending_allocation_field_is_rejected_at_schema_level(self) -> None:
        """extra='forbid' on ApplicationUpdate turns an allocation field into a
        Pydantic validation error (422 at the FastAPI layer) before the service
        ever runs — contract: 'REJECTED, not silently dropped'."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ApplicationUpdate(name="X", allocated_percentage=50.0)

    @pytest.mark.asyncio
    async def test_description_can_be_updated(self) -> None:
        svc = _make_service()
        app = _application(12)
        svc._applications.get_by_id = AsyncMock(return_value=app)
        body = ApplicationUpdate(description="Updated description")

        await svc.update_application(101, 12, body, _user())

        called_data = svc._applications.update.call_args.args[1]
        assert called_data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_status_can_be_set_to_inactive(self) -> None:
        svc = _make_service()
        app = _application(12)
        svc._applications.get_by_id = AsyncMock(return_value=app)
        body = ApplicationUpdate(status=ApplicationStatus.INACTIVE)

        await svc.update_application(101, 12, body, _user())

        svc._applications.update.assert_awaited_once()
        called_data = svc._applications.update.call_args.args[1]
        assert called_data["status"] == ApplicationStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_moderator_is_rejected(self) -> None:
        svc = _make_service(roles=("MODERATOR",))
        svc._applications.get_by_id = AsyncMock(return_value=_application(12))
        body = ApplicationUpdate(name="X")

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_application(101, 12, body, _user(tenant_id=101))

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
        svc._applications.update.assert_not_awaited()


class TestListApplications:
    @pytest.mark.asyncio
    async def test_delegates_search_and_domain_filters(self) -> None:
        svc = _make_service()
        svc._applications.list_for_tenant = AsyncMock(return_value=([_application(12)], 1))

        items, total = await svc.list_applications(
            101, _user(), search="market", domain="marketing", offset=0, limit=100
        )

        assert total == 1
        assert items[0].id == 12
        svc._applications.list_for_tenant.assert_awaited_once_with(
            101, search="market", domain="marketing", offset=0, limit=100
        )

    @pytest.mark.asyncio
    async def test_moderator_is_rejected(self) -> None:
        svc = _make_service(roles=("MODERATOR",))

        with pytest.raises(HTTPException) as exc_info:
            await svc.list_applications(101, _user(tenant_id=101))

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"


class TestSearchWildcardEscaping:
    """Bug scenario: an Application literally named e.g. "50%_off_promo" must
    not have its '%'/'_' treated as SQL LIKE wildcards when a caller searches
    for it — a search for "50%" must match only a literal '50%', not "50"
    followed by anything.
    """

    def test_percent_sign_is_escaped(self) -> None:
        assert _escape_like("50%") == "50\\%"

    def test_underscore_is_escaped(self) -> None:
        assert _escape_like("promo_code") == "promo\\_code"

    def test_literal_backslash_is_escaped_first(self) -> None:
        # Must escape '\' before '%'/'_', or an input like "50\%" would have
        # its backslash left bare, changing what the DB interprets as an
        # escape sequence versus a literal character.
        assert _escape_like("50\\%") == "50\\\\\\%"

    def test_plain_text_is_unchanged(self) -> None:
        assert _escape_like("Marketing Bot") == "Marketing Bot"
