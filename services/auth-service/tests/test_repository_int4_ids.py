"""Repository lookups by an id outside the int4 range of tenants.id,
applications.id and api_keys.id.

asyncpg refuses to encode such a bind value (DataError: value out of int32
range), so before the guard e.g. PUT /auth/tenants/999999999999/budget-allocation
or PATCH /auth/api-keys/99999999999 surfaced as a 500 INTERNAL_ERROR instead
of 404 NOT_FOUND. The lookups must return None without ever reaching the DB.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.ids import INT4_MAX, is_int4_id
from app.repositories.tenant_repository import TenantRepository

# (repository, method, number of id arguments)
_LOOKUPS = [
    (TenantRepository, "get_by_id", 1),
    (TenantRepository, "get_operational_fields", 1),
    (TenantRepository, "get_by_id_for_update", 1),
    (ApplicationRepository, "get_by_id", 1),
    (ApplicationRepository, "get_by_id_for_update", 1),
    (ApplicationRepository, "get_by_id_for_tenant", 2),
    (APIKeyRepository, "get_by_id", 1),
    (APIKeyRepository, "get_by_id_for_tenant", 2),
]
_LOOKUP_IDS = [f"{repo.__name__}.{method}" for repo, method, _ in _LOOKUPS]
_OUT_OF_RANGE = [99999999999, 2**31, 0, -1]


def _repo(repo_cls):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return repo_cls(db), db


@pytest.mark.parametrize(
    "value, expected",
    [(1, True), (INT4_MAX, True), (INT4_MAX + 1, False), (0, False), (-1, False), (None, False)],
)
def test_is_int4_id(value, expected):
    assert is_int4_id(value) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("repo_cls, method, arity", _LOOKUPS, ids=_LOOKUP_IDS)
@pytest.mark.parametrize("bad_id", _OUT_OF_RANGE)
async def test_out_of_range_id_returns_none_without_query(repo_cls, method, arity, bad_id):
    repo, db = _repo(repo_cls)

    assert await getattr(repo, method)(*[bad_id] * arity) is None
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repo_cls, method",
    [(ApplicationRepository, "get_by_id_for_tenant"), (APIKeyRepository, "get_by_id_for_tenant")],
    ids=["ApplicationRepository", "APIKeyRepository"],
)
@pytest.mark.parametrize("args", [(1, 2**31), (2**31, 1)], ids=["bad-tenant", "bad-id"])
async def test_tenant_scoped_lookup_checks_both_ids(repo_cls, method, args):
    repo, db = _repo(repo_cls)

    assert await getattr(repo, method)(*args) is None
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("repo_cls, method, arity", _LOOKUPS, ids=_LOOKUP_IDS)
async def test_in_range_id_still_queries(repo_cls, method, arity):
    repo, db = _repo(repo_cls)

    assert await getattr(repo, method)(*[INT4_MAX] * arity) is None
    db.execute.assert_awaited_once()
