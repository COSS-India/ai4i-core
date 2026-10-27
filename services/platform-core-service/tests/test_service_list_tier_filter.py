"""GET /services ?tier_id= filter (AI4IDS-3488).

The Application fallback picker lists only the services mapped to the
Institution's Tier — services with no Tier are left out (Jira: "the active
services mapped to that Tier"). Unlike the admin-only tier_ids filter, a
non-admin caller (Institution Admin) may use it.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from app.repositories.model_management.service_repository import (
    ServiceListFilters,
    ServiceRepository,
)


def _db_capturing_stmt():
    db = MagicMock()
    captured = {}

    async def fake_execute(stmt):
        captured["stmt"] = stmt
        result = MagicMock()
        result.scalar.return_value = 0
        result.all.return_value = []
        return result

    db.execute = AsyncMock(side_effect=fake_execute)
    return db, captured


def _where(stmt) -> str:
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    return sql.split("WHERE", 1)[1]


def test_list_services_keeps_only_services_mapped_to_the_tier():
    db, captured = _db_capturing_stmt()
    asyncio.run(ServiceRepository(db).list_services(filters=ServiceListFilters(mapped_to_tier="tier-gold")))

    where = _where(captured["stmt"])
    assert "'tier-gold' = ANY (mm_services.tier_ids)" in where
    # Untiered services are not offered.
    assert "tier_ids IS NULL" not in where
    assert "cardinality" not in where


def test_count_services_applies_the_same_tier_filter():
    db, captured = _db_capturing_stmt()
    asyncio.run(ServiceRepository(db).count_services(filters=ServiceListFilters(mapped_to_tier="tier-gold")))

    assert "'tier-gold' = ANY (mm_services.tier_ids)" in _where(captured["stmt"])


def test_no_tier_means_no_tier_condition():
    db, captured = _db_capturing_stmt()
    asyncio.run(ServiceRepository(db).list_services())

    assert "tier_ids" not in _where(captured["stmt"])


def test_route_accepts_tier_id_from_non_admin_callers():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("app.routes.service", "app/routes/service.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.routes.service"] = module
    spec.loader.exec_module(module)

    params = module.ServiceListFilterParams(is_published=True, tier_id=" tier-gold ")
    assert params.tier_id == " tier-gold "
    # tier_id is not admin-only: a non-admin caller (Institution Admin) may use it.
    module._reject_admin_only_filters(params, is_admin=False)
