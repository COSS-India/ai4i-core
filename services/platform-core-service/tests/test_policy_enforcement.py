"""app/services/policy_management/policy_service.py — effective policy status.

A policy is in force only when it, its sub-category and its category are all
active. These tests pin the generated SQL: the joins up the hierarchy and the
three is_active conditions. Toggling a parent must not rewrite policy rows,
which test_policy_category_status.py covers on the write side.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.policy_management import policy_service


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _session(*, rows=(), first=None) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    result.first.return_value = first
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


class TestEnforcedPoliciesQuery:
    def test_joins_up_to_the_category(self):
        sql = _sql(policy_service.enforced_policies_query())
        assert "JOIN sub_category ON sub_category.id = policy.sub_category_id" in sql
        assert "JOIN category ON category.id = sub_category.category_id" in sql

    def test_requires_policy_sub_category_and_category_active(self):
        sql = _sql(policy_service.enforced_policies_query())
        for flag in ("policy.is_active", "sub_category.is_active", "category.is_active"):
            assert flag in sql
        assert sql.count(" AND ") >= 2

    def test_does_not_filter_by_sub_category_by_default(self):
        assert "policy.sub_category_id =" not in _sql(policy_service.enforced_policies_query())

    def test_filters_by_sub_category(self):
        sql = _sql(policy_service.enforced_policies_query(sub_category_id=3))
        assert "policy.sub_category_id = 3" in sql


@pytest.mark.asyncio
class TestEnforcedPoliciesService:
    async def test_lists_rows_from_the_enforced_query(self):
        row = MagicMock()
        session = _session(rows=[row])
        assert await policy_service.list_enforced_policies(session, sub_category_id=3) == [row]
        sql = _sql(session.execute.await_args.args[0])
        assert "category.is_active" in sql and "policy.sub_category_id = 3" in sql

    @pytest.mark.parametrize("first,expected", [((5,), True), (None, False)])
    async def test_is_policy_enforced(self, first, expected):
        session = _session(first=first)
        assert await policy_service.is_policy_enforced(session, 5) is expected
        sql = _sql(session.execute.await_args.args[0])
        assert "policy.id = 5" in sql and "category.is_active" in sql
