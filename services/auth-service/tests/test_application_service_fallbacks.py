"""Application service_fallbacks (AI4IDS-3488): request shape, catalogue
validation against mm_services, and the Redis key auth:app:{id}:service_fallbacks.
Mock-repo pattern, mirroring tests/test_application_crud.py."""

import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.application import Application, ApplicationStatus
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationUpdate, clean_service_fallbacks
from app.services.application_service import ApplicationService
from app.services.service_fallback_validator import validate_service_fallbacks

TIER = "6f1c0000-0000-0000-0000-000000000001"


def _run(coro):
    return asyncio.run(coro)


# ── Request shape ─────────────────────────────────────────────────────────────

def test_clean_strips_ids_keeps_order_and_drops_empty_lists():
    assert clean_service_fallbacks({" nmt-a ": [" nmt-c", "nmt-b"], "asr-a": []}) == {"nmt-a": ["nmt-c", "nmt-b"]}


@pytest.mark.parametrize("bad", [{"": ["x"]}, {"a": [""]}, {"a": ["a"]}, {"a": ["b", "b"]}])
def test_clean_rejects_bad_shapes(bad):
    with pytest.raises(ValueError):
        clean_service_fallbacks(bad)


def test_create_and_update_schemas():
    assert ApplicationCreate(name="App").service_fallbacks is None
    assert ApplicationCreate(name="App", service_fallbacks={"a": ["b"]}).service_fallbacks == {"a": ["b"]}
    assert ApplicationUpdate(service_fallbacks={}).service_fallbacks == {}
    assert "service_fallbacks" not in ApplicationUpdate(name="x").model_dump(exclude_unset=True)
    with pytest.raises(ValidationError):
        ApplicationUpdate(service_fallbacks=None)


# ── Catalogue validation ──────────────────────────────────────────────────────

def _row(service_id, task_type="nmt", published=True, deleted=False, tier_ids=(TIER,)):
    return {
        "service_id": service_id,
        "task_type": task_type,
        "is_published": published,
        "deleted_at": datetime(2026, 1, 1) if deleted else None,
        "tier_ids": list(tier_ids),
    }


def _session(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _code(exc_info) -> str:
    return exc_info.value.detail["code"]


def test_valid_map_passes_and_empty_map_needs_no_catalogue():
    _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, TIER, _session([_row("nmt-a"), _row("nmt-b")])))
    _run(validate_service_fallbacks({}, None, None))


@pytest.mark.parametrize(
    "rows, code",
    [
        ([_row("nmt-a")], "SERVICE_NOT_FOUND"),
        ([_row("nmt-a"), _row("nmt-b", published=False)], "SERVICE_NOT_PUBLISHED"),
        ([_row("nmt-a"), _row("nmt-b", deleted=True)], "SERVICE_NOT_PUBLISHED"),
        ([_row("nmt-a"), _row("nmt-b", tier_ids=())], "SERVICE_NOT_IN_TIER"),
        ([_row("nmt-a"), _row("nmt-b", task_type="asr")], "TASK_TYPE_MISMATCH"),
    ],
)
def test_invalid_maps_are_422(rows, code):
    with pytest.raises(HTTPException) as exc:
        _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, TIER, _session(rows)))
    assert exc.value.status_code == 422 and _code(exc) == code


def test_tenant_without_tier_and_catalogue_unavailable():
    with pytest.raises(HTTPException) as exc:
        _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, None, _session([])))
    assert _code(exc) == "NO_ACTIVE_TIER"
    with pytest.raises(HTTPException) as exc:
        _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, TIER, None))
    assert exc.value.status_code == 503


# ── Service: save + Redis ─────────────────────────────────────────────────────

def _tenant() -> Tenant:
    return Tenant(
        id=101, name="Contact", organisation="Acme", email="c@acme.com",
        status=TenantStatus.ACTIVE, allocated_budget=Decimal("1000.00"), tier_id=TIER,
    )


def _service(app=None):
    application_repo = MagicMock()
    application_repo.get_by_id = AsyncMock(return_value=app)
    application_repo.get_by_name = AsyncMock(return_value=None)
    application_repo.create = AsyncMock()
    application_repo.commit = AsyncMock()
    application_repo.refresh = AsyncMock()

    async def _update(obj, data):
        for key, value in data.items():
            setattr(obj, key, value)

    application_repo.update = AsyncMock(side_effect=_update)
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock(return_value=_tenant())
    role_repo = MagicMock()
    role_repo.get_user_roles = AsyncMock(return_value=["ADMIN"])
    api_key_repo = MagicMock()
    api_key_repo.zero_allocation_for_applications = AsyncMock(return_value=[])
    cache = MagicMock()
    cache.set_app_service_fallbacks = AsyncMock()
    cache.set_app_policy_ids = AsyncMock()
    svc = ApplicationService(
        application_repo=application_repo, tenant_repo=tenant_repo, role_repo=role_repo,
        db=MagicMock(), api_key_repo=api_key_repo, cache_service=cache,
    )
    return svc, application_repo, cache


def _user() -> User:
    return User(id=uuid4(), email="a@b.com", username="u")


def _app(fallbacks=None) -> Application:
    return Application(id=7, tenant_id=101, name="App", status=ApplicationStatus.ACTIVE, service_fallbacks=fallbacks or {})


def test_create_validates_saves_and_writes_redis():
    svc, repo, cache = _service()
    repo.refresh = AsyncMock(side_effect=lambda app: setattr(app, "id", 7))
    body = ApplicationCreate(name="App", service_fallbacks={"nmt-a": ["nmt-b"]})

    app = _run(svc.create_application(101, body, _user(), _session([_row("nmt-a"), _row("nmt-b")])))

    assert app.service_fallbacks == {"nmt-a": ["nmt-b"]}
    cache.set_app_service_fallbacks.assert_awaited_once_with(7, {"nmt-a": ["nmt-b"]})


def test_create_with_invalid_fallback_saves_nothing():
    svc, repo, cache = _service()
    body = ApplicationCreate(name="App", service_fallbacks={"nmt-a": ["nmt-b"]})
    with pytest.raises(HTTPException) as exc:
        _run(svc.create_application(101, body, _user(), _session([_row("nmt-a")])))
    assert _code(exc) == "SERVICE_NOT_FOUND"
    repo.create.assert_not_called()
    cache.set_app_service_fallbacks.assert_not_called()


def test_update_replaces_map_and_writes_redis():
    svc, _, cache = _service(_app({"nmt-a": ["nmt-b"]}))
    app = _run(svc.update_application(101, 7, ApplicationUpdate(service_fallbacks={}), _user(), _session([])))
    assert app.service_fallbacks == {}
    cache.set_app_service_fallbacks.assert_awaited_once_with(7, {})


def test_unrelated_update_leaves_redis_alone():
    svc, _, cache = _service(_app({"nmt-a": ["nmt-b"]}))
    app = _run(svc.update_application(101, 7, ApplicationUpdate(name="Renamed"), _user(), None))
    assert app.service_fallbacks == {"nmt-a": ["nmt-b"]}
    cache.set_app_service_fallbacks.assert_not_called()
