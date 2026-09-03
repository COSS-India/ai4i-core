"""Unit tests for Application CRUD (create/get/list/update) — mock-repo pattern,
mirroring tests/test_tenant_organisation_uniqueness.py.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

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
    application_repo.sum_allocated_percentage = AsyncMock(return_value=Decimal("0"))
    application_repo.create = AsyncMock()
    application_repo.update = AsyncMock()
    application_repo.commit = AsyncMock()
    application_repo.refresh = AsyncMock()

    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock(
        return_value=_tenant(101, allocated_budget=Decimal("100000.00"))
    )
    tenant_repo.get_by_id_for_update = AsyncMock(
        return_value=_tenant(101, allocated_budget=Decimal("100000.00"))
    )

    role_repo = MagicMock()
    role_repo.get_user_roles = AsyncMock(return_value=list(roles))

    db = MagicMock()
    db.rollback = AsyncMock()

    return ApplicationService(
        application_repo=application_repo,
        tenant_repo=tenant_repo,
        role_repo=role_repo,
        db=db,
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


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _unique_violation(constraint_name: str) -> IntegrityError:
    """Build an IntegrityError shaped like the real one — verified live
    against the actual DB: SQLAlchemy's IntegrityError.orig is the asyncpg
    dbapi wrapper, whose __cause__ is the real asyncpg.exceptions.UniqueViolationError
    carrying .constraint_name. Faking that exact shape (not just IntegrityError
    generically) so the fix's constraint-name check is exercised for real."""
    cause = MagicMock()
    cause.constraint_name = constraint_name
    orig = MagicMock()
    orig.__cause__ = cause
    return IntegrityError("INSERT ...", {}, orig)


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

    def test_unknown_field_is_rejected_not_silently_dropped(self) -> None:
        """Bug scenario: POST {"name": "App", "allocated_budget": 50000} used
        to have allocated_budget silently ignored (Create has no such field —
        only allocated_percentage on create) and still return 201, letting
        the client believe the amount took effect. Must 422 instead, matching
        ApplicationUpdate's existing "REJECTED, not silently dropped" behavior."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ApplicationCreate(name="App", allocated_budget=50000)

    def test_typo_field_is_rejected_not_silently_dropped(self) -> None:
        """Same bug, more realistic trigger: a client typo like
        'allocatedPercentage' instead of 'allocated_percentage' used to be
        silently ignored — the Application would be created with NO budget
        at all and no error, while the client believes it set one."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ApplicationCreate(name="App", allocatedPercentage=30)

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
    async def test_concurrent_same_name_create_raises_409_not_500(self) -> None:
        """Bug scenario: two concurrent creates both pass get_by_name (neither
        sees the other's uncommitted row); the second's commit() raises the
        real unique-violation, which used to surface as an unhandled 500."""
        svc = _make_service()
        svc._applications.commit = AsyncMock(
            side_effect=_unique_violation("uq_applications_tenant_name_lower")
        )
        body = ApplicationCreate(name="Marketing Bot")

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_application(101, body, _user())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "APPLICATION_NAME_ALREADY_EXISTS"
        svc._db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unrelated_integrity_error_on_create_is_not_masked_as_409(self) -> None:
        """Adversarial case: an IntegrityError on a DIFFERENT constraint must
        NOT be reported as a name conflict — that would hide a real bug."""
        svc = _make_service()
        svc._applications.commit = AsyncMock(
            side_effect=_unique_violation("some_other_constraint")
        )
        body = ApplicationCreate(name="Marketing Bot")

        with pytest.raises(IntegrityError):
            await svc.create_application(101, body, _user())

        svc._db.rollback.assert_awaited_once()

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
    async def test_budget_bearing_create_locks_the_tenant_row(self) -> None:
        """Bug scenario: locking Application rows takes no lock when a tenant
        has zero of them yet, so two concurrent first-creates both read
        sum=0 and both pass the cap check. Locking the tenant row instead
        serializes every concurrent create regardless of existing row count —
        this asserts the fixed code path takes that lock, since a mocked
        unit test can't reproduce the actual DB-level race the reviewer
        measured live."""
        svc = _make_service()
        body = ApplicationCreate(name="App A", allocated_percentage=Decimal("60.0"))

        await svc.create_application(101, body, _user())

        svc._tenants.get_by_id_for_update.assert_awaited_once_with(101)

    @pytest.mark.asyncio
    async def test_create_without_percentage_does_not_lock_tenant_row(self) -> None:
        """No budget means no cap to protect — shouldn't pay for a lock it doesn't need."""
        svc = _make_service()
        body = ApplicationCreate(name="App A")

        await svc.create_application(101, body, _user())

        svc._tenants.get_by_id_for_update.assert_not_awaited()

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
    async def test_concurrent_rename_to_same_name_raises_409_not_500(self) -> None:
        """Same race, rename path: two concurrent renames to the same new
        name both pass get_by_name, second commit() hits the real constraint."""
        svc = _make_service()
        svc._applications.get_by_id = AsyncMock(return_value=_application(12, name="Old Name"))
        svc._applications.commit = AsyncMock(
            side_effect=_unique_violation("uq_applications_tenant_name_lower")
        )
        body = ApplicationUpdate(name="New Shared Name")

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_application(101, 12, body, _user())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "APPLICATION_NAME_ALREADY_EXISTS"
        svc._db.rollback.assert_awaited_once()

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
    async def test_explicit_null_name_is_rejected_at_schema_level(self) -> None:
        """Bug scenario: PATCH {"name": null} used to reach the service, where
        None.strip() raised an unhandled AttributeError -> 500. name backs a
        NOT NULL column, so an explicit null must 422 before the handler runs,
        the same way the allocation-field-on-update case already does."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ApplicationUpdate(name=None)

    @pytest.mark.asyncio
    async def test_explicit_null_status_is_rejected_at_schema_level(self) -> None:
        """Bug scenario: PATCH {"status": null} used to reach the service and
        set app.status = None, failing the NOT NULL column constraint as an
        unhandled IntegrityError -> 500 at commit."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ApplicationUpdate(status=None)

    @pytest.mark.asyncio
    async def test_explicit_null_domain_and_description_are_still_allowed(self) -> None:
        """domain/description back NULLable columns — explicit null is the
        legitimate way to clear them, and must keep working (this is not
        the bug: only NOT NULL fields — name, status — must reject null)."""
        svc = _make_service()
        app = _application(12, domain="old-domain", description="old description")
        svc._applications.get_by_id = AsyncMock(return_value=app)
        body = ApplicationUpdate(domain=None, description=None)

        await svc.update_application(101, 12, body, _user())

        called_data = svc._applications.update.call_args.args[1]
        assert called_data["domain"] is None
        assert called_data["description"] is None

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
    async def test_deactivating_releases_the_applications_allocation(self) -> None:
        """The ACTIVE -> INACTIVE transition clears allocated_budget and
        allocated_percentage in the SAME update — not a separate call, so
        there's no window where the row is INACTIVE but still holding its
        old ceiling. Without this, AllocationService's own exclusion of
        INACTIVE Applications from the sibling sum only frees the room
        until this Application is reactivated with its stale allocation
        still attached, at which point the Tenant would be holding more
        ceilings than its budget again."""
        svc = _make_service()
        app = _application(
            12, allocated_budget=Decimal("40000"), allocated_percentage=Decimal("40")
        )
        svc._applications.get_by_id = AsyncMock(return_value=app)
        body = ApplicationUpdate(status=ApplicationStatus.INACTIVE)

        await svc.update_application(101, 12, body, _user())

        called_data = svc._applications.update.call_args.args[1]
        assert called_data["status"] == ApplicationStatus.INACTIVE
        assert called_data["allocated_budget"] is None
        assert called_data["allocated_percentage"] is None

    @pytest.mark.asyncio
    async def test_reactivating_does_not_touch_allocation_fields(self) -> None:
        """The clearing is one-directional — going back to ACTIVE doesn't
        try to restore or otherwise touch allocation fields at all. A
        reactivated Application comes back with whatever it currently has
        (None, per the deactivation above) — an explicit fresh allocation
        via the Budget Allocation endpoints is required either way."""
        svc = _make_service()
        app = Application(
            id=12, tenant_id=101, name="Marketing Bot", status=ApplicationStatus.INACTIVE,
        )
        svc._applications.get_by_id = AsyncMock(return_value=app)
        body = ApplicationUpdate(status=ApplicationStatus.ACTIVE)

        await svc.update_application(101, 12, body, _user())

        called_data = svc._applications.update.call_args.args[1]
        assert called_data["status"] == ApplicationStatus.ACTIVE
        assert "allocated_budget" not in called_data
        assert "allocated_percentage" not in called_data

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


class TestSuccessEnvelope:
    """Bug scenario: the 4 Application routes returned their payload bare
    (response_model=ApplicationResponse directly), while every other
    /auth/tenants/... route wraps in {"success": true, "data": ...} via a
    SuccessResponse subclass. A client that unwraps .data uniformly across
    tenant-admin screens got `undefined` for Applications specifically.

    A schema-level check can't catch this — the schema was always correct,
    the bug was the ROUTE returning the unwrapped type. Only a real HTTP
    round-trip through the actual route (not calling the service directly)
    proves the wire shape a client actually receives.
    """

    @staticmethod
    def _client():
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.dependencies.auth import get_current_user
        from app.dependencies.services import get_application_service
        from app.routes.application import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        svc = _make_service()
        svc._applications.get_by_id = AsyncMock(
            return_value=_application(12, name="Marketing Bot", domain="marketing", created_at=_now())
        )

        # Real BaseRepository.create/update set attributes on the passed
        # object (create() populates server defaults on flush; update() does
        # setattr per key) — a bare AsyncMock() doesn't, so the object
        # returned to the route wouldn't reflect the write. Match that
        # behavior so the wire-level assertions below check real values.
        async def _fake_create(obj):
            obj.id = obj.id or 99
            obj.status = obj.status or ApplicationStatus.ACTIVE
            obj.created_at = _now()
            return obj

        async def _fake_update(obj, data):
            for k, v in data.items():
                setattr(obj, k, v)
            return obj

        svc._applications.create = AsyncMock(side_effect=_fake_create)
        svc._applications.update = AsyncMock(side_effect=_fake_update)

        app.dependency_overrides[get_current_user] = lambda: _user(tenant_id=101)
        app.dependency_overrides[get_application_service] = lambda: svc
        return TestClient(app), svc

    def test_create_response_is_wrapped_in_success_data_envelope(self) -> None:
        client, _ = self._client()

        resp = client.post(
            "/api/v1/auth/tenants/101/applications", json={"name": "Marketing Bot"}
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["name"] == "Marketing Bot"
        # Bare (unwrapped) would put "name" at the top level instead.
        assert "name" not in body

    def test_get_response_is_wrapped_in_success_data_envelope(self) -> None:
        client, _ = self._client()

        resp = client.get("/api/v1/auth/tenants/101/applications/12")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["id"] == 12

    def test_list_response_wraps_items_and_total_under_data(self) -> None:
        client, svc = self._client()
        svc._applications.list_for_tenant = AsyncMock(
            return_value=([_application(12, name="Marketing Bot", created_at=_now())], 1)
        )

        resp = client.get("/api/v1/auth/tenants/101/applications")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["total"] == 1
        assert body["data"]["items"][0]["name"] == "Marketing Bot"
        # Bare (unwrapped) would put "items"/"total" at the top level instead.
        assert "items" not in body
        assert "total" not in body

    def test_update_response_is_wrapped_in_success_data_envelope(self) -> None:
        client, _ = self._client()

        resp = client.patch(
            "/api/v1/auth/tenants/101/applications/12", json={"domain": "new-domain"}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["domain"] == "new-domain"


class TestBudgetDerivedFromLockedTenantNotStaleRead:
    """Bug scenario (vipuldeveloper review, PR #1491): tenant is loaded
    unlocked in _load_tenant_or_404, then again — locked — in
    _assert_allocation_within_cap. SQLAlchemy's identity map hands back the
    same Python object for the second read unless the query forces a
    refresh, so if a concurrent PATCH .../tenants/{id}/budget commits
    between the two reads, the lock is genuinely acquired but the derived
    allocated_budget still comes from the pre-revision figure. Verified live
    against Postgres by the reviewer: unlocked read saw allocated_budget=None,
    the FOR UPDATE read returned "the same object" with the same stale None,
    while the DB's actual value was 777.00.

    This mock-repo test reproduces the same shape by giving the two repo
    calls genuinely different return values (mocks don't share an identity
    map the way a real AsyncSession does, so this doesn't exercise SQLAlchemy
    itself — it pins the service-layer contract: create_application MUST
    derive allocated_budget from whatever get_by_id_for_update returns, not
    from the earlier get_by_id call). The repository-level fix
    (execution_options(populate_existing=True) in both
    TenantRepository.get_by_id_for_update and
    ApplicationRepository.get_by_id_for_update) is what makes that return
    value trustworthy against a real DB; it has no unit-testable surface of
    its own beyond "the query executes," so it's covered by this contract
    test plus the live-DB derivation this reviewer already ran.
    """

    @pytest.mark.asyncio
    async def test_uses_the_locked_read_not_the_earlier_unlocked_one(self) -> None:
        svc = _make_service()
        # Unlocked read (the 404 check) sees the pre-revision figure.
        svc._tenants.get_by_id = AsyncMock(
            return_value=_tenant(101, allocated_budget=Decimal("0.00"))
        )
        # A concurrent PATCH .../budget committed between the two reads —
        # the locked read must see its result.
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(101, allocated_budget=Decimal("777.00"))
        )
        body = ApplicationCreate(name="Marketing Bot", allocated_percentage=Decimal("30.0"))

        app = await svc.create_application(101, body, _user())

        # 777.00 * 30% = 233.10, not 0.00 (which the stale pre-revision
        # figure of 0.00 would have produced — same failure shape as the
        # reviewer's repro: derived amount silently drifts from the actual
        # tenant budget).
        assert app.allocated_budget == Decimal("233.10")

    @pytest.mark.asyncio
    async def test_no_percentage_never_reads_stale_or_locked_tenant_budget(self) -> None:
        """No allocation means no cap check, no lock, no derivation — the
        unlocked tenant.allocated_budget is never even read for this path."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(
            return_value=_tenant(101, allocated_budget=Decimal("999999.00"))
        )
        body = ApplicationCreate(name="Marketing Bot")

        app = await svc.create_application(101, body, _user())

        assert app.allocated_budget is None
        svc._tenants.get_by_id_for_update.assert_not_awaited()
