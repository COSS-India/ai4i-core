"""TenantRepository lookups with an id outside tenants.id's int4 range.

asyncpg refuses to encode such a bind value (DataError: value out of int32
range), so before the guard PUT /auth/tenants/999999999999/budget-allocation
surfaced as a 500 INTERNAL_ERROR instead of 404 NOT_FOUND. The lookups must
return None without ever reaching the DB.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.tenant_repository import TenantRepository

_LOOKUPS = ("get_by_id", "get_operational_fields", "get_by_id_for_update")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", _LOOKUPS)
@pytest.mark.parametrize("tenant_id", [999999999999, 2**31, 0, -1])
async def test_out_of_range_tenant_id_returns_none_without_query(method, tenant_id):
    db = MagicMock()
    db.execute = AsyncMock()
    repo = TenantRepository(db)

    assert await getattr(repo, method)(tenant_id) is None
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", _LOOKUPS)
async def test_in_range_tenant_id_still_queries(method):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    repo = TenantRepository(db)

    assert await getattr(repo, method)(2**31 - 1) is None
    db.execute.assert_awaited_once()
