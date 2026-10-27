"""Unit tests for Application service_fallbacks (AI4IDS-3488): request-shape
checks, catalogue validation against mm_services, and keeping the Redis key
auth:app:{id}:service_fallbacks in sync — mock-repo pattern, mirroring
tests/test_application_crud.py.
"""

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
from app.schemas.application import ApplicationCreate, ApplicationUpdate, normalize_service_fallbacks
from app.services.application_service import ApplicationService
from app.services.service_fallback_validator import validate_service_fallbacks

TIER = "6f1c0000-0000-0000-0000-000000000001"


def _run(coro):
    return asyncio.run(coro)


# ── Request shape ─────────────────────────────────────────────────────────────

def test_normalize_strips_ids_and_drops_empty_lists():
    assert normalize_service_fallbacks({" nmt-a ": [" nmt-b "], "nmt-c": []}) == {"nmt-a": ["nmt-b"]}


def test_normalize_keeps_order():
    assert normalize_service_fallbacks({"a": ["c", "b"]}) == {"a": ["c", "b"]}


@pytest.mark.parametrize(
    "value, message",
    [
        ({"a": ["a"]}, "own fallback"),
        ({"a": ["b", "b"]}, "repeat"),
        ({"a": [""]}, "blank"),
        ({" ": ["b"]}, "blank"),
    ],
)
def test_normalize_rejects_bad_shapes(value, message):
    with pytest.raises(ValueError, match=message):
        normalize_service_fallbacks(value)


def test_create_schema_accepts_and_normalizes():
    body = ApplicationCreate(name="App", service_fallbacks={"a": ["b"], "c": []})
    assert body.service_fallbacks == {"a": ["b"]}


def test_update_schema_rejects_explicit_null():
    with pytest.raises(ValidationError):
        ApplicationUpdate(service_fallbacks=None)


def test_update_schema_accepts_empty_map_to_clear():
    assert ApplicationUpdate(service_fallbacks={}).service_fallbacks == {}


# ── Catalogue validation ──────────────────────────────────────────────────────

def _row(service_id, task_type="nmt", published=True, deleted=False, tier_ids=(TIER,)):
    return {
        "service_id": service_id,
        "task_type": task_type,
        "is_published": published,
        "deleted_at": datetime(2026, 1, 1) if deleted else None,
        "tier_ids": list(tier_ids) if tier_ids is not None else None,
    }


def _session(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _code(exc_info) -> str:
    return exc_info.value.detail["code"]


def test_valid_map_passes():
    session = _session([_row("nmt-a"), _row("nmt-b")])
    _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, TIER, session))


@pytest.mark.parametrize("tier_ids", [(), None])
def test_service_with_no_tier_is_rejected(tier_ids):
    session = _session([_row("nmt-a"), _row("nmt-b", tier_ids=tier_ids)])
    with pytest.raises(HTTPException) as exc_info:
        _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, TIER, session))
    assert _code(exc_info) == "SERVICE_NOT_IN_TIER"


def test_empty_map_needs_no_catalogue():
    _run(validate_service_fallbacks({}, None, None))


@pytest.mark.parametrize(
    "rows, code",
    [
        ([_row("nmt-a")], "SERVICE_NOT_FOUND"),
        ([_row("nmt-a"), _row("nmt-b", published=False)], "SERVICE_NOT_PUBLISHED"),
        ([_row("nmt-a"), _row("nmt-b", deleted=True)], "SERVICE_NOT_PUBLISHED"),
        ([_row("nmt-a"), _row("nmt-b", tier_ids=("other-tier",))], "SERVICE_NOT_IN_TIER"),
        ([_row("nmt-a"), _row("nmt-b", task_type="asr")], "TASK_TYPE_MISMATCH"),
    ],
)
def test_invalid_maps_are_rejected(rows, code):
    with pytest.raises(HTTPException) as exc_info:
        _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, TIER, _session(rows)))
    assert exc_info.value.status_code == 422
    assert _code(exc_info) == code


def test_tenant_without_tier_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, None, _session([])))
    assert _code(exc_info) == "NO_ACTIVE_TIER"


def test_catalogue_unavailable_is_503():
    with pytest.raises(HTTPException) as exc_info:
        _run(validate_service_fallbacks({"nmt-a": ["nmt-b"]}, TIER, None))
    assert exc_info.value.status_code == 503


# ── ApplicationService keeps Redis in sync ────────────────────────────────────

def _tenant() -> Tenant:
    return Tenant(
        id=101, name="Contact", organisation="Acme", email="c@acme.com",
        status=TenantStatus.ACTIVE, allocated_budget=Decimal("1000.00"), tier_id=TIER,
    )


def _application(status=ApplicationStatus.ACTIVE, fallbacks=None) -> Application:
    return Application(id=7, tenant_id=101, name="App", status=status, service_fallbacks=fallbacks or {})


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
    cache.delete_app_service_fallbacks = AsyncMock()
    cache.set_app_policy_ids = AsyncMock()
    svc = ApplicationService(
        application_repo=application_repo, tenant_repo=tenant_repo, role_repo=role_repo,
        db=MagicMock(), api_key_repo=api_key_repo, cache_service=cache,
    )
    return svc, cache


def _user() -> User:
    return User(id=uuid4(), email="a@b.com", username="u")


def test_create_validates_and_writes_redis():
    svc, cache = _service()
    body = ApplicationCreate(name="App", service_fallbacks={"nmt-a": ["nmt-b"]})
    session = _session([_row("nmt-a"), _row("nmt-b")])

    app = _run(svc.create_application(101, body, _user(), session))

    assert app.service_fallbacks == {"nmt-a": ["nmt-b"]}
    cache.set_app_service_fallbacks.assert_awaited_once_with(app.id, {"nmt-a": ["nmt-b"]})


def test_create_with_invalid_fallback_saves_nothing():
    svc, cache = _service()
    body = ApplicationCreate(name="App", service_fallbacks={"nmt-a": ["asr-x"]})
    session = _session([_row("nmt-a"), _row("asr-x", task_type="asr")])

    with pytest.raises(HTTPException):
        _run(svc.create_application(101, body, _user(), session))
    svc._applications.create.assert_not_called()
    cache.set_app_service_fallbacks.assert_not_called()


def test_update_fallbacks_writes_redis():
    app = _application()
    svc, cache = _service(app)
    session = _session([_row("nmt-a"), _row("nmt-c")])

    _run(svc.update_application(101, 7, ApplicationUpdate(service_fallbacks={"nmt-a": ["nmt-c"]}), _user(), session))

    assert app.service_fallbacks == {"nmt-a": ["nmt-c"]}
    cache.set_app_service_fallbacks.assert_awaited_once_with(7, {"nmt-a": ["nmt-c"]})


def test_unrelated_update_leaves_redis_alone():
    svc, cache = _service(_application(fallbacks={"nmt-a": ["nmt-b"]}))

    _run(svc.update_application(101, 7, ApplicationUpdate(name="Renamed"), _user(), None))

    cache.set_app_service_fallbacks.assert_not_called()
    cache.delete_app_service_fallbacks.assert_not_called()


def test_deactivate_deletes_redis_key():
    svc, cache = _service(_application(fallbacks={"nmt-a": ["nmt-b"]}))

    _run(svc.update_application(101, 7, ApplicationUpdate(status=ApplicationStatus.INACTIVE), _user(), None))

    cache.delete_app_service_fallbacks.assert_awaited_once_with(7)


def test_reactivate_writes_map_back():
    svc, cache = _service(_application(status=ApplicationStatus.INACTIVE, fallbacks={"nmt-a": ["nmt-b"]}))

    _run(svc.update_application(101, 7, ApplicationUpdate(status=ApplicationStatus.ACTIVE), _user(), None))

    cache.set_app_service_fallbacks.assert_awaited_once_with(7, {"nmt-a": ["nmt-b"]})


def test_internal_lookup_reloads_and_caches():
    svc, cache = _service(_application(fallbacks={"nmt-a": ["nmt-b"]}))

    assert _run(svc.get_service_fallbacks_internal(7)) == {"nmt-a": ["nmt-b"]}
    cache.set_app_service_fallbacks.assert_awaited_once_with(7, {"nmt-a": ["nmt-b"]})


@pytest.mark.parametrize("app", [None, _application(status=ApplicationStatus.INACTIVE, fallbacks={"nmt-a": ["nmt-b"]})])
def test_internal_lookup_unknown_or_inactive_is_empty_and_cached(app):
    svc, cache = _service(app)

    assert _run(svc.get_service_fallbacks_internal(7)) == {}
    cache.set_app_service_fallbacks.assert_awaited_once_with(7, {})
